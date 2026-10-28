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
