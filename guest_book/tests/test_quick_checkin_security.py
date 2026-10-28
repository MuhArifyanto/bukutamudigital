"""
Pengujian komprehensif untuk Quick Check-in Admin (TUGAS 3.2).

Memastikan:
1. Dua tamu bernama sama tidak tertukar; record Tamu dibuat terpisah jika tidak ada NIK/telepon yang cocok.
2. Pencocokan hanya terjadi jika ada pengenal unik (NIK atau telepon) yang cocok tepat 1 akun.
3. Email dummy acak unik dan aman terhadap bentrok IntegrityError tanpa menyebabkan HTTP 500.
4. Validasi input: panjang nama (minimal 2), format NIK (16 digit), format telepon (8-15 digit).
5. Otorisasi ketat: Non-admin dan anonim ditolak (401/403/redirect).
6. Transaksi atomik: jika jadwal/kuota tidak valid, rollback bersih (tidak ada record Tamu yatim).
7. Method selain POST ditolak (405).
"""

import json
from datetime import datetime, date, timedelta, time
import zoneinfo
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.db import IntegrityError

from ..models import Tamu, Pegawai, Departemen, Instansi, Kunjungan, KunjunganStatus, CalendarSettings
from ..validators import JAKARTA_TZ

QUICK_URL = reverse('tamu:api_quick_checkin')


class QuickCheckinSecurityTests(TestCase):
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
        cls.pegawai = Pegawai.objects.create(
            name="Pegawai Penerima",
            username="pegawaicek",
            email="penerima@bekasikab.go.id",
            department_rel=cls.dept,
            role="staff",
            account_status="active",
            password=make_password("password123")
        )

        # Admin Django (Staff)
        cls.admin_user = User.objects.create_user(
            username="admin_loket",
            email="admin@bekasikab.go.id",
            password="adminpassword123",
            is_staff=True
        )

        # Tamu Eksisting dengan NIK dan Telepon resmi
        cls.tamu_eksisting = Tamu.objects.create(
            name="Budi Santoso",
            email="budi.asli@example.com",
            phone="081234567890",
            nik="3216010101010001",
            instansi="PT Asli Indonesia",
            account_status="active",
            registration_type="manual",
            password=make_password("password123")
        )

    def setUp(self):
        self.client = Client()

    def _login_admin(self, client=None):
        c = client or self.client
        c.force_login(self.admin_user)
        return c

    def _post_json(self, payload, client=None):
        c = client or self.client
        return c.post(
            QUICK_URL,
            data=json.dumps(payload),
            content_type='application/json'
        )

    # ── 1. Keamanan Otorisasi & Method ────────────────────────────────────────
    def test_anonymous_and_non_admin_rejected(self):
        """User anonim atau tamu biasa tidak boleh mengakses quick checkin."""
        payload = {'name': 'Tamu Ilegal'}
        resp = self._post_json(payload)
        # @admin_login_required me-redirect anonim ke login admin
        self.assertEqual(resp.status_code, 302)

        # Tamu biasa login via session
        tamu_client = Client()
        sess = tamu_client.session
        sess['tamu_id'] = str(self.tamu_eksisting.pk)
        sess.save()
        resp_tamu = self._post_json(payload, client=tamu_client)
        self.assertEqual(resp_tamu.status_code, 302)

    def test_non_post_methods_rejected(self):
        """Method GET, PUT, DELETE harus ditolak 405."""
        self._login_admin()
        for method in ('get', 'put', 'delete'):
            resp = getattr(self.client, method)(QUICK_URL)
            self.assertEqual(resp.status_code, 405)

    # ── 2. Pencegahan Salah Tautan Tamu Bernama Sama ──────────────────────────
    def test_two_guests_with_same_name_get_separate_records(self):
        """
        Dua tamu dengan nama persis sama ('Budi Santoso') tanpa NIK/telepon
        TIDAK boleh digabungkan. Harus menghasilkan 2 record Tamu yang berbeda.
        """
        self._login_admin()
        payload = {
            'name': 'Budi Santoso',  # Sama dengan nama tamu_eksisting
            'instansi': 'Instansi Berbeda',
            'purpose': 'Bertemu keperluan lain'
        }
        resp = self._post_json(payload)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

        # Pastikan ada 2 Tamu bernama 'Budi Santoso'
        budis = list(Tamu.objects.filter(name='Budi Santoso'))
        self.assertEqual(len(budis), 2)

        # Kunjungan baru tidak tertaut ke tamu_eksisting
        kunjungan_id = resp.json()['kunjungan_id']
        kunjungan = Kunjungan.objects.get(pk=kunjungan_id)
        self.assertNotEqual(kunjungan.tamu.pk, self.tamu_eksisting.pk)
        self.assertTrue(kunjungan.tamu.email.startswith('quick_'))

    def test_matching_by_nik_links_to_existing_tamu(self):
        """Jika NIK diisi dan cocok dengan tamu yang ada, tautkan ke tamu tersebut."""
        self._login_admin()
        payload = {
            'name': 'Budi S.',  # Variasi nama sedikit berbeda
            'nik': self.tamu_eksisting.nik,  # NIK cocok
            'purpose': 'Koordinasi data NIK'
        }
        resp = self._post_json(payload)
        self.assertEqual(resp.status_code, 200)

        kunjungan_id = resp.json()['kunjungan_id']
        kunjungan = Kunjungan.objects.get(pk=kunjungan_id)
        # Tertaut ke tamu_eksisting
        self.assertEqual(kunjungan.tamu.pk, self.tamu_eksisting.pk)

    def test_matching_by_phone_links_to_existing_tamu(self):
        """Jika telepon diisi dan cocok, tautkan ke tamu tersebut."""
        self._login_admin()
        payload = {
            'name': 'Budi Telepon',
            'phone': self.tamu_eksisting.phone,  # Telepon cocok
            'purpose': 'Koordinasi telepon'
        }
        resp = self._post_json(payload)
        self.assertEqual(resp.status_code, 200)

        kunjungan_id = resp.json()['kunjungan_id']
        kunjungan = Kunjungan.objects.get(pk=kunjungan_id)
        self.assertEqual(kunjungan.tamu.pk, self.tamu_eksisting.pk)

    # ── 3. Email Dummy Unik & Penanganan Bentrok ──────────────────────────────
    def test_dummy_email_retry_handles_collision_without_500(self):
        """
        Jika terjadi IntegrityError bentrok email dummy, fungsi harus me-retry
        dengan email baru dan tetap berhasil 200 (bukan error 500).
        """
        self._login_admin()
        payload = {'name': 'Tamu Uji Tabrakan'}

        call_count = 0
        real_create = Tamu.objects.create

        def mock_create_with_one_collision(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Simulasi tabrakan email sekali
                raise IntegrityError("Duplicate entry for key 'email'")
            return real_create(*args, **kwargs)

        with patch.object(Tamu.objects, 'create', side_effect=mock_create_with_one_collision):
            resp = self._post_json(payload)
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.json()['success'])
            self.assertGreaterEqual(call_count, 2)

    # ── 4. Validasi Input yang Ketat ──────────────────────────────────────────
    def test_name_validation(self):
        """Nama kosong atau kurang dari 2 karakter harus ditolak 400."""
        self._login_admin()
        for invalid_name in ('', '   ', 'A', None, 123):
            resp = self._post_json({'name': invalid_name})
            self.assertEqual(resp.status_code, 400)
            self.assertFalse(resp.json()['success'])

    def test_nik_validation(self):
        """NIK yang tidak tepat 16 digit angka harus ditolak 400."""
        self._login_admin()
        for bad_nik in ('12345', '12345678901234567', '321601010101000A', 'abcdefghijklmnop'):
            resp = self._post_json({'name': 'Tamu Valid', 'nik': bad_nik})
            self.assertEqual(resp.status_code, 400)
            self.assertIn("16 digit", resp.json()['error'])

    def test_phone_validation(self):
        """Nomor telepon di luar 8-15 digit harus ditolak 400."""
        self._login_admin()
        for bad_phone in ('123', '08123', '123456789012345678'):
            resp = self._post_json({'name': 'Tamu Valid', 'phone': bad_phone})
            self.assertEqual(resp.status_code, 400)
            self.assertIn("telepon", resp.json()['error'].lower())

    # ── 5. Transaksi Atomik (Rollback Jika Jadwal Gagal) ──────────────────────
    def test_atomic_rollback_leaves_no_orphan_tamu(self):
        """
        Jika validasi kunjungan gagal (misal instansi libur),
        record Tamu yang baru dibuat harus di-rollback dan tidak tersimpan.
        """
        self._login_admin()
        test_date = date(2026, 11, 20)
        CalendarSettings.objects.create(
            date=test_date,
            is_holiday=True,
            holiday_name="Libur Resmi Uji"
        )

        initial_tamu_count = Tamu.objects.count()

        # Coba daftar di hari libur (is_admin bypass hari libur jika bukan error validasi,
        # jadi kita uji dengan tanggal/waktu yang memicu ValidationError)
        payload = {
            'name': 'Tamu Calon Yatim',
            'date': 'bukan-tanggal-valid',
            'time': '99:99'
        }
        resp = self._post_json(payload)
        self.assertEqual(resp.status_code, 400)

        # Tidak boleh ada record Tamu yatim yang tertinggal
        self.assertEqual(Tamu.objects.count(), initial_tamu_count)
        self.assertFalse(Tamu.objects.filter(name='Tamu Calon Yatim').exists())
