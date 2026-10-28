"""
API Views — Notifikasi & Status Kunjungan
"""
import json
from django.http import JsonResponse
from django.utils import timezone
from django.core.paginator import Paginator

from .base import admin_login_required, check_is_admin
from ..models import Notification, Kunjungan, Pegawai, Tamu


def get_authenticated_recipient(request):
    """
    Menentukan identitas penerima valid secara hierarkis dari sesi server:
    1. Admin: check_is_admin(request) -> ('admin', 'admin')
    2. Pegawai: session pegawai_id valid & aktif di DB -> ('pegawai', str(pegawai.id))
    3. Tamu: session tamu_id valid & aktif di DB (dan bukan admin) -> ('tamu', str(tamu.id))
    4. Sesi tidak valid / anonim -> (None, None)
    """
    is_admin, admin_id = check_is_admin(request)
    if is_admin:
        return 'admin', 'admin'

    pegawai_id = request.session.get('pegawai_id')
    if pegawai_id:
        try:
            pegawai = Pegawai.objects.filter(pk=pegawai_id, account_status='active').first()
            if pegawai:
                return 'pegawai', str(pegawai.id)
        except Exception:
            pass

    tamu_id = request.session.get('tamu_id')
    if tamu_id:
        try:
            tamu = Tamu.objects.filter(pk=tamu_id, account_status='active').first()
            if tamu:
                return 'tamu', str(tamu.id)
        except Exception:
            pass

    return None, None


def api_mark_notification_read(request):
    """Tandai 1 notifikasi sebagai terbaca (Admin, Pegawai, atau Tamu)"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    recipient_type, recipient_id = get_authenticated_recipient(request)
    if not recipient_type:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    try:
        notif_id = None
        if request.body:
            try:
                data = json.loads(request.body)
                if isinstance(data, dict):
                    notif_id = data.get('notification_id')
            except Exception:
                pass
        if not notif_id:
            notif_id = request.POST.get('notification_id')

        if not notif_id:
            return JsonResponse({'success': False, 'error': 'notification_id is required'}, status=400)

        notif = Notification.objects.filter(id=notif_id).first()
        if not notif:
            return JsonResponse({'success': False, 'error': 'Notification not found'}, status=404)

        # Kontrol Akses (Anti-IDOR)
        if recipient_type == 'admin':
            if notif.recipient_type != 'admin':
                return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)
        else:
            if notif.recipient_type != recipient_type or str(notif.recipient_id) != str(recipient_id):
                return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

        notif.status = 'read'
        notif.read_at = timezone.now()
        notif.save(update_fields=['status', 'read_at'])
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


def api_mark_all_notifications_read(request):
    """Tandai SEMUA notifikasi belum dibaca milik pengguna yang sedang login"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    recipient_type, recipient_id = get_authenticated_recipient(request)
    if not recipient_type:
        return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=401)

    try:
        updated = Notification.objects.filter(
            recipient_id=recipient_id,
            recipient_type=recipient_type,
            status='unread'
        ).update(status='read', read_at=timezone.now())
        return JsonResponse({'success': True, 'updated': updated})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=400)


def api_update_kunjungan_status(request):
    """API untuk update status kunjungan oleh Admin atau Pegawai (via WorkflowEngine)"""
    is_admin, admin_id = check_is_admin(request)
    pegawai_id = request.session.get('pegawai_id')

    if not (is_admin or pegawai_id):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            kunjungan_id = data.get('kunjungan_id')
            new_status = data.get('status')
            rejection_reason = data.get('rejection_reason', '').strip() or None
            notes = data.get('notes', '').strip() or None

            if not kunjungan_id or not new_status:
                return JsonResponse({'error': 'kunjungan_id dan status wajib diisi'}, status=400)

            kunjungan = Kunjungan.objects.select_related('tamu', 'pegawai').get(id=kunjungan_id)
            user_id = str(admin_id) if is_admin else str(pegawai_id)
            user_type = 'admin' if is_admin else 'pegawai'

            from ..workflow_engine import WorkflowEngine
            engine = WorkflowEngine(kunjungan)
            engine.transition(new_status=new_status, user_id=user_id, user_type=user_type, notes=notes, rejection_reason=rejection_reason)
            return JsonResponse({'success': True})

        except Kunjungan.DoesNotExist:
            return JsonResponse({'error': 'Kunjungan tidak ditemukan'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)

    return JsonResponse({'error': 'Invalid method'}, status=405)


def api_get_unread_count(request):
    """Jumlah notifikasi belum dibaca (Admin, Tamu & Pegawai)"""
    recipient_type, recipient_id = get_authenticated_recipient(request)
    if not recipient_type:
        return JsonResponse({'unread_count': 0})

    count = Notification.objects.filter(
        recipient_id=recipient_id,
        recipient_type=recipient_type,
        status='unread'
    ).count()
    return JsonResponse({'unread_count': count})


def api_get_recent_notifications(request):
    """Notifikasi terbaru untuk dropdown (Admin, Tamu & Pegawai)"""
    recipient_type, recipient_id = get_authenticated_recipient(request)
    if not recipient_type:
        return JsonResponse({
            'notifications': [],
            'pagination': {
                'has_next': False,
                'has_previous': False,
                'current_page': 1,
                'total_pages': 1,
                'total_items': 0
            }
        })

    page = request.GET.get('page', 1)
    page_size = request.GET.get('page_size', 5)

    qs = Notification.objects.filter(
        recipient_id=recipient_id,
        recipient_type=recipient_type
    ).order_by('-created_at')
    paginator = Paginator(qs, page_size)
    try:
        notifications = paginator.page(page)
    except Exception:
        notifications = paginator.page(1)

    data = [{
        'title': n.title, 'message': n.message,
        'created_at': timezone.localtime(n.created_at).strftime('%H:%M'),
        'status': n.status, 'notification_type': n.notification_type,
        'related_object_id': n.related_object_id
    } for n in notifications]

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
