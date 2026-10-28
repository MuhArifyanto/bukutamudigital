import json
from unittest.mock import patch
from django.urls import reverse
from django.test import Client

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
