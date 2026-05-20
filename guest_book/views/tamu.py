from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from .base import tamu_login_required, base_context
from ..models import Kunjungan, Pegawai, Message, Departemen
from ..forms import KunjunganForm, PesanForm
from ..utils import send_notification

def landing_view(request):
    """View untuk Landing Page utama"""
    tamu_id = request.session.get('tamu_id')
    user_logged_in = False
    user_name = ""
    
    if tamu_id:
        from ..models import Tamu
        tamu = Tamu.objects.filter(pk=tamu_id).first()
        if tamu:
            user_logged_in = True
            user_name = tamu.name

    return render(request, 'guest_book/tamu_landing.html', {
        'user_logged_in': user_logged_in,
        'user_name': user_name,
    })

def tentang_kami_view(request):
    return render(request, 'guest_book/tamu_tentang_kami.html')

def kebijakan_privasi_view(request):
    return render(request, 'guest_book/tamu_kebijakan_privasi.html')

@tamu_login_required
def dashboard_view(request, tamu):
    """View untuk Dashboard Tamu"""
    now = timezone.now()
    kunjungan_qs = Kunjungan.objects.filter(tamu=tamu)
    stats = {
        'total': kunjungan_qs.count(),
        'pending': kunjungan_qs.filter(status='pending').count(),
        'in_progress': kunjungan_qs.filter(status='in_progress').count(),
        'completed': kunjungan_qs.filter(status='completed').count(),
        'bulan_ini': kunjungan_qs.filter(arrival_time__year=now.year, arrival_time__month=now.month).count(),
    }
    kunjungan_list = kunjungan_qs.select_related('pegawai').order_by('-created_at')[:5]

    ctx = base_context(tamu, 'dashboard')
    ctx.update({'stats': stats, 'kunjungan_list': kunjungan_list})
    return render(request, 'guest_book/tamu_dashboard.html', ctx)

@tamu_login_required
def kunjungan_baru_view(request, tamu):
    form = KunjunganForm(request.POST or None)
    pegawai_list = Pegawai.objects.filter(account_status='active')

    if request.method == 'POST' and form.is_valid():
        kunjungan = form.save(commit=False)
        kunjungan.tamu = tamu
        kunjungan.status = 'pending'
        kunjungan.save()
        
        messages.success(request, "Kunjungan Anda berhasil didaftarkan!")
        
        # Notifikasi ke Admin
        send_notification(
            recipient_id='admin',
            recipient_type='admin',
            notification_type='visit_registered',
            title='Kunjungan Baru Terdaftar',
            message=f'Tamu {tamu.name} telah menjadwalkan kunjungan baru.',
            related_object_id=str(kunjungan.id)
        )
        
        # Kirim Email ke User
        from django.core.mail import EmailMultiAlternatives
        from django.template.loader import render_to_string
        from django.utils.html import strip_tags
        from django.urls import reverse
        from datetime import datetime, time
        from django.db.models import Q
        from django.utils import timezone
        
        try:
            # Hitung nomor urut & nomor unik
            arrival_date = kunjungan.arrival_time.date()
            start_of_day = timezone.make_aware(datetime.combine(arrival_date, time.min))
            end_of_day = timezone.make_aware(datetime.combine(arrival_date, time.max))
            
            count = Kunjungan.objects.filter(
                arrival_time__range=(start_of_day, end_of_day)
            ).filter(
                Q(arrival_time__lt=kunjungan.arrival_time) | Q(arrival_time=kunjungan.arrival_time, id__lt=kunjungan.id)
            ).count() + 1
            
            nomor_urut = f"{count:02d}"
            nomor_unik = str(kunjungan.id)[:8].upper()
            
            card_url = request.build_absolute_uri(reverse('tamu:tamu_cetak_kartu', kwargs={'pk': kunjungan.id}))
            
            # Render template email
            context = {
                'kunjungan': kunjungan,
                'nomor_urut': nomor_urut,
                'nomor_unik': nomor_unik,
                'card_url': card_url,
            }
            html_content = render_to_string('guest_book/email_kunjungan.html', context)
            text_content = strip_tags(html_content)
            
            # Buat pesan email
            subject = f"Jadwal Kunjungan Berhasil Didaftarkan - Kode: {nomor_unik}"
            from_email = 'no-reply@diskominfosantik.bekasikab.go.id'
            to_email = tamu.email
            
            msg = EmailMultiAlternatives(subject, text_content, from_email, [to_email])
            msg.attach_alternative(html_content, "text/html")
            msg.send()
        except Exception as e:
            # Jika gagal kirim email, log saja agar tidak menghentikan proses booking!
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Gagal mengirim email ke {tamu.email}: {str(e)}")
        
        return redirect('tamu:riwayat')

    bidang_list = Departemen.objects.all().order_by('nama')
    
    ctx = base_context(tamu, 'kunjungan_baru')
    ctx.update({'form': form, 'pegawai_list': pegawai_list, 'bidang_list': bidang_list})
    return render(request, 'guest_book/tamu_kunjungan_baru.html', ctx)

@tamu_login_required
def riwayat_view(request, tamu):
    qs = Kunjungan.objects.filter(tamu=tamu).select_related('pegawai').order_by('-arrival_time')
    status_filter = request.GET.get('status', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
        
    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        qs = qs.filter(Q(purpose__icontains=q) | Q(pegawai__name__icontains=q))
        
    date_filter = request.GET.get('date', '')
    if date_filter:
        qs = qs.filter(arrival_time__date=date_filter)

    # Calculate stats for the current user (unfiltered)
    base_qs = Kunjungan.objects.filter(tamu=tamu)
    stats = {
        'total': base_qs.count(),
        'pending': base_qs.filter(status='pending').count(),
        'cancelled': base_qs.filter(status='cancelled').count(),
    }

    paginator = Paginator(qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    ctx = base_context(tamu, 'riwayat')
    ctx.update({
        'kunjungan_list': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'stats': stats,
    })
    return render(request, 'guest_book/tamu_riwayat.html', ctx)

@tamu_login_required
def kunjungan_detail_view(request, tamu, pk):
    kunjungan = get_object_or_404(Kunjungan, pk=pk, tamu=tamu)
    status_history = kunjungan.status_history.order_by('changed_at')
    notes_list = kunjungan.notes_history.order_by('created_at')

    ctx = base_context(tamu, 'riwayat')
    ctx.update({
        'kunjungan': kunjungan,
        'status_history': status_history,
        'notes_list': notes_list,
    })
    return render(request, 'guest_book/tamu_kunjungan_detail.html', ctx)

@tamu_login_required
def kunjungan_batal_view(request, tamu, pk):
    if request.method == 'POST':
        kunjungan = get_object_or_404(Kunjungan, pk=pk, tamu=tamu, status='pending')
        kunjungan.status = 'cancelled'
        kunjungan.save(update_fields=['status', 'updated_at'])
        messages.success(request, "Kunjungan berhasil dibatalkan.")
        
        send_notification(
            recipient_id='admin',
            recipient_type='admin',
            notification_type='system_alert',
            title='Kunjungan Dibatalkan oleh Tamu',
            message=f'Tamu {tamu.name} telah membatalkan kunjungan mereka.',
            related_object_id=str(kunjungan.id)
        )
    return redirect('tamu:riwayat')

@tamu_login_required
def pesan_baru_view(request, tamu):
    form = PesanForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        Message.objects.create(
            sender_id=str(tamu.pk),
            sender_type='tamu',
            subject=d['subject'],
            content=d['content'],
            status='pending',
        )
        messages.success(request, "Pesan berhasil dikirim ke admin!")
        
        send_notification(
            recipient_id='admin',
            recipient_type='admin',
            notification_type='message_received',
            title='Pesan Baru Masuk',
            message=f'Tamu {tamu.name} mengirim pesan: "{d["subject"]}"',
            related_object_id=str(tamu.pk)
        )
        return redirect('tamu:dashboard')

    ctx = base_context(tamu, '')
    ctx['form'] = form
    return render(request, 'guest_book/tamu_pesan_baru.html', ctx)

@tamu_login_required
def notifications_view(request, tamu):
    """View untuk daftar notifikasi pengguna (tamu)"""
    from ..models import Notification
    from django.utils import timezone
    notifications = Notification.objects.filter(
        recipient_id=str(tamu.pk), 
        recipient_type='tamu'
    ).order_by('-created_at')

    # Jika belum ada notifikasi, buat satu notifikasi selamat datang agar tidak kosong
    if not notifications.exists():
        Notification.objects.create(
            recipient_id=str(tamu.pk),
            recipient_type='tamu',
            notification_type='system_alert',
            title='Sistem Notifikasi Aktif',
            message='Fitur notifikasi Anda telah diaktifkan secara real-time. Anda akan menerima pembaruan status kunjungan dan pesan di sini.',
            status='unread'
        )
        # Re-query
        notifications = Notification.objects.filter(
            recipient_id=str(tamu.pk), 
            recipient_type='tamu'
        ).order_by('-created_at')

    # Mark all as read
    notifications.filter(status='unread').update(status='read', read_at=timezone.now())

    ctx = base_context(tamu, 'notifications')
    ctx['notifications'] = notifications
    return render(request, 'guest_book/tamu_notifications.html', ctx)
@tamu_login_required
def user_chat_view(request, tamu):
    """View untuk Chat Tamu ke Admin (WA Style)"""
    from ..models import ChatMessage, Admin, Pegawai
    session_id = str(tamu.pk)
    messages_qs = ChatMessage.objects.filter(session_id=session_id).order_by('created_at')
    messages_list = list(messages_qs)
    
    # Mark read messages from admin
    ChatMessage.objects.filter(session_id=session_id, sender_type='admin', is_read=False).update(is_read=True)
    
    # Optimasi: Ambil semua sender yang terlibat
    admin_ids = [msg.sender_id for msg in messages_list if msg.sender_type == 'admin']
    pegawai_ids = [msg.sender_id for msg in messages_list if msg.sender_type == 'pegawai']
    
    # Validasi UUID agar tidak error jika ada data kotor (misal: "null")
    import uuid
    def is_valid_uuid(val):
        if not val:
            return False
        try:
            uuid.UUID(str(val))
            return True
        except (ValueError, AttributeError, TypeError):
            return False
            
    valid_admin_ids = [uid for uid in admin_ids if is_valid_uuid(uid)]
    valid_pegawai_ids = [uid for uid in pegawai_ids if is_valid_uuid(uid)]
    
    admins = {str(a.pk): a for a in Admin.objects.filter(pk__in=valid_admin_ids)}
    pegawais = {str(p.pk): p for p in Pegawai.objects.filter(pk__in=valid_pegawai_ids)}
    
    # Fallback untuk sender_id 'admin' (data lama/hardcoded)
    from ..models import Admin
    default_admin = Admin.objects.first()
    
    for msg in messages_list:
        if msg.sender_type == 'tamu':
            msg.sender_obj = tamu
        elif msg.sender_type == 'admin':
            if msg.sender_id == 'admin':
                msg.sender_obj = default_admin
            else:
                msg.sender_obj = admins.get(msg.sender_id)
        elif msg.sender_type == 'pegawai':
            msg.sender_obj = pegawais.get(msg.sender_id)
            
    ctx = base_context(tamu, 'chat')
    ctx.update({
        'messages_list': messages_list,
        'session_id': session_id,
    })
    return render(request, 'guest_book/tamu_chat.html', ctx)

@tamu_login_required
def tamu_kunjungan_cetak_pdf(request, tamu):
    """View untuk mencetak riwayat kunjungan tamu ke PDF (via browser print)"""
    qs = Kunjungan.objects.filter(tamu=tamu).select_related('pegawai').order_by('-arrival_time')
    
    # Terapkan filter yang sama dengan halaman riwayat
    status_filter = request.GET.get('status', '')
    if status_filter:
        qs = qs.filter(status=status_filter)
        
    q = request.GET.get('q', '').strip()
    if q:
        from django.db.models import Q
        qs = qs.filter(Q(purpose__icontains=q) | Q(pegawai__name__icontains=q))
        
    date_filter = request.GET.get('date', '')
    if date_filter:
        qs = qs.filter(arrival_time__date=date_filter)

    ctx = base_context(tamu, 'riwayat')
    ctx.update({
        'kunjungan_list': qs,
    })
    return render(request, 'guest_book/tamu_kunjungan_cetak_pdf.html', ctx)

@tamu_login_required
def profil_view(request, tamu):
    """View untuk profil pengguna (tamu)"""
    total_kunjungan = Kunjungan.objects.filter(tamu=tamu).count()
    total_instansi = Kunjungan.objects.filter(tamu=tamu).values('pegawai__department').distinct().count()
    recent_visits = Kunjungan.objects.filter(tamu=tamu).order_by('-arrival_time')[:3]
    
    # Hitung kapan terakhir ganti password
    from ..models import AuditLog
    last_change_date = tamu.registration_date
    logs = AuditLog.objects.filter(
        user_id=str(tamu.id),
        user_type='tamu',
        action='update',
        table_name='tamu'
    ).order_by('-timestamp')
    
    for log in logs:
        if log.new_value and 'password' in log.new_value:
            last_change_date = log.timestamp
            break
            
    days_since_change = (timezone.now() - last_change_date).days
    needs_password_change = days_since_change >= 90
    
    ctx = base_context(tamu, 'profil')
    ctx.update({
        'tamu': tamu,
        'total_kunjungan': total_kunjungan,
        'total_instansi': total_instansi,
        'recent_visits': recent_visits,
        'needs_password_change': needs_password_change,
        'days_since_change': days_since_change,
    })
    return render(request, 'guest_book/tamu_profil.html', ctx)


@tamu_login_required
def tamu_cetak_kartu_view(request, tamu, pk):
    """View untuk mencetak kartu pengunjung oleh user"""
    from django.shortcuts import get_object_or_404
    from ..models import Kunjungan, Instansi
    
    kunjungan = get_object_or_404(Kunjungan, pk=pk, tamu=tamu)
    
    # Ambil data instansi untuk logo/nama
    instansi = Instansi.objects.first()
    
    # Hitung nomor urut untuk hari tersebut
    from datetime import datetime, time
    from django.db.models import Q
    
    arrival_date = kunjungan.arrival_time.date()
    start_of_day = timezone.make_aware(datetime.combine(arrival_date, time.min))
    end_of_day = timezone.make_aware(datetime.combine(arrival_date, time.max))
    
    count = Kunjungan.objects.filter(
        arrival_time__range=(start_of_day, end_of_day)
    ).filter(
        Q(arrival_time__lt=kunjungan.arrival_time) | Q(arrival_time=kunjungan.arrival_time, id__lt=kunjungan.id)
    ).count() + 1
    
    nomor_urut = f"{count:02d}"
    nomor_unik = str(kunjungan.id)[:8].upper()
    
    ctx = base_context(tamu, 'riwayat')
    ctx.update({
        'kunjungan': kunjungan,
        'instansi': instansi,
        'nomor_urut': nomor_urut,
        'nomor_unik': nomor_unik,
    })
    return render(request, 'guest_book/admin_cetak_kartu.html', ctx)
