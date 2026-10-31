"""
guest_book/validators.py
Fungsi validasi jadwal kunjungan terpusat (Centralized Visit Scheduling Validator).
Dipakai oleh:
- KunjunganForm.clean() (guest_book/forms.py)
- kunjungan_baru_view (guest_book/views/tamu.py)
- admin_kunjungan_manual_create (guest_book/views/admin_kunjungan.py)
- api_quick_checkin (guest_book/views/api_admin.py)
- api_import_excel_kunjungan (guest_book/views/api_admin.py)
"""

from datetime import datetime, time, timedelta, date as dt_date
import zoneinfo
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
from django.db.models import Count
from django.db.models.functions import TruncDate

from .models import Instansi, CalendarSettings, Kunjungan, KunjunganStatus


JAKARTA_TZ = zoneinfo.ZoneInfo('Asia/Jakarta')

# Status kunjungan yang aktif menggunakan kuota harian.
# Kunjungan berstatus cancelled, ditolak_admin, dan ditolak_pegawai TIDAK dihitung.
ACTIVE_QUOTA_STATUSES = [
    KunjunganStatus.MENUNGGU_ADMIN,
    KunjunganStatus.MENUNGGU_PEGAWAI,
    KunjunganStatus.DISETUJUI_PEGAWAI,
    KunjunganStatus.DISETUJUI,
    KunjunganStatus.IN_PROGRESS,
    KunjunganStatus.COMPLETED,
]


def get_day_range_aware(visit_date):
    """
    Menghasilkan (start_of_day, start_of_next_day) sebagai datetime aware di zona Asia/Jakarta.
    Gunakan arrival_time__gte=start_of_day dan arrival_time__lt=start_of_next_day
    agar kueri memanfaatkan index B-Tree tanpa celah microsecond.
    """
    if isinstance(visit_date, str):
        visit_date = datetime.strptime(visit_date.strip(), '%Y-%m-%d').date()
    elif isinstance(visit_date, datetime):
        visit_date = timezone.localtime(visit_date, JAKARTA_TZ).date()

    start_of_day = datetime.combine(visit_date, time.min, tzinfo=JAKARTA_TZ)
    start_of_next_day = start_of_day + timedelta(days=1)
    return start_of_day, start_of_next_day


def get_default_holiday_status(visit_date):
    """
    Mengecek status libur bawaan (real-time Google Calendar / Kalender Indonesia & Akhir Pekan)
    jika belum ada override manual admin di CalendarSettings.
    Returns: (is_holiday: bool, holiday_name: str)
    """
    from .utils import get_google_calendar_holidays

    if isinstance(visit_date, str):
        visit_date = datetime.strptime(visit_date.strip(), '%Y-%m-%d').date()
    elif isinstance(visit_date, datetime):
        visit_date = timezone.localtime(visit_date, JAKARTA_TZ).date()

    # 1. Cek Hari Libur Nasional Indonesia (Google Calendar / Resmi)
    year_holidays = get_google_calendar_holidays(visit_date.year) or []
    holidays_map = {h['date']: h['name'] for h in year_holidays}
    date_iso = visit_date.isoformat()
    if date_iso in holidays_map:
        return True, holidays_map[date_iso]

    # 2. Cek Akhir Pekan & Hari Kerja Operasional Instansi
    instansi = Instansi.objects.first()
    hari_kerja_raw = instansi.hari_kerja if instansi and instansi.hari_kerja else '0,1,2,3,4'
    try:
        hari_kerja_list = [int(h.strip()) for h in hari_kerja_raw.split(',') if h.strip().isdigit()]
    except Exception:
        hari_kerja_list = [0, 1, 2, 3, 4]

    if visit_date.weekday() not in hari_kerja_list:
        if visit_date.weekday() == 5:
            return True, 'Libur Akhir Pekan (Sabtu)'
        elif visit_date.weekday() == 6:
            return True, 'Libur Akhir Pekan (Minggu)'
        else:
            return True, 'Di Luar Hari Operasional Instansi'

    return False, ''


def get_daily_quota_info(visit_date, exclude_kunjungan_id=None):
    """
    Fungsi pusat untuk menghitung kuota dan status kunjungan harian.
    Dipakai oleh api_check_quota, validate_kunjungan_schedule, dan form validasi.

    Returns dict:
        {
            'date': visit_date (date),
            'quota': int,
            'booked': int,
            'available': int,
            'is_holiday': bool,
            'holiday_name': str,
            'is_full': bool,
        }
    """
    if isinstance(visit_date, str):
        visit_date = datetime.strptime(visit_date.strip(), '%Y-%m-%d').date()
    elif isinstance(visit_date, datetime):
        visit_date = timezone.localtime(visit_date, JAKARTA_TZ).date()

    setting = CalendarSettings.objects.filter(date=visit_date).first()
    instansi = Instansi.objects.first()
    quota = setting.daily_quota if setting else (
        instansi.kapasitas_maksimal if instansi and instansi.kapasitas_maksimal else 50
    )

    default_is_holiday, default_holiday_name = get_default_holiday_status(visit_date)

    if setting is not None:
        is_holiday = bool(setting.is_holiday)
        holiday_name = setting.holiday_name or (default_holiday_name if is_holiday else '')
    else:
        is_holiday = default_is_holiday
        holiday_name = default_holiday_name

    start_of_day, start_of_next_day = get_day_range_aware(visit_date)
    booked_qs = Kunjungan.objects.filter(
        arrival_time__gte=start_of_day,
        arrival_time__lt=start_of_next_day,
        status__in=ACTIVE_QUOTA_STATUSES
    )
    if exclude_kunjungan_id:
        booked_qs = booked_qs.exclude(pk=exclude_kunjungan_id)

    booked = booked_qs.count()
    available = max(0, quota - booked) if not is_holiday else 0
    is_full = (booked >= quota) or is_holiday

    return {
        'date': visit_date,
        'quota': quota,
        'booked': booked,
        'available': available,
        'is_holiday': is_holiday,
        'holiday_name': holiday_name,
        'is_full': is_full,
    }


def get_monthly_quota_usage(year, month):
    """
    Mengambil jumlah kunjungan aktif (ACTIVE_QUOTA_STATUSES) per hari untuk 1 bulan penuh
    menggunakan SATU kueri tunggal terindeks tanpa memicu N+1.
    Toleran terhadap database yang belum memuat tabel nama zona waktu MySQL.

    Returns: dict {day_number (int): booked_count (int)}
    """
    start_of_month = datetime(year, month, 1, 0, 0, 0, tzinfo=JAKARTA_TZ)
    if month == 12:
        start_of_next_month = datetime(year + 1, 1, 1, 0, 0, 0, tzinfo=JAKARTA_TZ)
    else:
        start_of_next_month = datetime(year, month + 1, 1, 0, 0, 0, tzinfo=JAKARTA_TZ)

    # 1 kueri tunggal terindeks yang hanya mengambil kolom arrival_time
    arrival_times = (
        Kunjungan.objects
        .filter(
            arrival_time__gte=start_of_month,
            arrival_time__lt=start_of_next_month,
            status__in=ACTIVE_QUOTA_STATUSES
        )
        .values_list('arrival_time', flat=True)
    )

    result = {}
    for dt in arrival_times:
        if dt:
            local_day = timezone.localtime(dt, JAKARTA_TZ).day
            result[local_day] = result.get(local_day, 0) + 1
    return result


def make_aware_if_naive(dt):
    """Memastikan objek datetime timezone-aware."""
    if dt is None:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def validate_kunjungan_schedule(
    arrival_time,
    departure_time=None,
    instance=None,
    is_admin=False,
    is_import=False,
    lock_for_update=False
):
    """
    Validasi terpusat untuk jadwal kunjungan buku tamu digital.

    Aturan:
    1. Waktu kedatangan tidak boleh di masa lampau (dengan toleransi 5 menit untuk Tamu).
       Dikecualikan untuk import data historis atau Admin yang mencatat kunjungan langsung hari ini.
    2. Waktu selesai harus setelah waktu kedatangan (departure_time > arrival_time).
    3. Jam operasional: arrival_time dan departure_time harus dalam rentang jam_buka s.d. jam_tutup instansi.
    4. Hari kerja: hari kunjungan harus terdaftar dalam hari_kerja instansi (jika dikonfigurasi).
    5. Hari libur: tanggal kunjungan tidak boleh berstatus is_holiday di CalendarSettings.
    6. Kuota harian: jumlah kunjungan aktif (ACTIVE_QUOTA_STATUSES) pada tanggal terkait belum melebihi daily_quota.
       Mendukung row-level locking (select_for_update) untuk mencegah race condition.

    Raises:
        ValidationError: jika ada pelanggaran aturan jadwal.
    """
    if not arrival_time:
        raise ValidationError({'arrival_time': "Waktu kedatangan wajib diisi."})

    arrival_time = make_aware_if_naive(arrival_time)
    departure_time = make_aware_if_naive(departure_time)

    now = timezone.now()
    arrival_local = timezone.localtime(arrival_time)
    visit_date = arrival_local.date()

    # ── 1. Validasi Waktu Lampau ──────────────────────────────────────────────
    if not is_import:
        # Untuk Tamu: kedatangan tidak boleh di masa lampau (diberi toleransi 5 menit jeda submit form)
        if not is_admin:
            if arrival_time < (now - timedelta(minutes=5)):
                raise ValidationError({
                    'arrival_time': "Waktu kedatangan tidak boleh di masa lampau."
                })
        else:
            # Untuk Admin di loket: kunjungan masa lampau hanya diizinkan untuk hari yang sama (misal tamu baru selesai)
            # Jika tanggal kunjungan sebelum hari ini, tolak jika bukan impor
            today_local = timezone.localtime(now).date()
            if visit_date < today_local:
                raise ValidationError({
                    'arrival_time': "Tanggal kunjungan sudah lewat."
                })

    # ── 2. Validasi Urutan Waktu Kedatangan & Pulang ──────────────────────────
    if arrival_time and departure_time:
        if departure_time <= arrival_time:
            raise ValidationError({
                'departure_time': "Waktu pulang harus setelah waktu kedatangan."
            })

    # Ambil pengaturan instansi
    instansi = Instansi.objects.first()
    jam_buka = instansi.jam_buka if instansi and instansi.jam_buka else time(8, 0)
    jam_tutup = instansi.jam_tutup if instansi and instansi.jam_tutup else time(16, 0)
    hari_kerja_raw = instansi.hari_kerja if instansi and instansi.hari_kerja else '0,1,2,3,4'

    buka_str = jam_buka.strftime('%H:%M')
    tutup_str = jam_tutup.strftime('%H:%M')

    # ── 3. Validasi Hari Kerja & Jam Operasional ──────────────────────────────
    if not is_import and not is_admin:
        # Hari kerja (0=Senin, 1=Selasa, ..., 6=Minggu)
        try:
            hari_kerja_list = [int(h.strip()) for h in hari_kerja_raw.split(',') if h.strip().isdigit()]
        except Exception:
            hari_kerja_list = [0, 1, 2, 3, 4]

        if arrival_local.weekday() not in hari_kerja_list:
            raise ValidationError({
                'arrival_time': "Instansi tidak beroperasi pada hari tersebut."
            })

        # Jam operasional kedatangan
        arr_time = arrival_local.time()
        if arr_time < jam_buka or arr_time > jam_tutup:
            raise ValidationError({
                'arrival_time': f"Jam kedatangan di luar jam operasional ({buka_str} - {tutup_str})."
            })

        # Jam operasional kepulangan (jika diisi)
        if departure_time:
            dep_local = timezone.localtime(departure_time)
            dep_time = dep_local.time()
            if dep_time > jam_tutup or dep_time < jam_buka:
                raise ValidationError({
                    'departure_time': f"Perkiraan waktu pulang di luar jam operasional ({buka_str} - {tutup_str})."
                })

    # ── 4. Validasi Hari Libur (CalendarSettings, Kalender Indonesia, Akhir Pekan) ──
    default_is_holiday, default_h_name = get_default_holiday_status(visit_date)
    calendar_setting = None
    if lock_for_update and transaction.get_connection().in_atomic_block:
        calendar_setting, _ = CalendarSettings.objects.select_for_update().get_or_create(
            date=visit_date,
            defaults={
                'daily_quota': instansi.kapasitas_maksimal if instansi and instansi.kapasitas_maksimal else 50,
                'is_holiday': default_is_holiday,
                'holiday_name': default_h_name,
            }
        )
    else:
        calendar_setting = CalendarSettings.objects.filter(date=visit_date).first()

    if not is_import and not is_admin:
        quota_info = get_daily_quota_info(visit_date)
        if quota_info['is_holiday']:
            holiday_name = quota_info['holiday_name'] or "Hari Libur Resmi"
            raise ValidationError({
                'arrival_time': f"Instansi libur pada tanggal tersebut ({holiday_name})."
            })

    # ── 5. Validasi Kuota Harian ──────────────────────────────────────────────
    daily_quota = calendar_setting.daily_quota if calendar_setting else (
        instansi.kapasitas_maksimal if instansi and instansi.kapasitas_maksimal else 50
    )

    # Hitung jumlah kunjungan yang sedang/sudah memakai kuota pada tanggal ini
    start_of_day, start_of_next_day = get_day_range_aware(visit_date)

    booked_qs = Kunjungan.objects.filter(
        arrival_time__gte=start_of_day,
        arrival_time__lt=start_of_next_day,
        status__in=ACTIVE_QUOTA_STATUSES
    )
    if instance and getattr(instance, 'pk', None):
        booked_qs = booked_qs.exclude(pk=instance.pk)

    booked_count = booked_qs.count()

    if not is_import and booked_count >= daily_quota:
        raise ValidationError({
            'arrival_time': f"Kuota kunjungan pada tanggal tersebut sudah penuh (maksimal {daily_quota} orang)."
        })

    return True
