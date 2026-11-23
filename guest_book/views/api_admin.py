"""
API Views — Kalender, Kunjungan (quick checkin, quota, import), Debug, Profil, Webhook
"""
import json
import logging
from datetime import datetime
from functools import wraps

from django.conf import settings as dj_settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.contrib.auth.hashers import make_password

from .base import (
    admin_login_required, tamu_login_required,
    check_is_admin, check_is_super_admin, clamp_page_size,
)
from ..models import Notification, Kunjungan, Tamu, CalendarSettings

logger = logging.getLogger(__name__)


def _debug_endpoint_disabled_in_prod(view_func):
    """Menonaktifkan endpoint debug sepenuhnya saat settings.DEBUG=False."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not getattr(dj_settings, 'DEBUG', False):
            return JsonResponse({'success': False, 'error': 'Not found'}, status=404)
        return view_func(request, *args, **kwargs)
    return wrapper


# ── Kalender ──────────────────────────────────────────────────────────────────

@admin_login_required
def api_update_quota(request):
    """Update kuota harian kalender dengan validasi tanggal dan rentang kuota."""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            if not isinstance(data, dict):
                return JsonResponse({'error': 'Payload tidak valid.'}, status=400)
            date_str = str(data.get('date') or '').strip()
            if not date_str:
                return JsonResponse({'error': 'Parameter tanggal wajib diisi.'}, status=400)
            parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()

            quota = data.get('quota')
            parsed_quota = None
            if quota is not None:
                if isinstance(quota, bool):
                    return JsonResponse({'error': 'Kuota harian harus berupa angka bulat.'}, status=400)
                parsed_quota = int(quota)
                if parsed_quota < 0 or parsed_quota > 5000:
                    return JsonResponse({'error': 'Kuota harian harus berada dalam rentang 0 hingga 5000.'}, status=400)

            is_holiday = data.get('is_holiday')
            holiday_name = data.get('holiday_name')

            setting, _ = CalendarSettings.objects.get_or_create(date=parsed_date)
            if parsed_quota is not None:
                setting.daily_quota = parsed_quota
            if is_holiday is not None:
                setting.is_holiday = bool(is_holiday)
            if holiday_name is not None:
                setting.holiday_name = str(holiday_name).strip()[:255]
            setting.save()
            return JsonResponse({'success': True})
        except (ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({'error': 'Format tanggal atau kuota tidak valid.'}, status=400)
        except Exception:
            logger.exception("Gagal memperbarui kuota kalender")
            return JsonResponse({'error': 'Gagal memperbarui kuota kalender.'}, status=500)
    return JsonResponse({'error': 'Invalid method'}, status=405)


@admin_login_required
def api_toggle_holiday(request):
    """Toggle status libur pada tanggal tertentu"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            date_str = data.get('date')
            if not date_str:
                return JsonResponse({'error': 'Parameter date diperlukan.'}, status=400)

            from ..validators import get_daily_quota_info
            current_info = get_daily_quota_info(date_str)
            effective_is_holiday = current_info['is_holiday']

            setting, _ = CalendarSettings.objects.get_or_create(date=date_str)
            setting.is_holiday = not effective_is_holiday
            if setting.is_holiday:
                setting.holiday_name = data.get('holiday_name') or current_info.get('holiday_name') or 'Hari Libur / Tutup'
            else:
                setting.holiday_name = ''
            setting.save()
            return JsonResponse({'success': True, 'is_holiday': setting.is_holiday, 'holiday_name': setting.holiday_name})
        except (ValueError, TypeError, json.JSONDecodeError):
            return JsonResponse({'error': 'Format tanggal atau permintaan tidak valid.'}, status=400)
        except Exception:
            logger.exception("Gagal mengubah status hari libur")
            return JsonResponse({'error': 'Gagal mengubah status hari libur.'}, status=500)
    return JsonResponse({'error': 'Invalid method'}, status=405)


@admin_login_required
def api_import_calendar_csv(request):
    """Import data kalender dari Excel/CSV dengan validasi ukuran, magic bytes, dan batas baris."""
    import pandas as pd
    from django.contrib import messages as dj_messages
    from django.db import transaction
    from ..utils import validate_uploaded_file

    if request.method != 'POST' or not request.FILES.get('file'):
        dj_messages.error(request, 'File tidak ditemukan atau metode tidak valid.')
        return JsonResponse({'error': 'File tidak ditemukan'}, status=400)

    file = request.FILES['file']
    max_import_bytes = 5 * 1024 * 1024
    if file.size > max_import_bytes:
        dj_messages.error(request, 'Ukuran file melebihi batas maksimum 5 MB.')
        return JsonResponse({'error': 'Ukuran file melebihi batas maksimum 5 MB.'}, status=400)

    filename = (file.name or '').lower()

    try:
        if filename.endswith('.csv'):
            sample = file.read(4096)
            file.seek(0)
            if b'\x00' in sample:
                dj_messages.error(request, 'File CSV tidak valid (terdeteksi data biner).')
                return JsonResponse({'error': 'File CSV tidak valid.'}, status=400)
            df = pd.read_csv(file, sep=None, engine='python')
        elif filename.endswith(('.xlsx', '.xls')):
            is_valid, err_msg, _ = validate_uploaded_file(
                file,
                max_size_bytes=max_import_bytes,
                allowed_extensions=['xlsx', 'xls'],
            )
            if not is_valid:
                dj_messages.error(request, err_msg)
                return JsonResponse({'error': err_msg}, status=400)
            df = pd.read_excel(file)
        else:
            dj_messages.error(request, 'Format file tidak didukung. Harap gunakan .csv, .xlsx, atau .xls.')
            return JsonResponse({'error': 'Format file tidak didukung'}, status=400)

        if len(df) > 500:
            dj_messages.error(request, 'File melebihi batas maksimum 500 baris dalam satu kali impor.')
            return JsonResponse({'error': 'File melebihi batas maksimum 500 baris dalam satu kali impor.'}, status=400)

        expected_cols = ['tanggal', 'date']
        columns_lower = [str(c).lower().strip() for c in df.columns]
        has_date = any(col in columns_lower for col in expected_cols)

        if has_date:
            df.columns = columns_lower
        elif len(df) > 0:
            first_row = [str(c).lower().strip() for c in df.iloc[0]]
            if any(col in first_row for col in expected_cols):
                df.columns = first_row
                df = df.iloc[1:]
            else:
                dj_messages.error(request, 'Kolom Tanggal tidak ditemukan dalam file.')
                return JsonResponse({'error': 'Kolom Tanggal tidak ditemukan'}, status=400)
        else:
            dj_messages.error(request, 'File kosong.')
            return JsonResponse({'error': 'File kosong'}, status=400)

        success_count = 0
        errors = []

        with transaction.atomic():
            for i, row in df.iterrows():
                date_val = row.get('tanggal') or row.get('date')
                quota = row.get('kuota') or row.get('quota') or 50
                libur_raw = str(row.get('libur') or 'tidak').lower()
                is_holiday = libur_raw in ['ya', 'yes', '1', 'true']
                holiday_name = row.get('nama_libur') or row.get('keterangan libur') or row.get('keterangan_libur') or ''

                if pd.notna(date_val) and str(date_val).strip() != '':
                    try:
                        dt = pd.to_datetime(date_val).date()
                        parsed_quota = int(float(quota)) if pd.notna(quota) and str(quota).strip() != '' else 50
                        if parsed_quota < 0 or parsed_quota > 5000:
                            raise ValueError('Kuota di luar rentang 0..5000')
                        setting, _ = CalendarSettings.objects.get_or_create(date=dt)
                        setting.daily_quota = parsed_quota
                        setting.is_holiday = is_holiday
                        setting.holiday_name = str(holiday_name).strip()[:255] if pd.notna(holiday_name) else ''
                        setting.save()
                        success_count += 1
                    except Exception as e:
                        logger.warning("Gagal mengimpor baris kalender index %s: %s", i, e)
                        errors.append(f"Baris index {i}: format tanggal atau kuota tidak valid")
                        continue

        msg = f'{success_count} data berhasil diimpor.'
        if errors:
            msg += f' Terdapat {len(errors)} baris gagal. Contoh error: {errors[0]}'

        dj_messages.success(request, msg)
        return JsonResponse({'success': True, 'message': msg})

    except Exception:
        logger.exception("Fatal error saat import kalender")
        return JsonResponse({'error': 'Gagal memproses file kalender. Pastikan format file valid.'}, status=400)


def api_google_holidays(request, year):
    """Ambil data libur nasional (Publik, dengan validasi rentang tahun & rate limit)."""
    from .auth import check_rate_limit, get_client_ip, record_rate_limit_attempt
    from ..utils import get_google_calendar_holidays

    try:
        year_int = int(year)
    except (ValueError, TypeError):
        return JsonResponse({'success': False, 'error': 'Parameter tahun tidak valid.'}, status=400)

    if not (2000 <= year_int <= 2100):
        return JsonResponse(
            {'success': False, 'error': 'Tahun harus berada dalam rentang 2000 hingga 2100.'},
            status=400,
        )

    client_ip = get_client_ip(request)
    rl_key = f"rl_google_holidays_{client_ip}"
    if check_rate_limit(rl_key, max_attempts=30, fail_closed=False):
        return JsonResponse(
            {'success': False, 'error': 'Terlalu banyak permintaan. Silakan coba lagi sebentar lagi.'},
            status=429,
        )
    record_rate_limit_attempt(rl_key, timeout_seconds=60)

    holidays = get_google_calendar_holidays(year_int)
    if not holidays:
        holidays = [{'date': f'{year_int}-01-01', 'name': 'Tahun Baru (Fallback)'}]
    return JsonResponse({'year': year_int, 'holidays': holidays})


def api_check_quota(request):
    """Cek kuota kunjungan pada tanggal tertentu (Akses Publik/Tamu)"""
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'success': False, 'error': 'Tanggal wajib diisi'}, status=400)

    try:
        from ..validators import get_daily_quota_info
        info = get_daily_quota_info(date_str)

        return JsonResponse({
            'success': True,
            'quota': info['quota'],
            'booked': info['booked'],
            'is_holiday': info['is_holiday'],
            'holiday_name': info['holiday_name'],
            'available': info['available'],
            'is_full': info['is_full'],
        })
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Format tanggal tidak valid.'}, status=400)
    except Exception:
        logger.exception("Gagal memeriksa kuota kalender untuk tanggal %s", date_str)
        return JsonResponse({'success': False, 'error': 'Gagal memeriksa kuota kunjungan.'}, status=500)


# ── Kunjungan ─────────────────────────────────────────────────────────────────

@admin_login_required
def api_quick_checkin(request):
    """Pendaftaran tamu cepat dari dashboard admin dengan validasi ketat & transaksi atomik"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    is_admin, admin_id = check_is_admin(request)
    if not is_admin:
        return JsonResponse({'success': False, 'error': 'Akses khusus Administrator.'}, status=403)

    try:
        try:
            data = json.loads(request.body or b'{}')
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({'success': False, 'error': 'Payload JSON tidak valid.'}, status=400)

        if not isinstance(data, dict):
            return JsonResponse({'success': False, 'error': 'Format data tidak valid.'}, status=400)

        # 1. Validasi Nama (Wajib, 2 s.d. 100 karakter)
        raw_name = data.get('name')
        if not isinstance(raw_name, str) or not raw_name.strip():
            return JsonResponse({'success': False, 'error': 'Nama tamu wajib diisi.'}, status=400)
        clean_name = raw_name.strip()[:100]
        if len(clean_name) < 2:
            return JsonResponse({'success': False, 'error': 'Nama tamu minimal 2 karakter.'}, status=400)

        # 2. Validasi NIK jika diisi (harus tepat 16 digit angka)
        raw_nik = data.get('nik')
        clean_nik = None
        if raw_nik is not None and str(raw_nik).strip():
            candidate_nik = str(raw_nik).strip()
            if not candidate_nik.isdigit() or len(candidate_nik) != 16:
                return JsonResponse({'success': False, 'error': 'NIK harus tepat 16 digit angka.'}, status=400)
            clean_nik = candidate_nik

        # 3. Validasi No. Telepon jika diisi (8 s.d. 15 digit angka)
        raw_phone = data.get('phone')
        clean_phone = None
        if raw_phone is not None and str(raw_phone).strip():
            candidate_phone = str(raw_phone).strip()
            digits_only = ''.join(c for c in candidate_phone if c.isdigit())
            if len(digits_only) < 8 or len(digits_only) > 15:
                return JsonResponse({'success': False, 'error': 'Nomor telepon harus antara 8 hingga 15 digit angka.'}, status=400)
            clean_phone = candidate_phone[:20]

        # 4. Instansi & Keperluan
        clean_instansi = str(data.get('instansi') or '').strip()[:255]
        clean_purpose = str(data.get('purpose') or 'Kunjungan Mendadak').strip()[:500]
        if not clean_purpose:
            clean_purpose = 'Kunjungan Mendadak'

        # 5. Tanggal & Waktu Kedatangan
        from ..validators import JAKARTA_TZ
        date_str = str(data.get('date') or timezone.localtime(timezone.now(), JAKARTA_TZ).date().isoformat()).strip()
        time_str = str(data.get('time') or '09:00').strip()
        try:
            arrival_naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            arrival_dt = timezone.make_aware(arrival_naive, JAKARTA_TZ)
        except ValueError:
            return JsonResponse({'success': False, 'error': 'Format tanggal atau waktu tidak valid.'}, status=400)

        # 6. Status Kunjungan
        from ..models import KunjunganStatus
        raw_status = str(data.get('status') or 'in_progress').strip()
        if raw_status in ('pending', 'menunggu_admin'):
            target_status = KunjunganStatus.MENUNGGU_ADMIN
        elif raw_status == 'in_progress':
            target_status = KunjunganStatus.IN_PROGRESS
        else:
            target_status = KunjunganStatus.IN_PROGRESS

        # 7. Pegawai Tujuan jika diisi
        pegawai_id = data.get('pegawai_id')
        pegawai = None
        if pegawai_id:
            from ..models import Pegawai
            pegawai = Pegawai.objects.filter(id=pegawai_id, account_status='active').first()
            if not pegawai:
                return JsonResponse({'success': False, 'error': 'Pegawai yang dipilih tidak ditemukan atau non-aktif.'}, status=404)

        visit_id = data.get('visit_id')
        existing_kunjungan = None
        if visit_id:
            existing_kunjungan = Kunjungan.objects.filter(id=visit_id).first()
            if not existing_kunjungan:
                return JsonResponse({'success': False, 'error': 'Kunjungan tidak ditemukan.'}, status=404)

        # 8 & 9. Transaksi Atomik + Validasi Jadwal/Kuota Terkunci (select_for_update)
        import uuid
        from django.core.exceptions import ValidationError as DjangoValidationError
        from django.db import IntegrityError, transaction
        from ..validators import validate_kunjungan_schedule
        from ..workflow_engine import WorkflowEngine

        try:
            with transaction.atomic():
                validate_kunjungan_schedule(
                    arrival_time=arrival_dt,
                    instance=existing_kunjungan,
                    is_admin=True,
                    is_import=False,
                    lock_for_update=True,
                )

                # Aturan pencocokan Tamu:
                # 1. Jika NIK ada -> cari tamu aktif dengan NIK tersebut (tepat 1 match)
                # 2. Jika phone ada -> cari tamu aktif dengan phone tersebut (tepat 1 match)
                # 3. Jika tidak ada / tidak cocok -> buat Tamu baru mandiri (nama sama tidak tertukar)
                tamu = None
                if clean_nik:
                    nik_matches = list(Tamu.objects.filter(Tamu.nik_lookup_q(clean_nik), account_status='active')[:2])
                    if len(nik_matches) == 1:
                        tamu = nik_matches[0]
                elif clean_phone:
                    phone_matches = list(Tamu.objects.filter(phone=clean_phone, account_status='active')[:2])
                    if len(phone_matches) == 1:
                        tamu = phone_matches[0]

                if not tamu:
                    # Pembuatan Tamu baru dengan email dummy UUID penuh & anti-collision retry loop
                    created = False
                    for _ in range(3):
                        dummy_email = f"quick_{uuid.uuid4().hex}@guest.local"
                        try:
                            with transaction.atomic():
                                tamu = Tamu.objects.create(
                                    name=clean_name,
                                    email=dummy_email,
                                    instansi=clean_instansi,
                                    nik=clean_nik,
                                    phone=clean_phone or '',
                                    account_status='active',
                                    registration_type='manual'
                                )
                                created = True
                                break
                        except IntegrityError:
                            continue
                    if not created:
                        return JsonResponse({'success': False, 'error': 'Gagal membuat akun tamu unik. Silakan coba lagi.'}, status=500)

                # Buat atau Perbarui Kunjungan
                if existing_kunjungan:
                    kunjungan = existing_kunjungan
                    kunjungan.arrival_time = arrival_dt
                    kunjungan.purpose = clean_purpose
                    kunjungan.pegawai = pegawai
                    if clean_instansi and not kunjungan.tamu.instansi:
                        kunjungan.tamu.instansi = clean_instansi
                        kunjungan.tamu.save(update_fields=['instansi'])

                    if kunjungan.status != target_status:
                        engine = WorkflowEngine(kunjungan)
                        is_valid, _ = engine.can_transition(target_status, admin_id or 'admin', 'admin')
                        if is_valid:
                            engine.transition(target_status, admin_id or 'admin', 'admin', notes='Updated via quick checkin')
                        else:
                            kunjungan.status = target_status
                            kunjungan.save(update_fields=['status'])
                    kunjungan.save()
                else:
                    kunjungan = Kunjungan.objects.create(
                        tamu=tamu,
                        arrival_time=arrival_dt,
                        purpose=clean_purpose,
                        status=target_status,
                        pegawai=pegawai
                    )
        except DjangoValidationError as val_err:
            if hasattr(val_err, 'message_dict'):
                err_msg = '; '.join([f"{k}: {', '.join(v)}" for k, v in val_err.message_dict.items()])
            elif hasattr(val_err, 'message'):
                err_msg = val_err.message
            else:
                err_msg = str(val_err)
            return JsonResponse({'success': False, 'error': err_msg}, status=400)

        # Kirim notifikasi ke Pegawai jika kunjungan ditujukan ke pegawai (setelah transaksi commit)
        from ..utils import send_notification
        if pegawai:
            try:
                send_notification(
                    recipient_id=str(pegawai.id),
                    recipient_type='pegawai',
                    notification_type='visit_registered',
                    title='Ada Tamu untuk Anda!',
                    message=f'Tamu {tamu.name} dari {tamu.instansi or "-"} ingin menemui Anda.',
                    related_object_id=str(kunjungan.id)
                )
            except Exception as notif_err:
                logger.warning("Gagal mengirim notifikasi quick checkin ke pegawai: %s", notif_err)

        return JsonResponse({'success': True, 'kunjungan_id': str(kunjungan.id)})

    except Exception as e:
        logger.exception("Error pada api_quick_checkin: %s", str(e))
        return JsonResponse({'success': False, 'error': 'Terjadi kesalahan sistem saat memproses check-in.'}, status=500)


@admin_login_required
def api_get_visits_by_date(request):
    """Ambil daftar kunjungan berdasarkan tanggal"""
    date_str = request.GET.get('date')
    page = request.GET.get('page', 1)
    page_size = clamp_page_size(request.GET.get('page_size'), default=50, max_size=100)

    if not date_str:
        return JsonResponse({'success': False, 'error': 'Tanggal wajib diisi'}, status=400)

    try:
        from ..validators import get_day_range_aware
        start_day, next_day = get_day_range_aware(date_str)
        qs = (
            Kunjungan.objects
            .filter(arrival_time__gte=start_day, arrival_time__lt=next_day)
            .select_related('tamu')
            .order_by('arrival_time')
        )
        paginator = Paginator(qs, page_size)
        try:
            visits = paginator.page(page)
        except Exception:
            visits = paginator.page(1)

        data = [{'id': v.id, 'tamu_name': v.tamu.name if v.tamu else '-', 'instansi': v.tamu.instansi if v.tamu else '-', 'time': v.arrival_time.strftime('%H:%M'), 'status': v.status, 'purpose': v.purpose} for v in visits]
        return JsonResponse({'success': True, 'visits': data, 'pagination': {'has_next': visits.has_next(), 'has_previous': visits.has_previous(), 'current_page': visits.number, 'total_pages': paginator.num_pages, 'total_items': paginator.count}})
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Format tanggal tidak valid.'}, status=400)
    except Exception:
        logger.exception("Gagal mengambil daftar kunjungan untuk tanggal %s", date_str)
        return JsonResponse({'success': False, 'error': 'Gagal mengambil data kunjungan.'}, status=500)


@admin_login_required
def api_import_visits_excel(request):
    """Import data kunjungan dari Excel dengan validasi keamanan dan transaksi atomik"""
    if request.method == 'POST' and request.FILES.get('file'):
        file = request.FILES['file']

        # 1 & 2. Validasi ukuran (<=5MB), ekstensi (.xlsx/.xls), magic bytes & anti ZIP-bomb
        from ..utils import validate_uploaded_file
        is_valid, err_msg, _ = validate_uploaded_file(
            file,
            max_size_bytes=5 * 1024 * 1024,
            allowed_extensions=['xlsx', 'xls'],
        )
        if not is_valid:
            return JsonResponse({'error': err_msg}, status=400)

        try:
            import uuid
            import pandas as pd
            from django.core.exceptions import ValidationError as DjangoValidationError
            from django.core.validators import validate_email
            from django.db import transaction
            from ..validators import normalize_and_validate_phone, validate_kunjungan_schedule

            df = pd.read_excel(file)
            df.columns = [str(c).lower().strip() for c in df.columns]

            # 3. Batasi jumlah baris untuk mencegah DoS
            if len(df) > 500:
                return JsonResponse({'error': 'File melebihi batas maksimum 500 baris dalam satu kali impor.'}, status=400)

            required_cols = ['tanggal', 'nama tamu']
            if not all(col in df.columns for col in required_cols):
                return JsonResponse({'error': 'File harus memiliki kolom "Tanggal" dan "Nama Tamu"'}, status=400)

            success_count = 0
            with transaction.atomic():
                for _, row in df.iterrows():
                    date_val = row.get('tanggal')
                    nama_tamu = str(row.get('nama tamu') or row.get('nama') or '').strip()
                    instansi = str(row.get('instansi') or '').strip()
                    keperluan = str(row.get('keperluan') or row.get('tujuan') or 'Kunjungan').strip()
                    jam = str(row.get('jam') or '09:00').strip()
                    raw_nik = str(row.get('nik') or '').strip()
                    raw_email = str(row.get('email') or '').strip().lower()
                    raw_phone = row.get('telepon') or row.get('phone') or ''

                    if pd.notna(date_val) and nama_tamu and nama_tamu.lower() != 'nan':
                        nama_tamu = nama_tamu[:255]
                        instansi = '' if instansi.lower() == 'nan' else instansi[:255]
                        keperluan = 'Kunjungan' if keperluan.lower() == 'nan' else keperluan[:500]
                        if jam.lower() == 'nan':
                            jam = '09:00'

                        try:
                            dt = timezone.make_aware(pd.to_datetime(f"{date_val} {jam}"))
                        except Exception:
                            continue

                        try:
                            validate_kunjungan_schedule(
                                arrival_time=dt,
                                is_admin=True,
                                is_import=True
                            )
                        except DjangoValidationError:
                            continue

                        clean_nik = raw_nik if (raw_nik.isdigit() and len(raw_nik) == 16) else None
                        clean_email = None
                        if raw_email and raw_email != 'nan':
                            try:
                                validate_email(raw_email)
                                clean_email = raw_email
                            except DjangoValidationError:
                                clean_email = None
                        try:
                            clean_phone = normalize_and_validate_phone(
                                '' if str(raw_phone).lower() == 'nan' else raw_phone,
                                allow_placeholder=True,
                            )
                        except DjangoValidationError:
                            clean_phone = '-'

                        # Pencocokan aman berbasis NIK / Email unik — tidak lagi menggabungkan tamu hanya karena nama sama
                        tamu = None
                        if clean_nik:
                            matches = list(Tamu.objects.filter(Tamu.nik_lookup_q(clean_nik), account_status='active')[:2])
                            if len(matches) == 1:
                                tamu = matches[0]
                        elif clean_email:
                            tamu = Tamu.objects.filter(email__iexact=clean_email, account_status='active').first()

                        if not tamu:
                            tamu = Tamu.objects.create(
                                name=nama_tamu,
                                email=clean_email or f"import_{uuid.uuid4().hex}@guest.local",
                                nik=clean_nik,
                                phone=clean_phone,
                                instansi=instansi,
                                password=make_password(None),
                                account_status='active',
                                registration_type='manual',
                            )

                        Kunjungan.objects.create(
                            tamu=tamu,
                            arrival_time=dt,
                            purpose=keperluan,
                            status=Kunjungan.Status.MENUNGGU_ADMIN
                        )
                        success_count += 1

            return JsonResponse({'success': True, 'message': f'{success_count} kunjungan berhasil diimpor.'})
        except Exception:
            logger.exception("Gagal memproses file impor Excel kunjungan")
            return JsonResponse({'error': 'Gagal memproses file Excel. Pastikan format kolom sesuai template.'}, status=400)

    return JsonResponse({'error': 'File tidak ditemukan atau metode tidak valid'}, status=400)


# ── Profil ────────────────────────────────────────────────────────────────────

@admin_login_required
def api_update_profile_picture(request):
    """Perbarui foto profil admin milik akun yang sedang login (tanpa fallback lintas akun)."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    from .auth import check_rate_limit, get_client_ip, record_rate_limit_attempt
    from .base import invalidate_admin_cache, record_audit_log, resolve_admin_tamu_profile
    from ..utils import validate_uploaded_file

    client_ip = get_client_ip(request)
    actor_key = (
        f"staff_{request.user.pk}"
        if getattr(request, 'user', None) and request.user.is_authenticated
        else f"tamu_{request.session.get('tamu_id', 'anon')}"
    )
    rl_key = f"rl_admin_avatar_{actor_key}_{client_ip}"
    if check_rate_limit(rl_key, max_attempts=15, fail_closed=False):
        return JsonResponse(
            {'success': False, 'error': 'Terlalu banyak unggahan foto profil. Coba lagi dalam beberapa menit.'},
            status=429,
        )
    record_rate_limit_attempt(rl_key, timeout_seconds=900)

    file_obj = request.FILES.get('profile_picture')
    if not file_obj:
        return JsonResponse({'success': False, 'error': 'No file uploaded'}, status=400)

    is_valid, error_message, _ = validate_uploaded_file(
        file_obj,
        max_size_bytes=2 * 1024 * 1024,
        allowed_extensions=['jpg', 'jpeg', 'png', 'webp']
    )
    if not is_valid:
        return JsonResponse({'success': False, 'error': error_message}, status=400)

    admin_user = resolve_admin_tamu_profile(request, create_if_missing=True)
    if admin_user:
        try:
            admin_user.profile_picture = file_obj
            admin_user.save(update_fields=['profile_picture'])
            invalidate_admin_cache(
                tamu_id=str(admin_user.id),
                staff_user_id=str(request.user.pk) if request.user.is_authenticated else None,
            )

            record_audit_log(
                user_id=str(admin_user.id),
                user_type='admin',
                action='update',
                table_name='tamu',
                record_id=str(admin_user.id),
                new_value={'profile_picture': admin_user.profile_picture.url},
                ip_address=client_ip,
            )
            return JsonResponse({'success': True, 'file_url': admin_user.profile_picture.url})
        except Exception:
            logger.exception("Gagal menyimpan foto profil admin")
            return JsonResponse({'success': False, 'error': 'Terjadi kesalahan saat menyimpan foto profil'}, status=500)

    return JsonResponse({'success': False, 'error': 'Admin record tidak ditemukan'}, status=404)


@tamu_login_required
def api_tamu_update_profile_picture(request, tamu):
    """Perbarui foto profil tamu dengan rate limiting & validasi magic bytes."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    from .auth import check_rate_limit, get_client_ip, record_rate_limit_attempt
    from .base import record_audit_log
    from ..utils import validate_uploaded_file

    client_ip = get_client_ip(request)
    rl_key = f"rl_tamu_avatar_{tamu.pk}_{client_ip}"
    if check_rate_limit(rl_key, max_attempts=10, fail_closed=False):
        return JsonResponse(
            {'success': False, 'error': 'Terlalu banyak unggahan foto profil. Coba lagi dalam 15 menit.'},
            status=429,
        )
    record_rate_limit_attempt(rl_key, timeout_seconds=900)

    file_obj = request.FILES.get('profile_picture')
    if not file_obj:
        return JsonResponse({'success': False, 'error': 'No file uploaded'}, status=400)

    is_valid, error_message, _ = validate_uploaded_file(
        file_obj,
        max_size_bytes=2 * 1024 * 1024,
        allowed_extensions=['jpg', 'jpeg', 'png', 'webp']
    )
    if not is_valid:
        return JsonResponse({'success': False, 'error': error_message}, status=400)

    try:
        tamu.profile_picture = file_obj
        tamu.save(update_fields=['profile_picture'])

        record_audit_log(
            user_id=str(tamu.id),
            user_type='tamu',
            action='update',
            table_name='tamu',
            record_id=str(tamu.id),
            new_value={'profile_picture': tamu.profile_picture.url},
            ip_address=client_ip,
        )
        return JsonResponse({'success': True, 'file_url': tamu.profile_picture.url})
    except Exception:
        logger.exception("Gagal menyimpan foto profil tamu")
        return JsonResponse({'success': False, 'error': 'Terjadi kesalahan saat menyimpan foto profil'}, status=500)


@tamu_login_required
def api_tamu_update_profile_data(request, tamu):
    """Perbarui data pribadi tamu dengan validasi nomor telepon & panjang instansi."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    try:
        from django.core.exceptions import ValidationError as DjangoValidationError
        from ..validators import normalize_and_validate_phone
        from .auth import get_client_ip
        from .base import record_audit_log

        data = json.loads(request.body)
        if not isinstance(data, dict):
            return JsonResponse({'success': False, 'error': 'Format data profil tidak valid.'}, status=400)

        raw_phone = data.get('phone')
        raw_instansi = data.get('instansi')
        updated_fields = []

        if raw_phone is not None and str(raw_phone).strip() != '':
            try:
                tamu.phone = normalize_and_validate_phone(raw_phone, allow_placeholder=False)
                updated_fields.append('phone')
            except DjangoValidationError as phone_err:
                return JsonResponse({'success': False, 'error': phone_err.messages[0]}, status=400)

        if raw_instansi is not None:
            if not isinstance(raw_instansi, str):
                return JsonResponse({'success': False, 'error': 'Format nama instansi tidak valid.'}, status=400)
            clean_instansi = raw_instansi.strip()[:255]
            if clean_instansi:
                tamu.instansi = clean_instansi
                updated_fields.append('instansi')

        if updated_fields:
            tamu.save(update_fields=updated_fields)
            record_audit_log(
                user_id=str(tamu.id),
                user_type='tamu',
                action='update',
                table_name='tamu',
                record_id=str(tamu.id),
                new_value={'phone': tamu.phone, 'instansi': tamu.instansi},
                ip_address=get_client_ip(request),
            )
        return JsonResponse({'success': True})
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Format data profil tidak valid.'}, status=400)
    except Exception:
        logger.exception("Gagal memperbarui profil tamu %s", getattr(tamu, 'id', '-'))
        return JsonResponse({'success': False, 'error': 'Gagal memperbarui data profil.'}, status=500)


@admin_login_required
def api_update_profile_data(request):
    """Perbarui data pribadi admin milik akun yang sedang login (tanpa fallback lintas akun)."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    try:
        from django.core.exceptions import ValidationError as DjangoValidationError
        from django.core.validators import validate_email
        from .auth import get_client_ip
        from .base import invalidate_admin_cache, record_audit_log, resolve_admin_tamu_profile

        data = json.loads(request.body)
        if not isinstance(data, dict):
            return JsonResponse({'success': False, 'error': 'Format data profil tidak valid.'}, status=400)

        name = str(data.get('name') or '').strip()[:255]
        email = str(data.get('email') or '').strip().lower()
        nip = str(data.get('nip') or '').strip()[:50] or None
        jabatan = str(data.get('jabatan') or '').strip()[:100] or None

        if not name or not email:
            return JsonResponse({'success': False, 'error': 'Nama dan Email wajib diisi'}, status=400)

        try:
            validate_email(email)
        except DjangoValidationError:
            return JsonResponse({'success': False, 'error': 'Format email tidak valid.'}, status=400)

        admin_user = resolve_admin_tamu_profile(request, create_if_missing=True)
        if not admin_user:
            return JsonResponse({'success': False, 'error': 'Profil administrator milik akun ini tidak ditemukan.'}, status=404)

        if Tamu.objects.filter(email__iexact=email).exclude(pk=admin_user.pk).exists():
            return JsonResponse({'success': False, 'error': 'Email sudah digunakan oleh akun lain.'}, status=409)

        admin_user.name = name
        admin_user.email = email
        admin_user.nip = nip
        admin_user.jabatan = jabatan
        admin_user.save(update_fields=['name', 'email', 'nip', 'jabatan'])

        if getattr(request, 'user', None) and request.user.is_authenticated and request.user.is_staff:
            auth_fields = []
            if request.user.email != email:
                request.user.email = email
                auth_fields.append('email')
            if request.user.first_name != name[:150]:
                request.user.first_name = name[:150]
                auth_fields.append('first_name')
            if auth_fields:
                request.user.save(update_fields=auth_fields)

        invalidate_admin_cache(
            tamu_id=str(admin_user.id),
            staff_user_id=str(request.user.pk) if request.user.is_authenticated else None,
        )
        record_audit_log(
            user_id=str(admin_user.id),
            user_type='admin',
            action='update',
            table_name='tamu',
            record_id=str(admin_user.id),
            new_value={'name': name, 'email': email, 'nip': nip, 'jabatan': jabatan},
            ip_address=get_client_ip(request),
        )
        return JsonResponse({'success': True})
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Format data profil tidak valid.'}, status=400)
    except Exception:
        logger.exception("Gagal memperbarui profil admin")
        return JsonResponse({'success': False, 'error': 'Gagal memperbarui profil admin.'}, status=500)


@admin_login_required
def api_change_password(request):
    """Ganti password admin pada akun autentikasi utama (Django User & tabel Admin)."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

    from django.contrib.auth import update_session_auth_hash
    from django.contrib.auth.models import User
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError
    from ..models import Admin
    from .base import record_audit_log

    if 'application/json' in (request.content_type or '').lower():
        try:
            payload = json.loads(request.body or b'{}')
            if not isinstance(payload, dict):
                payload = {}
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'Format payload JSON tidak valid.'}, status=400)
    else:
        payload = request.POST

    old_pw = payload.get('old_password') or ''
    new_pw = payload.get('new_password') or ''
    confirm_pw = payload.get('confirm_password')

    if not old_pw or not new_pw:
        return JsonResponse(
            {'success': False, 'error': 'Password lama dan password baru wajib diisi.'},
            status=400,
        )

    if confirm_pw is not None and new_pw != confirm_pw:
        return JsonResponse(
            {'success': False, 'error': 'Konfirmasi password baru tidak cocok.'},
            status=400,
        )

    if old_pw == new_pw:
        return JsonResponse(
            {'success': False, 'error': 'Password baru tidak boleh sama dengan password lama.'},
            status=400,
        )

    if not (
        getattr(request, 'user', None)
        and request.user.is_authenticated
        and request.user.is_staff
        and request.user.is_active
    ):
        return JsonResponse(
            {'success': False, 'error': 'Sesi administrator Django tidak terautentikasi.'},
            status=403,
        )

    auth_user = request.user

    if not auth_user.check_password(old_pw):
        return JsonResponse({'success': False, 'error': 'Password lama tidak sesuai.'}, status=400)

    try:
        validate_password(new_pw, user=auth_user)
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': ' '.join(exc.messages)}, status=400)

    auth_user.set_password(new_pw)
    auth_user.save(update_fields=['password'])

    if getattr(request, 'user', None) and request.user.is_authenticated and request.user.pk == auth_user.pk:
        update_session_auth_hash(request, auth_user)

    if auth_user.email:
        Admin.objects.filter(email__iexact=auth_user.email).update(password=auth_user.password)

    # Profil Tamu dengan is_admin=True hanya untuk metadata UI, tidak boleh punya kredensial login Tamu
    Tamu.objects.filter(is_admin=True).exclude(password__isnull=True).update(password=None)

    record_audit_log(
        user_id=str(auth_user.pk),
        user_type='admin',
        action='update',
        table_name='auth_user',
        record_id=str(auth_user.pk),
        new_value='Admin memperbarui password melalui portal admin.',
        ip_address=request.META.get('REMOTE_ADDR'),
    )
    return JsonResponse({'success': True, 'message': 'Password berhasil diperbarui.'})


@admin_login_required
def api_update_notification_settings(request):
    """Perbarui preferensi notifikasi admin di database (per akun admin)."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

    try:
        from .base import resolve_admin_record
        from ..models import Admin

        data = json.loads(request.body)
        if not isinstance(data, dict):
            return JsonResponse({'success': False, 'error': 'Payload tidak valid.'}, status=400)

        email_notif = data.get('email_notif')
        push_notif = data.get('push_notif')

        if email_notif is not None and not isinstance(email_notif, bool):
            return JsonResponse({'success': False, 'error': 'Nilai email_notif harus boolean.'}, status=400)
        if push_notif is not None and not isinstance(push_notif, bool):
            return JsonResponse({'success': False, 'error': 'Nilai push_notif harus boolean.'}, status=400)

        admin_record = resolve_admin_record(getattr(request, 'user', None), create_if_missing=True)
        if admin_record is None:
            tamu_id = request.session.get('tamu_id')
            if tamu_id:
                tamu_admin = Tamu.objects.filter(
                    pk=tamu_id, is_admin=True, account_status='active'
                ).first()
                if tamu_admin and tamu_admin.email:
                    admin_record = Admin.objects.filter(
                        email__iexact=tamu_admin.email, account_status='active'
                    ).first()
                    if admin_record is None:
                        admin_record = Admin.objects.create(
                            name=tamu_admin.name or 'Administrator',
                            email=tamu_admin.email,
                            phone=tamu_admin.phone or '-',
                            password='!',
                            account_status='active',
                        )

        if admin_record is None:
            return JsonResponse({'success': False, 'error': 'Rekam akun administrator tidak ditemukan.'}, status=404)

        update_fields = []
        if email_notif is not None:
            admin_record.email_notif_enabled = email_notif
            update_fields.append('email_notif_enabled')
        if push_notif is not None:
            admin_record.push_notif_enabled = push_notif
            update_fields.append('push_notif_enabled')

        if update_fields:
            admin_record.save(update_fields=update_fields)

        return JsonResponse({
            'success': True,
            'email_notif_enabled': admin_record.email_notif_enabled,
            'push_notif_enabled': admin_record.push_notif_enabled,
        })
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Gagal menyimpan preferensi notifikasi.'}, status=400)
    except Exception:
        logger.exception("Gagal memperbarui pengaturan notifikasi admin")
        return JsonResponse({'success': False, 'error': 'Gagal memperbarui pengaturan notifikasi.'}, status=500)


# ── User Management ───────────────────────────────────────────────────────────

def api_toggle_user_status(request, user_id):

    """Blokir/aktifkan tamu (Khusus Admin)"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

    is_admin, admin_id = check_is_admin(request)
    if not is_admin:
        return JsonResponse({'success': False, 'error': 'Akses khusus Administrator. Unauthorized.'}, status=403)

    is_super, _ = check_is_super_admin(request)
    if not is_super:
        return JsonResponse({'success': False, 'error': 'Akses khusus Super Admin diperlukan untuk mengubah status pengguna.'}, status=403)

    try:
        tamu_obj = Tamu.objects.get(id=user_id)
        new_status = request.POST.get('status')
        if new_status not in dict(Tamu.STATUS_CHOICES).keys():
            return JsonResponse({'success': False, 'error': 'Status invalid'}, status=400)

        # Cegah admin menonaktifkan akun admin sendiri agar tidak terkunci
        current_tamu_id = request.session.get('tamu_id')
        is_self = (str(tamu_obj.id) == str(admin_id)) or (current_tamu_id and str(tamu_obj.id) == str(current_tamu_id))
        if request.user.is_authenticated:
            if request.user.email and tamu_obj.email == request.user.email:
                is_self = True
            if request.user.username and tamu_obj.name == request.user.username:
                is_self = True

        if is_self and new_status != 'active':
            return JsonResponse({'success': False, 'error': 'Anda tidak dapat menonaktifkan akun admin Anda sendiri.'}, status=400)

        old_status = tamu_obj.account_status
        tamu_obj.account_status = new_status
        tamu_obj.save()

        if tamu_obj.is_admin:
            from .base import invalidate_admin_cache
            invalidate_admin_cache(tamu_id=str(tamu_obj.id))

        if new_status != 'active':
            from ..security_utils import revoke_user_sessions
            revoke_user_sessions('tamu', str(tamu_obj.id))

        from .base import record_audit_log
        record_audit_log(
            user_id=str(admin_id),
            user_type='admin',
            action='update',
            table_name='tamu',
            record_id=str(tamu_obj.id),
            old_value={'account_status': old_status},
            new_value={'account_status': new_status, 'name': tamu_obj.name},
            ip_address=request.META.get('REMOTE_ADDR')
        )

        return JsonResponse({'success': True, 'new_status': new_status})
    except Tamu.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Pengguna tidak ditemukan.'}, status=404)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'ID pengguna tidak valid.'}, status=400)
    except Exception:
        logger.exception("Gagal mengubah status akun tamu %s", user_id)
        return JsonResponse({'success': False, 'error': 'Gagal mengubah status pengguna.'}, status=500)


# ── Dashboard Stats & Debug ───────────────────────────────────────────────────

@admin_login_required
def api_dashboard_stats(request):
    """Statistik dashboard secara real-time"""
    now = timezone.localtime(timezone.now())
    today = now.date()

    total_tamu = Tamu.objects.count()
    start_of_today = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    end_of_today = timezone.make_aware(datetime.combine(today, datetime.max.time()))
    kunjungan_hari_ini = Kunjungan.objects.filter(arrival_time__range=(start_of_today, end_of_today)).count()
    menunggu_verifikasi = Kunjungan.objects.filter(
        status__in=Kunjungan.Status.PENDING_VERIFICATION
    ).count()

    setting = CalendarSettings.objects.filter(date=today).first()
    quota = setting.daily_quota if setting else 50
    sisa_slot = max(quota - kunjungan_hari_ini, 0)

    return JsonResponse({'success': True, 'total_tamu': total_tamu, 'kunjungan_hari_ini': kunjungan_hari_ini, 'menunggu_verifikasi': menunggu_verifikasi, 'quota': quota, 'sisa_slot': sisa_slot})


@_debug_endpoint_disabled_in_prod
@admin_login_required
def api_debug_calendar_settings(request):
    """Debug: lihat data CalendarSettings (Khusus Admin, nonaktif saat DEBUG=False)"""
    page = request.GET.get('page', 1)
    page_size = clamp_page_size(request.GET.get('page_size'), default=20, max_size=100)
    paginator = Paginator(CalendarSettings.objects.order_by('-date', 'id'), page_size)
    page_obj = paginator.get_page(page)
    data = [
        {
            'date': s.date.isoformat(),
            'quota': s.daily_quota,
            'is_holiday': s.is_holiday,
            'holiday_name': s.holiday_name,
        }
        for s in page_obj.object_list
    ]
    return JsonResponse({
        'success': True,
        'data': data,
        'pagination': {
            'current_page': page_obj.number,
            'page_size': page_size,
            'total_pages': paginator.num_pages,
            'total_items': paginator.count,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        },
    })


@_debug_endpoint_disabled_in_prod
@admin_login_required
def api_debug_counts(request):
    """Debug: lihat data kunjungan bulan berjalan dengan pagination (Khusus Admin, nonaktif saat DEBUG=False)"""
    from ..validators import get_month_range_aware

    now = timezone.localtime(timezone.now())
    month_start, next_month_start = get_month_range_aware(now.year, now.month)
    kunjungan_month = (
        Kunjungan.objects.filter(
            arrival_time__gte=month_start,
            arrival_time__lt=next_month_start,
        )
        .only('id', 'arrival_time')
        .order_by('-arrival_time', 'id')
    )
    page = request.GET.get('page', 1)
    page_size = clamp_page_size(request.GET.get('page_size'), default=50, max_size=100)
    paginator = Paginator(kunjungan_month, page_size)
    page_obj = paginator.get_page(page)
    data = [
        {
            'id': str(k.id),
            'arrival_time': timezone.localtime(k.arrival_time).isoformat() if k.arrival_time else None,
            'day': timezone.localtime(k.arrival_time).day if k.arrival_time else None,
        }
        for k in page_obj.object_list
    ]
    return JsonResponse({
        'success': True,
        'count': paginator.count,
        'data': data,
        'pagination': {
            'current_page': page_obj.number,
            'page_size': page_size,
            'total_pages': paginator.num_pages,
            'total_items': paginator.count,
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
        },
    })


# ── Firebase Webhook ──────────────────────────────────────────────────────────

@csrf_exempt
def api_webhook_delete_user(request):
    """Webhook API: hapus satu user non-admin di MySQL saat dihapus dari Firebase."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    import hmac
    from django.conf import settings as dj_settings

    expected_token = (getattr(dj_settings, 'FIREBASE_WEBHOOK_SECRET', None) or '').strip()
    if not expected_token:
        return JsonResponse({'success': False, 'error': 'Webhook not configured'}, status=500)

    auth_header = (request.headers.get('Authorization') or '').strip()
    expected_header = f"Bearer {expected_token}"
    if not hmac.compare_digest(auth_header.encode('utf-8'), expected_header.encode('utf-8')):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    try:
        try:
            data = json.loads(request.body or b'{}')
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'Invalid JSON payload'}, status=400)

        if not isinstance(data, dict):
            return JsonResponse({'success': False, 'error': 'Invalid payload object'}, status=400)

        uid_raw = data.get('uid')
        email_raw = data.get('email')
        uid = uid_raw.strip() if isinstance(uid_raw, str) else ''
        email = email_raw.strip().lower() if isinstance(email_raw, str) else ''

        if not uid and not email:
            return JsonResponse({'success': False, 'error': 'Missing uid or email'}, status=400)

        from django.db.models import Q
        from django.db.models.signals import post_delete
        from ..signals import delete_firebase_user
        from .base import record_audit_log

        # Bangun filter HANYA dari field non-kosong untuk mencegah kecocokan massal pada NULL/string kosong
        lookup = Q()
        if uid:
            lookup |= Q(google_id=uid)
        if email:
            lookup |= Q(email__iexact=email)

        tamu_qs = Tamu.objects.filter(lookup).exclude(is_admin=True).exclude(Tamu.nik_lookup_q('admin'))
        matches = list(tamu_qs[:3])
        if not matches:
            return JsonResponse({'success': True, 'message': 'User not found in MySQL, no action taken'})

        if len(matches) > 1:
            logger.warning(
                "Webhook delete_user dibatalkan karena selektor cocok lebih dari 1 akun (matches=%d).",
                len(matches),
            )
            return JsonResponse({'success': False, 'error': 'Ambiguous user selector'}, status=409)

        target = matches[0]
        target_id = str(target.pk)
        post_delete.disconnect(delete_firebase_user, sender=Tamu)
        try:
            count, _ = Tamu.objects.filter(pk=target.pk).delete()
        finally:
            post_delete.connect(delete_firebase_user, sender=Tamu)

        if count > 0:
            record_audit_log(
                user_id='firebase_webhook',
                user_type='admin',
                action='delete',
                table_name='tamu',
                record_id=target_id,
                old_value=f"Dihapus via Firebase webhook (uid_present={bool(uid)}, email_present={bool(email)})",
                ip_address=request.META.get('REMOTE_ADDR'),
            )
            return JsonResponse({'success': True, 'message': 'User deleted from MySQL successfully'})
        return JsonResponse({'success': True, 'message': 'User not found in MySQL, no action taken'})

    except Exception:
        logger.exception("Error tidak terduga pada api_webhook_delete_user")
        return JsonResponse({'success': False, 'error': 'Internal server error'}, status=500)


def _parse_json_or_post(request):
    if 'application/json' in (request.content_type or '').lower():
        try:
            payload = json.loads(request.body or b'{}')
            return payload if isinstance(payload, dict) else {}
        except (ValueError, TypeError):
            return None
    return request.POST


@admin_login_required
def api_admin_2fa_setup(request):
    """Hasilkan secret TOTP sementara untuk konfigurasi 2FA di profil admin."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    from ..security_utils import (
        build_totp_uri,
        encrypt_secret,
        format_totp_secret,
        generate_totp_secret,
    )
    from .base import resolve_admin_record

    auth_user = request.user if (
        getattr(request, 'user', None)
        and request.user.is_authenticated
        and request.user.is_staff
        and request.user.is_active
    ) else None
    if auth_user is None:
        return JsonResponse({'success': False, 'error': 'Autentikasi staff Django diperlukan untuk setup 2FA.'}, status=403)

    admin_record = resolve_admin_record(auth_user, create_if_missing=True)
    if admin_record is None:
        return JsonResponse({'success': False, 'error': 'Profil administrator tidak ditemukan.'}, status=404)

    secret = generate_totp_secret()
    request.session['pending_admin_2fa_setup_secret'] = encrypt_secret(secret)
    request.session['pending_admin_2fa_setup_user_id'] = str(auth_user.pk)
    account_label = (getattr(auth_user, 'email', None) or admin_record.email or 'admin@diskominfosantik.local')

    return JsonResponse({
        'success': True,
        'secret': secret,
        'secret_formatted': format_totp_secret(secret),
        'otpauth_uri': build_totp_uri(secret, account_label),
    })


@admin_login_required
def api_admin_2fa_enable(request):
    """Aktifkan TOTP 2FA setelah verifikasi password saat ini dan kode OTP 6 digit pertama berhasil."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    payload = _parse_json_or_post(request)
    if payload is None:
        return JsonResponse({'success': False, 'error': 'Format payload tidak valid.'}, status=400)

    auth_user = request.user if (
        getattr(request, 'user', None)
        and request.user.is_authenticated
        and request.user.is_staff
        and request.user.is_active
    ) else None
    if auth_user is None:
        return JsonResponse({'success': False, 'error': 'Autentikasi staff Django diperlukan untuk mengaktifkan 2FA.'}, status=403)

    from django.core.cache import cache
    from ..security_utils import decrypt_secret, encrypt_secret, verify_totp_code
    from .base import ADMIN_2FA_VERIFIED_SESSION_KEY, record_audit_log, resolve_admin_record
    from .auth import check_rate_limit, get_client_ip, record_rate_limit_attempt, clear_rate_limit

    rl_key = f"rl_admin_2fa_enable_{auth_user.pk}"
    if check_rate_limit(rl_key, max_attempts=5):
        return JsonResponse(
            {'success': False, 'error': 'Terlalu banyak percobaan gagal aktivasi 2FA. Coba lagi nanti.'},
            status=429,
        )

    current_password = payload.get('password') or payload.get('current_password') or ''
    if not current_password:
        return JsonResponse(
            {'success': False, 'error': 'Password saat ini wajib diisi untuk mengaktifkan 2FA.'},
            status=400,
        )
    if not auth_user.check_password(current_password):
        record_rate_limit_attempt(rl_key)
        return JsonResponse({'success': False, 'error': 'Password administrator saat ini tidak sesuai.'}, status=403)

    otp_code = (payload.get('otp_code') or '').strip()
    encrypted_pending = request.session.get('pending_admin_2fa_setup_secret')
    pending_uid = request.session.get('pending_admin_2fa_setup_user_id')
    if not encrypted_pending or pending_uid != str(auth_user.pk):
        return JsonResponse({'success': False, 'error': 'Sesi setup 2FA belum dimulai atau tidak cocok dengan akun Anda.'}, status=400)

    raw_secret = decrypt_secret(encrypted_pending)
    if not verify_totp_code(
        raw_secret,
        otp_code,
        valid_window=1,
        replay_scope=f"admin_setup_{auth_user.pk}",
    ):
        record_rate_limit_attempt(rl_key)
        return JsonResponse({'success': False, 'error': 'Kode OTP 6 digit tidak sesuai atau sudah digunakan. Coba lagi.'}, status=400)

    clear_rate_limit(rl_key)
    admin_record = resolve_admin_record(auth_user, create_if_missing=True)
    if admin_record is None:
        return JsonResponse({'success': False, 'error': 'Profil administrator tidak ditemukan.'}, status=404)

    admin_record.two_fa_enabled = True
    admin_record.two_fa_secret = encrypt_secret(raw_secret)
    admin_record.save(update_fields=['two_fa_enabled', 'two_fa_secret'])
    request.session.pop('pending_admin_2fa_setup_secret', None)
    request.session.pop('pending_admin_2fa_setup_user_id', None)
    request.session[ADMIN_2FA_VERIFIED_SESSION_KEY] = str(auth_user.pk)

    record_audit_log(
        user_id=str(auth_user.pk),
        user_type='admin',
        action='update',
        table_name='admin',
        record_id=str(admin_record.id),
        new_value='Mengaktifkan Autentikasi Dua Faktor (2FA TOTP) Administrator.',
        ip_address=get_client_ip(request),
    )
    return JsonResponse({'success': True, 'two_fa_enabled': True, 'message': '2FA berhasil diaktifkan.'})


@admin_login_required
def api_admin_2fa_disable(request):
    """Nonaktifkan TOTP 2FA administrator dengan verifikasi password saat ini."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    payload = _parse_json_or_post(request)
    if payload is None:
        return JsonResponse({'success': False, 'error': 'Format payload tidak valid.'}, status=400)

    current_password = payload.get('password') or ''
    if not current_password:
        return JsonResponse({'success': False, 'error': 'Password saat ini wajib diisi untuk menonaktifkan 2FA.'}, status=400)

    from .base import ADMIN_2FA_VERIFIED_SESSION_KEY, record_audit_log, resolve_admin_record
    from .auth import check_rate_limit, get_client_ip, record_rate_limit_attempt, clear_rate_limit

    auth_user = request.user if (
        getattr(request, 'user', None)
        and request.user.is_authenticated
        and request.user.is_staff
        and request.user.is_active
    ) else None

    if auth_user is None:
        return JsonResponse({'success': False, 'error': 'Autentikasi staff Django diperlukan untuk menonaktifkan 2FA.'}, status=403)

    rl_key = f"rl_admin_2fa_disable_{auth_user.pk}"
    if check_rate_limit(rl_key, max_attempts=5):
        return JsonResponse(
            {'success': False, 'error': 'Terlalu banyak percobaan gagal. Coba lagi nanti.'},
            status=429,
        )

    if not auth_user.check_password(current_password):
        record_rate_limit_attempt(rl_key)
        return JsonResponse({'success': False, 'error': 'Password administrator tidak sesuai.'}, status=403)

    clear_rate_limit(rl_key)
    admin_record = resolve_admin_record(auth_user)
    if admin_record:
        admin_record.two_fa_enabled = False
        admin_record.two_fa_secret = None
        admin_record.save(update_fields=['two_fa_enabled', 'two_fa_secret'])

        record_audit_log(
            user_id=str(auth_user.pk),
            user_type='admin',
            action='update',
            table_name='admin',
            record_id=str(admin_record.id),
            new_value='Menonaktifkan Autentikasi Dua Faktor (2FA TOTP) Administrator.',
            ip_address=get_client_ip(request),
        )

    request.session.pop('pending_admin_2fa_setup_secret', None)
    request.session.pop('pending_admin_2fa_setup_user_id', None)
    request.session.pop(ADMIN_2FA_VERIFIED_SESSION_KEY, None)
    return JsonResponse({'success': True, 'two_fa_enabled': False, 'message': '2FA berhasil dinonaktifkan.'})
