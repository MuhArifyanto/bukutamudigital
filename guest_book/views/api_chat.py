"""
API Views — Chat (send, upload, history, delete, search users)
"""
import json
import logging

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator

from .base import admin_login_required, check_is_admin, clamp_page_size
from ..models import Notification, ChatMessage, Tamu

logger = logging.getLogger(__name__)


@admin_login_required
def api_send_chat_message(request):
    """Kirim pesan chat (Admin)"""
    try:
        data = json.loads(request.body)
        session_id = data.get('session_id')
        content = data.get('content')

        if not session_id or not content:
            return JsonResponse({'success': False, 'error': 'Data tidak lengkap'}, status=400)

        msg = ChatMessage.objects.create(
            session_id=session_id, sender_id='admin',
            sender_type='admin', content=content
        )

        Notification.objects.create(
            recipient_id=session_id, recipient_type='tamu',
            notification_type='message_replied',
            title='Pesan Dibalas oleh Admin',
            message=f'Admin: {content}', related_object_id='admin'
        )

        from ..utils import send_chat_sidebar_update
        send_chat_sidebar_update(
            session_id=session_id,
            sender_id='admin',
            sender_type='admin',
            message=content,
            message_type='text',
            message_id=msg.id,
            created_at_dt=msg.created_at,
        )

        return JsonResponse({'success': True, 'message': {
            'id': str(msg.id), 'content': msg.content,
            'created_at': msg.created_at.strftime('%H:%M')
        }})
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({'success': False, 'error': 'Format pesan tidak valid.'}, status=400)
    except Exception:
        logger.exception("Gagal mengirim pesan chat oleh admin")
        return JsonResponse({'success': False, 'error': 'Terjadi kesalahan saat mengirim pesan.'}, status=500)


def _resolve_active_chat_actor(request):
    """
    Verifikasi identitas pengakses endpoint chat terhadap status aktif di database.
    Mengembalikan tuple: (is_admin: bool, active_tamu_id: str, active_pegawai_id: str).
    """
    from django.core.exceptions import ValidationError
    from ..models import Pegawai

    is_admin, _ = check_is_admin(request)
    if is_admin:
        return True, '', ''

    active_tamu_id = ''
    raw_tamu_id = str(request.session.get('tamu_id') or '').strip()
    if raw_tamu_id:
        try:
            if Tamu.objects.filter(pk=raw_tamu_id, account_status='active').exists():
                active_tamu_id = raw_tamu_id
        except (ValueError, TypeError, ValidationError):
            active_tamu_id = ''

    active_pegawai_id = ''
    raw_pegawai_id = str(request.session.get('pegawai_id') or '').strip()
    if raw_pegawai_id:
        try:
            if Pegawai.objects.filter(pk=raw_pegawai_id, account_status='active').exists():
                active_pegawai_id = raw_pegawai_id
        except (ValueError, TypeError, ValidationError):
            active_pegawai_id = ''

    return False, active_tamu_id, active_pegawai_id


def api_upload_chat_file(request):

    """Upload file/gambar dalam chat ke Storage dengan verifikasi status akun aktif."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    is_admin, tamu_id, pegawai_id = _resolve_active_chat_actor(request)
    if not (is_admin or tamu_id or pegawai_id):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    # Rate limit unggahan lampiran chat (maks 15 file per 5 menit per aktor/IP)
    from .auth import check_rate_limit, get_client_ip, record_rate_limit_attempt
    client_ip = get_client_ip(request)
    actor_tag = (
        f"admin_{getattr(request.user, 'pk', 's')}"
        if is_admin
        else (f"pegawai_{pegawai_id}" if pegawai_id else f"tamu_{tamu_id}")
    )
    rl_key = f"rl_chat_upload_{actor_tag}_{client_ip}"
    if check_rate_limit(rl_key, max_attempts=15, fail_closed=False):
        return JsonResponse(
            {'success': False, 'error': 'Terlalu banyak unggahan berkas dalam waktu singkat. Coba lagi dalam beberapa menit.'},
            status=429,
        )
    record_rate_limit_attempt(rl_key, timeout_seconds=300)

    file_obj = request.FILES.get('file')
    if not file_obj:
        return JsonResponse({'success': False, 'error': 'No file uploaded'}, status=400)

    original_name = (getattr(file_obj, 'name', '') or '').replace('/', '_').replace('\\', '_')

    from ..utils import validate_uploaded_file
    is_valid, error_message, safe_name = validate_uploaded_file(
        file_obj,
        max_size_bytes=5 * 1024 * 1024,
        allowed_extensions=['doc', 'docx', 'xls', 'xlsx', 'png', 'jpg', 'jpeg', 'pdf']
    )
    if not is_valid:
        return JsonResponse({'success': False, 'error': error_message}, status=400)

    from django.core.files.storage import default_storage

    try:
        path = default_storage.save(f'chat_attachments/{safe_name}', file_obj)
        file_url = default_storage.url(path)
    except Exception:
        logger.exception("Gagal menyimpan lampiran chat ke penyimpanan media")
        return JsonResponse({
            'success': False,
            'error': 'Gagal mengunggah berkas ke penyimpanan. Silakan coba beberapa saat lagi.'
        }, status=500)

    ext = safe_name.split('.')[-1].lower() if '.' in safe_name else ''
    message_type = 'image' if ext in ['jpg', 'jpeg', 'png'] else 'file'

    return JsonResponse({
        'success': True, 'file_url': file_url,
        'file_path': path, 'message_type': message_type,
        'file_name': original_name
    })


def api_search_users(request):
    """Cari user untuk mulai chat baru dengan proteksi privasi, optimasi kueri & rate limit"""
    is_admin, tamu_id, pegawai_id = _resolve_active_chat_actor(request)

    if not (is_admin or tamu_id or pegawai_id):
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    # Rate limiting: max 30 pencarian per menit per IP / user
    from .auth import get_client_ip, check_rate_limit, record_rate_limit_attempt
    client_ip = get_client_ip(request)
    user_identifier = f"admin_{request.user.id}" if is_admin else (f"pegawai_{pegawai_id}" if pegawai_id else f"tamu_{tamu_id}")
    rl_key = f"rl_chat_search_{client_ip}_{user_identifier}"
    if check_rate_limit(rl_key, max_attempts=30):
        return JsonResponse({'success': False, 'error': 'Terlalu banyak permintaan pencarian. Silakan tunggu sebentar.'}, status=429)
    record_rate_limit_attempt(rl_key, timeout_seconds=60)

    query = request.GET.get('q', '').strip()
    # Hindari full-table scan pada query kosong atau kurang dari 2 karakter
    if len(query) < 2:
        return JsonResponse({'success': True, 'users': []})

    from ..models import Tamu, Pegawai, Kunjungan, ChatRoom
    users_data = []

    # 1. Jika TAMU:
    # Tamu HANYA boleh mencari Pegawai yang ditugaskan pada kunjungannya.
    # Tamu TIDAK PERNAH boleh mencari data sesama Tamu (mencegah enumerasi & kebocoran data pribadi).
    if tamu_id and not is_admin and not pegawai_id:
        assigned_pegawai_ids = Kunjungan.objects.filter(
            tamu_id=tamu_id,
            pegawai__isnull=False
        ).values_list('pegawai_id', flat=True).distinct()

        pegawai_list = Pegawai.objects.filter(
            id__in=assigned_pegawai_ids,
            name__icontains=query,
            account_status='active'
        ).select_related('department_rel').only('id', 'name', 'department_rel__nama')[:10]

        for p in pegawai_list:
            dept_name = p.department_rel.nama if p.department_rel else 'Pegawai'
            users_data.append({
                'id': str(p.id),
                'name': p.name,
                'email': dept_name,
                'session_id': ChatRoom.session_id_for_pegawai_admin(p.id),
                'type': 'pegawai'
            })

        return JsonResponse({'success': True, 'users': users_data})

    # 2. Jika ADMIN atau PEGAWAI:
    # Boleh mencari Tamu dan Pegawai aktif
    tamu_list = Tamu.objects.filter(
        name__icontains=query,
        account_status='active'
    ).only('id', 'name', 'instansi')[:10]

    for t in tamu_list:
        users_data.append({
            'id': str(t.id),
            'name': t.name,
            'email': t.instansi or 'Tamu',
            'session_id': ChatRoom.session_id_for_tamu(t.id),
            'type': 'tamu'
        })

    # Cari Pegawai (dengan select_related('department_rel') untuk mencegah query N+1)
    pegawai_query = Pegawai.objects.filter(
        name__icontains=query,
        account_status='active'
    ).select_related('department_rel').only('id', 'name', 'department_rel__nama')

    if pegawai_id and not is_admin:
        pegawai_query = pegawai_query.exclude(id=pegawai_id)

    pegawai_list = pegawai_query[:10]

    for p in pegawai_list:
        dept_name = p.department_rel.nama if p.department_rel else 'Pegawai'
        users_data.append({
            'id': str(p.id),
            'name': p.name,
            'email': dept_name,
            'session_id': ChatRoom.session_id_for_pegawai_admin(p.id),
            'type': 'pegawai'
        })

    return JsonResponse({'success': True, 'users': users_data})


def _build_chat_room_meta(session_id, is_admin, tamu_id, pegawai_id):
    """Susun metadata header ruang chat sesuai peran pengguna yang membuka room."""
    from ..models import ChatRoom, Pegawai, Kunjungan
    from ..utils import is_session_handed_off_to_admin

    parsed = ChatRoom.parse_session_id(session_id)
    room_type = parsed['room_type']
    entity_uuid = parsed['entity_uuid']

    if room_type == ChatRoom.RoomType.PEGAWAI_ADMIN:
        pegawai = (
            Pegawai.objects.select_related('department_rel').filter(id=entity_uuid).first()
            if entity_uuid is not None else None
        )
        if is_admin:
            name = pegawai.name if pegawai else 'Pegawai'
            subtitle = (
                pegawai.department_rel.nama
                if (pegawai and pegawai.department_rel)
                else 'Saluran komunikasi terverifikasi'
            )
            return {
                'session_id': session_id,
                'name': name,
                'subtitle': subtitle,
                'participant_type': 'pegawai',
                'role_label': 'Pegawai Dinas',
                'avatar_letters': name[:2].upper(),
                'is_admin_room': False,
                'ai_handoff_active': False,
            }
        return {
            'session_id': session_id,
            'name': 'Admin Diskominfosantik',
            'subtitle': 'Saluran koordinasi dengan Admin Diskominfosantik',
            'participant_type': 'admin',
            'role_label': 'Admin Resepsionis',
            'avatar_letters': 'AD',
            'is_admin_room': True,
            'ai_handoff_active': False,
        }

    if room_type == ChatRoom.RoomType.KUNJUNGAN:
        kunjungan = (
            Kunjungan.objects.select_related('tamu', 'pegawai', 'pegawai__department_rel')
            .filter(id=entity_uuid)
            .first()
            if entity_uuid is not None else None
        )
        if pegawai_id and not is_admin:
            tamu_name = kunjungan.tamu.name if (kunjungan and kunjungan.tamu) else 'Tamu'
            return {
                'session_id': session_id,
                'name': tamu_name,
                'subtitle': 'Kunjungan Resmi Buku Tamu Digital • Sesi Terverifikasi',
                'participant_type': 'tamu',
                'role_label': 'Tamu Resmi',
                'avatar_letters': tamu_name[:2].upper(),
                'is_admin_room': False,
                'ai_handoff_active': False,
            }
        peg_name = kunjungan.pegawai.name if (kunjungan and kunjungan.pegawai) else 'Pegawai'
        peg_sub = 'Pegawai'
        if kunjungan and kunjungan.pegawai:
            peg_sub = kunjungan.pegawai.department or (
                kunjungan.pegawai.department_rel.nama if kunjungan.pegawai.department_rel else 'Pegawai'
            )
        return {
            'session_id': session_id,
            'name': peg_name,
            'subtitle': peg_sub,
            'participant_type': 'pegawai',
            'role_label': 'Pegawai Tujuan',
            'avatar_letters': peg_name[:2].upper(),
            'is_admin_room': False,
            'ai_handoff_active': False,
        }

    # Room Tamu <-> Admin
    if is_admin:
        guest = Tamu.objects.filter(id=entity_uuid).first() if entity_uuid is not None else None
        guest_name = guest.name if guest else 'Tamu'
        guest_sub = (guest.instansi if guest else None) or 'Saluran komunikasi terverifikasi'
        return {
            'session_id': session_id,
            'name': guest_name,
            'subtitle': guest_sub,
            'participant_type': 'tamu',
            'role_label': 'Tamu Resmi',
            'avatar_letters': guest_name[:2].upper(),
            'is_admin_room': False,
            'ai_handoff_active': False,
        }

    return {
        'session_id': session_id,
        'name': 'Admin Diskominfosantik',
        'subtitle': 'Layanan Umum & Asisten AI',
        'participant_type': 'admin',
        'role_label': 'Admin Resepsionis',
        'avatar_letters': 'AD',
        'is_admin_room': True,
        'ai_handoff_active': is_session_handed_off_to_admin(session_id),
    }


def api_get_chat_messages(request):
    """Ambil history chat terbaru (Admin, Pegawai, atau Tamu yang berhak)"""
    session_id = request.GET.get('session_id')
    last_id = request.GET.get('last_id')
    mark_read = request.GET.get('mark_read') == '1'
    page = request.GET.get('page', 1)
    page_size = clamp_page_size(request.GET.get('page_size'), default=50, max_size=100)

    if not session_id:
        return JsonResponse({'success': False, 'error': 'session_id required'}, status=400)

    # Validasi Hak Akses Sesi Chat & Status Aktif DB (K-3)
    is_admin, tamu_id, pegawai_id = _resolve_active_chat_actor(request)

    from ..models import ChatRoom, Kunjungan
    from ..permissions import PermissionManager

    parsed = ChatRoom.parse_session_id(session_id)
    has_permission = False
    if is_admin:
        has_permission = True
    elif tamu_id and parsed['room_type'] == ChatRoom.RoomType.TAMU_ADMIN and (
        session_id == tamu_id or session_id == f"tamu_{tamu_id}"
    ):
        has_permission = True
    elif pegawai_id and parsed['room_type'] == ChatRoom.RoomType.PEGAWAI_ADMIN and (
        session_id == ChatRoom.session_id_for_pegawai_admin(pegawai_id)
    ):
        has_permission = True
    elif parsed['room_type'] == ChatRoom.RoomType.KUNJUNGAN and parsed['entity_uuid'] is not None:
        kunjungan = Kunjungan.objects.filter(id=parsed['entity_uuid']).first()
        if kunjungan and PermissionManager.can_access_chat_pegawai_tamu(kunjungan):
            if pegawai_id and str(kunjungan.pegawai_id) == pegawai_id:
                has_permission = True
            elif tamu_id and str(kunjungan.tamu_id) == tamu_id:
                has_permission = True

    if not has_permission:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)

    qs = ChatMessage.objects.filter(session_id=session_id)
    if last_id:
        try:
            last_msg = ChatMessage.objects.get(id=last_id)
            qs = qs.filter(created_at__gt=last_msg.created_at)
        except Exception:
            pass

    qs = qs.order_by('-created_at')
    paginator = Paginator(qs, page_size)
    try:
        page_obj = paginator.page(page)
    except Exception:
        page_obj = paginator.page(1)

    from ..templatetags.custom_filters import smart_date

    messages_data = []
    mark_read_ids = []
    for m in reversed(page_obj.object_list):
        messages_data.append({
            'id': str(m.id),
            'content': m.content,
            'sender_id': str(m.sender_id),
            'sender_type': m.sender_type,
            'message_type': m.message_type,
            'file_url': m.attachment.url if m.attachment else None,
            'is_read': bool(m.is_read),
            'created_at': timezone.localtime(m.created_at).strftime('%H:%M') if m.created_at else '',
            'created_at_iso': m.created_at.isoformat() if m.created_at else '',
            'date_label': smart_date(m.created_at) if m.created_at else '',
        })
        if not m.is_read:
            if is_admin and m.sender_type != 'admin' and not session_id.startswith('kunjungan_'):
                mark_read_ids.append(m.id)
            elif pegawai_id and not is_admin and m.sender_type != 'pegawai':
                mark_read_ids.append(m.id)
            elif tamu_id and not is_admin and m.sender_type != 'tamu':
                mark_read_ids.append(m.id)

    if mark_read:
        viewer_sender = 'admin' if is_admin else ('pegawai' if pegawai_id else 'tamu')
        ChatMessage.objects.filter(
            session_id=session_id,
            is_read=False,
        ).exclude(sender_type=viewer_sender).update(is_read=True)
    elif mark_read_ids:
        ChatMessage.objects.filter(id__in=mark_read_ids, is_read=False).update(is_read=True)

    # Sinkronkan notifikasi chat terkait agar badge lonceng juga ikut terbarui
    unread_notif_count = None
    if mark_read or mark_read_ids:
        from django.db.models import Q
        if is_admin:
            Notification.objects.filter(
                recipient_type='admin', status='unread', related_object_id=session_id
            ).update(status='read', read_at=timezone.now())
            unread_notif_count = Notification.objects.filter(recipient_type='admin', status='unread').count()
        elif pegawai_id:
            Notification.objects.filter(
                recipient_id=str(pegawai_id), recipient_type='pegawai', status='unread'
            ).filter(
                Q(related_object_id=session_id) | Q(related_object_id=session_id.replace('kunjungan_', '', 1))
            ).update(status='read', read_at=timezone.now())
            unread_notif_count = Notification.objects.filter(
                recipient_id=str(pegawai_id), recipient_type='pegawai', status='unread'
            ).count()
        elif tamu_id:
            Notification.objects.filter(
                recipient_id=str(tamu_id), recipient_type='tamu', status='unread'
            ).filter(
                Q(related_object_id=session_id)
                | Q(related_object_id='admin')
                | Q(related_object_id=session_id.replace('kunjungan_', '', 1))
            ).update(status='read', read_at=timezone.now())
            unread_notif_count = Notification.objects.filter(
                recipient_id=str(tamu_id), recipient_type='tamu', status='unread'
            ).count()

    room_meta = _build_chat_room_meta(session_id, is_admin, tamu_id, pegawai_id)
    room_meta['unread_notifications_count'] = unread_notif_count

    return JsonResponse({
        'success': True,
        'session_id': session_id,
        'room_meta': room_meta,
        'messages': messages_data,
        'pagination': {
            'has_next': page_obj.has_next(),
            'has_previous': page_obj.has_previous(),
            'current_page': page_obj.number,
            'total_pages': paginator.num_pages,
            'total_items': paginator.count
        }
    })


def api_delete_chat_message(request, message_id):

    """Hapus pesan chat oleh admin (Khusus Admin)"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Invalid method'}, status=405)

    is_admin, admin_id = check_is_admin(request)
    if not is_admin:
        return JsonResponse({'success': False, 'error': 'Akses khusus Administrator. Unauthorized.'}, status=403)

    try:
        msg = ChatMessage.objects.get(id=message_id)
        content_excerpt = msg.content[:50] + '...' if len(msg.content) > 50 else msg.content

        from .base import record_audit_log
        record_audit_log(
            user_id=str(admin_id), user_type='admin', action='delete',
            table_name='chat_message', record_id=str(msg.id),
            old_value=f"Menghapus chat: {content_excerpt}",
            ip_address=request.META.get('REMOTE_ADDR')
        )

        msg.delete()
        return JsonResponse({'success': True})
    except ChatMessage.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Pesan tidak ditemukan.'}, status=404)
    except Exception:
        logger.exception("Gagal menghapus pesan chat %s", message_id)
        return JsonResponse({'success': False, 'error': 'Gagal menghapus pesan.'}, status=500)


@admin_login_required
def api_summarize_chat_conversation(request):
    """
    Endpoint Ringkasan & Analisis Percakapan AI (Groq LLM) pada halaman Chat Admin.
    Mendukung metode POST (JSON payload {'session_id': '...'}) maupun GET (?session_id=...).
    """
    if request.method not in ('POST', 'GET'):
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    is_admin, _ = check_is_admin(request)
    if not is_admin:
        return JsonResponse({'success': False, 'error': 'Akses khusus Administrator.'}, status=403)

    session_id = ''
    if request.method == 'POST':
        try:
            body_data = json.loads(request.body or b'{}')
            if isinstance(body_data, dict):
                session_id = str(body_data.get('session_id') or '').strip()
        except (ValueError, TypeError, json.JSONDecodeError):
            session_id = ''
        if not session_id:
            session_id = str(request.POST.get('session_id') or '').strip()
    else:
        session_id = str(request.GET.get('session_id') or '').strip()

    if not session_id:
        return JsonResponse({'success': False, 'error': 'Parameter session_id wajib diisi.'}, status=400)

    try:
        from ..utils import summarize_chat_conversation_with_groq
        result = summarize_chat_conversation_with_groq(session_id)
        status_code = 200 if result.get('success') else 400
        return JsonResponse(result, status=status_code)
    except Exception:
        logger.exception("Gagal membuat ringkasan percakapan AI untuk sesi %s", session_id)
        return JsonResponse({'success': False, 'error': 'Gagal membuat ringkasan percakapan AI.'}, status=500)

