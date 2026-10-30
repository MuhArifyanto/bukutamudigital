from django.urls import reverse
from django.test import Client
from .base import BaseSecurityTestCase
from ..models import LoginAttempt
import json


class SessionAndAuthTestCase(BaseSecurityTestCase):
    """
    Uji sesi, rotasi session key, flush logout, dan rate limiting brute-force login.
    """

    def test_session_cycle_key_and_role_purge_on_tamu_login(self):
        """Saat tamu login berhasil, session key harus berganti dan session pegawai lama dibersihkan."""
        client = Client()
        # Masukkan session dummy pegawai
        s = client.session
        s['pegawai_id'] = str(self.pegawai.pk)
        s.save()
        old_session_key = client.session.session_key

        url = reverse('tamu:login')
        # Login dengan Tamu A
        resp = client.post(url, {
            'username': self.tamu_a.email,
            'password': 'password123'
        })
        self.assertEqual(resp.status_code, 302)

        # Sesi key harus berganti
        new_session_key = client.session.session_key
        self.assertNotEqual(old_session_key, new_session_key)

        # Session tamu_id harus terisi, pegawai_id lama harus dibersihkan
        self.assertEqual(client.session.get('tamu_id'), str(self.tamu_a.pk))
        self.assertIsNone(client.session.get('pegawai_id'))

    def test_logout_flushes_session_completely(self):
        """Logout tamu dan pegawai harus melakukan flush penuh pada sesi."""
        # 1. Tamu logout
        tamu_client = self.get_client('tamu_a')
        self.assertIsNotNone(tamu_client.session.get('tamu_id'))

        logout_url = reverse('tamu:logout')
        resp = tamu_client.get(logout_url)
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(tamu_client.session.get('tamu_id'))

        # 2. Pegawai logout
        pegawai_client = self.get_client('pegawai')
        self.assertIsNotNone(pegawai_client.session.get('pegawai_id'))

        pegawai_logout_url = reverse('tamu:pegawai_logout')
        resp = pegawai_client.get(pegawai_logout_url)
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(pegawai_client.session.get('pegawai_id'))
        self.assertIsNone(pegawai_client.session.get('pegawai_name'))

    def test_rate_limiting_tamu_login(self):
        """Setelah 5 kali gagal login, percobaan ke-6 harus dikunci/ditangguhkan."""
        client = Client()
        url = reverse('tamu:login')

        for i in range(5):
            resp = client.post(url, {
                'username': self.tamu_a.email,
                'password': 'wrongpassword'
            })
            self.assertEqual(resp.status_code, 200)

        # Percobaan ke-6 dengan password benar pun harus ditangguhkan
        resp = client.post(url, {
            'username': self.tamu_a.email,
            'password': 'password123'
        })
        self.assertEqual(resp.status_code, 200)
        messages_text = [m.message for m in list(resp.context['messages'])]
        self.assertTrue(any("ditangguhkan sementara" in m for m in messages_text))

    def test_rate_limiting_admin_login(self):
        """Admin login harus memiliki rate limiting setelah 5 kali gagal."""
        client = Client()
        url = reverse('tamu:admin_login')

        for i in range(5):
            resp = client.post(url, {
                'username': 'admin_user',
                'password': 'wrongpassword'
            })
            self.assertEqual(resp.status_code, 200)

        # Percobaan ke-6
        resp = client.post(url, {
            'username': 'admin_user',
            'password': 'adminpassword123'
        })
        self.assertEqual(resp.status_code, 200)
        messages_text = [m.message for m in list(resp.context['messages'])]
        self.assertTrue(any("Akses ditangguhkan" in m for m in messages_text))

    def test_generic_error_message_pegawai_login(self):
        """Pesan error login pegawai tidak boleh membocorkan status akun atau ketidakberadaan akun."""
        client = Client()
        url = reverse('tamu:pegawai_login')

        # Akun tidak terdaftar
        resp = client.post(url, {
            'login_id': 'nonexistent_user@example.com',
            'password': 'password123'
        })
        self.assertEqual(resp.status_code, 200)
        messages_1 = [m.message for m in list(resp.context['messages'])]
        self.assertIn('Email/Username atau password yang Anda masukkan salah.', messages_1)

        # Akun terdaftar tapi status inactive
        self.pegawai.account_status = 'inactive'
        self.pegawai.save()

        resp = client.post(url, {
            'login_id': self.pegawai.email,
            'password': 'password123'
        })
        self.assertEqual(resp.status_code, 200)
        messages_2 = [m.message for m in list(resp.context['messages'])]
        # Pesan error harus generik, sama persis dengan akun tidak terdaftar
        self.assertIn('Email/Username atau password yang Anda masukkan salah.', messages_2)

    def test_pegawai_profile_password_change_allows_login(self):
        """Pegawai yang mengganti password di halaman profil tetap dapat login dengan password baru."""
        from django.contrib.auth.hashers import check_password
        pegawai_client = self.get_client('pegawai')
        profile_url = reverse('tamu:pegawai_profile')

        resp = pegawai_client.post(profile_url, {
            'name': 'Pegawai Satu Updated',
            'phone': '081234567892',
            'new_password': 'NewPassword2026!'
        })
        self.assertEqual(resp.status_code, 302)

        self.pegawai.refresh_from_db()
        self.assertTrue(check_password('NewPassword2026!', self.pegawai.password))

        # Logout lalu login ulang menggunakan password baru
        pegawai_client.get(reverse('tamu:pegawai_logout'))
        login_resp = pegawai_client.post(reverse('tamu:pegawai_login'), {
            'login_id': self.pegawai.email,
            'password': 'NewPassword2026!'
        })
        self.assertEqual(login_resp.status_code, 302)
        self.assertEqual(pegawai_client.session.get('pegawai_id'), str(self.pegawai.pk))

    def test_pegawai_legacy_sha256_password_auto_migrated_on_login(self):
        """Pegawai yang terlanjur memiliki hash SHA-256 lama tetap bisa login dan otomatis dimigrasi ke PBKDF2."""
        import hashlib
        from django.contrib.auth.hashers import check_password
        self.pegawai.password = hashlib.sha256(b'LegacyPass123!').hexdigest()
        self.pegawai.save(update_fields=['password'])

        client = Client()
        resp = client.post(reverse('tamu:pegawai_login'), {
            'login_id': self.pegawai.email,
            'password': 'LegacyPass123!'
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(client.session.get('pegawai_id'), str(self.pegawai.pk))

        self.pegawai.refresh_from_db()
        self.assertIn('$', self.pegawai.password)
        self.assertTrue(check_password('LegacyPass123!', self.pegawai.password))

    def test_admin_statistik_add_pegawai_hashes_password(self):
        """Penambahan pegawai dari halaman statistik admin wajib meng-hash password dengan make_password."""
        from django.contrib.auth.hashers import check_password
        from ..models import Pegawai
        admin_client = self.get_client('admin')
        resp = admin_client.post(reverse('tamu:admin_statistik'), {
            'action': 'add_pegawai',
            'name': 'Pegawai Baru Statistik',
            'email': 'pegawai.baru@bekasikab.go.id',
            'phone': '081299998888',
            'department': str(self.departemen.pk),
        })
        self.assertEqual(resp.status_code, 302)

        new_pegawai = Pegawai.objects.filter(email='pegawai.baru@bekasikab.go.id').first()
        self.assertIsNotNone(new_pegawai)
        self.assertNotEqual(new_pegawai.password, 'password123')
        self.assertTrue(check_password('password123', new_pegawai.password))

        # Pastikan pegawai baru bisa login
        client = Client()
        login_resp = client.post(reverse('tamu:pegawai_login'), {
            'login_id': 'pegawai.baru@bekasikab.go.id',
            'password': 'password123',
        })
        self.assertEqual(login_resp.status_code, 302)
        self.assertEqual(client.session.get('pegawai_id'), str(new_pegawai.pk))

    def test_admin_login_uses_get_client_ip_behind_proxy(self):
        """admin_login_view wajib menggunakan get_client_ip(request) agar rate-limit tidak salah memblokir proxy."""
        from ..models import LoginAttempt
        client = Client()
        resp = client.post(
            reverse('tamu:admin_login'),
            {'username': self.admin_django.username, 'password': 'adminpassword123'},
            REMOTE_ADDR='127.0.0.1',
            HTTP_X_FORWARDED_FOR='203.0.113.77',
        )
        self.assertEqual(resp.status_code, 302)
        attempt = LoginAttempt.objects.filter(user_type='admin', success=True).order_by('-timestamp').first()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.ip_address, '203.0.113.77')

    def test_decorators_redirect_to_valid_tamu_namespace(self):
        """Decorator di guest_book.decorators wajib redirect ke 'tamu:pegawai_login' dan 'tamu:pegawai_dashboard'."""
        from django.test import RequestFactory
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.http import HttpResponse
        from ..decorators import pegawai_login_required, pegawai_role_required

        @pegawai_login_required
        def dummy_login_view(request):
            return HttpResponse('ok')

        @pegawai_role_required(['manager'])
        def dummy_manager_view(request):
            return HttpResponse('ok')

        rf = RequestFactory()
        # 1. Belum login -> redirect ke tamu:pegawai_login
        req_anon = rf.get('/pegawai/dummy/')
        req_anon.session = {}
        setattr(req_anon, '_messages', FallbackStorage(req_anon))
        resp_anon = dummy_login_view(req_anon)
        self.assertEqual(resp_anon.status_code, 302)
        self.assertEqual(resp_anon.url, reverse('tamu:pegawai_login'))

        # 2. Sudah login sebagai staff, akses view khusus manager -> redirect ke tamu:pegawai_dashboard
        req_staff = rf.get('/pegawai/manager-only/')
        req_staff.session = {'pegawai_id': str(self.pegawai.pk)}
        setattr(req_staff, '_messages', FallbackStorage(req_staff))
        resp_staff = dummy_manager_view(req_staff)
        self.assertEqual(resp_staff.status_code, 302)
        self.assertEqual(resp_staff.url, reverse('tamu:pegawai_dashboard'))
        self.assertEqual(req_staff._pegawai, self.pegawai)
