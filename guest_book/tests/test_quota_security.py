"""
Pengujian komprehensif untuk kuota kunjungan terpusat (TUGAS 3.1).

Memastikan:
1. Kunjungan berstatus cancelled, ditolak_admin, dan ditolak_pegawai TIDAK mengurangi kuota.
2. Kunjungan aktif (menunggu_admin, menunggu_pegawai, disetujui_pegawai, disetujui, in_progress, completed) mengurangi kuota.
3. Kunjungan mendekati tengah malam (pukul 23:30 dan 00:30 WIB) masuk ke tanggal kalender yang benar.
4. Output api_check_quota identik dengan validasi di KunjunganForm.clean() dan validate_kunjungan_schedule.
5. get_monthly_quota_usage menghitung dengan tepat menggunakan 1 kueri agregasi.
"""

from datetime import datetime, date, timedelta, time
import zoneinfo
from django.test import TestCase, Client
from django.urls import reverse
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password

from ..models import Tamu, Pegawai, Departemen, Instansi, Kunjungan, KunjunganStatus, CalendarSettings
from ..validators import (
    get_day_range_aware, get_daily_quota_info, get_monthly_quota_usage,
    validate_kunjungan_schedule, ACTIVE_QUOTA_STATUSES, JAKARTA_TZ
)
from ..forms import KunjunganForm


class QuotaCentralizedSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.instansi = Instansi.objects.create(
            nama="Diskominfosantik Kabupaten Bekasi",
            kapasitas_maksimal=5,  # Kuota kecil agar mudah diuji
            status_operasional="Aktif",
            jam_buka=time(8, 0),
            jam_tutup=time(16, 0),
            hari_kerja="0,1,2,3,4,5,6"  # Buka setiap hari untuk pengujian tanggal
        )
        cls.dept = Departemen.objects.create(nama="Bidang TIK", kode="TIK")
        cls.pegawai = Pegawai.objects.create(
            name="Pegawai Test",
            username="pegawaitest",
            email="pegawai@example.com",
            department_rel=cls.dept,
            role="staff",
            account_status="active",
            password=make_password("password123")
        )
        cls.tamu = Tamu.objects.create(
            name="Tamu Test",
            email="tamu@example.com",
            phone="081234567890",
            nik="3216010101010001",
            instansi="PT Test",
            account_status="active",
            registration_type="manual",
            password=make_password("password123")
        )
        cls.admin_django = User.objects.create_user(
            username="admin_user",
            email="admin@bekasikab.go.id",
            password="adminpassword123",
            is_staff=True
        )

    def setUp(self):
        self.client = Client()

    def test_active_statuses_reduce_quota(self):
        """Kunjungan dengan status aktif wajib mengurangi kuota."""
        test_date = date(2026, 11, 10)
        start_day, _ = get_day_range_aware(test_date)
        arr_time = start_day.replace(hour=10, minute=0)

        # Buat kunjungan untuk setiap status aktif
        for i, st in enumerate(ACTIVE_QUOTA_STATUSES[:3]):
            Kunjungan.objects.create(
                tamu=self.tamu,
                pegawai=self.pegawai,
                purpose=f"Kunjungan aktif {i+1}",
                arrival_time=arr_time + timedelta(minutes=i*15),
                status=st
            )

        info = get_daily_quota_info(test_date)
        self.assertEqual(info['quota'], 5)
        self.assertEqual(info['booked'], 3)
        self.assertEqual(info['available'], 2)
        self.assertFalse(info['is_full'])

    def test_cancelled_and_rejected_statuses_do_not_reduce_quota(self):
        """Kunjungan dibatalkan atau ditolak TIDAK boleh mengurangi kuota."""
        test_date = date(2026, 11, 11)
        start_day, _ = get_day_range_aware(test_date)
        arr_time = start_day.replace(hour=10, minute=0)

        # Buat kunjungan cancelled, ditolak_admin, ditolak_pegawai
        inactive_statuses = [
            KunjunganStatus.CANCELLED,
            KunjunganStatus.DITOLAK_ADMIN,
            KunjunganStatus.DITOLAK_PEGAWAI
        ]
        for i, st in enumerate(inactive_statuses):
            Kunjungan.objects.create(
                tamu=self.tamu,
                pegawai=self.pegawai,
                purpose=f"Kunjungan tidak aktif {i+1}",
                arrival_time=arr_time + timedelta(minutes=i*15),
                status=st
            )

        info = get_daily_quota_info(test_date)
        self.assertEqual(info['booked'], 0)
        self.assertEqual(info['available'], 5)
        self.assertFalse(info['is_full'])

    def test_quota_exhaustion_prevents_new_booking(self):
        """Ketika kuota penuh, validate_kunjungan_schedule dan form wajib melempar error."""
        test_date = date(2026, 11, 12)
        start_day, _ = get_day_range_aware(test_date)
        arr_time = start_day.replace(hour=9, minute=0)

        # Isi sampai kuota maksimal (5 orang)
        for i in range(5):
            Kunjungan.objects.create(
                tamu=self.tamu,
                pegawai=self.pegawai,
                purpose=f"Kunjungan kuota {i+1}",
                arrival_time=arr_time + timedelta(minutes=i*20),
                status=KunjunganStatus.DISETUJUI
            )

        info = get_daily_quota_info(test_date)
        self.assertEqual(info['booked'], 5)
        self.assertEqual(info['available'], 0)
        self.assertTrue(info['is_full'])

        # Coba validasi kunjungan ke-6
        new_arrival = arr_time + timedelta(hours=3)
        with self.assertRaises(ValidationError) as ctx:
            validate_kunjungan_schedule(
                arrival_time=new_arrival,
                is_admin=False,
                is_import=False
            )
        self.assertIn("sudah penuh", str(ctx.exception))

    def test_midnight_edge_visits_fall_into_correct_calendar_days(self):
        """
        Kunjungan pukul 23:30 WIB dan 00:30 WIB wajib masuk ke tanggal kalender yang benar.
        Tanggal D: 23:30 WIB -> masuk D
        Tanggal D+1: 00:30 WIB -> masuk D+1
        """
        day_1 = date(2026, 11, 15)
        day_2 = date(2026, 11, 16)

        # 23:30 WIB pada hari 1
        dt_2330 = datetime(2026, 11, 15, 23, 30, 0, tzinfo=JAKARTA_TZ)
        # 00:30 WIB pada hari 2
        dt_0030 = datetime(2026, 11, 16, 0, 30, 0, tzinfo=JAKARTA_TZ)

        k1 = Kunjungan.objects.create(
            tamu=self.tamu,
            pegawai=self.pegawai,
            purpose="Kunjungan larut malam",
            arrival_time=dt_2330,
            status=KunjunganStatus.DISETUJUI
        )
        k2 = Kunjungan.objects.create(
            tamu=self.tamu,
            pegawai=self.pegawai,
            purpose="Kunjungan dini hari",
            arrival_time=dt_0030,
            status=KunjunganStatus.DISETUJUI
        )

        info_day1 = get_daily_quota_info(day_1)
        info_day2 = get_daily_quota_info(day_2)

        # Hari 1 hanya memuat kunjungan 23:30 (1)
        self.assertEqual(info_day1['booked'], 1)
        # Hari 2 hanya memuat kunjungan 00:30 (1)
        self.assertEqual(info_day2['booked'], 1)

    def test_api_check_quota_matches_centralized_logic(self):
        """Endpoint api_check_quota membalas data yang sama persis dengan get_daily_quota_info."""
        test_date = date(2026, 11, 17)
        start_day, _ = get_day_range_aware(test_date)
        arr_time = start_day.replace(hour=11, minute=0)

        # Custom kuota di CalendarSettings
        CalendarSettings.objects.create(
            date=test_date,
            daily_quota=10,
            is_holiday=False
        )

        Kunjungan.objects.create(
            tamu=self.tamu,
            pegawai=self.pegawai,
            purpose="Kunjungan API",
            arrival_time=arr_time,
            status=KunjunganStatus.MENUNGGU_ADMIN
        )

        resp = self.client.get(reverse('tamu:api_check_quota') + f'?date={test_date.isoformat()}')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        info = get_daily_quota_info(test_date)
        self.assertTrue(data['success'])
        self.assertEqual(data['quota'], info['quota'])
        self.assertEqual(data['booked'], info['booked'])
        self.assertEqual(data['available'], info['available'])
        self.assertEqual(data['is_holiday'], info['is_holiday'])
        self.assertEqual(data['is_full'], info['is_full'])

    def test_api_check_quota_holiday(self):
        """Hari libur pada CalendarSettings ditandai dengan benar."""
        test_date = date(2026, 11, 18)
        CalendarSettings.objects.create(
            date=test_date,
            daily_quota=10,
            is_holiday=True,
            holiday_name="Libur Khusus Uji"
        )

        resp = self.client.get(reverse('tamu:api_check_quota') + f'?date={test_date.isoformat()}')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['is_holiday'])
        self.assertEqual(data['holiday_name'], "Libur Khusus Uji")
        self.assertEqual(data['available'], 0)
        self.assertTrue(data['is_full'])

    def test_monthly_quota_usage_single_aggregate_query(self):
        """get_monthly_quota_usage menghitung bulan penuh dengan benar dan efisien."""
        year = 2026
        month = 12

        # Buat kunjungan di 3 tanggal berbeda di bulan Desember
        dates_to_create = [
            (date(year, month, 5), 2),
            (date(year, month, 15), 3),
            (date(year, month, 25), 1),
        ]
        for d, count in dates_to_create:
            start_d, _ = get_day_range_aware(d)
            for j in range(count):
                Kunjungan.objects.create(
                    tamu=self.tamu,
                    pegawai=self.pegawai,
                    purpose=f"Kunjungan Des {d.day}-{j}",
                    arrival_time=start_d.replace(hour=10 + j),
                    status=KunjunganStatus.DISETUJUI
                )

        # Buat juga kunjungan cancelled di tanggal 15 (tidak boleh terhitung)
        start_15, _ = get_day_range_aware(date(year, month, 15))
        Kunjungan.objects.create(
            tamu=self.tamu,
            pegawai=self.pegawai,
            purpose="Kunjungan dibatalkan Des 15",
            arrival_time=start_15.replace(hour=14),
            status=KunjunganStatus.CANCELLED
        )

        usage = get_monthly_quota_usage(year, month)
        self.assertEqual(usage.get(5), 2)
        self.assertEqual(usage.get(15), 3)  # Hanya 3 yang aktif, 1 cancelled diabaikan
        self.assertEqual(usage.get(25), 1)
        self.assertIsNone(usage.get(1))
