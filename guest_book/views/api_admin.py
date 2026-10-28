"""
API Views — Kalender, Kunjungan (quick checkin, quota, import), Debug, Profil, Webhook
"""
import json
import logging
from datetime import datetime

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator
from django.contrib.auth.hashers import make_password

from .base import admin_login_required, tamu_login_required, check_is_admin
from ..models import Notification, Kunjungan, Tamu, CalendarSettings

logger = logging.getLogger(__name__)


# ── Kalender ──────────────────────────────────────────────────────────────────

@admin_login_required
def api_update_quota(request):
    """Update kuota harian kalender"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            date_str = data.get('date')
            quota = data.get('quota')
            is_holiday = data.get('is_holiday')
            holiday_name = data.get('holiday_name')

            setting, _ = CalendarSettings.objects.get_or_create(date=date_str)
            if quota is not None:
                setting.daily_quota = quota
            if is_holiday is not None:
                setting.is_holiday = is_holiday
            if holiday_name is not None:
                setting.holiday_name = holiday_name
            setting.save()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid method'}, status=405)


@admin_login_required
def api_toggle_holiday(request):
    """Toggle status libur pada tanggal tertentu"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            date_str = data.get('date')
            setting, _ = CalendarSettings.objects.get_or_create(date=date_str)
            setting.is_holiday = not setting.is_holiday
            if not setting.is_holiday:
                setting.holiday_name = ''
            setting.save()
            return JsonResponse({'success': True, 'is_holiday': setting.is_holiday})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid method'}, status=405)


@admin_login_required
def api_import_calendar_csv(request):
    """Import data kalender dari Excel/CSV"""
    import pandas as pd
    from django.contrib import messages as dj_messages

    if request.method != 'POST' or not request.FILES.get('file'):
        dj_messages.error(request, 'File tidak ditemukan atau metode tidak valid.')
        return JsonResponse({'error': 'File tidak ditemukan'}, status=400)

    file = request.FILES['file']
    filename = file.name.lower()

    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(file, sep=None, engine='python')
        elif filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(file)
        else:
            dj_messages.error(request, 'Format file tidak didukung. Harap gunakan .csv, .xlsx, atau .xls.')
            return JsonResponse({'error': 'Format file tidak didukung'}, status=400)

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

        for i, row in df.iterrows():
            date_val = row.get('tanggal') or row.get('date')
            quota = row.get('kuota') or row.get('quota') or 50
            libur_raw = str(row.get('libur') or 'tidak').lower()
            is_holiday = libur_raw in ['ya', 'yes', '1', 'true']
            holiday_name = row.get('nama_libur') or row.get('keterangan libur') or row.get('keterangan_libur') or ''

            if pd.notna(date_val) and str(date_val).strip() != '':
                try:
                    dt = pd.to_datetime(date_val).date()
                    setting, _ = CalendarSettings.objects.get_or_create(date=dt)
                    setting.daily_quota = int(float(quota)) if pd.notna(quota) and str(quota).strip() != '' else 50
                    setting.is_holiday = is_holiday
                    setting.holiday_name = str(holiday_name) if pd.notna(holiday_name) else ''
                    setting.save()
                    success_count += 1
                except Exception as e:
                    errors.append(f"Baris index {i}: {str(e)}")
                    continue

        msg = f'{success_count} data berhasil diimpor.'
        if errors:
            msg += f' Terdapat {len(errors)} baris gagal. Contoh error: {errors[0]}'

        dj_messages.success(request, msg)
        return JsonResponse({'success': True, 'message': msg})

    except Exception as e:
        logger.exception("Fatal error saat import kalender: %s", str(e))
        return JsonResponse({'error': f'Gagal memproses file: {str(e)}'}, status=400)


def api_google_holidays(request, year):
    """Ambil data libur (Public)"""
    from ..utils import get_google_calendar_holidays
    holidays = get_google_calendar_holidays(year)
    if not holidays:
        holidays = [{'date': f'{year}-01-01', 'name': 'Tahun Baru (Fallback)'}]
    return JsonResponse({'year': year, 'holidays': holidays})


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
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


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

        # 8. Validasi Jadwal & Kuota Terpusat
        from ..validators import validate_kunjungan_schedule
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            validate_kunjungan_schedule(
                arrival_time=arrival_dt,
                instance=existing_kunjungan,
                is_admin=True,
                is_import=False
            )
        except DjangoValidationError as val_err:
            if hasattr(val_err, 'message_dict'):
                err_msg = '; '.join([f"{k}: {', '.join(v)}" for k, v in val_err.message_dict.items()])
            elif hasattr(val_err, 'message'):
                err_msg = val_err.message
            else:
                err_msg = str(val_err)
            return JsonResponse({'success': False, 'error': err_msg}, status=400)

        # 9. Transaksi Atomik: Pembuatan/Pencocokan Tamu dan Kunjungan
        import uuid
        from django.db import IntegrityError, transaction
        from ..workflow_engine import WorkflowEngine

        with transaction.atomic():
            # Aturan pencocokan Tamu:
            # 1. Jika NIK ada -> cari tamu aktif dengan NIK tersebut (tepat 1 match)
            # 2. Jika phone ada -> cari tamu aktif dengan phone tersebut (tepat 1 match)
            # 3. Jika tidak ada / tidak cocok -> buat Tamu baru mandiri (nama sama tidak tertukar)
            tamu = None
            if clean_nik:
                nik_matches = list(Tamu.objects.filter(nik=clean_nik, account_status='active')[:2])
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

            # Kirim notifikasi ke Pegawai jika kunjungan ditujukan ke pegawai
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
    page_size = request.GET.get('page_size', 50)

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
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@admin_login_required
def api_import_visits_excel(request):
    """Import data kunjungan dari Excel dengan validasi keamanan dan transaksi atomik"""
    if request.method == 'POST' and request.FILES.get('file'):
        file = request.FILES['file']
        
        # 1. Batasi ukuran file (maksimal 5 MB)
        if file.size > 5 * 1024 * 1024:
            return JsonResponse({'error': 'Ukuran file melebihi batas maksimum 5 MB.'}, status=400)

        # 2. Validasi format ekstensi
        ext = file.name.lower().split('.')[-1] if '.' in file.name else ''
        if ext not in ['xlsx', 'xls']:
            return JsonResponse({'error': 'Format file harus berupa .xlsx atau .xls'}, status=400)

        try:
            import pandas as pd
            from django.db import transaction

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

                    if date_val and nama_tamu:
                        # Validasi panjang string
                        if len(nama_tamu) > 255:
                            nama_tamu = nama_tamu[:255]
                        if len(instansi) > 255:
                            instansi = instansi[:255]
                        if len(keperluan) > 500:
                            keperluan = keperluan[:500]

                        try:
                            dt = timezone.make_aware(pd.to_datetime(f"{date_val} {jam}"))
                        except Exception:
                            continue

                        from ..validators import validate_kunjungan_schedule
                        from django.core.exceptions import ValidationError as DjangoValidationError
                        try:
                            validate_kunjungan_schedule(
                                arrival_time=dt,
                                is_admin=True,
                                is_import=True
                            )
                        except DjangoValidationError:
                            continue

                        email_dummy = f"import_{str(nama_tamu).lower().replace(' ', '_')[:30]}@guest.local"
                        tamu, _ = Tamu.objects.get_or_create(
                            name=nama_tamu,
                            defaults={'email': email_dummy, 'instansi': instansi, 'account_status': 'active', 'registration_type': 'manual'}
                        )
                        Kunjungan.objects.create(
                            tamu=tamu,
                            arrival_time=dt,
                            purpose=keperluan,
                            status=Kunjungan.Status.MENUNGGU_ADMIN
                        )
                        success_count += 1

            return JsonResponse({'success': True, 'message': f'{success_count} kunjungan berhasil diimpor.'})
        except Exception as e:
            logger.exception("Gagal memproses file impor Excel kunjungan")
            return JsonResponse({'error': 'Gagal memproses file Excel. Pastikan format kolom sesuai template.'}, status=400)

    return JsonResponse({'error': 'File tidak ditemukan atau metode tidak valid'}, status=400)


# ── Profil ────────────────────────────────────────────────────────────────────

@admin_login_required
def api_update_profile_picture(request):
    """Perbarui foto profil admin"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    file_obj = request.FILES.get('profile_picture')
    if not file_obj:
        return JsonResponse({'success': False, 'error': 'No file uploaded'}, status=400)

    from ..utils import validate_uploaded_file
    is_valid, error_message, _ = validate_uploaded_file(
        file_obj,
        max_size_bytes=2 * 1024 * 1024,
        allowed_extensions=['jpg', 'jpeg', 'png', 'webp']
    )
    if not is_valid:
        return JsonResponse({'success': False, 'error': error_message}, status=400)

    from .base import check_is_admin
    _, admin_id = check_is_admin(request)
    admin_user = None
    if admin_id:
        try:
            import uuid
            uuid.UUID(str(admin_id))
            admin_user = Tamu.objects.filter(id=admin_id).first()
        except (ValueError, TypeError, Exception):
            admin_user = None
    if not admin_user:
        admin_user = Tamu.objects.filter(is_admin=True).first() or Tamu.objects.filter(nik='admin').first()

    if admin_user:
        try:
            admin_user.profile_picture = file_obj
            admin_user.save(update_fields=['profile_picture'])

            from .base import record_audit_log
            record_audit_log(
                user_id=str(admin_user.id),
                user_type='admin',
                action='update',
                table_name='tamu',
                record_id=str(admin_user.id),
                new_value={'profile_picture': admin_user.profile_picture.url},
                ip_address=request.META.get('REMOTE_ADDR')
            )
            return JsonResponse({'success': True, 'file_url': admin_user.profile_picture.url})
        except Exception:
            logger.exception("Gagal menyimpan foto profil admin")
            return JsonResponse({'success': False, 'error': 'Terjadi kesalahan saat menyimpan foto profil'}, status=500)

    return JsonResponse({'success': False, 'error': 'Admin record tidak ditemukan'}, status=404)


@tamu_login_required
def api_tamu_update_profile_picture(request, tamu):
    """Perbarui foto profil tamu"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    file_obj = request.FILES.get('profile_picture')
    if not file_obj:
        return JsonResponse({'success': False, 'error': 'No file uploaded'}, status=400)

    from ..utils import validate_uploaded_file
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

        from .base import record_audit_log
        record_audit_log(
            user_id=str(tamu.id),
            user_type='tamu',
            action='update',
            table_name='tamu',
            record_id=str(tamu.id),
            new_value={'profile_picture': tamu.profile_picture.url},
            ip_address=request.META.get('REMOTE_ADDR')
        )
        return JsonResponse({'success': True, 'file_url': tamu.profile_picture.url})
    except Exception:
        logger.exception("Gagal menyimpan foto profil tamu")
        return JsonResponse({'success': False, 'error': 'Terjadi kesalahan saat menyimpan foto profil'}, status=500)



@tamu_login_required
def api_tamu_update_profile_data(request, tamu):
    """Perbarui data pribadi tamu"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body)
        phone = data.get('phone')
        instansi = data.get('instansi')
        if phone:
            tamu.phone = phone
        if instansi:
            tamu.instansi = instansi
        tamu.save(update_fields=['phone', 'instansi'])

        from .base import record_audit_log
        record_audit_log(user_id=str(tamu.id), user_type='tamu', action='update', table_name='tamu', record_id=str(tamu.id), new_value={'phone': tamu.phone, 'instansi': tamu.instansi}, ip_address=request.META.get('REMOTE_ADDR'))
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@admin_login_required
def api_update_profile_data(request):
    """Perbarui data pribadi admin"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body)
        name = data.get('name')
        email = data.get('email')
        nip = data.get('nip')
        jabatan = data.get('jabatan')

        if not name or not email:
            return JsonResponse({'success': False, 'error': 'Nama dan Email wajib diisi'}, status=400)

        admin_user = Tamu.objects.filter(is_admin=True).first() or Tamu.objects.filter(nik='admin').first()
        if admin_user:
            admin_user.name = name
            admin_user.email = email
            admin_user.nip = nip
            admin_user.jabatan = jabatan
            admin_user.save(update_fields=['name', 'email', 'nip', 'jabatan'])

            from .base import record_audit_log
            record_audit_log(user_id=str(admin_user.id), user_type='admin', action='update', table_name='tamu', record_id=str(admin_user.id), new_value={'name': name, 'email': email, 'nip': nip, 'jabatan': jabatan}, ip_address=request.META.get('REMOTE_ADDR'))
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'Admin record tidak ditemukan'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


@admin_login_required
def api_change_password(request):
    """Ganti password admin"""
    if request.method == 'POST':
        new_pw = request.POST.get('new_password')
        if not new_pw:
            return JsonResponse({'success': False, 'error': 'Password tidak boleh kosong'})
        admin_user = Tamu.objects.filter(is_admin=True).first() or Tamu.objects.filter(nik='admin').first()
        if admin_user:
            admin_user.password = make_password(new_pw)
            admin_user.save(update_fields=['password'])
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'Admin record tidak ditemukan'})
    return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)


@admin_login_required
def api_update_notification_settings(request):
    """Perbarui preferensi notifikasi admin"""
    import os
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            email_notif = data.get('email_notif')
            push_notif = data.get('push_notif')

            pref_path = os.path.join(os.path.dirname(__file__), '../admin_preferences.json')
            prefs = {}
            if os.path.exists(pref_path):
                with open(pref_path, 'r') as f:
                    prefs = json.load(f)

            if email_notif is not None:
                prefs['email_notif_enabled'] = email_notif
            if push_notif is not None:
                prefs['push_notif_enabled'] = push_notif

            with open(pref_path, 'w') as f:
                json.dump(prefs, f)

            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)


# ── User Management ───────────────────────────────────────────────────────────

def api_toggle_user_status(request, user_id):

    """Blokir/aktifkan tamu (Khusus Admin)"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

    is_admin, admin_id = check_is_admin(request)
    if not is_admin:
        return JsonResponse({'success': False, 'error': 'Akses khusus Administrator. Unauthorized.'}, status=403)

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
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


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


@admin_login_required
def api_debug_calendar_settings(request):
    """Debug: lihat data CalendarSettings (Khusus Admin)"""
    data = [{'date': s.date.isoformat(), 'quota': s.daily_quota, 'is_holiday': s.is_holiday, 'holiday_name': s.holiday_name} for s in CalendarSettings.objects.order_by('-date')[:20]]
    return JsonResponse({'success': True, 'data': data})


@admin_login_required
def api_debug_counts(request):
    """Debug: lihat data kunjungan (Khusus Admin)"""
    now = timezone.localtime(timezone.now())
    year, month = now.year, now.month
    kunjungan_month = Kunjungan.objects.filter(arrival_time__year=year, arrival_time__month=month)
    data = [{'id': str(k.id), 'arrival_time': k.arrival_time.isoformat() if k.arrival_time else None, 'day': k.arrival_time.day if k.arrival_time else None} for k in kunjungan_month]
    return JsonResponse({'count': kunjungan_month.count(), 'data': data})


# ── Firebase Webhook ──────────────────────────────────────────────────────────

@csrf_exempt
def api_webhook_delete_user(request):
    """Webhook API: hapus user MySQL saat dihapus dari Firebase."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    from django.conf import settings as dj_settings
    auth_header = request.headers.get('Authorization')
    expected_token = getattr(dj_settings, 'FIREBASE_WEBHOOK_SECRET', None)

    if not expected_token:
        return JsonResponse({'success': False, 'error': 'Webhook not configured'}, status=500)

    if not auth_header or auth_header != f"Bearer {expected_token}":
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
        uid = data.get('uid')
        email = data.get('email')

        if not uid and not email:
            return JsonResponse({'success': False, 'error': 'Missing uid or email'}, status=400)

        from django.db.models import Q
        from django.db.models.signals import post_delete
        from ..signals import delete_firebase_user

        tamu_qs = Tamu.objects.filter(Q(google_id=uid) | Q(email=email)) if (uid or email) else Tamu.objects.none()

        post_delete.disconnect(delete_firebase_user, sender=Tamu)
        try:
            count, _ = tamu_qs.delete()
            deleted = count > 0
        finally:
            post_delete.connect(delete_firebase_user, sender=Tamu)

        if deleted:
            return JsonResponse({'success': True, 'message': 'User deleted from MySQL successfully'})
        return JsonResponse({'success': True, 'message': 'User not found in MySQL, no action taken'})

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
