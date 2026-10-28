from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
import json

from .base import BaseSecurityTestCase
from ..models import Kunjungan, KunjunganStatus, Notification


class IDORAndWorkflowTestCase(BaseSecurityTestCase):
    """
    Uji keamanan lintas pengguna (Anti-IDOR) dan kebenaran alur kerja (Workflow & Stats).
    """

    def setUp(self):
        super().setUp()

        # Kunjungan milik Tamu A
        self.kunjungan_a = Kunjungan.objects.create(
            tamu=self.tamu_a,
            pegawai=self.pegawai,
            arrival_time=timezone.now() + timedelta(days=1),
            purpose="Konsultasi Jaringan",
            status=KunjunganStatus.MENUNGGU_ADMIN
        )

        # Kunjungan milik Tamu B
        self.kunjungan_b = Kunjungan.objects.create(
            tamu=self.tamu_b,
            pegawai=self.pegawai,
            arrival_time=timezone.now() + timedelta(days=2),
            purpose="Pengajuan subdomain",
            status=KunjunganStatus.MENUNGGU_ADMIN
        )

    def test_idor_cancel_visit(self):
        """Tamu A tidak boleh dapat membatalkan kunjungan milik Tamu B."""
        url = reverse('tamu:kunjungan_batal', kwargs={'pk': self.kunjungan_b.id})
        resp = self.get_client('tamu_a').post(url)
        # Menghasilkan 404 karena filter tamu=tamu_a tidak menemukan kunjungan_b
        self.assertEqual(resp.status_code, 404)
        self.kunjungan_b.refresh_from_db()
        self.assertEqual(self.kunjungan_b.status, KunjunganStatus.MENUNGGU_ADMIN)

    def test_cancel_own_pending_visit_success(self):
        """Tamu A dapat membatalkan kunjungannya sendiri yang masih berstatus pending/cancelable."""
        url = reverse('tamu:kunjungan_batal', kwargs={'pk': self.kunjungan_a.id})
        resp = self.get_client('tamu_a').post(url)
        self.assertEqual(resp.status_code, 302)
        self.kunjungan_a.refresh_from_db()
        self.assertEqual(self.kunjungan_a.status, KunjunganStatus.CANCELLED)

    def test_cannot_cancel_completed_visit(self):
        """Tamu tidak boleh dapat membatalkan kunjungan yang sudah berstatus 'completed'."""
        self.kunjungan_a.status = KunjunganStatus.COMPLETED
        self.kunjungan_a.save()

        url = reverse('tamu:kunjungan_batal', kwargs={'pk': self.kunjungan_a.id})
        resp = self.get_client('tamu_a').post(url)
        self.assertEqual(resp.status_code, 404)
        self.kunjungan_a.refresh_from_db()
        self.assertEqual(self.kunjungan_a.status, KunjunganStatus.COMPLETED)

    def test_idor_view_visit_detail(self):
        """Tamu A tidak boleh melihat detail kunjungan milik Tamu B."""
        url = reverse('tamu:kunjungan_detail', kwargs={'pk': self.kunjungan_b.id})
        resp = self.get_client('tamu_a').get(url)
        self.assertEqual(resp.status_code, 404)

    def test_idor_print_visit_card(self):
        """Tamu A tidak boleh mencetak kartu kunjungan milik Tamu B."""
        url = reverse('tamu:tamu_cetak_kartu', kwargs={'pk': self.kunjungan_b.id})
        resp = self.get_client('tamu_a').get(url)
        self.assertEqual(resp.status_code, 404)

    def test_idor_mark_notification_read(self):
        """Tamu A tidak boleh bisa menandai notifikasi milik Tamu B sebagai terbaca."""
        notif_b = Notification.objects.create(
            recipient_id=str(self.tamu_b.id),
            recipient_type='tamu',
            notification_type='system_alert',
            title='Alert Tamu B',
            message='Pesan rahasia Tamu B',
            status='unread'
        )

        url = reverse('tamu:api_mark_notification_read')
        # Tamu A mencoba menandai notif B
        resp = self.get_client('tamu_a').post(
            url,
            data=json.dumps({'notification_id': str(notif_b.id)}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json().get('success'))

        notif_b.refresh_from_db()
        self.assertEqual(notif_b.status, 'unread')

        # Tamu B menandai notifikasinya sendiri -> sukses
        resp = self.get_client('tamu_b').post(
            url,
            data=json.dumps({'notification_id': str(notif_b.id)}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get('success'))
        notif_b.refresh_from_db()
        self.assertEqual(notif_b.status, 'read')

    def test_dashboard_stats_pending_verification_count(self):
        """
        Kartu 'Menunggu Verifikasi' harus HANYA menghitung status:
        menunggu_admin, menunggu_pegawai, dan disetujui_pegawai.
        """
        now = timezone.now()
        # Bersihkan data kunjungan sebelumnya agar hitungan presisi
        Kunjungan.objects.all().delete()

        # Buat kombinasi status:
        # Menunggu Verifikasi:
        Kunjungan.objects.create(tamu=self.tamu_a, arrival_time=now, purpose="P1", status=KunjunganStatus.MENUNGGU_ADMIN)
        Kunjungan.objects.create(tamu=self.tamu_a, arrival_time=now, purpose="P2", status=KunjunganStatus.MENUNGGU_ADMIN)
        Kunjungan.objects.create(tamu=self.tamu_b, arrival_time=now, purpose="P3", status=KunjunganStatus.MENUNGGU_PEGAWAI)
        Kunjungan.objects.create(tamu=self.tamu_b, arrival_time=now, purpose="P4", status=KunjunganStatus.DISETUJUI_PEGAWAI)

        # Status yang BUKAN menunggu verifikasi:
        Kunjungan.objects.create(tamu=self.tamu_a, arrival_time=now, purpose="P5", status=KunjunganStatus.DISETUJUI)
        Kunjungan.objects.create(tamu=self.tamu_a, arrival_time=now, purpose="P6", status=KunjunganStatus.IN_PROGRESS)
        Kunjungan.objects.create(tamu=self.tamu_b, arrival_time=now, purpose="P7", status=KunjunganStatus.COMPLETED)
        Kunjungan.objects.create(tamu=self.tamu_b, arrival_time=now, purpose="P8", status=KunjunganStatus.CANCELLED)

        # Cek via api_dashboard_stats
        url = reverse('tamu:api_dashboard_stats')
        resp = self.get_client('admin').get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get('menunggu_verifikasi'), 4)

    def test_anti_lockout_admin(self):
        """Admin tidak boleh menonaktifkan akun adminnya sendiri."""
        url = reverse('tamu:api_toggle_user_status', kwargs={'user_id': self.admin_tamu.id})
        resp = self.get_client('admin').post(url, {'status': 'inactive'})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data.get('success'))
        self.assertIn("tidak dapat menonaktifkan akun admin Anda sendiri", data.get('error', ''))

        self.admin_tamu.refresh_from_db()
        self.assertEqual(self.admin_tamu.account_status, 'active')
