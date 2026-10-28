from django.urls import reverse
from .base import BaseSecurityTestCase
from ..models import Kunjungan, KunjunganStatus, ChatMessage
from django.utils import timezone
import json


class AuthorizationMatrixTestCase(BaseSecurityTestCase):
    """
    Uji matriks akses: setiap endpoint dicoba oleh 4 peran (anonim, Tamu, Pegawai, Admin).
    """

    def test_admin_portal_access(self):
        """Halaman admin hanya boleh diakses oleh Admin, peran lain di-redirect (302)."""
        endpoints = [
            'tamu:admin_dashboard',
            'tamu:admin_statistik',
            'tamu:admin_kunjungan_list',
            'tamu:admin_kalender',
            'tamu:admin_instansi',
            'tamu:admin_pengguna',
            'tamu:admin_audit_log',
        ]
        for ep in endpoints:
            url = reverse(ep)
            # Anonim -> 302
            resp = self.get_client('anon').get(url)
            self.assertEqual(resp.status_code, 302, f"Anonim harus di-redirect dari {ep}")

            # Tamu -> 302
            resp = self.get_client('tamu_a').get(url)
            self.assertEqual(resp.status_code, 302, f"Tamu harus di-redirect dari {ep}")

            # Pegawai -> 302
            resp = self.get_client('pegawai').get(url)
            self.assertEqual(resp.status_code, 302, f"Pegawai harus di-redirect dari {ep}")

            # Admin -> 200
            resp = self.get_client('admin').get(url)
            self.assertEqual(resp.status_code, 200, f"Admin harus dapat mengakses {ep}")

    def test_admin_api_dashboard_stats(self):
        """API statistik dashboard hanya boleh diakses oleh Admin."""
        url = reverse('tamu:api_dashboard_stats')

        # Anonim -> 302 (redirect ke admin login)
        resp = self.get_client('anon').get(url)
        self.assertEqual(resp.status_code, 302)

        # Tamu -> 302
        resp = self.get_client('tamu_a').get(url)
        self.assertEqual(resp.status_code, 302)

        # Pegawai -> 302
        resp = self.get_client('pegawai').get(url)
        self.assertEqual(resp.status_code, 302)

        # Admin -> 200
        resp = self.get_client('admin').get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get('success'))

    def test_admin_api_toggle_user_status(self):
        """Toggle status pengguna hanya boleh dieksekusi oleh Admin."""
        url = reverse('tamu:api_toggle_user_status', kwargs={'user_id': self.tamu_b.id})

        # Anonim -> 403
        resp = self.get_client('anon').post(url, {'status': 'inactive'})
        self.assertEqual(resp.status_code, 403)

        # Tamu A -> 403 (mencoba menonaktifkan Tamu B)
        resp = self.get_client('tamu_a').post(url, {'status': 'inactive'})
        self.assertEqual(resp.status_code, 403)
        self.tamu_b.refresh_from_db()
        self.assertEqual(self.tamu_b.account_status, 'active')

        # Pegawai -> 403
        resp = self.get_client('pegawai').post(url, {'status': 'inactive'})
        self.assertEqual(resp.status_code, 403)

        # Admin -> 200
        resp = self.get_client('admin').post(url, {'status': 'inactive'})
        self.assertEqual(resp.status_code, 200)
        self.tamu_b.refresh_from_db()
        self.assertEqual(self.tamu_b.account_status, 'inactive')

    def test_admin_api_delete_chat_message(self):
        """Hapus chat hanya boleh dieksekusi oleh Admin."""
        msg = ChatMessage.objects.create(
            session_id=str(self.tamu_a.id),
            sender_id=str(self.tamu_a.id),
            sender_type='tamu',
            content='Pesan uji coba'
        )
        url = reverse('tamu:api_delete_chat_message', kwargs={'message_id': msg.id})

        # Tamu A -> 403
        resp = self.get_client('tamu_a').post(url)
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(ChatMessage.objects.filter(id=msg.id).exists())

        # Pegawai -> 403
        resp = self.get_client('pegawai').post(url)
        self.assertEqual(resp.status_code, 403)

        # Admin -> 200
        resp = self.get_client('admin').post(url)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(ChatMessage.objects.filter(id=msg.id).exists())

    def test_pegawai_portal_access(self):
        """Portal pegawai hanya boleh diakses oleh Pegawai."""
        endpoints = [
            'tamu:pegawai_dashboard',
            'tamu:pegawai_kunjungan_list',
            'tamu:pegawai_chat',
            'tamu:pegawai_profile',
        ]
        for ep in endpoints:
            url = reverse(ep)
            # Anonim -> 302
            resp = self.get_client('anon').get(url)
            self.assertEqual(resp.status_code, 302)

            # Tamu -> 302
            resp = self.get_client('tamu_a').get(url)
            self.assertEqual(resp.status_code, 302)

            # Pegawai -> 200
            resp = self.get_client('pegawai').get(url)
            self.assertEqual(resp.status_code, 200, f"Pegawai harus dapat mengakses {ep}")

    def test_tamu_portal_access(self):
        """Portal tamu hanya boleh diakses oleh Tamu yang login."""
        endpoints = [
            'tamu:dashboard',
            'tamu:kunjungan_baru',
            'tamu:riwayat',
            'tamu:user_chat',
            'tamu:profil',
        ]
        for ep in endpoints:
            url = reverse(ep)
            # Anonim -> 302
            resp = self.get_client('anon').get(url)
            self.assertEqual(resp.status_code, 302)

            # Tamu -> 200
            resp = self.get_client('tamu_a').get(url)
            self.assertEqual(resp.status_code, 200, f"Tamu harus dapat mengakses {ep}")

    def test_admin_pegawai_access_and_pii_protection(self):
        """Halaman admin_pegawai hanya untuk Admin dan tidak membocorkan hash password."""
        url = reverse('tamu:admin_pegawai')

        # Anonim -> 302
        self.assertEqual(self.get_client('anon').get(url).status_code, 302)

        # Tamu -> 302
        self.assertEqual(self.get_client('tamu_a').get(url).status_code, 302)

        # Pegawai -> 302
        self.assertEqual(self.get_client('pegawai').get(url).status_code, 302)

        # Admin -> 200
        resp = self.get_client('admin').get(url)
        self.assertEqual(resp.status_code, 200)

        # Pastikan template merender nama pegawai tapi TIDAK membocorkan hash password
        content = resp.content.decode('utf-8')
        self.assertIn(self.pegawai.name, content)
        self.assertNotIn(self.pegawai.password, content)

    def test_admin_pegawai_update_role_and_status_authorization(self):
        """Update role dan status pegawai hanya boleh dilakukan oleh Admin."""
        import json
        role_url = reverse('tamu:admin_pegawai_update_role', kwargs={'pegawai_id': self.pegawai.id})
        status_url = reverse('tamu:admin_pegawai_update_status', kwargs={'pegawai_id': self.pegawai.id})

        # Non-admin (Tamu A) -> 302
        resp = self.get_client('tamu_a').post(role_url, json.dumps({'role': 'supervisor'}), content_type='application/json')
        self.assertEqual(resp.status_code, 302)

        # Admin -> 200 (Update role)
        resp = self.get_client('admin').post(role_url, json.dumps({'role': 'supervisor'}), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.pegawai.refresh_from_db()
        self.assertEqual(self.pegawai.role, 'supervisor')

        # Admin -> 200 (Update status)
        resp = self.get_client('admin').post(status_url, json.dumps({'status': 'inactive'}), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.pegawai.refresh_from_db()
        self.assertEqual(self.pegawai.account_status, 'inactive')

