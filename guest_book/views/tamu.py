import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from django.db.models import Count, Q as _Q
from .base import tamu_login_required, base_context
from ..models import Kunjungan, Pegawai, Message, Departemen
from ..forms import KunjunganForm, PesanForm
from ..utils import send_notification

logger = logging.getLogger(__name__)

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
    base_qs = Kunjungan.objects.filter(tamu=tamu)

    # 1 query: semua status sekaligus via conditional Count
    agg = base_qs.aggregate(
        total=Count('id'),
        pending=Count('id', filter=_Q(status__in=['menunggu_admin', 'menunggu_pegawai', 'disetujui_pegawai'])),
        in_progress=Count('id', filter=_Q(status='in_progress')),
        completed=Count('id', filter=_Q(status='completed')),
        bulan_ini=Count('id', filter=_Q(
            arrival_time__year=now.year,
            arrival_time__month=now.month,
        )),
    )
    stats = agg  # aggregate() langsung kembalikan dict dengan key yang sama
    
    q = request.GET.get('q', '').strip()
    kunjungan_qs = base_qs
    if q:
        from django.db.models import Q
        kunjungan_qs = kunjungan_qs.filter(Q(purpose__icontains=q) | Q(pegawai__name__icontains=q))
        
    kunjungan_list = kunjungan_qs.select_related('pegawai').order_by('-created_at')[:5]

    ctx = base_context(tamu, 'dashboard')
    ctx.update({'stats': stats, 'kunjungan_list': kunjungan_list})
    return render(request, 'guest_book/tamu_dashboard.html', ctx)

@tamu_login_required
def kunjungan_baru_view(request, tamu):
    form = KunjunganForm(request.POST or None)
    pegawai_list = Pegawai.objects.filter(account_status='active').select_related('department_rel')

    if request.method == 'POST' and form.is_valid():
        from django.db import transaction
        from ..validators import validate_kunjungan_schedule
        from django.core.exceptions import ValidationError as DjangoValidationError

        kunjungan = form.save(commit=False)
        kunjungan.tamu = tamu
        kunjungan.status = 'menunggu_admin'

        try:
            with transaction.atomic():
                validate_kunjungan_schedule(
                    arrival_time=kunjungan.arrival_time,
                    departure_time=kunjungan.departure_time,
                    instance=kunjungan,
                    is_admin=False,
                    is_import=False,
                    lock_for_update=True
                )
                kunjungan.save()
        except DjangoValidationError as e:
            if hasattr(e, 'error_dict'):
                for field, error_list in e.error_dict.items():
                    for err in error_list:
                        form.add_error(field, err)
            elif hasattr(e, 'message'):
                form.add_error('arrival_time', e.message)
            else:
                form.add_error('arrival_time', str(e))
            return render(request, 'guest_book/tamu_kunjungan_baru.html', {
                'form': form,
                'pegawai_list': pegawai_list,
            })

        # ── N8N Auto-Routing: AI pilihkan pegawai yang paling sesuai ──────────
        from ..utils import call_n8n_routing
        n8n_result = call_n8n_routing(
            kunjungan_id=kunjungan.id,
            purpose=kunjungan.purpose,
            pegawai_queryset=pegawai_list,
        )
        if n8n_result and n8n_result.get('pegawai_id'):
            try:
                pegawai_assign = Pegawai.objects.get(
                    pk=n8n_result['pegawai_id'],
                    account_status='active'
                )
                kunjungan.pegawai = pegawai_assign
                kunjungan.status = 'menunggu_pegawai'
                kunjungan.admin_notes = (
                    f"[Auto-Routing AI] Pegawai direkomendasikan oleh N8N.\n"
                    f"Bidang: {n8n_result.get('bidang', '-')}\n"
                    f"Confidence: {n8n_result.get('confidence', '-')}\n"
                    f"Alasan: {n8n_result.get('alasan', '-')}"
                )
                kunjungan.save(update_fields=['pegawai', 'status', 'admin_notes'])
                messages.success(
                    request,
                    f"Kunjungan Anda berhasil didaftarkan dan telah diarahkan ke "
                    f"{pegawai_assign.name} ({pegawai_assign.jabatan or 'Pegawai'})."
                )
            except Pegawai.DoesNotExist:
                messages.success(request, "Kunjungan Anda berhasil didaftarkan!")
        else:
            messages.success(request, "Kunjungan Anda berhasil didaftarkan!")
        # ── End N8N Routing ───────────────────────────────────────────────────
        
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
            
            # Kirim email di latar belakang menggunakan thread agar tidak memblokir UI (Asynchronous)
            import threading
            threading.Thread(target=msg.send).start()
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

    # Calculate stats for the current user (1 query, unfiltered)
    base_qs = Kunjungan.objects.filter(tamu=tamu)
    stats = base_qs.aggregate(
        total=Count('id'),
        pending=Count('id', filter=_Q(status__in=Kunjungan.Status.PENDING_VERIFICATION)),
        cancelled=Count('id', filter=_Q(status='cancelled')),
    )

    paginator = Paginator(qs, 100)
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
    from ..permissions import PermissionManager
    
    kunjungan = get_object_or_404(Kunjungan, pk=pk, tamu=tamu)
    status_history = kunjungan.status_history.all().order_by('-changed_at')
    notes_list = kunjungan.notes_history.all().order_by('created_at')
    
    # Get rejection reason if any
    rejection_note = None
    if kunjungan.status == 'ditolak_pegawai':
        rejection_note = kunjungan.notes_history.filter(note_type='rejection').first()
    
    # Check if chat is available
    chat_available = PermissionManager.can_access_chat_pegawai_tamu(kunjungan)
    chat_session_id = f'kunjungan_{kunjungan.id}' if chat_available else None

    ctx = base_context(tamu, 'riwayat')
    ctx.update({
        'kunjungan': kunjungan,
        'status_history': status_history,
        'notes_list': notes_list,
        'rejection_note': rejection_note,
        'chat_available': chat_available,
        'chat_session_id': chat_session_id,
    })
    return render(request, 'guest_book/tamu_kunjungan_detail.html', ctx)

@tamu_login_required
def kunjungan_batal_view(request, tamu, pk):
    if request.method == 'POST':
        kunjungan = get_object_or_404(
            Kunjungan.objects.select_related('pegawai'), 
            pk=pk, 
            tamu=tamu, 
            status__in=Kunjungan.Status.CANCELABLE
        )
        kunjungan.status = 'cancelled'
        kunjungan.save(update_fields=['status', 'updated_at'])
        messages.success(request, "Kunjungan berhasil dibatalkan.")
        
        try:
            send_notification(
                recipient_id='admin',
                recipient_type='admin',
                notification_type='system_alert',
                title='Kunjungan Dibatalkan oleh Tamu',
                message=f'Tamu {tamu.name} telah membatalkan kunjungan mereka.',
                related_object_id=str(kunjungan.id)
            )
        except Exception as notif_err:
            logger.warning("Gagal mengirim notifikasi pembatalan ke admin: %s", notif_err)
        
        if kunjungan.pegawai:
            try:
                send_notification(
                    recipient_id=str(kunjungan.pegawai.id),
                    recipient_type='pegawai',
                    notification_type='system_alert',
                    title='Kunjungan Dibatalkan oleh Tamu',
                    message=f'Tamu {tamu.name} telah membatalkan jadwal kunjungan mereka.',
                    related_object_id=str(kunjungan.id)
                )
            except Exception as notif_err:
                logger.warning("Gagal mengirim notifikasi pembatalan ke pegawai: %s", notif_err)
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
    """View untuk Chat Tamu — Admin & Pegawai (multi-conversation, WA style)"""
    from ..models import ChatMessage, Pegawai, Kunjungan
    from .base import _get_cached_admin_user

    admin_user = _get_cached_admin_user()

    # ── 1. Conversation dengan Admin ─────────────────────────────────────────
    admin_session_id = str(tamu.pk)
    admin_last_msg = ChatMessage.objects.filter(session_id=admin_session_id).order_by('-created_at').first()
    admin_unread = ChatMessage.objects.filter(
        session_id=admin_session_id, sender_type='admin', is_read=False
    ).count()

    conversations = [{
        'id': 'admin',
        'session_id': admin_session_id,
        'type': 'admin',
        'name': 'Admin Diskominfosantik',
        'subtitle': 'Layanan Umum',
        'avatar_letters': 'AD',
        'last_message': admin_last_msg,
        'unread_count': admin_unread,
    }]

    # ── 2. Conversations dengan Pegawai (dari kunjungan tamu) ─────────────────
    kunjungan_list = list(Kunjungan.objects.filter(
        tamu=tamu,
        status__in=['disetujui', 'in_progress', 'completed'],
        pegawai__isnull=False,
    ).select_related('pegawai', 'pegawai__department_rel').order_by('-created_at')[:20])

    session_ids = [f'kunjungan_{k.id}' for k in kunjungan_list]
    unread_counts = {}
    last_messages = {}

    if session_ids:
        unread_qs = ChatMessage.objects.filter(
            session_id__in=session_ids, is_read=False
        ).exclude(sender_type='tamu').values('session_id').annotate(c=Count('id'))
        unread_counts = {item['session_id']: item['c'] for item in unread_qs}

        # Ambil pesan terakhir per session secara batch
        recent_msgs = ChatMessage.objects.filter(
            session_id__in=session_ids
        ).order_by('session_id', '-created_at')
        for msg in recent_msgs:
            if msg.session_id not in last_messages:
                last_messages[msg.session_id] = msg

    for k in kunjungan_list:
        session_id = f'kunjungan_{k.id}'
        conversations.append({
            'id': str(k.id),
            'session_id': session_id,
            'type': 'pegawai',
            'name': k.pegawai.name,
            'subtitle': k.pegawai.department or (k.pegawai.department_rel.nama if k.pegawai.department_rel else 'Pegawai'),
            'avatar_letters': k.pegawai.name[:2].upper(),
            'last_message': last_messages.get(session_id),
            'unread_count': unread_counts.get(session_id, 0),
        })

    # ── 3. Tentukan active conversation ───────────────────────────────────────
    active_session = request.GET.get('session', admin_session_id)
    active_conv = next((c for c in conversations if c['session_id'] == active_session), conversations[0])

    # Mark as read
    ChatMessage.objects.filter(
        session_id=active_conv['session_id'], is_read=False
    ).exclude(sender_type='tamu').update(is_read=True)

    # Load messages for active conversation
    messages_qs = ChatMessage.objects.filter(
        session_id=active_conv['session_id']
    ).order_by('-created_at')[:50]
    messages_list = list(reversed(messages_qs))

    # Attach sender objects secara batch (mencegah N+1 query)
    pegawai_ids = {msg.sender_id for msg in messages_list if msg.sender_type == 'pegawai' and msg.sender_id}
    pegawai_map = {}
    if pegawai_ids:
        pegawai_map = {
            str(p.id): p 
            for p in Pegawai.objects.filter(id__in=pegawai_ids).select_related('department_rel')
        }

    for msg in messages_list:
        if msg.sender_type == 'tamu':
            msg.sender_obj = tamu
        elif msg.sender_type == 'admin':
            msg.sender_obj = admin_user
        elif msg.sender_type == 'pegawai':
            msg.sender_obj = pegawai_map.get(str(msg.sender_id))

    ctx = base_context(tamu, 'chat')
    ctx.update({
        'conversations': conversations,
        'active_conv': active_conv,
        'messages_list': messages_list,
        'admin_user': admin_user,
        'tamu_id': str(tamu.pk),
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
def tamu_chat_pegawai_view(request, tamu, kunjungan_id):
    """Chat interface antara Tamu dan Pegawai untuk kunjungan tertentu."""
    from django.core.exceptions import PermissionDenied
    from ..models import ChatMessage
    from ..permissions import PermissionManager
    
    kunjungan = get_object_or_404(Kunjungan, pk=kunjungan_id, tamu=tamu)
    
    # Validasi permission
    if not PermissionManager.can_access_chat_pegawai_tamu(kunjungan):
        messages.warning(request, "Chat hanya tersedia setelah kunjungan di-ACC oleh Admin")
        return redirect('tamu:kunjungan_detail', pk=kunjungan_id)
    
    session_id = f'kunjungan_{kunjungan.id}'
    
    # Get chat history
    messages_list = ChatMessage.objects.filter(
        session_id=session_id
    ).order_by('-created_at')[:50]
    messages_list = list(reversed(messages_list))
    
    ctx = base_context(tamu, 'chat')
    ctx.update({
        'kunjungan': kunjungan,
        'session_id': session_id,
        'chat_partner': kunjungan.pegawai.name if kunjungan.pegawai else 'Pegawai',
        'messages_list': messages_list,
    })
    return render(request, 'guest_book/tamu_chat_pegawai.html', ctx)


@tamu_login_required
def profil_view(request, tamu):
    """View untuk profil pengguna (tamu)"""
    base_qs = Kunjungan.objects.filter(tamu=tamu)

    # 1 query: total + distinct departemen sekaligus
    agg = base_qs.aggregate(total=Count('id'))
    total_kunjungan = agg['total']

    # Distinct count tidak bisa digabung dalam aggregate() standar Django,
    # tapi 1 query values+distinct jauh lebih efisien dari 2 filter().count() terpisah
    total_instansi = base_qs.values('pegawai__department').distinct().count()

    # 1 query: 3 kunjungan terbaru
    recent_visits = base_qs.select_related('pegawai').order_by('-arrival_time')[:3]

    # Cari tanggal terakhir ganti password dari AuditLog
    # Ambil hanya 1 log terbaru yang mengandung 'password' — tidak perlu load semua log
    from ..models import AuditLog
    last_password_log = AuditLog.objects.filter(
        user_id=str(tamu.id),
        user_type='tamu',
        action='update',
        table_name='tamu',
        new_value__has_key='password',
    ).order_by('-timestamp').values('timestamp').first()

    last_change_date = last_password_log['timestamp'] if last_password_log else tamu.registration_date
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
