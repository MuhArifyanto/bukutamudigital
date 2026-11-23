"""
Views Admin — Modul Pengaturan & Profil
Berisi: profil admin, instansi, pengguna, pegawai, audit log, chat, notifikasi
"""
import json
import logging
import uuid

from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.http import JsonResponse
from django.db.models import Count, Q, Max
from django.core.paginator import Paginator

from .base import (
    admin_login_required, check_is_super_admin, clamp_page_size,
    get_admin_context, get_admin_name, resolve_admin_record,
)
from ..models import (
    Admin, Tamu, Pegawai, Instansi, Departemen,
    Notification, AuditLog, LoginAttempt, Kunjungan
)

logger = logging.getLogger(__name__)


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

    admin_record = resolve_admin_record(getattr(request, 'user', None))
    if admin_record is None and admin_user and getattr(admin_user, 'email', None):
        admin_record = Admin.objects.filter(
            email__iexact=admin_user.email, account_status='active'
        ).first()

    context['email_notif_enabled'] = bool(admin_record.email_notif_enabled) if admin_record else True
    context['push_notif_enabled'] = bool(admin_record.push_notif_enabled) if admin_record else False
    context['admin_2fa_enabled'] = bool(admin_record and admin_record.two_fa_enabled and admin_record.two_fa_secret)

    return render(request, 'guest_book/admin_profil.html', context)


@admin_login_required
def admin_instansi_view(request):
    """Manajemen Instansi dan Departemen"""
    instansi = Instansi.objects.first()
    departemen_all = Departemen.objects.all().order_by('nama')

    if request.method == 'POST':
        is_super, _ = check_is_super_admin(request)
        if not is_super:
            messages.error(request, "Akses khusus Super Admin diperlukan untuk mengubah pengaturan instansi atau bidang.")
            return redirect('tamu:admin_instansi')

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
            referer = request.META.get('HTTP_REFERER')
            if referer and url_has_allowed_host_and_scheme(
                referer,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(referer)
            return redirect('tamu:admin_instansi')

        elif action == 'add_departemen':
            nama = (request.POST.get('nama') or '').strip()
            kode = (request.POST.get('kode') or '').strip()
            if not nama:
                messages.error(request, "Nama bidang/departemen wajib diisi.")
                return redirect('tamu:admin_instansi')

            dep = Departemen.objects.create(nama=nama, kode=kode or None)

            from .base import record_audit_log
            from .auth import get_client_ip
            admin_actor = (
                str(request.user.pk)
                if getattr(request, 'user', None) and request.user.is_authenticated
                else str(request.session.get('tamu_id', 'admin'))
            )
            record_audit_log(
                user_id=admin_actor, user_type='admin', action='create',
                table_name='departemen', record_id=str(dep.id),
                new_value=f"Menambahkan bidang baru: {nama}",
                ip_address=get_client_ip(request)
            )
            messages.success(request, f"Departemen {nama} berhasil ditambahkan.")
            return redirect('tamu:admin_instansi')

        elif action == 'delete_departemen':
            import uuid
            from .base import record_audit_log
            from .auth import get_client_ip

            dept_id = (request.POST.get('dept_id') or '').strip()
            try:
                dept_uuid = uuid.UUID(dept_id)
            except (ValueError, TypeError):
                messages.error(request, "ID bidang/departemen tidak valid.")
                return redirect('tamu:admin_instansi')

            dep = Departemen.objects.filter(pk=dept_uuid).first()
            if not dep:
                messages.error(request, "Bidang/departemen tidak ditemukan.")
                return redirect('tamu:admin_instansi')

            active_pegawai_count = dep.pegawai_list.filter(account_status='active').count()
            if active_pegawai_count > 0:
                messages.error(
                    request,
                    f"Bidang {dep.nama} tidak dapat dihapus karena masih memiliki {active_pegawai_count} pegawai aktif. "
                    "Pindahkan atau nonaktifkan pegawai terlebih dahulu."
                )
                return redirect('tamu:admin_instansi')

            dep_id_str = str(dep.id)
            dep_nama = dep.nama
            dep_kode = dep.kode
            dep.delete()

            admin_actor = (
                str(request.user.pk)
                if getattr(request, 'user', None) and request.user.is_authenticated
                else str(request.session.get('tamu_id', 'admin'))
            )
            record_audit_log(
                user_id=admin_actor,
                user_type='admin',
                action='delete',
                table_name='departemen',
                record_id=dep_id_str,
                old_value={'nama': dep_nama, 'kode': dep_kode},
                ip_address=get_client_ip(request),
            )
            messages.success(request, f"Bidang {dep_nama} berhasil dihapus.")
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
    from ..models import ChatMessage, ChatRoom, Pegawai

    # 1. Ambil list session_id beserta waktu pesan terakhirnya
    sessions = list(ChatMessage.objects.values('session_id').annotate(last_msg=Max('created_at')).order_by('-last_msg'))
    active_session_id = request.GET.get('session') or request.GET.get('guest')

    # 2. Kumpulkan semua ID Tamu dan Pegawai dari session_id memakai parser terstruktur
    tamu_ids = []
    pegawai_ids = []
    session_ids = []
    parsed_sessions = {}

    for s in sessions:
        sid = s['session_id']
        session_ids.append(sid)
        parsed = ChatRoom.parse_session_id(sid)
        parsed_sessions[sid] = parsed
        if parsed['entity_uuid'] is not None:
            if parsed['room_type'] == ChatRoom.RoomType.PEGAWAI_ADMIN:
                pegawai_ids.append(parsed['entity_uuid'])
            elif parsed['room_type'] == ChatRoom.RoomType.TAMU_ADMIN:
                tamu_ids.append(parsed['entity_uuid'])

    # 3. Batch query (Single DB hit) untuk data Tamu, Pegawai, Unread, dan Last Message
    tamu_dict = {str(t.id): t for t in Tamu.objects.filter(id__in=tamu_ids)}
    pegawai_dict = {str(p.id): p for p in Pegawai.objects.select_related('department_rel').filter(id__in=pegawai_ids)}

    # Ambil jumlah unread & pesan terakhir secara batch (memakai index komposit)
    unread_counts = ChatMessage.unread_counts_by_session(session_ids, exclude_sender_type='admin')
    latest_msg_dict = ChatMessage.latest_by_session(session_ids)

    conversations = []
    active_conversation = None

    # 4. Susun data percakapan
    for s in sessions:
        sid = s['session_id']
        parsed = parsed_sessions[sid]
        conv_data = None

        if parsed['room_type'] == ChatRoom.RoomType.PEGAWAI_ADMIN and parsed['entity_uuid']:
            pegawai = pegawai_dict.get(str(parsed['entity_uuid']))
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
        elif parsed['room_type'] == ChatRoom.RoomType.TAMU_ADMIN and parsed['entity_uuid']:
            guest = tamu_dict.get(str(parsed['entity_uuid']))
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
        else:
            continue

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
        parsed_active = ChatRoom.parse_session_id(active_session_id)
        if parsed_active['room_type'] == ChatRoom.RoomType.PEGAWAI_ADMIN and parsed_active['entity_uuid']:
            pegawai = Pegawai.objects.select_related('department_rel').filter(id=parsed_active['entity_uuid']).first()
            if pegawai:
                ChatRoom.resolve_or_create_for_session(active_session_id)
                active_conversation = {
                    'session_id': active_session_id, 'participant_type': 'pegawai',
                    'guest': None, 'pegawai': pegawai, 'name': pegawai.name,
                    'subtitle': pegawai.department_rel.nama if pegawai.department_rel else 'Pegawai',
                    'last_message': None, 'unread_count': 0, 'messages': [],
                }
        elif parsed_active['room_type'] == ChatRoom.RoomType.TAMU_ADMIN and parsed_active['entity_uuid']:
            guest = Tamu.objects.filter(id=parsed_active['entity_uuid']).first()
            if guest:
                ChatRoom.resolve_or_create_for_session(active_session_id)
                active_conversation = {
                    'session_id': active_session_id, 'participant_type': 'tamu',
                    'guest': guest, 'pegawai': None, 'name': guest.name,
                    'subtitle': guest.instansi or 'Tamu',
                    'last_message': None, 'unread_count': 0, 'messages': [],
                }

    if active_conversation:
        conversations.insert(0, active_conversation)

    # Mark as read untuk sesi yang aktif
    if active_session_id:
        ChatMessage.objects.filter(
            session_id=active_session_id, is_read=False
        ).exclude(sender_type='admin').update(is_read=True)
    if active_conversation:
        active_conversation['unread_count'] = 0

    context = get_admin_context(request)
    context.update({'conversations': conversations, 'active_page': 'chat'})
    return render(request, 'guest_book/admin_chat.html', context)


@admin_login_required
def admin_audit_log_view(request):
    """View untuk Laporan Aktivitas (Audit Log)"""
    q_action = request.GET.get('action', '').strip()
    logs_query = AuditLog.objects.all().order_by('-timestamp')
    if q_action:
        logs_query = logs_query.filter(action=q_action)

    paginator = Paginator(logs_query, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    _attach_audit_log_user_names(page_obj.object_list)

    ctx = get_admin_context(request)
    ctx.update({'active_page': 'audit_log', 'page_obj': page_obj, 'q_action': q_action})
    return render(request, 'guest_book/admin_audit_log.html', ctx)


@admin_login_required
def admin_audit_log_cetak_pdf(request):
    """View untuk mencetak PDF Laporan Aktivitas (terbatas & bebas N+1)."""
    q_action = request.GET.get('action', '').strip()
    limit = clamp_page_size(request.GET.get('limit'), default=500, min_size=1, max_size=1000)

    logs_qs = AuditLog.objects.all().order_by('-timestamp')
    if q_action:
        logs_qs = logs_qs.filter(action=q_action)

    logs_all = _attach_audit_log_user_names(logs_qs[:limit])

    context = get_admin_context(request)
    context.update({'logs_all': logs_all, 'q_action': q_action, 'print_limit': limit})
    return render(request, 'guest_book/admin_audit_log_cetak_pdf.html', context)


def _normalize_uuid_str(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _attach_audit_log_user_names(logs):
    """Batch-resolve user_name untuk koleksi AuditLog tanpa N+1 query."""
    from django.contrib.auth.models import User

    logs_list = list(logs)
    if not logs_list:
        return logs_list

    tamu_uuids = set()
    admin_uuids = set()
    admin_int_ids = set()
    pegawai_uuids = set()
    normalized_ids = {}

    for log in logs_list:
        uid = (log.user_id or '').strip()
        if not uid or (log.user_type == 'admin' and uid == 'admin'):
            continue

        if log.user_type == 'admin':
            if uid.isdigit():
                admin_int_ids.add(int(uid))
            else:
                norm_id = _normalize_uuid_str(uid)
                if norm_id:
                    normalized_ids[uid] = norm_id
                    parsed_uuid = uuid.UUID(norm_id)
                    tamu_uuids.add(parsed_uuid)
                    admin_uuids.add(parsed_uuid)
        elif log.user_type == 'tamu':
            norm_id = _normalize_uuid_str(uid)
            if norm_id:
                normalized_ids[uid] = norm_id
                tamu_uuids.add(uuid.UUID(norm_id))
        elif log.user_type == 'pegawai':
            norm_id = _normalize_uuid_str(uid)
            if norm_id:
                normalized_ids[uid] = norm_id
                pegawai_uuids.add(uuid.UUID(norm_id))

    tamu_map = {}
    tamu_admin_map = {}
    if tamu_uuids:
        for tid, name, is_admin in Tamu.objects.filter(id__in=tamu_uuids).values_list('id', 'name', 'is_admin'):
            key = str(tid)
            tamu_map[key] = name
            if is_admin:
                tamu_admin_map[key] = name

    admin_model_map = {}
    if admin_uuids:
        for aid, name in Admin.objects.filter(id__in=admin_uuids).values_list('id', 'name'):
            admin_model_map[str(aid)] = name

    auth_user_map = {}
    if admin_int_ids:
        for u in User.objects.filter(pk__in=admin_int_ids).only('id', 'username', 'first_name', 'last_name'):
            auth_user_map[str(u.pk)] = (u.get_full_name() or '').strip() or u.username

    pegawai_map = {}
    if pegawai_uuids:
        for pid, name in Pegawai.objects.filter(id__in=pegawai_uuids).values_list('id', 'name'):
            pegawai_map[str(pid)] = name

    for log in logs_list:
        uid = (log.user_id or '').strip()
        norm_uid = normalized_ids.get(uid, uid)
        if log.user_type == 'admin':
            if uid == 'admin':
                log.user_name = "Administrator"
            elif norm_uid in tamu_admin_map:
                log.user_name = tamu_admin_map[norm_uid]
            elif norm_uid in admin_model_map:
                log.user_name = admin_model_map[norm_uid]
            elif uid in auth_user_map:
                log.user_name = auth_user_map[uid]
            else:
                log.user_name = log.user_id
        elif log.user_type == 'tamu':
            log.user_name = tamu_map.get(norm_uid) or f"Tamu ({uid[:8]})"
        elif log.user_type == 'pegawai':
            log.user_name = pegawai_map.get(norm_uid) or log.user_id
        else:
            log.user_name = log.user_id

    return logs_list


def _resolve_user_name(log):
    """Helper kompatibilitas: resolve user_name untuk satu AuditLog entry."""
    return _attach_audit_log_user_names([log])[0].user_name


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
    # Sinkronisasi data awal pegawai hanya dijalankan melalui command CLI (`manage.py seed_pegawai`),
    # bukan saat HTTP GET request agar perubahan status/role admin tidak tertimpa.

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

    is_super, _ = check_is_super_admin(request)
    if not is_super:
        return JsonResponse({'success': False, 'message': 'Akses khusus Super Admin diperlukan untuk mengubah role pegawai.'}, status=403)

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
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'message': 'Format permintaan tidak valid.'}, status=400)
    except Exception:
        logger.exception("Gagal memperbarui role pegawai %s", pegawai_id)
        return JsonResponse({'success': False, 'message': 'Terjadi kesalahan saat memperbarui role pegawai.'}, status=500)


@admin_login_required
def admin_pegawai_update_status(request, pegawai_id):
    """Update status pegawai (AJAX endpoint)"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)

    is_super, _ = check_is_super_admin(request)
    if not is_super:
        return JsonResponse({'success': False, 'message': 'Akses khusus Super Admin diperlukan untuk mengubah status pegawai.'}, status=403)

    try:
        pegawai = Pegawai.objects.get(pk=pegawai_id)
        data = json.loads(request.body)
        new_status = data.get('status')

        if new_status not in dict(Pegawai.STATUS_CHOICES):
            return JsonResponse({'success': False, 'message': 'Status tidak valid'}, status=400)

        old_status = pegawai.account_status
        pegawai.account_status = new_status
        pegawai.save(update_fields=['account_status'])

        if new_status != 'active':
            from ..security_utils import revoke_user_sessions
            revoke_user_sessions('pegawai', str(pegawai.id))

        AuditLog.objects.create(
            user_id=get_admin_name(request), user_type='admin', action='update',
            table_name='pegawai', record_id=str(pegawai.id),
            old_value={'account_status': old_status}, new_value={'account_status': new_status},
            ip_address=request.META.get('REMOTE_ADDR')
        )

        return JsonResponse({'success': True, 'message': f'Status berhasil diubah menjadi {new_status}', 'new_status': new_status, 'pegawai_name': pegawai.name})

    except Pegawai.DoesNotExist:
        return JsonResponse({'success': False, 'message': 'Pegawai tidak ditemukan'}, status=404)
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'message': 'Format permintaan tidak valid.'}, status=400)
    except Exception:
        logger.exception("Gagal memperbarui status pegawai %s", pegawai_id)
        return JsonResponse({'success': False, 'message': 'Terjadi kesalahan saat memperbarui status pegawai.'}, status=500)

