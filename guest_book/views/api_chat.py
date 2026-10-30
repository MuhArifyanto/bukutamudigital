"""
API Views — Chat (send, upload, history, delete, search users)
"""
import json
import logging

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.core.paginator import Paginator

from .base import admin_login_required, check_is_admin
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

        return JsonResponse({'success': True, 'message': {
            'id': str(msg.id), 'content': msg.content,
            'created_at': msg.created_at.strftime('%H:%M')
        }})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


def api_upload_chat_file(request):

    """Upload file/gambar dalam chat ke Local Storage"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    is_logged_in = (
        (request.user.is_authenticated and request.user.is_staff)
        or bool(request.session.get('tamu_id'))
        or bool(request.session.get('pegawai_id'))
    )
    if not is_logged_in:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

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
    is_admin, _ = check_is_admin(request)
    tamu_id = str(request.session.get('tamu_id') or '')
    pegawai_id = str(request.session.get('pegawai_id') or '')

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

    from ..models import Tamu, Pegawai, Kunjungan
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
                'session_id': f"pegawai_admin_{p.id}",
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
            'session_id': str(t.id),
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
            'session_id': f"pegawai_admin_{p.id}",
            'type': 'pegawai'
        })

    return JsonResponse({'success': True, 'users': users_data})


def api_get_chat_messages(request):
    """Ambil history chat terbaru (Admin, Pegawai, atau Tamu yang berhak)"""
    session_id = request.GET.get('session_id')
    last_id = request.GET.get('last_id')
    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 50)

    if not session_id:
        return JsonResponse({'success': False, 'error': 'session_id required'}, status=400)

    # Validasi Hak Akses Sesi Chat
    is_admin, _ = check_is_admin(request)
    tamu_id = str(request.session.get('tamu_id', ''))
    pegawai_id = str(request.session.get('pegawai_id', ''))

    has_permission = False
    if is_admin:
        has_permission = True
    elif tamu_id and (session_id == tamu_id or session_id == f"tamu_{tamu_id}"):
        has_permission = True
    elif pegawai_id and (session_id == f"pegawai_admin_{pegawai_id}"):
        has_permission = True
    elif session_id.startswith('kunjungan_'):
        kunjungan_id = session_id.replace('kunjungan_', '')
        from ..models import Kunjungan
        from ..permissions import PermissionManager
        try:
            kunjungan = Kunjungan.objects.filter(id=kunjungan_id).first()
        except Exception:
            kunjungan = None
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

    messages_data = []
    for m in reversed(page_obj.object_list):
        messages_data.append({
            'id': str(m.id),
            'content': m.content,
            'sender_id': str(m.sender_id),
            'sender_type': m.sender_type,
            'message_type': m.message_type,
            'file_url': m.attachment.url if m.attachment else None,
            'created_at': timezone.localtime(m.created_at).strftime('%H:%M') if m.created_at else ''
        })
        if not m.is_read:
            if is_admin and m.sender_type != 'admin' and not session_id.startswith('kunjungan_'):
                m.is_read = True
                m.save(update_fields=['is_read'])
            elif pegawai_id and not is_admin and m.sender_type != 'pegawai':
                m.is_read = True
                m.save(update_fields=['is_read'])
            elif tamu_id and not is_admin and m.sender_type != 'tamu':
                m.is_read = True
                m.save(update_fields=['is_read'])

    return JsonResponse({
        'success': True,
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
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)
