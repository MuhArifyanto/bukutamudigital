"""
guest_book/tests/test_smoke_end_to_end.py
Smoke test alur kerja utama lintas peran (End-to-End):
- Tamu mendaftar dan mengajukan kunjungan
- Pegawai melihat dan memverifikasi
- Admin memverifikasi status & melihat statistik
- Chat antar peran & notifikasi
- Ekspor Excel kunjungan
"""

from django.urls import reverse
from django.utils import timezone
from .base import BaseSecurityTestCase
from ..models import Kunjungan, KunjunganStatus, ChatMessage, Notification
import io


class SmokeEndToEndTestCase(BaseSecurityTestCase):
    """Smoke test menyeluruh menguji alur bisnis inti."""

    def test_end_to_end_visit_workflow(self):
        # 1. Tamu A mengajukan kunjungan baru
        tamu_client = self.get_client('tamu_a')
        kunjungan_url = reverse('tamu:kunjungan_baru')
        tomorrow = timezone.now() + timezone.timedelta(days=1)
        while tomorrow.weekday() in [5, 6]:
            tomorrow += timezone.timedelta(days=1)
        payload = {
            'pegawai': str(self.pegawai.id),
            'purpose': 'Konsultasi Integrasi Sistem Satu Data',
            'arrival_time': tomorrow.strftime('%Y-%m-%dT10:00'),
            'departure_time': tomorrow.strftime('%Y-%m-%dT12:00'),
            'notes': 'Mohon konfirmasi kedatangan.',
        }
        resp = tamu_client.post(kunjungan_url, payload)
        self.assertIn(resp.status_code, (200, 302))

        # Verifikasi kunjungan terbentuk
        kunjungan = Kunjungan.objects.filter(tamu=self.tamu_a).order_by('-created_at').first()
        self.assertIsNotNone(kunjungan)
        self.assertEqual(kunjungan.purpose, 'Konsultasi Integrasi Sistem Satu Data')



        # 2. Pegawai melihat kunjungan di daftar kunjungan pegawai
        pegawai_client = self.get_client('pegawai')
        pegawai_list_url = reverse('tamu:pegawai_kunjungan_list')
        resp = pegawai_client.get(pegawai_list_url)
        self.assertEqual(resp.status_code, 200)

        # 3. Admin melihat statistik dashboard
        admin_client = self.get_client('admin')
        dash_url = reverse('tamu:admin_dashboard')
        resp = admin_client.get(dash_url)
        self.assertEqual(resp.status_code, 200)

        stats_api_url = reverse('tamu:api_dashboard_stats')
        resp = admin_client.get(stats_api_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('menunggu_verifikasi', data)
        self.assertEqual(data['menunggu_verifikasi'], 1)

        # 4. Chat dan notifikasi berjalan
        chat_msg = ChatMessage.objects.create(
            session_id=str(self.tamu_a.id),
            sender_id=str(self.tamu_a.id),
            sender_type='tamu',
            content='Halo Admin dan Pegawai, mohon konfirmasi kunjungannya.'
        )
        self.assertIsNotNone(chat_msg.id)

        notif = Notification.objects.create(
            recipient_id=str(self.tamu_a.id),
            recipient_type='tamu',
            title='Kunjungan Diajukan',
            message='Kunjungan Anda telah berhasil dicatat.',
            notification_type='visit_registered',
            status='unread'
        )
        self.assertEqual(notif.status, 'unread')

        # Tamu A menandai notifikasi telah dibaca
        import json
        mark_url = reverse('tamu:api_mark_notification_read')
        resp = tamu_client.post(
            mark_url,
            json.dumps({'notification_id': str(notif.id)}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        notif.refresh_from_db()
        self.assertEqual(notif.status, 'read')



        # 5. Ekspor Excel Kunjungan oleh Admin
        export_url = reverse('tamu:admin_kunjungan_export_excel')
        resp = admin_client.get(export_url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        self.assertTrue(len(resp.content) > 100)
