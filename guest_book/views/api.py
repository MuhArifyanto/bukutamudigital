import json
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from .base import admin_login_required, tamu_login_required
from ..models import Notification, Kunjungan, KunjunganStatusHistory, Tamu, CalendarSettings
from ..utils import send_notification
from django.contrib.auth.hashers import make_password

@admin_login_required
def api_mark_notification_read(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            notif_id = data.get('notification_id')
            if notif_id:
                Notification.objects.filter(id=notif_id).update(status='read', read_at=timezone.now())
                return JsonResponse({'success': True})
        except: pass
    return JsonResponse({'success': False}, status=400)

def api_mark_all_notifications_read(request):
    if request.method == 'POST':
        try:
            recipient_id = 'admin'
            recipient_type = 'admin'
            if request.session.get('tamu_id'):
                recipient_id = str(request.session.get('tamu_id'))
                recipient_type = 'tamu'
            
            Notification.objects.filter(
                recipient_id=recipient_id,
                recipient_type=recipient_type,
                status='unread'
            ).update(status='read', read_at=timezone.now())
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)}, status=400)
    return JsonResponse({'success': False, 'error': 'Invalid method'}, status=400)

@admin_login_required
def api_update_kunjungan_status(request):
    """API untuk update status kunjungan oleh Admin (Secure)"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            kunjungan_id = data.get('kunjungan_id')
            new_status = data.get('status')
            
            kunjungan = Kunjungan.objects.get(id=kunjungan_id)
            old_status = kunjungan.status
            kunjungan.status = new_status
            if new_status == 'completed':
                kunjungan.departure_time = timezone.now()
            kunjungan.save()
            
            KunjunganStatusHistory.objects.create(
                kunjungan=kunjungan,
                old_status=old_status,
                new_status=new_status,
                changed_by_id='admin',
                changed_by_type='admin'
            )
            
            send_notification(
                recipient_id=str(kunjungan.tamu.pk),
                recipient_type='tamu',
                notification_type='system_alert',
                title='Pembaruan Status Kunjungan',
                message=f'Status kunjungan Anda telah diperbarui menjadi: {kunjungan.get_status_display()}',
                related_object_id=str(kunjungan.id)
            )
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid method'}, status=405)

def api_get_unread_count(request):
    """API untuk mengambil jumlah notifikasi belum dibaca (Admin & Tamu)"""
    if not request.user.is_authenticated and not request.session.get('tamu_id'):
        return JsonResponse({'unread_count': 0})
        
    recipient_id = 'admin'
    recipient_type = 'admin'
    
    if request.session.get('tamu_id'):
        recipient_id = str(request.session.get('tamu_id'))
        recipient_type = 'tamu'
        
    count = Notification.objects.filter(
        recipient_id=recipient_id, 
        recipient_type=recipient_type, 
        status='unread'
    ).count()
    return JsonResponse({'unread_count': count})

def api_get_recent_notifications(request):
    """API untuk mengambil notifikasi terbaru untuk dropdown (Admin & Tamu)"""
    if not request.user.is_authenticated and not request.session.get('tamu_id'):
        return JsonResponse({'notifications': []})
        
    recipient_id = 'admin'
    recipient_type = 'admin'
    
    if request.session.get('tamu_id'):
        recipient_id = str(request.session.get('tamu_id'))
        recipient_type = 'tamu'
        
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 5)
        
    qs = Notification.objects.filter(
        recipient_id=recipient_id, 
        recipient_type=recipient_type
    ).order_by('-created_at')
    
    from django.core.paginator import Paginator
    paginator = Paginator(qs, page_size)
    try:
        notifications = paginator.page(page)
    except:
        notifications = paginator.page(1)
    
    from django.utils import timezone
    data = []
    for n in notifications:
        local_time = timezone.localtime(n.created_at)
        data.append({
            'title': n.title,
            'message': n.message,
            'created_at': local_time.strftime('%H:%M'),
            'status': n.status,
            'notification_type': n.notification_type,
            'related_object_id': n.related_object_id
        })
        
    return JsonResponse({
        'notifications': data,
        'pagination': {
            'has_next': notifications.has_next(),
            'has_previous': notifications.has_previous(),
            'current_page': notifications.number,
            'total_pages': paginator.num_pages,
            'total_items': paginator.count
        }
    })

@admin_login_required
def api_update_quota(request):
    """API untuk update kuota harian kalender"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            date_str = data.get('date')
            quota = data.get('quota')
            is_holiday = data.get('is_holiday')
            holiday_name = data.get('holiday_name')
            
            setting, created = CalendarSettings.objects.get_or_create(date=date_str)
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
    """API untuk toggle status libur pada tanggal tertentu"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            date_str = data.get('date')
            setting, created = CalendarSettings.objects.get_or_create(date=date_str)
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
    """API untuk import data kalender dari Excel/CSV"""
    import pandas as pd
    from django.contrib import messages
    from django.http import JsonResponse
    from ..models import CalendarSettings # Sesuaikan jika path models berbeda
    
    print("=== [DEBUG] MENGAKSES API IMPORT KALENDER ===")

    if request.method != 'POST' or not request.FILES.get('file'):
        print("=== [DEBUG] GAGAL: Method bukan POST atau tidak ada file ===")
        messages.error(request, 'File tidak ditemukan atau metode tidak valid.')
        return JsonResponse({'error': 'File tidak ditemukan'}, status=400)
        
    file = request.FILES['file']
    filename = file.name.lower()
    print(f"=== [DEBUG] File diterima: {filename} ===")
    
    try:
        # Baca file
        if filename.endswith('.csv'):
            # Gunakan sep=None dan engine='python' untuk mendeteksi separator otomatis (, atau ;)
            df = pd.read_csv(file, sep=None, engine='python')
            print("=== [DEBUG] Berhasil membaca CSV (Auto-detect separator) ===")
        elif filename.endswith('.xlsx') or filename.endswith('.xls'):
            df = pd.read_excel(file)
            print("=== [DEBUG] Berhasil membaca Excel ===")
        else:
            print("=== [DEBUG] GAGAL: Format file tidak didukung ===")
            messages.error(request, 'Format file tidak didukung. Harap gunakan .csv, .xlsx, atau .xls.')
            return JsonResponse({'error': 'Format file tidak didukung'}, status=400)
            
        # Cari baris yang berisi kolom 'tanggal' atau 'date'
        expected_cols = ['tanggal', 'date']
        
        # Coba cek di columns awal
        columns_lower = [str(c).lower().strip() for c in df.columns]
        has_date = any(col in columns_lower for col in expected_cols)
        
        if has_date:
            print("=== [DEBUG] Header ditemukan di baris pertama ===")
            df.columns = columns_lower
        else:
            # Jika tidak ada, cek baris pertama data (index 0)
            if len(df) > 0:
                first_row = [str(c).lower().strip() for c in df.iloc[0]]
                has_date_in_row = any(col in first_row for col in expected_cols)
                if has_date_in_row:
                    print("=== [DEBUG] Header ditemukan di baris pertama data, mempromosikan... ===")
                    df.columns = first_row
                    df = df.iloc[1:]
                else:
                    print("=== [DEBUG] GAGAL: Kolom tanggal tidak ditemukan ===")
                    messages.error(request, 'Kolom Tanggal tidak ditemukan dalam file.')
                    return JsonResponse({'error': 'Kolom Tanggal tidak ditemukan'}, status=400)
            else:
                print("=== [DEBUG] GAGAL: File kosong ===")
                messages.error(request, 'File kosong.')
                return JsonResponse({'error': 'File kosong'}, status=400)

        print(f"=== [DEBUG] Kolom yang akan diproses: {list(df.columns)} ===")
        print(f"=== [DEBUG] Jumlah baris data yang dibaca: {len(df)} ===")
        
        success_count = 0
        errors = []
        
        for i, row in df.iterrows():
            date_val = row.get('tanggal') or row.get('date')
            quota = row.get('kuota') or row.get('quota') or 50
            libur_raw = str(row.get('libur') or 'tidak').lower()
            is_holiday = libur_raw in ['ya', 'yes', '1', 'true']
            holiday_name = row.get('nama_libur') or row.get('keterangan libur') or row.get('keterangan_libur') or ''
            
            # Pastikan tanggal tidak kosong/NaN
            if pd.notna(date_val) and str(date_val).strip() != '':
                try:
                    dt = pd.to_datetime(date_val).date()
                    setting, _ = CalendarSettings.objects.get_or_create(date=dt)
                    
                    # Konversi kuota dengan aman
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
            
        print(f"=== [DEBUG] SELESAI: {msg} ===")
        messages.success(request, msg)
        return JsonResponse({'success': True, 'message': msg})
        
    except Exception as e:
        print(f"=== [DEBUG] EXCEPTION FATAL: {str(e)} ===")
        messages.error(request, f'Gagal memproses file: {str(e)}')
        return JsonResponse({'error': f'Gagal memproses file: {str(e)}'}, status=400)

@admin_login_required
def api_send_chat_message(request):
    """API untuk mengirim pesan chat (Admin)"""
    import json
    from ..models import ChatMessage
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        content = data.get('content')
        
        if not session_id or not content:
            return JsonResponse({'success': False, 'error': 'Data tidak lengkap'}, status=400)
            
        msg = ChatMessage.objects.create(
            session_id=session_id,
            sender_id='admin', 
            sender_type='admin',
            content=content
        )
        
        # Buat notifikasi untuk Tamu
        from ..models import Notification
        Notification.objects.create(
            recipient_id=session_id,
            recipient_type='tamu',
            notification_type='message_replied',
            title='Pesan Dibalas oleh Admin',
            message=f'Admin: {content}',
            related_object_id='admin'
        )
        
        return JsonResponse({
            'success': True, 
            'message': {
                'id': str(msg.id),
                'content': msg.content,
                'created_at': msg.created_at.strftime('%H:%M')
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@csrf_exempt
def api_upload_chat_file(request):
    """API untuk mengunggah file/gambar dalam chat ke Local Storage"""
    from django.http import JsonResponse
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
        
    # Cek login
    is_logged_in = False
    if request.user.is_authenticated and request.user.is_staff:
        is_logged_in = True
    elif request.session.get('tamu_id'):
        is_logged_in = True
        
    if not is_logged_in:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)
        
    file_obj = request.FILES.get('file')
    if not file_obj:
        return JsonResponse({'success': False, 'error': 'No file uploaded'}, status=400)
        
    # Validasi Ukuran (Max 5MB)
    if file_obj.size > 5 * 1024 * 1024:
        return JsonResponse({'success': False, 'error': 'Ukuran file melebihi 5 MB'}, status=400)
        
    # Validasi Ekstensi
    ext = file_obj.name.split('.')[-1].lower() if '.' in file_obj.name else ''
    allowed_extensions = ['doc', 'docx', 'xls', 'xlsx', 'png', 'jpg', 'jpeg', 'svg']
    if ext not in allowed_extensions:
        return JsonResponse({'success': False, 'error': 'Format file tidak diizinkan untuk alasan keamanan'}, status=400)
        
    from django.core.files.storage import default_storage
    from django.conf import settings
    import uuid
    
    # Generate random name to prevent collisions and execution
    safe_name = f"{uuid.uuid4().hex[:10]}_{file_obj.name.replace(' ', '_')}"
    path = default_storage.save(f'chat_attachments/{safe_name}', file_obj)
    file_url = f'{settings.MEDIA_URL}{path}'
    
    if ext in ['jpg', 'jpeg', 'png', 'svg']:
        message_type = 'image'
    else:
        message_type = 'file'
        
    return JsonResponse({
        'success': True,
        'file_url': file_url,
        'file_path': path,
        'message_type': message_type,
        'file_name': file_obj.name
    })

def api_search_users(request):
    """API untuk mencari user (Tamu) untuk mulai chat baru"""
    from ..models import Tamu
    from django.http import JsonResponse
    from django.core.paginator import Paginator
    
    query = request.GET.get('q', '')
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 10)
    
    if not query:
        return JsonResponse({'success': True, 'users': []})
        
    qs = Tamu.objects.filter(name__icontains=query)
    paginator = Paginator(qs, page_size)
    try:
        users = paginator.page(page)
    except:
        users = paginator.page(1)
        
    users_data = [{'id': str(u.id), 'name': u.name, 'email': u.email} for u in users]
    
    return JsonResponse({
        'success': True, 
        'users': users_data,
        'pagination': {
            'has_next': users.has_next(),
            'has_previous': users.has_previous(),
            'current_page': users.number,
            'total_pages': paginator.num_pages,
            'total_items': paginator.count
        }
    })

@admin_login_required
def api_get_chat_messages(request):
    """API untuk mengambil history chat terbaru"""
    from ..models import ChatMessage
    from django.core.paginator import Paginator
    session_id = request.GET.get('session_id')
    last_id = request.GET.get('last_id')
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 50)
    
    if not session_id:
        return JsonResponse({'success': False, 'error': 'session_id required'}, status=400)
        
    qs = ChatMessage.objects.filter(session_id=session_id)
    if last_id:
        try:
            last_msg = ChatMessage.objects.get(id=last_id)
            qs = qs.filter(created_at__gt=last_msg.created_at)
        except: pass
        
    qs = qs.order_by('-created_at')
    paginator = Paginator(qs, page_size)
    try:
        page_obj = paginator.page(page)
    except:
        page_obj = paginator.page(1)
        
    messages = []
    # Reverse to return chronological order
    for m in reversed(page_obj.object_list):
        messages.append({
            'id': str(m.id),
            'content': m.content,
            'sender_type': m.sender_type,
            'created_at': m.created_at.strftime('%H:%M')
        })
        # Mark as read if it's from user
        if m.sender_type == 'tamu':
            m.is_read = True
            m.save()
            
    return JsonResponse({
        'success': True, 
        'messages': messages,
        'pagination': {
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
            'current_page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_items': paginator.count
        }
    })

@admin_login_required
def api_quick_checkin(request):
    """API untuk pendaftaran tamu cepat dari dashboard admin"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            name = data.get('name')
            instansi = data.get('instansi', '')
            purpose = data.get('purpose', 'Kunjungan Mendadak')
            time_str = data.get('time', '09:00')
            date_str = data.get('date', timezone.now().date().isoformat())
            status = data.get('status', 'in_progress')
            pegawai_id = data.get('pegawai_id')
            visit_id = data.get('visit_id')
            
            # 1. Cari atau buat tamu (Gunakan email dummy jika tidak ada)
            email_dummy = f"quick_{name.lower().replace(' ', '_')}@guest.local"
            tamu = Tamu.objects.filter(name=name).first()
            if not tamu:
                tamu = Tamu.objects.create(
                    name=name, 
                    email=email_dummy, 
                    instansi=instansi,
                    account_status='active',
                    registration_type='manual'
                )
            
            # 2. Cari Pegawai jika ada
            from ..models import Pegawai
            pegawai = None
            if pegawai_id:
                pegawai = Pegawai.objects.filter(id=pegawai_id).first()
            
            # 3. Buat atau Update Kunjungan
            arrival_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            arrival_dt = timezone.make_aware(arrival_dt)
            
            if visit_id:
                kunjungan = Kunjungan.objects.filter(id=visit_id).first()
                if not kunjungan:
                    return JsonResponse({'success': False, 'error': 'Kunjungan tidak ditemukan'}, status=404)
                kunjungan.arrival_time = arrival_dt
                kunjungan.purpose = purpose
                kunjungan.status = status
                kunjungan.pegawai = pegawai
                kunjungan.save()
            else:
                kunjungan = Kunjungan.objects.create(
                    tamu=tamu,
                    arrival_time=arrival_dt,
                    purpose=purpose,
                    status=status,
                    pegawai=pegawai
                )
            
            # 4. Buat Notifikasi Kunjungan Baru untuk Admin
            from ..models import Notification, Instansi
            Notification.objects.create(
                recipient_id='admin',
                recipient_type='admin',
                notification_type='visit_registered',
                title='Kunjungan Baru Terdaftar',
                message=f'{tamu.name} dari {tamu.instansi} telah mendaftar kunjungan.',
                related_object_id=str(kunjungan.id)
            )
            
            # 5. Buat Notifikasi untuk Pegawai (Jika dipilih)
            if pegawai:
                Notification.objects.create(
                    recipient_id=str(pegawai.id),
                    recipient_type='pegawai',
                    notification_type='visit_registered',
                    title='Ada Tamu untuk Anda!',
                    message=f'Tamu {tamu.name} dari {tamu.instansi} ingin menemui Anda.',
                    related_object_id=str(kunjungan.id)
                )
            
            # 6. Cek Kuota & Buat Notifikasi jika Penuh
            instansi_obj = Instansi.objects.first()
            if instansi_obj:
                today_date = timezone.now().date()
                current_visits = Kunjungan.objects.filter(arrival_time__date=today_date, status='in_progress').count()
                if current_visits >= instansi_obj.kapasitas_maksimal:
                    Notification.objects.create(
                        recipient_id='admin',
                        recipient_type='admin',
                        notification_type='quota_reached',
                        title='Kuota Kunjungan Penuh!',
                        message=f'Kapasitas kunjungan untuk hari ini telah mencapai batas maksimal ({instansi_obj.kapasitas_maksimal}).',
                        related_object_id=str(instansi_obj.id)
                    )
            
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    return JsonResponse({'error': 'Invalid method'}, status=405)

def api_google_holidays(request, year):
    """API untuk mengambil data libur (Public)"""
    from ..utils import get_google_calendar_holidays
    holidays = get_google_calendar_holidays(year)
    if not holidays:
        holidays = [{'date': f'{year}-01-01', 'name': 'Tahun Baru (Fallback)'}]
    return JsonResponse({'year': year, 'holidays': holidays})

@admin_login_required
def api_get_visits_by_date(request):
    """API untuk mengambil daftar kunjungan berdasarkan tanggal"""
    date_str = request.GET.get('date')
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 50)
    
    if not date_str:
        return JsonResponse({'success': False, 'error': 'Tanggal wajib diisi'}, status=400)
        
    try:
        from ..models import Kunjungan
        from django.core.paginator import Paginator
        
        qs = Kunjungan.objects.filter(arrival_time__date=date_str).order_by('arrival_time')
        paginator = Paginator(qs, page_size)
        try:
            visits = paginator.page(page)
        except:
            visits = paginator.page(1)
            
        data = []
        for v in visits:
            data.append({
                'id': v.id,
                'tamu_name': v.tamu.name if v.tamu else '-',
                'instansi': v.tamu.instansi if v.tamu else '-',
                'time': v.arrival_time.strftime('%H:%M'),
                'status': v.status,
                'purpose': v.purpose
            })
        return JsonResponse({
            'success': True, 
            'visits': data,
            'pagination': {
                'has_next': visits.has_next(),
                'has_previous': visits.has_previous(),
                'current_page': visits.number,
                'total_pages': paginator.num_pages,
                'total_items': paginator.count
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@admin_login_required
def api_update_profile_picture(request):
    """API untuk memperbarui foto profil admin"""
    from django.http import JsonResponse
    from ..models import Tamu
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
        
    file_obj = request.FILES.get('profile_picture')
    if not file_obj:
        return JsonResponse({'success': False, 'error': 'No file uploaded'}, status=400)
        
    admin_user = Tamu.objects.filter(is_admin=True).first() or Tamu.objects.filter(nik='admin').first()
    if admin_user:
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
        
        return JsonResponse({
            'success': True,
            'file_url': admin_user.profile_picture.url
        })
    else:
        return JsonResponse({'success': False, 'error': 'Admin record tidak ditemukan'}, status=404)

@tamu_login_required
def api_tamu_update_profile_picture(request, tamu):
    """API untuk memperbarui foto profil tamu (warga)"""
    from django.http import JsonResponse
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
        
    file_obj = request.FILES.get('profile_picture')
    if not file_obj:
        return JsonResponse({'success': False, 'error': 'No file uploaded'}, status=400)
        
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
    
    return JsonResponse({
        'success': True,
        'file_url': tamu.profile_picture.url
    })

@tamu_login_required
def api_tamu_update_profile_data(request, tamu):
    """API untuk memperbarui data pribadi tamu (warga)"""
    from django.http import JsonResponse
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
        
    import json
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
        record_audit_log(
            user_id=str(tamu.id),
            user_type='tamu',
            action='update',
            table_name='tamu',
            record_id=str(tamu.id),
            new_value={'phone': tamu.phone, 'instansi': tamu.instansi},
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@admin_login_required
def api_update_profile_data(request):
    """API untuk memperbarui data pribadi admin"""
    from django.http import JsonResponse
    from ..models import Tamu
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
        
    import json
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
            record_audit_log(
                user_id=str(admin_user.id),
                user_type='admin',
                action='update',
                table_name='tamu',
                record_id=str(admin_user.id),
                new_value={'name': name, 'email': email, 'nip': nip, 'jabatan': jabatan},
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'error': 'Admin record tidak ditemukan'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@admin_login_required
def api_change_password(request):
    """API untuk mengganti password admin (Secure)"""
    if request.method == 'POST':
        new_pw = request.POST.get('new_password')
        if not new_pw:
            return JsonResponse({'success': False, 'error': 'Password tidak boleh kosong'})
        admin_user = Tamu.objects.filter(is_admin=True).first() or Tamu.objects.filter(nik='admin').first()
        if admin_user:
            admin_user.password = make_password(new_pw)
            admin_user.save(update_fields=['password'])
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'error': 'Admin record tidak ditemukan'})
    return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

def api_check_quota(request):
    """API untuk mengecek kuota kunjungan pada tanggal tertentu (Akses Publik/Tamu)"""
    date_str = request.GET.get('date')
    if not date_str:
        return JsonResponse({'success': False, 'error': 'Tanggal wajib diisi'}, status=400)
        
    try:
        from datetime import datetime
        date_obj = datetime.strptime(date_str, '%Y-%m-%d').date()
        
        # Ambil settings dari DB
        setting = CalendarSettings.objects.filter(date=date_obj).first()
        quota = setting.daily_quota if setting else 50
        is_holiday = setting.is_holiday if setting else False
        holiday_name = setting.holiday_name if setting else ''
        
        # Hitung jumlah kunjungan yang sudah terdaftar
        booked = Kunjungan.objects.filter(arrival_time__startswith=date_str).count()
        
        return JsonResponse({
            'success': True,
            'quota': quota,
            'booked': booked,
            'is_holiday': is_holiday,
            'holiday_name': holiday_name,
            'available': quota - booked if not is_holiday else 0
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@admin_login_required
def api_import_visits_excel(request):
    """API untuk import data kunjungan (Daftar Tamu) dari Excel"""
    if request.method == 'POST' and request.FILES.get('file'):
        file = request.FILES['file']
        try:
            import pandas as pd
            df = pd.read_excel(file)
            df.columns = [str(c).lower().strip() for c in df.columns]
            
            # Cek kolom wajib
            required_cols = ['tanggal', 'nama tamu']
            if not all(col in df.columns for col in required_cols):
                return JsonResponse({'error': 'File harus memiliki kolom "Tanggal" dan "Nama Tamu"'}, status=400)
                
            success_count = 0
            for _, row in df.iterrows():
                date_val = row.get('tanggal')
                nama_tamu = row.get('nama tamu') or row.get('nama')
                instansi = row.get('instansi') or ''
                keperluan = row.get('keperluan') or row.get('tujuan') or 'Kunjungan'
                jam = row.get('jam') or '09:00'
                
                if date_val and nama_tamu:
                    try:
                        # Parse date and time
                        dt = pd.to_datetime(f"{date_val} {jam}")
                        dt = timezone.make_aware(dt)
                        
                        # Cari atau buat tamu
                        from ..models import Tamu, Kunjungan
                        email_dummy = f"import_{str(nama_tamu).lower().replace(' ', '_')}@guest.local"
                        tamu, created = Tamu.objects.get_or_create(
                            name=nama_tamu,
                            defaults={
                                'email': email_dummy,
                                'instansi': instansi,
                                'account_status': 'active',
                                'registration_type': 'manual'
                            }
                        )
                        
                        # Buat Kunjungan
                        Kunjungan.objects.create(
                            tamu=tamu,
                            arrival_time=dt,
                            purpose=keperluan,
                            status='pending'
                        )
                        success_count += 1
                    except: continue
                    
            return JsonResponse({'success': True, 'message': f'{success_count} kunjungan berhasil diimpor.'})
        except Exception as e:
            return JsonResponse({'error': f'Gagal memproses file: {str(e)}'}, status=400)
    return JsonResponse({'error': 'File tidak ditemukan'}, status=400)

def api_debug_calendar_settings(request):
    """API Debug untuk melihat data CalendarSettings"""
    from ..models import CalendarSettings
    data = []
    for s in CalendarSettings.objects.order_by('-date')[:20]:
        data.append({
            'date': s.date.isoformat(),
            'quota': s.daily_quota,
            'is_holiday': s.is_holiday,
            'holiday_name': s.holiday_name
        })
    return JsonResponse({'success': True, 'data': data})

@admin_login_required
def api_update_notification_settings(request):
    """API untuk memperbarui preferensi notifikasi admin"""
    if request.method == 'POST':
        try:
            import json
            import os
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

def api_dashboard_stats(request):
    """API untuk mengambil statistik dashboard secara real-time"""
    from django.utils import timezone
    from datetime import datetime
    from ..models import Tamu, Kunjungan, CalendarSettings
    
    now = timezone.localtime(timezone.now())
    today = now.date()
    
    total_tamu = Tamu.objects.count()
    
    start_of_today = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    end_of_today = timezone.make_aware(datetime.combine(today, datetime.max.time()))
    
    kunjungan_hari_ini = Kunjungan.objects.filter(arrival_time__range=(start_of_today, end_of_today)).count()
    menunggu_verifikasi = Kunjungan.objects.filter(status='pending').count()
    
    setting = CalendarSettings.objects.filter(date=today).first()
    quota = setting.daily_quota if setting else 50
    sisa_slot = quota - kunjungan_hari_ini
    if sisa_slot < 0: sisa_slot = 0
    
    return JsonResponse({
        'success': True,
        'total_tamu': total_tamu,
        'kunjungan_hari_ini': kunjungan_hari_ini,
        'menunggu_verifikasi': menunggu_verifikasi,
        'quota': quota,
        'sisa_slot': sisa_slot
    })

def api_debug_counts(request):
    """API Debug untuk melihat data kunjungan"""
    from django.utils import timezone
    from ..models import Kunjungan
    
    year = 2026
    month = 5
    
    kunjungan_month = Kunjungan.objects.filter(
        arrival_time__startswith=f"{year}-{month:02d}"
    )
    
    data = []
    for k in kunjungan_month:
        data.append({
            'id': str(k.id),
            'arrival_time': k.arrival_time.isoformat() if k.arrival_time else None,
            'day': k.arrival_time.day if k.arrival_time else None
        })
        
    return JsonResponse({
        'count': kunjungan_month.count(),
        'data': data
    })


@csrf_exempt
def api_webhook_delete_user(request):
    """
    Webhook API to delete user in MySQL when deleted from Firebase.
    Triggered by Firebase Cloud Functions.
    Secured by a Shared Secret Token in Authorization header.
    """
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    # 1. Verify webhook secret
    from django.conf import settings
    auth_header = request.headers.get('Authorization')
    expected_token = getattr(settings, 'FIREBASE_WEBHOOK_SECRET', None)
    
    if not expected_token:
        import os
        expected_token = os.environ.get('FIREBASE_WEBHOOK_SECRET', 'super-secret-webhook-key-12345')

    if not auth_header or auth_header != f"Bearer {expected_token}":
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    try:
        data = json.loads(request.body)
        uid = data.get('uid')
        email = data.get('email')

        if not uid and not email:
            return JsonResponse({'success': False, 'error': 'Missing uid or email'}, status=400)

        deleted = False
        from django.db.models import Q
        tamu_qs = Tamu.objects.filter(Q(google_id=uid) | Q(email=email)) if uid or email else Tamu.objects.none()
        
        # Disconnect signal temporarily to avoid infinite deletion loop
        from django.db.models.signals import post_delete
        from ..signals import delete_firebase_user
        
        post_delete.disconnect(delete_firebase_user, sender=Tamu)
        try:
            count, _ = tamu_qs.delete()
            if count > 0:
                deleted = True
        finally:
            post_delete.connect(delete_firebase_user, sender=Tamu)

        if deleted:
            return JsonResponse({'success': True, 'message': 'User deleted from MySQL successfully'})
        else:
            return JsonResponse({'success': True, 'message': 'User not found in MySQL, no action taken'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
def api_delete_chat_message(request, message_id):
    """API untuk menghapus pesan obrolan (chat) oleh admin"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)
        
    # Verifikasi admin
    if not (request.user.is_authenticated and request.user.is_staff) and not request.session.get('tamu_id'):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)
        
    try:
        from ..models import ChatMessage
        msg = ChatMessage.objects.get(id=message_id)
        
        # Log to audit trail
        from .base import record_audit_log
        admin_id = request.session.get('tamu_id', 'admin')
        
        content_excerpt = msg.content[:50] + '...' if len(msg.content) > 50 else msg.content
        
        record_audit_log(
            user_id=str(admin_id),
            user_type='admin',
            action='delete',
            table_name='chat_message',
            record_id=str(msg.id),
            old_value=f"Menghapus chat: {content_excerpt}",
            ip_address=request.META.get('REMOTE_ADDR')
        )
        
        msg.delete()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)

@csrf_exempt
def api_toggle_user_status(request, user_id):
    """API untuk blokir/aktifkan tamu"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)
        
    # Harus admin
    if not (request.user.is_authenticated and request.user.is_staff) and not request.session.get('tamu_id'):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)
        
    try:
        from ..models import Tamu
        tamu_obj = Tamu.objects.get(id=user_id)
        
        new_status = request.POST.get('status')
        if new_status not in dict(Tamu.STATUS_CHOICES).keys():
            return JsonResponse({'success': False, 'error': 'Status invalid'}, status=400)
            
        old_status = tamu_obj.account_status
        tamu_obj.account_status = new_status
        tamu_obj.save()
        
        # Log to audit trail
        from .base import record_audit_log
        admin_id = request.session.get('tamu_id', 'admin')
        
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
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
