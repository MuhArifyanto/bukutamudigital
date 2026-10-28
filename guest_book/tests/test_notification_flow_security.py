"""
Pengujian komprehensif untuk Alur Notifikasi Perubahan Kunjungan (TUGAS 3.3).

Memastikan:
1. Pembatalan kunjungan oleh Tamu mengirim notifikasi ke Admin dan Pegawai yang ditugaskan.
2. Pembatalan kunjungan tanpa Pegawai tetap mengirim notifikasi ke Admin tanpa error.
3. Transisi status 'cancelled' pada WorkflowEngine mengirim notifikasi ke Tamu, Pegawai, dan Admin.
4. Delegasi kunjungan oleh Pegawai mengirim notifikasi delegasi ke rekan kerja penerima.
5. Pencatatan kunjungan manual oleh Admin mengirim notifikasi ke Pegawai, tanpa spam notifikasi ke Admin sendiri.
6. Graceful degradation: kegagalan send_notification tidak menggagalkan proses bisnis utama.
"""

from datetime import datetime, date, timedelta, time
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.utils import timezone

from ..models import Tamu, Pegawai, Departemen, Instansi, Kunjungan, KunjunganStatus, Notification
from ..workflow_engine import WorkflowEngine
from ..validators import JAKARTA_TZ


class NotificationFlowSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.instansi = Instansi.objects.create(
            nama="Diskominfosantik Kabupaten Bekasi",
            kapasitas_maksimal=50,
            status_operasional="Aktif",
            jam_buka=time(8, 0),
            jam_tutup=time(16, 0),
            hari_kerja="0,1,2,3,4,5,6"
        )
        cls.dept = Departemen.objects.create(nama="Bidang TIK", kode="TIK")
        cls.pegawai1 = Pegawai.objects.create(
            name="Pegawai Satu",
            username="pegawai1",
            email="pegawai1@bekasikab.go.id",
            department_rel=cls.dept,
            role="staff",
            account_status="active",
            password=make_password("password123")
        )
        cls.pegawai2 = Pegawai.objects.create(
            name="Pegawai Dua",
            username="pegawai2",
            email="pegawai2@bekasikab.go.id",
            department_rel=cls.dept,
            role="staff",
            account_status="active",
            password=make_password("password123")
        )

        cls.admin_user = User.objects.create_user(
            username="admin_notif",
            email="admin_notif@bekasikab.go.id",
            password="adminpassword123",
            is_staff=True
        )

        cls.tamu = Tamu.objects.create(
            name="Tamu Pemohon",
            email="tamu.notif@example.com",
            phone="081234567890",
            nik="3216010101010001",
            account_status="active",
            registration_type="manual"
        )

    def _login_tamu(self, client=None):
        c = client or self.client
        sess = c.session
        sess['tamu_id'] = str(self.tamu.id)
        sess['tamu_name'] = self.tamu.name
        sess['user_type'] = 'tamu'
        sess.save()
        return c

    def _login_pegawai(self, pegawai, client=None):
        c = client or self.client
        sess = c.session
        sess['pegawai_id'] = str(pegawai.id)
        sess['pegawai_name'] = pegawai.name
        sess['user_type'] = 'pegawai'
        sess.save()
        return c

    def _login_admin(self, client=None):
        c = client or self.client
        c.force_login(self.admin_user)
        return c

    # ── 1. Pembatalan Kunjungan oleh Tamu ─────────────────────────────────────
    def test_tamu_cancel_visit_notifies_both_admin_and_assigned_pegawai(self):
        """Saat tamu membatalkan kunjungan dengan pegawai tertugaskan, Admin & Pegawai menerima notifikasi."""
        visit_time = timezone.now() + timedelta(days=2)
        kunjungan = Kunjungan.objects.create(
            tamu=self.tamu,
            pegawai=self.pegawai1,
            arrival_time=visit_time,
            status=KunjunganStatus.MENUNGGU_ADMIN,
            purpose="Konsultasi IT"
        )

        self._login_tamu()
        cancel_url = reverse('tamu:kunjungan_batal', kwargs={'pk': kunjungan.id})

        notif_before = Notification.objects.count()
        resp = self.client.post(cancel_url)
        self.assertEqual(resp.status_code, 302)

        kunjungan.refresh_from_db()
        self.assertEqual(kunjungan.status, 'cancelled')

        # Verifikasi notifikasi admin
        admin_notif = Notification.objects.filter(
            recipient_id='admin',
            recipient_type='admin',
            related_object_id=str(kunjungan.id)
        ).first()
        self.assertIsNotNone(admin_notif)
        self.assertIn("Tamu Pemohon", admin_notif.message)

        # Verifikasi notifikasi pegawai
        pegawai_notif = Notification.objects.filter(
            recipient_id=str(self.pegawai1.id),
            recipient_type='pegawai',
            related_object_id=str(kunjungan.id)
        ).first()
        self.assertIsNotNone(pegawai_notif)
        self.assertIn("Tamu Pemohon", pegawai_notif.message)
        self.assertIn("batal", pegawai_notif.message.lower())

    def test_tamu_cancel_visit_without_pegawai_only_notifies_admin(self):
        """Jika tidak ada pegawai yang ditugaskan, hanya admin yang dinotifikasi (tanpa error)."""
        visit_time = timezone.now() + timedelta(days=2)
        kunjungan = Kunjungan.objects.create(
            tamu=self.tamu,
            pegawai=None,
            arrival_time=visit_time,
            status=KunjunganStatus.MENUNGGU_ADMIN,
            purpose="Kunjungan Umum"
        )

        self._login_tamu()
        cancel_url = reverse('tamu:kunjungan_batal', kwargs={'pk': kunjungan.id})
        resp = self.client.post(cancel_url)
        self.assertEqual(resp.status_code, 302)

        kunjungan.refresh_from_db()
        self.assertEqual(kunjungan.status, 'cancelled')

        admin_notif = Notification.objects.filter(
            recipient_id='admin',
            recipient_type='admin',
            related_object_id=str(kunjungan.id)
        ).first()
        self.assertIsNotNone(admin_notif)

    def test_tamu_cancel_graceful_when_notification_service_fails(self):
        """Kegagalan send_notification tidak boleh menggagalkan pembatalan kunjungan oleh Tamu."""
        visit_time = timezone.now() + timedelta(days=2)
        kunjungan = Kunjungan.objects.create(
            tamu=self.tamu,
            pegawai=self.pegawai1,
            arrival_time=visit_time,
            status=KunjunganStatus.MENUNGGU_ADMIN,
            purpose="Konsultasi Darurat"
        )

        self._login_tamu()
        cancel_url = reverse('tamu:kunjungan_batal', kwargs={'pk': kunjungan.id})

        with patch('guest_book.views.tamu.send_notification', side_effect=Exception("Simulated notification broker down")):
            resp = self.client.post(cancel_url)
            self.assertEqual(resp.status_code, 302)

        kunjungan.refresh_from_db()
        self.assertEqual(kunjungan.status, 'cancelled')

    # ── 2. WorkflowEngine Transisi Cancelled ──────────────────────────────────
    def test_workflow_engine_cancelled_transition_notifies_all_parties(self):
        """WorkflowEngine transisi ke CANCELLED harus menotifikasi Tamu, Pegawai, dan Admin."""
        visit_time = timezone.now() + timedelta(days=2)
        kunjungan = Kunjungan.objects.create(
            tamu=self.tamu,
            pegawai=self.pegawai1,
            arrival_time=visit_time,
            status=KunjunganStatus.MENUNGGU_ADMIN,
            purpose="Uji Workflow"
        )

        engine = WorkflowEngine(kunjungan)
        success = engine.transition(
            new_status=KunjunganStatus.CANCELLED,
            user_id='admin',
            user_type='admin',
            notes="Dibatalkan oleh sistem/admin"
        )
        self.assertTrue(success)

        # 1. Tamu
        tamu_notif = Notification.objects.filter(
            recipient_id=str(self.tamu.id),
            recipient_type='tamu',
            related_object_id=str(kunjungan.id)
        ).first()
        self.assertIsNotNone(tamu_notif)

        # 2. Pegawai
        pegawai_notif = Notification.objects.filter(
            recipient_id=str(self.pegawai1.id),
            recipient_type='pegawai',
            related_object_id=str(kunjungan.id)
        ).first()
        self.assertIsNotNone(pegawai_notif)
        self.assertIn("dibatalkan", pegawai_notif.message.lower())

        # 3. Admin
        admin_notif = Notification.objects.filter(
            recipient_id='admin',
            recipient_type='admin',
            related_object_id=str(kunjungan.id)
        ).first()
        self.assertIsNotNone(admin_notif)

    # ── 3. Delegasi Kunjungan Pegawai ─────────────────────────────────────────
    def test_pegawai_delegate_notifies_delegatee_colleague(self):
        """Saat pegawai mendelegasikan kunjungan, rekan penerima delegasi harus menerima notifikasi."""
        visit_time = timezone.now() + timedelta(days=2)
        kunjungan = Kunjungan.objects.create(
            tamu=self.tamu,
            pegawai=self.pegawai1,
            arrival_time=visit_time,
            status=KunjunganStatus.MENUNGGU_PEGAWAI,
            purpose="Koordinasi Jaringan"
        )

        self._login_pegawai(self.pegawai1)
        detail_url = reverse('tamu:pegawai_kunjungan_detail', kwargs={'pk': kunjungan.id})

        resp = self.client.post(detail_url, {
            'delegate_to': str(self.pegawai2.id),
            'delegate_reason': 'Sedang dinas luar kota'
        })
        self.assertEqual(resp.status_code, 302)

        kunjungan.refresh_from_db()
        self.assertEqual(kunjungan.pegawai, self.pegawai2)

        # Cek notifikasi ke rekan (pegawai2)
        rekan_notif = Notification.objects.filter(
            recipient_id=str(self.pegawai2.id),
            recipient_type='pegawai',
            related_object_id=str(kunjungan.id)
        ).first()
        self.assertIsNotNone(rekan_notif)
        self.assertIn("Pegawai Satu", rekan_notif.message)
        self.assertIn("Sedang dinas luar kota", rekan_notif.message)

    # ── 4. Kunjungan Manual Admin ─────────────────────────────────────────────
    def test_admin_manual_create_notifies_pegawai_without_admin_self_spam(self):
        """Pencatatan kunjungan manual oleh admin hanya menotifikasi pegawai yang dituju, tanpa spam ke admin sendiri."""
        self._login_admin()
        manual_url = reverse('tamu:admin_kunjungan_manual_create')

        payload = {
            'name': 'Tamu Walk-in',
            'email': 'walkin@example.com',
            'phone': '081299998888',
            'instansi': 'PT Contoh',
            'pegawai_id': str(self.pegawai1.id),
            'purpose': 'Pertemuan Walk-in'
        }

        notif_before_admin = Notification.objects.filter(recipient_type='admin').count()
        resp = self.client.post(manual_url, payload)
        self.assertEqual(resp.status_code, 302)

        # Admin tidak boleh bertambah notifikasinya (menghindari self-spam)
        notif_after_admin = Notification.objects.filter(recipient_type='admin').count()
        self.assertEqual(notif_after_admin, notif_before_admin)

        # Pegawai tujuan harus menerima notifikasi
        pegawai_notif = Notification.objects.filter(
            recipient_id=str(self.pegawai1.id),
            recipient_type='pegawai',
            notification_type='visit_registered'
        ).first()
        self.assertIsNotNone(pegawai_notif)
        self.assertIn("Tamu Walk-in", pegawai_notif.message)
