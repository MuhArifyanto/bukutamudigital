import logging
import threading
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.core.paginator import Paginator
from django.utils import timezone
from django.db.models import Count, Q as _Q
from django.views.decorators.csrf import ensure_csrf_cookie
from .base import tamu_login_required, base_context
from ..models import Kunjungan, KunjunganStatusHistory, Pegawai, Message, Departemen
from ..forms import KunjunganForm, PesanForm
from ..utils import send_notification

logger = logging.getLogger(__name__)


def _run_n8n_routing_bg(kunjungan_id, purpose, tamu_name, initial_pegawai_id=None):
    """
    Jalankan pemanggilan N8N Auto-Routing di latar belakang (background thread)
    agar halaman submit Tamu langsung instan (< 0.5 detik) tanpa menunggu AI selesai berpikir.
    """
    from django.db import close_old_connections
    from ..utils import call_n8n_routing

    close_old_connections()
    try:
        active_pegawai_qs = Pegawai.objects.filter(account_status='active').select_related('department_rel')
        n8n_result = call_n8n_routing(
            kunjungan_id=kunjungan_id,
            purpose=purpose,
            department=None,
            arrival_time=None,
            pegawai_queryset=active_pegawai_qs,
        )
        if not n8n_result:
            return

        kunjungan = Kunjungan.objects.select_related('pegawai').filter(pk=kunjungan_id).first()
        if not kunjungan or kunjungan.status != 'menunggu_admin':
            return

        ai_intent = n8n_result.get('intent', 'buat_kunjungan')
        ai_reply = n8n_result.get('reply') or n8n_result.get('replay') or n8n_result.get('alasan') or '-'
        ai_handoff = n8n_result.get('handoff')
        ai_bidang = n8n_result.get('bidang', '-')
        ai_conf = n8n_result.get('confidence', '-')

        pegawai_assign = None
        if n8n_result.get('pegawai_id'):
            pegawai_assign = Pegawai.objects.filter(
                pk=n8n_result['pegawai_id'],
                account_status='active'
            ).first()

        note_lines = [
            "[Auto-Routing AI N8N]",
            f"Intent: {ai_intent}",
        ]
        if ai_bidang and ai_bidang != '-':
            note_lines.append(f"Bidang: {ai_bidang}")
        if ai_conf and ai_conf != '-':
            note_lines.append(f"Confidence: {ai_conf}")
        if ai_handoff is not None:
            note_lines.append(f"Handoff: {ai_handoff}")
        if pegawai_assign:
            note_lines.append(f"Rekomendasi Pegawai: {pegawai_assign.name}")
        if ai_reply and ai_reply != '-':
            note_lines.append(f"Alasan/Reply AI: {ai_reply}")

        kunjungan.admin_notes = "\n".join(note_lines)

        # Jika Tamu belum memilih pegawai sendiri dan N8N merekomendasikan pegawai aktif:
        # arahkan otomatis ke menunggu_pegawai. Jika Tamu sudah memilih pegawai sendiri di form,
        # pertahankan pilihan Tamu dan simpan analisis AI di admin_notes.
        if pegawai_assign and not initial_pegawai_id:
            kunjungan.pegawai = pegawai_assign
            kunjungan.status = 'menunggu_pegawai'
            kunjungan.save(update_fields=['pegawai', 'status', 'admin_notes'])
            KunjunganStatusHistory.objects.create(
                kunjungan=kunjungan,
                old_status='menunggu_admin',
                new_status='menunggu_pegawai',
                changed_by_id='admin',
                changed_by_type='admin',
                notes=f'Auto-Routing AI ke {pegawai_assign.name}'
            )
            try:
                send_notification(
                    recipient_id=str(pegawai_assign.id),
                    recipient_type='pegawai',
                    notification_type='visit_forwarded',
                    title='Pembaruan Kunjungan',
                    message=f'Permintaan kunjungan baru dari {tamu_name} menunggu persetujuan Anda.',
                    related_object_id=str(kunjungan.id)
                )
            except Exception as notif_err:
                logger.warning("Gagal mengirim notifikasi auto-routing ke pegawai: %s", notif_err)
        else:
            kunjungan.save(update_fields=['admin_notes'])
    except Exception as bg_err:
        logger.warning("Gagal memproses N8N routing di background: %s", bg_err)
    finally:
        close_old_connections()


@ensure_csrf_cookie
def landing_view(request):
    """View untuk Landing Page utama"""
    tamu_id = request.session.get('tamu_id')
    user_logged_in = False
    user_name = ""
    
    if tamu_id:
        from ..models import Tamu
        tamu = Tamu.objects.filter(pk=tamu_id, account_status='active').first()
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
    from ..validators import get_month_range_aware

    now = timezone.localtime(timezone.now())
    month_start, next_month_start = get_month_range_aware(now.year, now.month)
    base_qs = Kunjungan.objects.filter(tamu=tamu)

    # 1 query: semua status sekaligus via conditional Count
    agg = base_qs.aggregate(
        total=Count('id'),
        pending=Count('id', filter=_Q(status__in=['menunggu_admin', 'menunggu_pegawai', 'disetujui_pegawai'])),
        in_progress=Count('id', filter=_Q(status='in_progress')),
        completed=Count('id', filter=_Q(status='completed')),
        bulan_ini=Count('id', filter=_Q(
            arrival_time__gte=month_start,
            arrival_time__lt=next_month_start,
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
    pegawai_list = Pegawai.objects.filter(account_status='active').select_related('department_rel').order_by('department_rel__nama', 'name')
    bidang_list = Departemen.objects.all().order_by('nama')

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
            ctx = base_context(tamu, 'kunjungan_baru')
            ctx.update({
                'form': form,
                'pegawai_list': pegawai_list,
                'bidang_list': bidang_list,
            })
            return render(request, 'guest_book/tamu_kunjungan_baru.html', ctx)

        # Tampilkan pesan sukses secara instan tanpa menunggu N8N selesai berpikir
        if kunjungan.pegawai:
            messages.success(
                request,
                f"Kunjungan Anda berhasil didaftarkan untuk menemui "
                f"{kunjungan.pegawai.name} ({kunjungan.pegawai.jabatan or 'Pegawai'})."
            )
        else:
            messages.success(request, "Kunjungan Anda berhasil didaftarkan!")

        # ── N8N Auto-Routing: Dijalankan Asynchronous di Background Thread ────
        initial_pegawai_id = str(kunjungan.pegawai_id) if kunjungan.pegawai_id else None
        threading.Thread(
            target=_run_n8n_routing_bg,
            args=(kunjungan.id, kunjungan.purpose, tamu.name, initial_pegawai_id),
            daemon=True,
        ).start()
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
            threading.Thread(target=msg.send, daemon=True).start()
        except Exception as e:
            # Jika gagal kirim email, log saja agar tidak menghentikan proses booking!
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
        from ..validators import filter_by_local_date
        qs = filter_by_local_date(qs, date_filter)

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
    from ..models import IKMSurvey
    
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

    # Cek Survei IKM
    ikm_survey = IKMSurvey.objects.filter(kunjungan=kunjungan).first()
    ticket_code = str(kunjungan.id)[:8].upper()

    ctx = base_context(tamu, 'riwayat')
    ctx.update({
        'kunjungan': kunjungan,
        'status_history': status_history,
        'notes_list': notes_list,
        'rejection_note': rejection_note,
        'chat_available': chat_available,
        'chat_session_id': chat_session_id,
        'ikm_survey': ikm_survey,
        'ticket_code': ticket_code,
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
        old_status = kunjungan.status
        kunjungan.status = 'cancelled'
        kunjungan.save(update_fields=['status', 'updated_at'])
        KunjunganStatusHistory.objects.create(
            kunjungan=kunjungan,
            old_status=old_status,
            new_status='cancelled',
            changed_by_id=str(tamu.id),
            changed_by_type='tamu',
            notes='Dibatalkan oleh Tamu'
        )
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
    from ..models import ChatMessage, ChatRoom, Pegawai, Kunjungan
    from .base import _get_cached_admin_user

    admin_user = _get_cached_admin_user()

    # ── 1. Conversation dengan Admin ─────────────────────────────────────────
    admin_session_id = ChatRoom.session_id_for_tamu(tamu.pk)

    # ── 2. Conversations dengan Pegawai (dari kunjungan tamu) ─────────────────
    kunjungan_list = list(Kunjungan.objects.filter(
        tamu=tamu,
        status__in=['disetujui_pegawai', 'disetujui', 'in_progress', 'completed'],
        pegawai__isnull=False,
    ).select_related('pegawai', 'pegawai__department_rel').order_by('-created_at')[:20])

    kunjungan_session_ids = [ChatRoom.session_id_for_kunjungan(k.id) for k in kunjungan_list]
    all_session_ids = [admin_session_id] + kunjungan_session_ids

    unread_counts = ChatMessage.unread_counts_by_session(all_session_ids, exclude_sender_type='tamu')
    last_messages = ChatMessage.latest_by_session(all_session_ids)

    conversations = [{
        'id': 'admin',
        'session_id': admin_session_id,
        'type': 'admin',
        'name': 'Admin Diskominfosantik',
        'subtitle': 'Layanan Umum & Asisten AI',
        'avatar_letters': 'AD',
        'last_message': last_messages.get(admin_session_id),
        'unread_count': unread_counts.get(admin_session_id, 0),
    }]

    for k in kunjungan_list:
        session_id = ChatRoom.session_id_for_kunjungan(k.id)
        peg_name = (k.pegawai.name if k.pegawai and k.pegawai.name else 'Pegawai')
        peg_dept = 'Pegawai'
        if k.pegawai:
            peg_dept = k.pegawai.department or (k.pegawai.department_rel.nama if k.pegawai.department_rel else 'Pegawai')
        conversations.append({
            'id': str(k.id),
            'session_id': session_id,
            'type': 'pegawai',
            'name': peg_name,
            'subtitle': peg_dept,
            'avatar_letters': peg_name[:2].upper(),
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
    active_conv['unread_count'] = 0

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

    from ..utils import get_session_strike_count, is_session_handed_off_to_admin

    ctx = base_context(tamu, 'chat')
    ctx.update({
        'conversations': conversations,
        'active_conv': active_conv,
        'messages_list': messages_list,
        'admin_user': admin_user,
        'tamu_id': str(tamu.pk),
        'ai_handoff_active': is_session_handed_off_to_admin(admin_session_id),
        'ai_strike_count': get_session_strike_count(admin_session_id),
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
        from ..validators import filter_by_local_date
        qs = filter_by_local_date(qs, date_filter)

    ctx = base_context(tamu, 'riwayat')
    ctx.update({
        'kunjungan_list': qs,
    })
    return render(request, 'guest_book/tamu_kunjungan_cetak_pdf.html', ctx)


@tamu_login_required
def tamu_chat_pegawai_view(request, tamu, kunjungan_id):
    """Chat interface antara Tamu dan Pegawai untuk kunjungan tertentu."""
    from django.core.exceptions import PermissionDenied
    from ..models import ChatMessage, ChatRoom
    from ..permissions import PermissionManager
    
    kunjungan = get_object_or_404(Kunjungan, pk=kunjungan_id, tamu=tamu)
    
    # Validasi permission
    if not PermissionManager.can_access_chat_pegawai_tamu(kunjungan):
        messages.warning(request, "Chat hanya tersedia setelah kunjungan di-ACC oleh Admin")
        return redirect('tamu:kunjungan_detail', pk=kunjungan_id)
    
    session_id = ChatRoom.session_id_for_kunjungan(kunjungan.id)
    
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

    from django.contrib.auth.hashers import is_password_usable

    ctx = base_context(tamu, 'profil')
    ctx.update({
        'tamu': tamu,
        'total_kunjungan': total_kunjungan,
        'total_instansi': total_instansi,
        'recent_visits': recent_visits,
        'needs_password_change': needs_password_change,
        'days_since_change': days_since_change,
        'has_local_password': is_password_usable(tamu.password),
    })
    return render(request, 'guest_book/tamu_profil.html', ctx)


@tamu_login_required
def tamu_export_personal_data(request, tamu):
    """Hak Akses & Portabilitas Data UU PDP: ekspor seluruh data pribadi milik Tamu dalam format JSON."""
    import json
    from django.http import HttpResponse, JsonResponse
    from ..models import ChatMessage, ChatRoom, IKMSurvey, Message, Notification
    from .auth import check_rate_limit, get_client_ip, record_rate_limit_attempt
    from .base import record_audit_log

    if request.method != 'GET':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    if tamu.is_admin or tamu.nik == 'admin':
        return JsonResponse({'success': False, 'error': 'Gunakan panel administrator untuk akun admin.'}, status=403)

    rl_key = f"rl_pdp_export_{tamu.pk}"
    if check_rate_limit(rl_key, max_attempts=5, fail_closed=False):
        return JsonResponse(
            {'success': False, 'error': 'Terlalu banyak permintaan ekspor data. Silakan coba lagi dalam 15 menit.'},
            status=429,
        )
    record_rate_limit_attempt(rl_key, timeout_seconds=900)

    visits = list(
        Kunjungan.objects.filter(tamu=tamu)
        .select_related('pegawai', 'pegawai__department_rel')
        .order_by('-arrival_time')
    )
    visit_ids = [v.id for v in visits]

    session_ids = [
        ChatRoom.session_id_for_tamu(tamu.pk),
        str(tamu.pk),
    ] + [ChatRoom.session_id_for_kunjungan(vid) for vid in visit_ids]

    chat_qs = ChatMessage.objects.filter(session_id__in=session_ids).order_by('created_at')
    msg_qs = Message.objects.filter(sender_id=str(tamu.pk), sender_type='tamu').order_by('-created_at')
    notif_qs = Notification.objects.filter(recipient_id=str(tamu.pk), recipient_type='tamu').order_by('-created_at')
    ikm_qs = IKMSurvey.objects.filter(tamu=tamu).order_by('-created_at')

    payload = {
        'exported_at': timezone.localtime(timezone.now()).isoformat(),
        'compliance': 'UU No. 27 Tahun 2022 tentang Pelindungan Data Pribadi (UU PDP)',
        'profile': {
            'id': str(tamu.pk),
            'name': tamu.name,
            'email': tamu.email,
            'phone': tamu.phone,
            'nik': tamu.nik,
            'instansi': tamu.instansi,
            'registration_type': tamu.registration_type,
            'account_status': tamu.account_status,
            'registration_date': timezone.localtime(tamu.registration_date).isoformat() if tamu.registration_date else None,
            'last_login': timezone.localtime(tamu.last_login).isoformat() if tamu.last_login else None,
        },
        'kunjungan': [
            {
                'id': str(v.id),
                'arrival_time': timezone.localtime(v.arrival_time).isoformat() if v.arrival_time else None,
                'departure_time': timezone.localtime(v.departure_time).isoformat() if v.departure_time else None,
                'purpose': v.purpose,
                'status': v.status,
                'status_display': v.get_status_display(),
                'pegawai': v.pegawai.name if v.pegawai else None,
                'departemen': (
                    v.pegawai.department_rel.nama
                    if v.pegawai and v.pegawai.department_rel
                    else (v.pegawai.department if v.pegawai else None)
                ),
                'created_at': timezone.localtime(v.created_at).isoformat() if v.created_at else None,
            }
            for v in visits
        ],
        'ikm_surveys': [
            {
                'id': str(s.id),
                'kunjungan_id': str(s.kunjungan_id),
                'rating': s.rating,
                'kesesuaian_persyaratan': s.kesesuaian_persyaratan,
                'kemudahan_prosedur': s.kemudahan_prosedur,
                'kecepatan_layanan': s.kecepatan_layanan,
                'keramahan_petugas': s.keramahan_petugas,
                'kualitas_sarana': s.kualitas_sarana,
                'ulasan': s.ulasan,
                'created_at': timezone.localtime(s.created_at).isoformat() if s.created_at else None,
            }
            for s in ikm_qs
        ],
        'messages': [
            {
                'id': str(m.id),
                'subject': m.subject,
                'content': m.content,
                'status': m.status,
                'created_at': timezone.localtime(m.created_at).isoformat() if m.created_at else None,
            }
            for m in msg_qs
        ],
        'chat_messages': [
            {
                'id': str(cm.id),
                'session_id': cm.session_id,
                'sender_type': cm.sender_type,
                'message_type': cm.message_type,
                'content': cm.content,
                'created_at': timezone.localtime(cm.created_at).isoformat() if cm.created_at else None,
            }
            for cm in chat_qs
        ],
        'notifications': [
            {
                'id': str(n.id),
                'notification_type': n.notification_type,
                'title': n.title,
                'message': n.message,
                'status': n.status,
                'created_at': timezone.localtime(n.created_at).isoformat() if n.created_at else None,
            }
            for n in notif_qs
        ],
    }

    record_audit_log(
        user_id=str(tamu.pk),
        user_type='tamu',
        action='create',
        table_name='pdp_data_export',
        record_id=str(tamu.pk),
        new_value={'format': 'json', 'kunjungan_count': len(payload['kunjungan'])},
        ip_address=get_client_ip(request),
    )

    filename = f"data_pribadi_tamu_{timezone.localtime(timezone.now()).strftime('%Y%m%d')}.json"
    response = HttpResponse(
        json.dumps(payload, ensure_ascii=False, indent=2),
        content_type='application/json; charset=utf-8',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response['Cache-Control'] = 'no-store, private'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@tamu_login_required
def tamu_delete_account_view(request, tamu):
    """Hak Penghapusan Data UU PDP: hapus/anonimkan data pribadi & tutup akun Tamu secara mandiri."""
    from django.contrib.auth.hashers import check_password, is_password_usable, make_password
    from django.core.files.storage import default_storage
    from django.db import transaction
    from django.http import HttpResponseNotAllowed
    from ..models import ChatMessage, ChatRoom, KunjunganNote, Message, Notification
    from ..security_utils import revoke_user_sessions
    from .auth import get_client_ip
    from .base import record_audit_log

    if request.method != 'POST':
        return HttpResponseNotAllowed(['POST'])

    if tamu.is_admin or tamu.nik == 'admin':
        messages.error(request, 'Akun administrator tidak dapat dihapus melalui portal tamu.')
        return redirect('tamu:profil')

    confirm_text = (request.POST.get('confirm_text') or '').strip().upper()
    if confirm_text != 'HAPUS':
        messages.error(request, 'Konfirmasi tidak sesuai. Ketik HAPUS untuk menghapus akun Anda.')
        return redirect('tamu:profil')

    if is_password_usable(tamu.password):
        current_password = request.POST.get('current_password') or ''
        if not current_password or not check_password(current_password, tamu.password):
            messages.error(request, 'Kata sandi saat ini wajib diisi dan harus sesuai untuk menghapus akun.')
            return redirect('tamu:profil')

    redacted_marker = '[Dihapus atas permintaan pemilik data (UU PDP)]'
    tamu_id_str = str(tamu.pk)

    visit_ids = list(Kunjungan.objects.filter(tamu=tamu).values_list('id', flat=True))
    session_ids = [
        ChatRoom.session_id_for_tamu(tamu.pk),
        tamu_id_str,
    ] + [ChatRoom.session_id_for_kunjungan(vid) for vid in visit_ids]

    chat_qs = ChatMessage.objects.filter(session_id__in=session_ids)
    legacy_msg_qs = Message.objects.filter(sender_id=tamu_id_str, sender_type='tamu')

    files_to_delete = []
    if tamu.profile_picture and getattr(tamu.profile_picture, 'name', None):
        files_to_delete.append(tamu.profile_picture.name)
    files_to_delete.extend(
        m.attachment.name
        for m in chat_qs.exclude(attachment='').exclude(attachment__isnull=True)
        if getattr(m.attachment, 'name', None)
    )
    files_to_delete.extend(
        m.attachment_path.name
        for m in legacy_msg_qs.exclude(attachment_path='').exclude(attachment_path__isnull=True)
        if getattr(m.attachment_path, 'name', None)
    )

    with transaction.atomic():
        cancelable_visits = list(
            Kunjungan.objects.filter(tamu=tamu, status__in=Kunjungan.Status.CANCELABLE)
        )
        for v in cancelable_visits:
            old_status = v.status
            v.status = Kunjungan.Status.CANCELLED
            v.save(update_fields=['status', 'updated_at'])
            KunjunganStatusHistory.objects.create(
                kunjungan=v,
                old_status=old_status,
                new_status=Kunjungan.Status.CANCELLED,
                changed_by_id=tamu_id_str,
                changed_by_type='tamu',
                notes='Dibatalkan otomatis karena penghapusan akun mandiri (UU PDP)',
            )

        Kunjungan.objects.filter(tamu=tamu).update(
            notes=redacted_marker,
            admin_notes=redacted_marker,
            rejection_reason=redacted_marker,
        )
        KunjunganNote.objects.filter(kunjungan_id__in=visit_ids).delete()
        chat_qs.delete()
        ChatRoom.objects.filter(tamu=tamu).delete()
        legacy_msg_qs.delete()
        Notification.objects.filter(recipient_id=tamu_id_str, recipient_type='tamu').delete()

        tamu.name = f"Tamu Anonim ({tamu_id_str[:8]})"
        tamu.email = f"anonymized-{tamu.pk}@redacted.local"
        tamu.phone = '-'
        tamu.nik = None
        tamu.nik_hash = None
        tamu.instansi = None
        tamu.google_id = None
        tamu.password = make_password(None)
        tamu.profile_picture = None
        tamu.account_status = 'inactive'
        tamu.save()

        record_audit_log(
            user_id=tamu_id_str,
            user_type='tamu',
            action='delete',
            table_name='tamu',
            record_id=tamu_id_str,
            new_value={
                'reason': 'self_service_pdp_erasure',
                'cancelled_visits': len(cancelable_visits),
            },
            ip_address=get_client_ip(request),
        )

    for file_name in files_to_delete:
        try:
            if default_storage.exists(file_name):
                default_storage.delete(file_name)
        except Exception as exc:
            logger.warning("Gagal menghapus berkas media saat hapus akun %s: %s", tamu_id_str, exc)

    revoke_user_sessions('tamu', tamu_id_str)
    request.session.flush()
    messages.success(
        request,
        'Akun dan data pribadi Anda telah berhasil dihapus/dianonimkan sesuai ketentuan UU PDP.',
    )
    return redirect('tamu:login')


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


@tamu_login_required
def api_submit_ikm_rating(request, tamu, pk):
    """API Tamu untuk mengirim rating & survei IKM untuk kunjungan yang telah selesai"""
    import json
    from django.http import JsonResponse
    from ..models import Kunjungan, IKMSurvey

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    kunjungan = Kunjungan.objects.filter(pk=pk).first()
    if not kunjungan:
        return JsonResponse({'success': False, 'error': 'Kunjungan tidak ditemukan.'}, status=404)

    if kunjungan.tamu != tamu:
        return JsonResponse({'success': False, 'error': 'Akses ditolak. Kunjungan ini bukan milik akun Anda.'}, status=403)

    if kunjungan.status != 'completed':
        return JsonResponse({'success': False, 'error': 'Survei kepuasan hanya dapat diisi untuk kunjungan yang telah selesai (Completed).'}, status=400)

    if IKMSurvey.objects.filter(kunjungan=kunjungan).exists():
        return JsonResponse({'success': False, 'error': 'Anda sudah pernah mengisi survei kepuasan untuk kunjungan ini.'}, status=400)

    try:
        data = json.loads(request.body.decode('utf-8')) if request.body else {}
    except Exception:
        data = request.POST

    try:
        rating = max(1, min(5, int(data.get('rating', 5))))
        u1 = max(1, min(5, int(data.get('kesesuaian_persyaratan', rating))))
        u2 = max(1, min(5, int(data.get('kemudahan_prosedur', rating))))
        u3 = max(1, min(5, int(data.get('kecepatan_layanan', rating))))
        u4 = max(1, min(5, int(data.get('keramahan_petugas', rating))))
        u5 = max(1, min(5, int(data.get('kualitas_sarana', rating))))
    except (ValueError, TypeError):
        rating = 5
        u1 = u2 = u3 = u4 = u5 = 5

    ulasan = (data.get('ulasan') or '').strip()

    survey, created = IKMSurvey.objects.update_or_create(
        kunjungan=kunjungan,
        defaults={
            'tamu': tamu,
            'rating': rating,
            'kesesuaian_persyaratan': u1,
            'kemudahan_prosedur': u2,
            'kecepatan_layanan': u3,
            'keramahan_petugas': u4,
            'kualitas_sarana': u5,
            'ulasan': ulasan,
        }
    )

    return JsonResponse({
        'success': True,
        'message': 'Terima kasih atas penilaian & masukan Anda untuk peningkatan layanan kami!',
        'rating': survey.rating,
        'ulasan': survey.ulasan,
    })
