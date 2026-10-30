"""
views/pegawai.py  — Portal Pegawai views.
Dashboard dan fitur-fitur lainnya akan dikembangkan di sini.
"""
import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from functools import wraps

from ..models import Pegawai

logger = logging.getLogger(__name__)


# ── Decorator Auth ──────────────────────────────────────────────────────────

def pegawai_login_required(view_func):
    """Decorator: redirect ke login pegawai jika belum autentikasi."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        pegawai_id = request.session.get('pegawai_id')
        if not pegawai_id:
            messages.error(request, 'Silakan masuk ke Portal Pegawai terlebih dahulu.')
            return redirect('tamu:pegawai_login')
        try:
            pegawai = Pegawai.objects.get(pk=pegawai_id, account_status='active')
        except Pegawai.DoesNotExist:
            request.session.flush()
            messages.error(request, 'Sesi tidak valid. Silakan masuk kembali.')
            return redirect('tamu:pegawai_login')
        request._pegawai = pegawai
        return view_func(request, *args, pegawai=pegawai, **kwargs)
    return wrapper


# ── Dashboard ───────────────────────────────────────────────────────────────

@pegawai_login_required
def pegawai_dashboard_view(request, pegawai=None):
    """Dashboard utama Portal Pegawai dengan pending approvals."""
    from django.utils import timezone
    from django.db.models import Count, Q
    from ..models import Kunjungan
    from ..permissions import PermissionManager

    now = timezone.now()
    
    # Kunjungan yang memerlukan approval dari pegawai ini
    pending_approvals = Kunjungan.objects.filter(
        pegawai=pegawai,
        status='menunggu_pegawai'
    ).select_related('tamu').order_by('-created_at')
    
    # Jika supervisor+, tampilkan juga request departemen
    department_requests = []
    if PermissionManager.can_view_department_requests(pegawai):
        department_requests = Kunjungan.objects.filter(
            pegawai__department_rel=pegawai.department_rel,
            status='menunggu_pegawai'
        ).exclude(pegawai=pegawai).select_related('tamu', 'pegawai').order_by('-created_at')[:10]
    
    # Statistik
    base_qs = Kunjungan.objects.filter(pegawai=pegawai)
    stats = {
        'total': base_qs.count(),
        'pending': pending_approvals.count(),
        'in_progress': base_qs.filter(status='in_progress').count(),
        'completed': base_qs.filter(status='completed').count(),
        'hari_ini': base_qs.filter(arrival_time__date=now.date()).count(),
    }
    
    # Kunjungan yang sudah disetujui (upcoming visits)
    upcoming_visits = base_qs.filter(
        status='disetujui',
        arrival_time__gte=now
    ).select_related('tamu').order_by('arrival_time')[:5]

    return render(request, 'guest_book/pegawai_dashboard.html', {
        'pegawai': pegawai,
        'active_page': 'dashboard',
        'stats': stats,
        'pending_approvals': pending_approvals,
        'department_requests': department_requests,
        'upcoming_visits': upcoming_visits,
    })



# ── Kunjungan Detail & Approval ─────────────────────────────────────────────

@pegawai_login_required
def pegawai_kunjungan_detail_view(request, pk, pegawai=None):
    """View detail kunjungan dengan form approval."""
    from django.shortcuts import get_object_or_404
    from django.core.exceptions import PermissionDenied, ValidationError
    from ..models import Kunjungan
    from ..forms import PegawaiResponseForm
    from ..workflow_engine import WorkflowEngine
    from ..permissions import PermissionManager
    
    kunjungan = get_object_or_404(Kunjungan, pk=pk)

    # Cek apakah pegawai dapat view kunjungan ini
    kunjungan_pegawai_id = str(kunjungan.pegawai.id) if kunjungan.pegawai else None
    is_assigned = kunjungan_pegawai_id == str(pegawai.id)
    is_dept_supervisor = (
        PermissionManager.can_view_department_requests(pegawai)
        and kunjungan.pegawai is not None
        and kunjungan.pegawai.department_rel == pegawai.department_rel
    )
    can_view = is_assigned or is_dept_supervisor

    if not can_view:
        messages.error(request, 'Anda tidak memiliki akses ke kunjungan ini.')
        return redirect('tamu:pegawai_kunjungan_list')

    # Cek apakah pegawai dapat respond
    can_respond = PermissionManager.can_approve_reject(pegawai, kunjungan) and kunjungan.status == 'menunggu_pegawai'
    
    from ..models import KunjunganNote
    from ..forms import PegawaiReportForm
    
    if request.method == 'POST':
        if can_respond and 'action' in request.POST:
            form = PegawaiResponseForm(request.POST)
            if form.is_valid():
                action = form.cleaned_data['action']
                notes = form.cleaned_data.get('notes')
                rejection_reason = form.cleaned_data.get('rejection_reason')
                reschedule_time = form.cleaned_data.get('reschedule_time')
                
                if action == 'approve':
                    new_status = 'disetujui_pegawai'
                    action_text = 'disetujui'
                elif action == 'reschedule':
                    new_status = 'ditolak_pegawai'
                    action_text = 'diusulkan untuk dijadwalkan ulang'
                    formatted_time = reschedule_time.strftime("%d %B %Y, %H:%M") if reschedule_time else ''
                    rejection_reason = f"[USULAN JADWAL ULANG: {formatted_time}]\n{rejection_reason}"
                else:
                    new_status = 'ditolak_pegawai'
                    action_text = 'ditolak'
                
                try:
                    engine = WorkflowEngine(kunjungan)
                    engine.transition(
                        new_status=new_status,
                        user_id=str(pegawai.id),
                        user_type='pegawai',
                        notes=notes,
                        rejection_reason=rejection_reason
                    )
                    
                    messages.success(request, f'Permintaan kunjungan telah {action_text}')
                    return redirect('tamu:pegawai_dashboard')
                    
                except (PermissionDenied, ValidationError) as e:
                    messages.error(request, str(e))
                    
        elif can_respond and 'delegate_to' in request.POST:
            delegate_to_id = request.POST.get('delegate_to')
            delegate_reason = request.POST.get('delegate_reason')
            if delegate_to_id:
                try:
                    rekan = Pegawai.objects.get(id=delegate_to_id, department_rel=pegawai.department_rel, account_status='active')
                    
                    # Update Kunjungan
                    kunjungan.pegawai = rekan
                    kunjungan.save(update_fields=['pegawai', 'updated_at'])
                    
                    # Add Note
                    from ..models import KunjunganNote
                    KunjunganNote.objects.create(
                        kunjungan=kunjungan,
                        author_id=str(pegawai.id),
                        author_type='pegawai',
                        content=f"Didelegasikan ke {rekan.name}. Alasan: {delegate_reason}",
                        note_type='internal'
                    )
                    
                    # Notifikasi ke rekan kerja penerima delegasi
                    from ..utils import send_notification
                    clean_reason = (delegate_reason[:150] + '...') if delegate_reason and len(delegate_reason) > 150 else (delegate_reason or '-')
                    try:
                        tamu_name = kunjungan.tamu.name if kunjungan.tamu else 'Tamu'
                        send_notification(
                            recipient_id=str(rekan.id),
                            recipient_type='pegawai',
                            notification_type='visit_forwarded',
                            title='Delegasi Kunjungan Masuk',
                            message=f'Rekan {pegawai.name} telah mendelegasikan kunjungan dari {tamu_name} kepada Anda. Alasan: {clean_reason}',
                            related_object_id=str(kunjungan.id)
                        )
                    except Exception as notif_err:
                        logger.warning("Gagal mengirim notifikasi delegasi ke rekan kerja: %s", notif_err)
                    
                    messages.success(request, f'Kunjungan berhasil didelegasikan ke {rekan.name}.')
                    return redirect('tamu:pegawai_kunjungan_list')
                except Pegawai.DoesNotExist:
                    messages.error(request, 'Rekan kerja tidak ditemukan atau tidak valid.')
        
        elif 'submit_report' in request.POST:
            report_form = PegawaiReportForm(request.POST)
            if report_form.is_valid():
                KunjunganNote.objects.create(
                    kunjungan=kunjungan,
                    author_id=str(pegawai.id),
                    author_type='pegawai',
                    content=report_form.cleaned_data['content'],
                    note_type='report'
                )
                messages.success(request, 'Laporan hasil pertemuan berhasil disimpan.')
                return redirect('tamu:pegawai_kunjungan_detail', pk=kunjungan.id)
                
    form = PegawaiResponseForm() if can_respond else None
    report_form = PegawaiReportForm()
    
    # Get reports (Laporan)
    reports = kunjungan.notes_history.filter(note_type='report').order_by('-created_at')
    
    # Get status history
    status_history = kunjungan.status_history.all().order_by('-changed_at')
    
    # Check chat availability
    chat_available = PermissionManager.can_access_chat_pegawai_tamu(kunjungan)
    chat_session_id = f'kunjungan_{kunjungan.id}' if chat_available else None
    
    # Rekan kerja untuk delegasi
    rekan_kerja = []
    if can_respond and pegawai.department_rel:
        rekan_kerja = Pegawai.objects.filter(
            department_rel=pegawai.department_rel, 
            account_status='active'
        ).exclude(id=pegawai.id)
    
    return render(request, 'guest_book/pegawai_kunjungan_detail.html', {
        'pegawai': pegawai,
        'kunjungan': kunjungan,
        'form': form,
        'report_form': report_form,
        'reports': reports,
        'can_respond': can_respond,
        'status_history': status_history,
        'chat_available': chat_available,
        'chat_session_id': chat_session_id,
        'rekan_kerja': rekan_kerja,
        'active_page': 'kunjungan'
    })


@pegawai_login_required
def pegawai_kunjungan_list_view(request, pegawai=None):
    """List semua kunjungan untuk pegawai dengan filter."""
    from django.core.paginator import Paginator
    from ..models import Kunjungan
    from ..permissions import PermissionManager
    
    # Base queryset
    if PermissionManager.can_view_department_requests(pegawai):
        # Supervisor+ dapat lihat semua di departemen
        kunjungan_qs = Kunjungan.objects.filter(
            pegawai__department_rel=pegawai.department_rel
        )
    else:
        # Staff hanya lihat miliknya
        kunjungan_qs = Kunjungan.objects.filter(pegawai=pegawai)
    
    # Filter by tab
    tab = request.GET.get('tab', 'menunggu')
    if tab == 'menunggu':
        # Fokus pada antrean yang butuh aksi segera
        kunjungan_qs = kunjungan_qs.filter(status='menunggu_pegawai')
    elif tab == 'riwayat':
        # Riwayat selesai, disetujui, ditolak, dll
        kunjungan_qs = kunjungan_qs.exclude(status='menunggu_pegawai')
        
    # Filter by status explicitly if provided
    status_filter = request.GET.get('status')
    if status_filter:
        kunjungan_qs = kunjungan_qs.filter(status=status_filter)
    
    # Filter by date
    date_filter = request.GET.get('date')
    if date_filter:
        kunjungan_qs = kunjungan_qs.filter(arrival_time__date=date_filter)
    
    # Search
    search_query = request.GET.get('search')
    if search_query:
        from django.db.models import Q
        kunjungan_qs = kunjungan_qs.filter(
            Q(tamu__name__icontains=search_query) |
            Q(purpose__icontains=search_query)
        )
    
    kunjungan_qs = kunjungan_qs.select_related('tamu', 'pegawai').order_by('-created_at')
    
    # Pagination
    paginator = Paginator(kunjungan_qs, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'guest_book/pegawai_kunjungan_list.html', {
        'pegawai': pegawai,
        'page_obj': page_obj,
        'status_filter': status_filter,
        'date_filter': date_filter,
        'search_query': search_query,
        'tab': tab,
        'active_page': 'kunjungan'
    })


@pegawai_login_required
def pegawai_kunjungan_cetak_pdf_view(request, pegawai=None):
    """View to print individual performance report (visits)."""
    from django.utils import timezone
    from ..models import Kunjungan

    now = timezone.now()
    month = request.GET.get('month', str(now.month))
    year = request.GET.get('year', str(now.year))
    
    kunjungan_qs = Kunjungan.objects.filter(
        pegawai=pegawai,
        arrival_time__year=year,
        arrival_time__month=month
    ).select_related('tamu', 'pegawai__department_rel').prefetch_related('notes_history').order_by('-arrival_time')
    
    # Map month number to indonesian name
    months_id = {
        '1': 'Januari', '2': 'Februari', '3': 'Maret', '4': 'April',
        '5': 'Mei', '6': 'Juni', '7': 'Juli', '8': 'Agustus',
        '9': 'September', '10': 'Oktober', '11': 'November', '12': 'Desember'
    }
    month_name = months_id.get(month, month)
    
    context = {
        'pegawai': pegawai,
        'kunjungan_list': kunjungan_qs,
        'month': month_name,
        'year': year,
        'print_date': now
    }
    return render(request, 'guest_book/pegawai_kunjungan_cetak_pdf.html', context)


# ── Chat dengan Admin ───────────────────────────────────────────────────────

@pegawai_login_required
def pegawai_chat_view(request, pegawai=None):
    """Unified chat interface for Pegawai (to Admin and Tamu)."""
    from ..models import ChatMessage, Kunjungan
    from ..permissions import PermissionManager
    from django.db.models import Q
    
    # Conversations list
    conversations = []
    
    # 1. Chat with Admin
    admin_session_id = f'pegawai_admin_{pegawai.id}'
    admin_last_msg = ChatMessage.objects.filter(session_id=admin_session_id).order_by('-created_at').first()
    admin_unread = ChatMessage.objects.filter(session_id=admin_session_id, is_read=False).exclude(sender_type='pegawai').count()
    
    conversations.append({
        'id': admin_session_id,
        'type': 'admin',
        'name': 'Admin Diskominfosantik',
        'session_id': admin_session_id,
        'last_message': admin_last_msg,
        'unread_count': admin_unread,
        'avatar_letters': 'AD',
        'is_admin': True,
    })
    
    # 2. Chat with Tamu (from Kunjungan)
    # Get all kunjungan that this pegawai can chat with
    # For simplicity, let's get kunjungan where this pegawai is the assignee, and status >= disetujui
    kunjungan_qs = Kunjungan.objects.filter(
        pegawai=pegawai,
        status__in=['disetujui_pegawai', 'disetujui', 'in_progress', 'completed']
    ).select_related('tamu').order_by('-created_at')
    
    for k in kunjungan_qs:
        if PermissionManager.can_access_chat_pegawai_tamu(k):
            session_id = f'kunjungan_{k.id}'
            last_msg = ChatMessage.objects.filter(session_id=session_id).order_by('-created_at').first()
            unread = ChatMessage.objects.filter(session_id=session_id, is_read=False).exclude(sender_type='pegawai').count()
            
            conversations.append({
                'id': str(k.id),
                'type': 'tamu',
                'name': k.tamu.name,
                'session_id': session_id,
                'last_message': last_msg,
                'unread_count': unread,
                'avatar_letters': k.tamu.name[:2].upper(),
                'is_admin': False,
                'kunjungan_id': str(k.id)
            })
            
    # Sort conversations by last_message.created_at descending, putting admin on top if no messages
    def get_sort_key(c):
        if c['last_message']:
            return c['last_message'].created_at.timestamp()
        return 0
        
    conversations.sort(key=get_sort_key, reverse=True)
    
    # Determine active session
    active_session_param = request.GET.get('session')
    active_conversation = None
    messages_list = []
    
    if active_session_param:
        for c in conversations:
            if c['session_id'] == active_session_param or c['id'] == active_session_param:
                active_conversation = c
                break
    
    if not active_conversation and conversations:
        active_conversation = conversations[0]
        
    if active_conversation:
        messages_list = ChatMessage.objects.filter(
            session_id=active_conversation['session_id']
        ).order_by('created_at')
        
        # Mark as read
        ChatMessage.objects.filter(
            session_id=active_conversation['session_id'],
            is_read=False
        ).exclude(sender_type='pegawai').update(is_read=True)
        
    return render(request, 'guest_book/pegawai_chat.html', {
        'pegawai': pegawai,
        'conversations': conversations,
        'active_conversation': active_conversation,
        'messages_list': messages_list,
        'active_page': 'chat'
    })

@pegawai_login_required
def pegawai_profile_view(request, pegawai=None):
    """View untuk update profil pegawai"""
    if request.method == 'POST':
        name = (request.POST.get('name') or '').strip()
        phone = (request.POST.get('phone') or '').strip()
        
        if name and phone:
            pegawai.name = name
            pegawai.phone = phone
            
            # Update password jika diisi
            new_password = request.POST.get('new_password') or ''
            if new_password:
                if len(new_password) < 8:
                    messages.error(request, 'Password baru minimal 8 karakter.')
                    return render(request, 'guest_book/pegawai_profile.html', {
                        'pegawai': pegawai,
                        'active_page': 'profil'
                    })
                from django.contrib.auth.hashers import make_password
                pegawai.password = make_password(new_password)
                
            pegawai.save()
            request.session['pegawai_name'] = pegawai.name
            messages.success(request, 'Profil berhasil diperbarui.')
            return redirect('tamu:pegawai_profile')
        else:
            messages.error(request, 'Nama dan Nomor Telepon wajib diisi.')
            
    return render(request, 'guest_book/pegawai_profile.html', {
        'pegawai': pegawai,
        'active_page': 'profil'
    })

