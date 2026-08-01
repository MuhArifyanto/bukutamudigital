from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from functools import wraps
from ..models import Tamu, Instansi

def get_tamu_from_session(request):
    """Ambil objek Tamu dari session, atau None jika tidak login."""
    tamu_id = request.session.get('tamu_id')
    if not tamu_id:
        return None
    try:
        return Tamu.objects.get(pk=tamu_id, account_status='active')
    except Exception:
        return None

def tamu_login_required(view_func):
    """Decorator: redirect ke login jika tamu belum autentikasi."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        tamu = get_tamu_from_session(request)
        if not tamu:
            messages.error(request, "Silakan masuk terlebih dahulu.")
            return redirect('tamu:login')
        return view_func(request, *args, tamu=tamu, **kwargs)
    return wrapper

def admin_login_required(view_func):
    """Decorator: pastikan yang akses adalah admin (via Django Auth)."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_staff:
            return view_func(request, *args, **kwargs)
        
        # Check via session if using Tamu as admin
        tamu_id = request.session.get('tamu_id')
        if tamu_id:
            from ..models import Tamu
            tamu = Tamu.objects.filter(id=tamu_id, is_admin=True).first()
            if tamu:
                return view_func(request, *args, **kwargs)
        
        messages.error(request, "Akses khusus Administrator. Silakan login.")
        return redirect('tamu:admin_login')
    return wrapper


def get_admin_name(request):
    """Helper untuk mendapatkan nama admin yang sedang login."""
    if request.user.is_authenticated:
        return request.user.first_name or request.user.username
    if request.session.get('tamu_id'):
        tamu_admin = Tamu.objects.filter(pk=request.session.get('tamu_id'), nik='admin').first()
        if tamu_admin:
            return tamu_admin.name
    return "Administrator"

def get_admin_context(request):
    """Helper untuk mengambil context standar portal admin."""
    try:
        instansi = Instansi.objects.first()
    except:
        instansi = None
    
    if not instansi:
        instansi = {
            'nama': 'Diskominfosantik Kabupaten Bekasi',
            'status_operasional': 'Aktif',
            'jumlah_petugas': 8,
            'kapasitas_maksimal': 20
        }
        
    admin_user = None
    if request.user.is_authenticated:
        admin_user = Tamu.objects.filter(is_admin=True).first() or Tamu.objects.filter(nik='admin').first()
    elif request.session.get('tamu_id'):
        admin_user = Tamu.objects.filter(pk=request.session.get('tamu_id')).first()

    profile_pic_url = None
    if admin_user and admin_user.profile_picture:
        try:
            profile_pic_url = f"{admin_user.profile_picture.url}?v={admin_user.registration_date.timestamp()}"
        except:
            profile_pic_url = None

    return {
        'admin_name': get_admin_name(request),
        'admin_profile_picture': profile_pic_url,
        'instansi': instansi,
        'admin_user': admin_user,
        'admin_nip': admin_user.nip if admin_user and hasattr(admin_user, 'nip') and admin_user.nip else None,
    }

def record_audit_log(user_id, user_type, action, table_name, record_id, old_value=None, new_value=None, ip_address=None):
    """Helper untuk mencatat aktivitas ke AuditLog"""
    from ..models import AuditLog
    try:
        AuditLog.objects.create(
            user_id=user_id,
            user_type=user_type,
            action=action,
            table_name=table_name,
            record_id=record_id,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address
        )
    except Exception as e:
        print(f"Error recording audit log: {e}")

def base_context(tamu, active_page=''):
    """Context dasar untuk halaman tamu."""
    from ..models import Notification
    unread_count = Notification.objects.filter(
        recipient_id=str(tamu.pk),
        recipient_type='tamu',
        status='unread'
    ).count()
    
    recent_notifications = Notification.objects.filter(
        recipient_id=str(tamu.pk),
        recipient_type='tamu'
    ).order_by('-created_at')[:5]
    
    return {
        'tamu': tamu,
        'user_name': tamu.name,
        'user_email': tamu.email,
        'user_logged_in': True,
        'active_page': active_page,
        'unread_notifications_count': unread_count,
        'recent_notifications': recent_notifications,
    }
