import json
import time
from unittest.mock import patch
from django.urls import reverse
from django.test import Client, RequestFactory

from .base import BaseSecurityTestCase
from ..models import Tamu


class FirebaseLoginSecurityTestCase(BaseSecurityTestCase):
    """
    Test suite keamanan untuk endpoint api_firebase_login:
    - Mitigasi Session Fixation via session.cycle_key().
    - Pembersihan kunci peran lama (pegawai_id, penanda admin) agar tidak terjadi campur peran.
    - Penolakan token palsu / tidak valid / kedaluwarsa (401).
    - Penolakan akun dengan status nonaktif / diblokir (403).
    - Penolakan token dengan email belum terverifikasi (email_verified=False) (403).
    - Pembatasan laju (Rate Limiting) pada percobaan gagal (429).
    """

    def setUp(self):
        super().setUp()
        self.url = reverse('tamu:api_firebase_login')

    @patch('google.oauth2.id_token.verify_firebase_token')
    def test_session_key_rotated_after_firebase_login(self, mock_verify):
        """Memverifikasi session key dirotasi (cycle_key) setelah login berhasil."""
        mock_verify.return_value = {
            'sub': 'google_uid_12345',
            'email': self.tamu_a.email,
            'email_verified': True,
            'name': self.tamu_a.name
        }

        client = Client()
        # Inisialisasi sesi sebelum login
        session = client.session
        session['init_probe'] = 'pre_session'
        session.save()
        old_session_key = client.session.session_key

        resp = client.post(
            self.url,
            data=json.dumps({'id_token': 'valid_firebase_token_mock'}),
            content_type='application/json'
        )

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get('success'))

        new_session_key = client.session.session_key
        # Session key harus berubah (mencegah session fixation)
        self.assertNotEqual(old_session_key, new_session_key)
        self.assertEqual(client.session.get('tamu_id'), str(self.tamu_a.pk))

    @patch('google.oauth2.id_token.verify_firebase_token')
    def test_legacy_role_keys_purged_on_login(self, mock_verify):
        """Memverifikasi seluruh penanda peran lain (pegawai, admin) dibersihkan dari sesi."""
        mock_verify.return_value = {
            'sub': 'google_uid_12345',
            'email': self.tamu_a.email,
            'email_verified': True,
            'name': self.tamu_a.name
        }

        client = Client()
        session = client.session
        # Simulasikan sisa session dari peran sebelumnya
        session['pegawai_id'] = 'fake_pegawai_uuid'
        session['pegawai_name'] = 'Pegawai Lama'
        session['pegawai_role'] = 'staff'
        session['is_admin'] = True
        session['role'] = 'admin'
        session.save()

        resp = client.post(
            self.url,
            data=json.dumps({'id_token': 'valid_firebase_token_mock'}),
            content_type='application/json'
        )

        self.assertEqual(resp.status_code, 200)
        curr_session = client.session
        self.assertEqual(curr_session.get('tamu_id'), str(self.tamu_a.pk))
        # Seluruh kunci peran sebelumnya harus bersih
        self.assertIsNone(curr_session.get('pegawai_id'))
        self.assertIsNone(curr_session.get('pegawai_name'))
        self.assertIsNone(curr_session.get('pegawai_role'))
        self.assertIsNone(curr_session.get('is_admin'))
        self.assertIsNone(curr_session.get('role'))

    @patch('google.oauth2.id_token.verify_firebase_token')
    def test_invalid_token_rejected_with_401(self, mock_verify):
        """Token tidak valid atau kedaluwarsa ditolak dengan status 401."""
        mock_verify.side_effect = ValueError("Token has expired")

        client = Client()
        resp = client.post(
            self.url,
            data=json.dumps({'id_token': 'expired_token_mock'}),
            content_type='application/json'
        )

        self.assertEqual(resp.status_code, 401)
        self.assertFalse(resp.json().get('success'))
        self.assertIsNone(client.session.get('tamu_id'))

    @patch('google.oauth2.id_token.verify_firebase_token')
    def test_unverified_email_rejected_with_403(self, mock_verify):
        """Token Firebase dengan email_verified=False ditolak 403 Forbidden."""
        mock_verify.return_value = {
            'sub': 'google_uid_fake',
            'email': 'unverified.user@example.com',
            'email_verified': False,
            'name': 'Unverified User'
        }

        client = Client()
        resp = client.post(
            self.url,
            data=json.dumps({'id_token': 'unverified_token_mock'}),
            content_type='application/json'
        )

        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json().get('success'))
        self.assertIn('belum diverifikasi', resp.json().get('message', ''))
        self.assertIsNone(client.session.get('tamu_id'))

    @patch('google.oauth2.id_token.verify_firebase_token')
    def test_inactive_account_rejected_with_403(self, mock_verify):
        """Akun tamu yang berstatus nonaktif/diblokir ditolak masuk (403 Forbidden)."""
        self.tamu_a.account_status = 'inactive'
        self.tamu_a.save(update_fields=['account_status'])

        mock_verify.return_value = {
            'sub': 'google_uid_12345',
            'email': self.tamu_a.email,
            'email_verified': True,
            'name': self.tamu_a.name
        }

        client = Client()
        resp = client.post(
            self.url,
            data=json.dumps({'id_token': 'valid_token_mock'}),
            content_type='application/json'
        )

        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json().get('success'))
        self.assertIn('dinonaktifkan atau diblokir', resp.json().get('message', ''))
        self.assertIsNone(client.session.get('tamu_id'))

    @patch('google.oauth2.id_token.verify_firebase_token')
    def test_rate_limiting_enforced_on_failed_attempts(self, mock_verify):
        """Lebih dari 5 percobaan gagal ditolak dengan status 429 Too Many Requests."""
        mock_verify.side_effect = ValueError("Invalid signature")

        client = Client()
        # 5 percobaan gagal pertama menghasilkan 401
        for _ in range(5):
            resp = client.post(
                self.url,
                data=json.dumps({'id_token': 'bad_token'}),
                content_type='application/json',
                REMOTE_ADDR='198.51.100.55'
            )
            self.assertEqual(resp.status_code, 401)

        # Percobaan ke-6 harus ditolak 429 Too Many Requests
        resp_blocked = client.post(
            self.url,
            data=json.dumps({'id_token': 'bad_token'}),
            content_type='application/json',
            REMOTE_ADDR='198.51.100.55'
        )
        self.assertEqual(resp_blocked.status_code, 429)
        self.assertIn('Terlalu banyak percobaan', resp_blocked.json().get('message', ''))

    @patch('google.oauth2.id_token.verify_firebase_token')
    def test_firebase_login_enforces_csrf_token(self, mock_verify):
        """Endpoint api_firebase_login wajib memvalidasi CSRF token (anti Login CSRF)."""
        mock_verify.return_value = {
            'sub': 'google_uid_csrf',
            'email': self.tamu_a.email,
            'email_verified': True,
            'name': self.tamu_a.name,
        }
        csrf_client = Client(enforce_csrf_checks=True)
        # POST tanpa X-CSRFToken ditolak 403
        blocked = csrf_client.post(
            self.url,
            data=json.dumps({'id_token': 'valid_token'}),
            content_type='application/json',
        )
        self.assertEqual(blocked.status_code, 403)
        self.assertIsNone(csrf_client.session.get('tamu_id'))

        # Ambil CSRF cookie lalu kirim X-CSRFToken -> berhasil 200
        csrf_client.get(reverse('tamu:login'))
        token = csrf_client.cookies.get('csrftoken').value
        ok = csrf_client.post(
            self.url,
            data=json.dumps({'id_token': 'valid_token'}),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(csrf_client.session.get('tamu_id'), str(self.tamu_a.pk))

    @patch('google.oauth2.id_token.verify_firebase_token')
    def test_unverified_firebase_email_signup_cannot_bypass_on_second_sso_login(self, mock_verify):
        """
        Registrasi awal firebase_email dengan email_verified=False tidak boleh mengikat
        google_id dan tidak boleh lolos pada percobaan kedua google_sso dengan email_verified=False.
        """
        email = 'new.unverified@example.com'
        uid = 'uid_unverified_bypass'
        mock_verify.return_value = {
            'sub': uid,
            'email': email,
            'email_verified': False,
            'name': 'Calon Tamu',
        }
        client = Client()
        # Siapkan sesi captcha valid (index 18 -> correct [4, 5])
        sess = client.session
        sess['captcha_expected_index'] = 18
        sess['captcha_issued_at'] = time.time()
        sess.save()

        # Request 1: firebase_email registration tanpa email_verified
        r1 = client.post(
            self.url,
            data=json.dumps({
                'id_token': 'tok1',
                'name': 'Calon Tamu',
                'phone': '081234567890',
                'instansi': 'Uji',
                'registration_type': 'firebase_email',
                'captcha_selected_tiles': '[4, 5]',
                'captcha_trajectory': '[{"x":1,"y":1,"t":10},{"x":2,"y":2,"t":27},{"x":3,"y":3,"t":68}]',
            }),
            content_type='application/json',
        )
        self.assertEqual(r1.status_code, 200)
        self.assertIsNone(client.session.get('tamu_id'))
        created_tamu = Tamu.objects.get(email=email)
        self.assertIsNone(created_tamu.google_id)

        # Request 2: login ulang memakai token tidak terverifikasi (google_sso) harus ditolak 403
        r2 = client.post(
            self.url,
            data=json.dumps({
                'id_token': 'tok2',
                'registration_type': 'google_sso',
            }),
            content_type='application/json',
        )
        self.assertEqual(r2.status_code, 403)
        self.assertIsNone(client.session.get('tamu_id'))

    @patch('google.oauth2.id_token.verify_firebase_token')
    def test_firebase_login_rejects_xss_phone_and_suspended_http_sessions(self, mock_verify):
        """Menolak nomor telepon berisi markup XSS serta memblokir sesi suspended di upload & workflow."""
        mock_verify.return_value = {
            'sub': 'uid_xss_phone',
            'email': 'xss.phone@example.com',
            'email_verified': True,
            'name': 'Tamu Phone',
        }
        client = Client()
        bad_phone = client.post(
            self.url,
            data=json.dumps({
                'id_token': 'tok',
                'phone': '<img src=x>',
                'registration_type': 'google_sso',
            }),
            content_type='application/json',
        )
        self.assertEqual(bad_phone.status_code, 400)

        # Suspended Tamu & Pegawai ditolak pada api_upload_chat_file dan api_update_kunjungan_status
        from django.core.files.uploadedfile import SimpleUploadedFile

        self.tamu_a.account_status = 'suspended'
        self.tamu_a.save(update_fields=['account_status'])
        c_tamu = Client()
        s1 = c_tamu.session
        s1['tamu_id'] = str(self.tamu_a.pk)
        s1.save()
        up = c_tamu.post(
            reverse('tamu:api_upload_chat_file'),
            {'file': SimpleUploadedFile('test.png', b'\x89PNG\r\n\x1a\n', content_type='image/png')},
        )
        self.assertEqual(up.status_code, 401)

        # Suspended Tamu juga wajib ditolak di api_search_users (401) dan api_get_chat_messages (403)
        search_tamu = c_tamu.get(reverse('tamu:api_search_users'), {'q': 'Pegawai'})
        self.assertEqual(search_tamu.status_code, 401)
        hist_tamu = c_tamu.get(reverse('tamu:api_get_chat_messages'), {'session_id': f'tamu_{self.tamu_a.pk}'})
        self.assertEqual(hist_tamu.status_code, 403)

        self.pegawai.account_status = 'suspended'
        self.pegawai.save(update_fields=['account_status'])
        c_peg = Client()
        s2 = c_peg.session
        s2['pegawai_id'] = str(self.pegawai.pk)
        s2.save()
        upd = c_peg.post(
            reverse('tamu:api_update_kunjungan_status'),
            data=json.dumps({'kunjungan_id': '00000000-0000-0000-0000-000000000000', 'status': 'disetujui_pegawai'}),
            content_type='application/json',
        )
        self.assertEqual(upd.status_code, 403)

        # Suspended Pegawai juga wajib ditolak di api_search_users (401) dan api_get_chat_messages (403)
        search_peg = c_peg.get(reverse('tamu:api_search_users'), {'q': 'Tamu'})
        self.assertEqual(search_peg.status_code, 401)
        hist_peg = c_peg.get(
            reverse('tamu:api_get_chat_messages'),
            {'session_id': f'pegawai_admin_{self.pegawai.pk}'},
        )
        self.assertEqual(hist_peg.status_code, 403)

        # Halaman login Tamu & Pegawai tidak boleh redirect loop jika sesi masih menyimpan ID akun suspended
        login_tamu_resp = c_tamu.get(reverse('tamu:login'))
        self.assertEqual(login_tamu_resp.status_code, 200)
        self.assertIsNone(c_tamu.session.get('tamu_id'))

        login_peg_resp = c_peg.get(reverse('tamu:pegawai_login'))
        self.assertEqual(login_peg_resp.status_code, 200)
        self.assertIsNone(c_peg.session.get('pegawai_id'))

    def test_notifications_context_ignores_suspended_tamu_and_unverified_staff(self):
        """notifications_context dan pegawai_notifications_context wajib mengabaikan akun nonaktif/belum 2FA."""
        from django.contrib.auth.models import AnonymousUser, User
        from django.contrib.sessions.backends.db import SessionStore
        from ..context_processors import notifications_context, pegawai_notifications_context
        from ..models import Admin, Notification
        from ..security_utils import encrypt_secret, generate_totp_secret

        staff_user = User.objects.create_user(
            username='ctxstaff',
            email='ctxstaff@example.com',
            password='Str0ng!Password#2026',
            is_staff=True,
        )
        Admin.objects.create(
            name='Ctx Admin',
            email='ctxstaff@example.com',
            two_fa_enabled=True,
            two_fa_secret=encrypt_secret(generate_totp_secret()),
            account_status='active',
        )
        Notification.objects.create(
            recipient_type='admin',
            status='unread',
            title='Notif Admin Rahasia',
            message='Isi rahasia',
            notification_type='visit_registered',
        )
        Notification.objects.create(
            recipient_type='tamu',
            recipient_id=str(self.tamu_a.pk),
            status='unread',
            title='Notif Tamu',
            message='Isi tamu',
            notification_type='visit_registered',
        )
        admin_tamu = Tamu.objects.create(
            name='Tamu Admin Suspended',
            email='tamu.admin.ctx@example.com',
            phone='081234567891',
            is_admin=True,
            account_status='suspended',
        )

        rf = RequestFactory()
        # Staff belum 2FA tidak boleh menerima notifikasi admin
        req_staff = rf.get('/')
        req_staff.session = SessionStore()
        req_staff.user = staff_user
        self.assertEqual(notifications_context(req_staff), {})

        # Tamu(is_admin=True) suspended tidak boleh menerima notifikasi admin
        req_tamu = rf.get('/')
        req_tamu.session = SessionStore()
        req_tamu.session['tamu_id'] = str(admin_tamu.pk)
        req_tamu.user = AnonymousUser()
        self.assertEqual(notifications_context(req_tamu), {})

        # Pegawai suspended tidak boleh menerima badge notif pegawai
        self.pegawai.account_status = 'suspended'
        self.pegawai.save(update_fields=['account_status'])
        req_peg = rf.get('/')
        req_peg.session = SessionStore()
        req_peg._pegawai = self.pegawai
        self.assertEqual(pegawai_notifications_context(req_peg), {})
