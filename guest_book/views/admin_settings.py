"""
Views Admin — Modul Pengaturan & Profil
Berisi: profil admin, instansi, pengguna, pegawai, audit log, chat, notifikasi
"""
import json
import os

from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.http import JsonResponse
from django.db.models import Count, Q, Max
from django.core.paginator import Paginator

from .base import admin_login_required, get_admin_context, get_admin_name
from ..models import (
    Tamu, Pegawai, Instansi, Departemen,
    Notification, AuditLog, LoginAttempt, Kunjungan
)


@admin_login_required
def admin_profil_view(request):
    """Profil Administrator"""
    context = get_admin_context(request)
    context['active_page'] = 'profil'

    admin_user = context.get('admin_user')
    if admin_user:
        total_login = LoginAttempt.objects.filter(email=admin_user.email, success=True).count()
        context['total_login'] = total_login

        logs = AuditLog.objects.filter(user_id=str(admin_user.id)).order_by('-timestamp')[:5]
        context['activity_logs'] = logs
        context['data_export'] = Kunjungan.objects.filter(status='completed').count()

        total_attempts = LoginAttempt.objects.filter(email=admin_user.email).count()
        context['uptime'] = round((total_login / total_attempts) * 100) if total_attempts > 0 else 100

        pref_path = os.path.join(os.path.dirname(__file__), '../admin_preferences.json')
        prefs = {}
        if os.path.exists(pref_path):
            try:
                with open(pref_path, 'r') as f:
                    prefs = json.load(f)
            except Exception:
                prefs = {}

        context['email_notif_enabled'] = prefs.get('email_notif_enabled', True)
        context['push_notif_enabled'] = prefs.get('push_notif_enabled', False)

    return render(request, 'guest_book/admin_profil.html', context)


@admin_login_required
def admin_instansi_view(request):
    """Manajemen Instansi dan Departemen"""
    instansi = Instansi.objects.first()
    departemen_all = Departemen.objects.all().order_by('nama')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_instansi':
            if not instansi:
                instansi = Instansi()
            instansi.nama = request.POST.get('nama')
            instansi.slogan = request.POST.get('slogan')
            instansi.status_operasional = request.POST.get('status_operasional')
            instansi.jumlah_petugas = int(request.POST.get('jumlah_petugas', 0))
            instansi.kapasitas_maksimal = int(request.POST.get('kapasitas_maksimal', 100))
            instansi.jam_buka = request.POST.get('jam_buka', '08:00')
            instansi.jam_tutup = request.POST.get('jam_tutup', '16:00')
            instansi.alamat = request.POST.get('alamat')

            hari_kerja = request.POST.get('hari_kerja')
            if hari_kerja:
                instansi.hari_kerja = hari_kerja
            instansi.save()

            from .base import invalidate_admin_cache, record_audit_log
            invalidate_admin_cache()
            admin_id = request.session.get('tamu_id', 'admin')
            record_audit_log(
                user_id=str(admin_id), user_type='admin', action='update',
                table_name='instansi', record_id=str(instansi.id),
                new_value=f"Update nama: {instansi.nama}, kapasitas: {instansi.kapasitas_maksimal}",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, "Data instansi berhasil diperbarui.")
            return redirect(request.META.get('HTTP_REFERER', 'tamu:admin_instansi'))

        elif action == 'add_departemen':
            nama = request.POST.get('nama')
            kode = request.POST.get('kode')
            dep = Departemen.objects.create(nama=nama, kode=kode)

            from .base import record_audit_log
            admin_id = request.session.get('tamu_id', 'admin')
            record_audit_log(
                user_id=str(admin_id), user_type='admin', action='create',
                table_name='departemen', record_id=str(dep.id),
                new_value=f"Menambahkan bidang baru: {nama}",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, f"Departemen {nama} berhasil ditambahkan.")
            return redirect('tamu:admin_instansi')

    context = get_admin_context(request)
    context.update({'instansi': instansi, 'departemen_all': departemen_all, 'active_page': 'instansi'})
    return render(request, 'guest_book/admin_instansi.html', context)


@admin_login_required
def admin_notifications_view(request):
    """Daftar Notifikasi untuk Admin"""
    notifications = Notification.objects.filter(
        recipient_id='admin', recipient_type='admin'
    ).order_by('-created_at')
    notifications.filter(status='unread').update(status='read', read_at=timezone.now())

    context = get_admin_context(request)
    context.update({'notifications': notifications, 'active_page': 'notifications'})
    return render(request, 'guest_book/admin_notifications.html', context)


@admin_login_required
def admin_chat_view(request):
    """Manajemen Chat Admin — menampilkan percakapan dari Tamu dan Pegawai."""
    from ..models import ChatMessage, Pegawai
    from django.db.models import Subquery, OuterRef

    # 1. Ambil list session_id beserta waktu pesan terakhirnya
    sessions = list(ChatMessage.objects.values('session_id').annotate(last_msg=Max('created_at')).order_by('-last_msg'))
    active_session_id = request.GET.get('session') or request.GET.get('guest')

    # 2. Kumpulkan semua ID Tamu dan Pegawai dari session_id
    tamu_ids = []
    pegawai_ids = []
    session_ids = []

    import uuid as _uuid
    for s in sessions:
        sid = s['session_id']
        session_ids.append(sid)
        if sid.startswith('pegawai_admin_'):
            pegawai_ids.append(sid.replace('pegawai_admin_', ''))
        else:
            t_id = sid.replace('tamu_', '') if sid.startswith('tamu_') else sid
            try:
                _uuid.UUID(str(t_id))
                tamu_ids.append(t_id)
            except (ValueError, AttributeError):
                pass  # Skip jika bukan UUID (e.g. kunjungan_*)

    # 3. Batch query (Single DB hit) untuk data Tamu, Pegawai, Unread, dan Last Message
    tamu_dict = {str(t.id): t for t in Tamu.objects.filter(id__in=tamu_ids)}
    pegawai_dict = {str(p.id): p for p in Pegawai.objects.select_related('department_rel').filter(id__in=pegawai_ids)}
    
    # Ambil jumlah unread per session (hanya dari tamu/pegawai ke admin)
    unread_counts = dict(
        ChatMessage.objects.filter(session_id__in=session_ids, is_read=False)
        .exclude(sender_type='admin')
        .values('session_id')
        .annotate(count=Count('id'))
        .values_list('session_id', 'count')
    )

    # Ambil pesan terakhir untuk tiap session (MySQL Compatible)
    latest_timestamps = [s['last_msg'] for s in sessions]
    latest_msgs_qs = ChatMessage.objects.filter(
        session_id__in=session_ids, 
        created_at__in=latest_timestamps
    ).order_by('-created_at')
    
    latest_msg_dict = {}
    for msg in latest_msgs_qs:
        if msg.session_id not in latest_msg_dict:
            latest_msg_dict[msg.session_id] = msg

    conversations = []
    active_conversation = None

    # 4. Susun data percakapan
    for s in sessions:
        sid = s['session_id']
        conv_data = None

        if sid.startswith('pegawai_admin_'):
            pid = sid.replace('pegawai_admin_', '')
            pegawai = pegawai_dict.get(pid)
            if not pegawai:
                continue

            conv_data = {
                'session_id': sid,
                'participant_type': 'pegawai',
                'guest': None,
                'pegawai': pegawai,
                'name': pegawai.name,
                'subtitle': pegawai.department_rel.nama if pegawai.department_rel else 'Pegawai',
            }
        else:
            t_id = sid.replace('tamu_', '') if sid.startswith('tamu_') else sid
            guest = tamu_dict.get(t_id)
            if not guest:
                continue

            conv_data = {
                'session_id': sid,
                'participant_type': 'tamu',
                'guest': guest,
                'pegawai': None,
                'name': guest.name,
                'subtitle': guest.instansi or 'Tamu',
            }

        # Lengkapi conv_data
        conv_data['last_message'] = latest_msg_dict.get(sid)
        conv_data['unread_count'] = unread_counts.get(sid, 0)
        
        # Hanya fetch history messages untuk sesi yang SEDANG AKTIF
        is_active = False
        if active_session_id:
            if sid == active_session_id:
                is_active = True
        elif not active_conversation:
            # Sesi valid pertama otomatis menjadi sesi aktif jika tidak ada parameter GET
            is_active = True
            active_session_id = sid

        if is_active:
            messages_list = list(ChatMessage.objects.filter(session_id=sid).order_by('-created_at')[:50])
            messages_list.reverse()
            conv_data['messages'] = messages_list
            active_conversation = conv_data
        else:
            conv_data['messages'] = []
            conversations.append(conv_data)

    # 5. Tangani fallback jika session aktif baru dibuat / kosong
    if active_session_id and not active_conversation:
        if active_session_id.startswith('pegawai_admin_'):
            pid = active_session_id.replace('pegawai_admin_', '')
            try:
                pegawai = Pegawai.objects.select_related('department_rel').get(id=pid)
                active_conversation = {
                    'session_id': active_session_id, 'participant_type': 'pegawai',
                    'guest': None, 'pegawai': pegawai, 'name': pegawai.name,
                    'subtitle': pegawai.department_rel.nama if pegawai.department_rel else 'Pegawai',
                    'last_message': None, 'unread_count': 0, 'messages': [],
                }
            except Pegawai.DoesNotExist:
                pass
        else:
            t_id = active_session_id.replace('tamu_', '') if active_session_id.startswith('tamu_') else active_session_id
            try:
                guest = Tamu.objects.get(id=t_id)
                active_conversation = {
                    'session_id': active_session_id, 'participant_type': 'tamu',
                    'guest': guest, 'pegawai': None, 'name': guest.name,
                    'subtitle': guest.instansi or 'Tamu',
                    'last_message': None, 'unread_count': 0, 'messages': [],
                }
            except (Tamu.DoesNotExist, ValueError):
                pass

    if active_conversation:
        conversations.insert(0, active_conversation)

    # Mark as read untuk sesi yang aktif
    if active_session_id:
        ChatMessage.objects.filter(
            session_id=active_session_id, is_read=False
        ).exclude(sender_type='admin').update(is_read=True)

    context = get_admin_context(request)
    context.update({'conversations': conversations, 'active_page': 'chat'})
    return render(request, 'guest_book/admin_chat.html', context)


@admin_login_required
def admin_audit_log_view(request):
    """View untuk Laporan Aktivitas (Audit Log)"""
    q_action = request.GET.get('action', '')
    logs_query = AuditLog.objects.all().order_by('-timestamp')
    if q_action:
        logs_query = logs_query.filter(action=q_action)

    paginator = Paginator(logs_query, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    for log in page_obj:
        log.user_name = _resolve_user_name(log)

    ctx = get_admin_context(request)
    ctx.update({'active_page': 'audit_log', 'page_obj': page_obj, 'q_action': q_action})
    return render(request, 'guest_book/admin_audit_log.html', ctx)


@admin_login_required
def admin_audit_log_cetak_pdf(request):
    """View untuk mencetak PDF Laporan Aktivitas"""
    logs_all = AuditLog.objects.all().order_by('-timestamp')
    for log in logs_all:
        log.user_name = _resolve_user_name(log)

    instansi = Instansi.objects.first()
    context = get_admin_context(request)
    context.update({'logs_all': logs_all, 'instansi': instansi})
    return render(request, 'guest_book/admin_audit_log_cetak_pdf.html', context)


def _resolve_user_name(log):
    """Helper: resolve user_name dari AuditLog entry."""
    if log.user_type == 'admin':
        if log.user_id == 'admin':
            return "Administrator"

        try:
            return Tamu.objects.get(id=log.user_id, is_admin=True).name
        except Exception:
            return log.user_id
    elif log.user_type == 'tamu':
        try:
            return Tamu.objects.get(id=log.user_id).name
        except Exception:
            return f"Tamu ({log.user_id[:8]})"
    return log.user_id


@admin_login_required
def admin_pengguna_view(request):
    """Manajemen Pengguna (Blokir/Aktifkan Tamu) dengan Paginasi Efisien"""
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()

    users = Tamu.objects.filter(is_admin=False).annotate(total_visits=Count('kunjungan')).order_by('-registration_date')
    if query:
        users = users.filter(Q(name__icontains=query) | Q(email__icontains=query))
    if status_filter:
        users = users.filter(account_status=status_filter)

    paginator = Paginator(users, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = get_admin_context(request)
    context.update({
        'active_page': 'pengguna',
        'users': page_obj,
        'page_obj': page_obj,
        'query': query,
        'status_filter': status_filter
    })
    return render(request, 'guest_book/admin_pengguna.html', context)


@admin_login_required
def admin_pegawai_view(request):
    """Manajemen Pegawai dengan Role Management"""
    query = request.GET.get('q', '')
    status_filter = request.GET.get('status', '')
    role_filter = request.GET.get('role', '')
    dept_filter = request.GET.get('dept', '')

    pegawai_list = Pegawai.objects.select_related('department_rel').annotate(
        total_visits=Count('kunjungan_diterima')
    ).order_by('-created_at')

    if query:
        pegawai_list = pegawai_list.filter(Q(name__icontains=query) | Q(email__icontains=query) | Q(nip__icontains=query))
    if status_filter:
        pegawai_list = pegawai_list.filter(account_status=status_filter)
    if role_filter:
        pegawai_list = pegawai_list.filter(role=role_filter)
    if dept_filter:
        pegawai_list = pegawai_list.filter(department_rel_id=dept_filter)

    stats = Pegawai.objects.aggregate(
        total=Count('id'),
        active=Count('id', filter=Q(account_status='active')),
        staff=Count('id', filter=Q(role='staff')),
        supervisor=Count('id', filter=Q(role='supervisor')),
        manager=Count('id', filter=Q(role='manager')),
        admin=Count('id', filter=Q(role='admin')),
    )

    paginator = Paginator(pegawai_list, 100)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = get_admin_context(request)
    context.update({
        'active_page': 'pegawai',
        'pegawai_list': page_obj,
        'departemen_list': Departemen.objects.all().order_by('nama'),
        'query': query,
        'status_filter': status_filter,
        'role_filter': role_filter,
        'dept_filter': dept_filter,
        'stats': stats,
        'role_choices': Pegawai.ROLE_CHOICES,
        'status_choices': Pegawai.STATUS_CHOICES,
    })
    return render(request, 'guest_book/admin_pegawai.html', context)


@admin_login_required
def admin_pegawai_update_role(request, pegawai_id):
    """Update role pegawai (AJAX endpoint)"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    try:
        pegawai = Pegawai.objects.get(pk=pegawai_id)
        data = json.loads(request.body)
        new_role = data.get('role')

        if new_role not in dict(Pegawai.ROLE_CHOICES):
            return JsonResponse({'success': False, 'message': 'Role tidak valid'}, status=400)

        old_role = pegawai.role
        pegawai.role = new_role
        pegawai.save(update_fields=['role'])

        AuditLog.objects.create(
            user_id=get_admin_name(request), user_type='admin', action='update',
            table_name='pegawai', record_id=str(pegawai.id),
            old_value={'role': old_role}, new_value={'role': new_role},
            ip_address=request.META.get('REMOTE_ADDR')
        )

        return JsonResponse({'success': True, 'message': f'Role berhasil diubah menjadi {new_role}', 'new_role': new_role, 'pegawai_name': pegawai.name})

    except Pegawai.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Pegawai tidak ditemukan'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)


@admin_login_required
def admin_pegawai_update_status(request, pegawai_id):
    """Update status pegawai (AJAX endpoint)"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    try:
        pegawai = Pegawai.objects.get(pk=pegawai_id)
        data = json.loads(request.body)
        new_status = data.get('status')

        if new_status not in dict(Pegawai.STATUS_CHOICES):
            return JsonResponse({'success': False, 'message': 'Status tidak valid'}, status=400)

        old_status = pegawai.account_status
        pegawai.account_status = new_status
        pegawai.save(update_fields=['account_status'])

        AuditLog.objects.create(
            user_id=get_admin_name(request), user_type='admin', action='update',
            table_name='pegawai', record_id=str(pegawai.id),
            old_value={'account_status': old_status}, new_value={'account_status': new_status},
            ip_address=request.META.get('REMOTE_ADDR')
        )

        return JsonResponse({'success': True, 'message': f'Status berhasil diubah menjadi {new_status}', 'new_status': new_status, 'pegawai_name': pegawai.name})

    except Pegawai.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Pegawai tidak ditemukan'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)

