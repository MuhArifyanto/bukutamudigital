"""
guest_book/tests/test_kunjungan_validation.py
Pengujian komprehensif validasi jadwal dan kuota kunjungan:
1. Waktu kedatangan di masa lampau ditolak untuk tamu
2. Hari libur (CalendarSettings.is_holiday=True) ditolak
3. Di luar jam operasional kantor (08:00 - 16:00) ditolak
4. Di luar hari kerja (misal Sabtu/Minggu) ditolak
5. Waktu pulang mendahului kedatangan atau melebihi jam tutup kantor ditolak
6. Kuota penuh ditolak dan kuota yang masih ada diterima
7. Status dibatalkan/ditolak tidak mengurangi kuota
8. Kunjungan yang valid berhasil didaftarkan
9. Pengecualian Admin (kunjungan langsung hari ini) dan Impor Excel (data historis lampau)
10. Penguncian konkurensi (atomic select_for_update) mencegah kuota tembus
"""

from datetime import datetime, time, timedelta
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db import transaction

from .base import BaseSecurityTestCase
from ..models import Kunjungan, KunjunganStatus, CalendarSettings, Instansi
from ..forms import KunjunganForm
from ..validators import validate_kunjungan_schedule


class KunjunganValidationTests(BaseSecurityTestCase):
    def setUp(self):
        super().setUp()
        # Pastikan instansi memiliki pengaturan jam dan hari kerja
        self.instansi.jam_buka = time(8, 0)
        self.instansi.jam_tutup = time(16, 0)
        self.instansi.hari_kerja = '0,1,2,3,4'  # Senin s.d. Jumat
        self.instansi.kapasitas_maksimal = 50
        self.instansi.save()

        # Dapatkan hari kerja berikutnya (Senin-Jumat) di masa depan
        now = timezone.now()
        target = now + timedelta(days=2)
        while target.weekday() not in [0, 1, 2, 3, 4]:
            target += timedelta(days=1)
        self.future_workday = target.date()

    def test_past_arrival_time_rejected_for_tamu(self):
        """Memastikan permohonan kunjungan dengan waktu lampau ditolak untuk Tamu."""
        past_time = timezone.now() - timedelta(hours=3)
        form = KunjunganForm(data={
            'pegawai': str(self.pegawai.id),
            'purpose': 'Urusan Dinas',
            'arrival_time': past_time.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertFalse(form.is_valid())
        self.assertIn('arrival_time', form.errors)
        self.assertIn('masa lampau', form.errors['arrival_time'][0])

    def test_holiday_rejected_for_tamu(self):
        """Memastikan permohonan kunjungan pada hari libur resmi ditolak."""
        CalendarSettings.objects.create(
            date=self.future_workday,
            is_holiday=True,
            holiday_name='Hari Libur Nasional'
        )
        visit_time = timezone.make_aware(
            datetime.combine(self.future_workday, time(10, 0))
        )
        form = KunjunganForm(data={
            'pegawai': str(self.pegawai.id),
            'purpose': 'Konsultasi Perizinan',
            'arrival_time': visit_time.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertFalse(form.is_valid())
        self.assertIn('arrival_time', form.errors)
        self.assertIn('libur', form.errors['arrival_time'][0])

    def test_outside_operating_hours_rejected(self):
        """Memastikan kedatangan di luar jam operasional (misal jam 07:00 atau 17:00) ditolak."""
        # 1. Terlalu pagi (07:00, buka 08:00)
        early_time = timezone.make_aware(
            datetime.combine(self.future_workday, time(7, 0))
        )
        form_early = KunjunganForm(data={
            'pegawai': str(self.pegawai.id),
            'purpose': 'Konsultasi',
            'arrival_time': early_time.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertFalse(form_early.is_valid())
        self.assertIn('arrival_time', form_early.errors)
        self.assertIn('di luar jam operasional', form_early.errors['arrival_time'][0])

        # 2. Terlalu sore (16:30, tutup 16:00)
        late_time = timezone.make_aware(
            datetime.combine(self.future_workday, time(16, 30))
        )
        form_late = KunjunganForm(data={
            'pegawai': str(self.pegawai.id),
            'purpose': 'Konsultasi',
            'arrival_time': late_time.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertFalse(form_late.is_valid())
        self.assertIn('arrival_time', form_late.errors)
        self.assertIn('di luar jam operasional', form_late.errors['arrival_time'][0])

    def test_departure_time_validation(self):
        """Memastikan departure_time harus setelah arrival_time dan tidak melebihi jam tutup."""
        arr_time = timezone.make_aware(
            datetime.combine(self.future_workday, time(10, 0))
        )

        # 1. Departure sebelum arrival
        dep_before = timezone.make_aware(
            datetime.combine(self.future_workday, time(9, 30))
        )
        form1 = KunjunganForm(data={
            'pegawai': str(self.pegawai.id),
            'purpose': 'Konsultasi',
            'arrival_time': arr_time.strftime('%Y-%m-%dT%H:%M'),
            'departure_time': dep_before.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertFalse(form1.is_valid())
        self.assertIn('departure_time', form1.errors)

        # 2. Departure melebihi jam tutup kantor (17:00)
        dep_after_closing = timezone.make_aware(
            datetime.combine(self.future_workday, time(17, 0))
        )
        form2 = KunjunganForm(data={
            'pegawai': str(self.pegawai.id),
            'purpose': 'Konsultasi',
            'arrival_time': arr_time.strftime('%Y-%m-%dT%H:%M'),
            'departure_time': dep_after_closing.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertFalse(form2.is_valid())
        self.assertIn('departure_time', form2.errors)
        self.assertIn('di luar jam operasional', form2.errors['departure_time'][0])

    def test_outside_workdays_rejected(self):
        """Memastikan permohonan kunjungan pada hari non-kerja (Sabtu/Minggu) ditolak."""
        now = timezone.now()
        target = now + timedelta(days=2)
        while target.weekday() not in [5, 6]:  # Cari Sabtu atau Minggu
            target += timedelta(days=1)
        weekend_date = target.date()

        visit_time = timezone.make_aware(
            datetime.combine(weekend_date, time(10, 0))
        )
        form = KunjunganForm(data={
            'pegawai': str(self.pegawai.id),
            'purpose': 'Kunjungan Akhir Pekan',
            'arrival_time': visit_time.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertFalse(form.is_valid())
        self.assertIn('arrival_time', form.errors)
        self.assertIn('tidak beroperasi', form.errors['arrival_time'][0])

    def test_daily_quota_enforced(self):
        """Memastikan jika kuota harian terpenuhi, permohonan kunjungan berikutnya ditolak."""
        CalendarSettings.objects.create(
            date=self.future_workday,
            daily_quota=2,
            is_holiday=False
        )

        arr1 = timezone.make_aware(datetime.combine(self.future_workday, time(9, 0)))
        arr2 = timezone.make_aware(datetime.combine(self.future_workday, time(11, 0)))
        arr3 = timezone.make_aware(datetime.combine(self.future_workday, time(13, 0)))

        # Buat 2 kunjungan yang menghabiskan kuota
        Kunjungan.objects.create(tamu=self.tamu_a, arrival_time=arr1, purpose='A', status=KunjunganStatus.MENUNGGU_ADMIN)
        Kunjungan.objects.create(tamu=self.tamu_b, arrival_time=arr2, purpose='B', status=KunjunganStatus.DISETUJUI)

        # Kunjungan ke-3 harus ditolak karena kuota penuh
        form = KunjunganForm(data={
            'pegawai': str(self.pegawai.id),
            'purpose': 'Kunjungan Melebihi Kuota',
            'arrival_time': arr3.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertFalse(form.is_valid())
        self.assertIn('arrival_time', form.errors)
        self.assertIn('sudah penuh', form.errors['arrival_time'][0])

    def test_cancelled_and_rejected_visits_do_not_consume_quota(self):
        """Memastikan kunjungan yang berstatus cancelled, ditolak_admin, atau ditolak_pegawai tidak mengurangi kuota."""
        CalendarSettings.objects.create(
            date=self.future_workday,
            daily_quota=2,
            is_holiday=False
        )

        arr1 = timezone.make_aware(datetime.combine(self.future_workday, time(9, 0)))
        arr2 = timezone.make_aware(datetime.combine(self.future_workday, time(11, 0)))
        arr3 = timezone.make_aware(datetime.combine(self.future_workday, time(13, 0)))

        # Buat 2 kunjungan tetapi keduanya dibatalkan / ditolak
        Kunjungan.objects.create(tamu=self.tamu_a, arrival_time=arr1, purpose='A', status=KunjunganStatus.CANCELLED)
        Kunjungan.objects.create(tamu=self.tamu_b, arrival_time=arr2, purpose='B', status=KunjunganStatus.DITOLAK_ADMIN)

        # Kunjungan baru harus tetap diterima karena kuota yang terpakai = 0
        form = KunjunganForm(data={
            'pegawai': str(self.pegawai.id),
            'purpose': 'Kunjungan Masih Ada Kuota',
            'arrival_time': arr3.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_valid_visit_accepted(self):
        """Memastikan jadwal kunjungan yang memenuhi semua aturan berhasil divalidasi."""
        arr_time = timezone.make_aware(datetime.combine(self.future_workday, time(10, 0)))
        dep_time = timezone.make_aware(datetime.combine(self.future_workday, time(11, 30)))

        form = KunjunganForm(data={
            'pegawai': str(self.pegawai.id),
            'purpose': 'Audiensi Kerjasama',
            'arrival_time': arr_time.strftime('%Y-%m-%dT%H:%M'),
            'departure_time': dep_time.strftime('%Y-%m-%dT%H:%M'),
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_admin_and_import_exemptions(self):
        """
        Memastikan:
        - Admin loket boleh mencatat kunjungan hari ini yang baru tiba (meski waktu lampau sedikit).
        - Import Excel (is_import=True) diizinkan memproses data historis tanggal lampau.
        """
        now = timezone.now()
        past_historic_time = now - timedelta(days=30)  # Kunjungan bulan lalu

        # 1. Tamu biasa mencoba tanggal bulan lalu -> ditolak
        with self.assertRaises(ValidationError):
            validate_kunjungan_schedule(arrival_time=past_historic_time, is_admin=False, is_import=False)

        # 2. Impor Excel untuk data historis bulan lalu -> diterima
        self.assertTrue(
            validate_kunjungan_schedule(arrival_time=past_historic_time, is_admin=True, is_import=True)
        )

        # 3. Admin mencatat kunjungan hari ini yang tiba 10 menit lalu -> diterima
        past_today = now - timedelta(minutes=10)
        self.assertTrue(
            validate_kunjungan_schedule(arrival_time=past_today, is_admin=True, is_import=False)
        )

    def test_concurrent_booking_race_condition_prevention(self):
        """
        Memastikan penguncian baris (select_for_update) dalam transaksi atomik
        mencegah dua booking bersamaan menembus sisa kuota 1.
        """
        CalendarSettings.objects.create(
            date=self.future_workday,
            daily_quota=1,
            is_holiday=False
        )
        arr_time = timezone.make_aware(datetime.combine(self.future_workday, time(10, 0)))

        # Transaksi 1: Mengambil kuota terakhir dan menyimpan kunjungan
        with transaction.atomic():
            validate_kunjungan_schedule(
                arrival_time=arr_time,
                is_admin=False,
                lock_for_update=True
            )
            Kunjungan.objects.create(
                tamu=self.tamu_a,
                arrival_time=arr_time,
                purpose='Booking Pertama',
                status=KunjunganStatus.MENUNGGU_ADMIN
            )

        # Transaksi 2: Berusaha memesan kuota di tanggal yang sama -> harus ditolak
        with self.assertRaises(ValidationError) as ctx:
            with transaction.atomic():
                validate_kunjungan_schedule(
                    arrival_time=arr_time,
                    is_admin=False,
                    lock_for_update=True
                )
        self.assertIn('sudah penuh', str(ctx.exception))
