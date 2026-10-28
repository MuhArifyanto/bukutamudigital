from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.core.cache import cache
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
    """Decorator: redirect ke login jika tamu belum autentikasi.

    Menyimpan objek tamu di request._tamu agar context processor
    bisa menggunakannya tanpa query ulang ke database.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        tamu = get_tamu_from_session(request)
        if not tamu:
            messages.error(request, "Silakan masuk terlebih dahulu.")
            return redirect('tamu:login')
        # Titipkan di request agar context processor bisa pakai tanpa query ulang
        request._tamu = tamu
        return view_func(request, *args, tamu=tamu, **kwargs)
    return wrapper

def check_is_admin(request):
    """
    Helper untuk memverifikasi apakah request berasal dari Administrator
    (baik Django staff auth maupun Tamu dengan flag is_admin=True).
    Returns: (is_admin: bool, admin_id: str | None)
    """
    if request.user.is_authenticated and request.user.is_staff:
        return True, str(request.user.id)
    
    tamu_id = request.session.get('tamu_id')
    if tamu_id:
        tamu = Tamu.objects.filter(id=tamu_id, is_admin=True, account_status='active').first()
        if tamu:
            return True, str(tamu.id)
    
    return False, None

def admin_login_required(view_func):
    """Decorator: pastikan yang akses adalah admin (via Django Auth atau Tamu is_admin)."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        is_admin, _ = check_is_admin(request)
        if is_admin:
            return view_func(request, *args, **kwargs)
        
        messages.error(request, "Akses khusus Administrator. Silakan login.")
        return redirect('tamu:admin_login')
    return wrapper


# ── Cache helpers ────────────────────────────────────────────────────────────
# TTL pendek (5 menit) agar perubahan profil/instansi cepat terlihat
_ADMIN_USER_CACHE_TTL   = 60 * 5   # 5 menit
_INSTANSI_CACHE_TTL     = 60 * 10  # 10 menit


def _get_cached_instansi():
    """Ambil Instansi dari cache; fallback ke DB jika miss."""
    instansi = cache.get('instansi_utama')
    if instansi is None:
        try:
            instansi = Instansi.objects.first()
        except Exception:
            instansi = None
        if instansi:
            cache.set('instansi_utama', instansi, _INSTANSI_CACHE_TTL)
    return instansi


def _get_cached_admin_user(tamu_id=None):
    """
    Ambil objek admin Tamu dari cache.

    Dua jalur:
    - tamu_id tersedia (Tamu.is_admin via session) → cache per tamu_id
    - tamu_id None (Django Auth staff)              → cache admin pertama
    """
    if tamu_id:
        cache_key = f'admin_user_{tamu_id}'
        admin_user = cache.get(cache_key)
        if admin_user is None:
            admin_user = Tamu.objects.filter(pk=tamu_id).first()
            if admin_user:
                cache.set(cache_key, admin_user, _ADMIN_USER_CACHE_TTL)
    else:
        cache_key = 'admin_user_primary'
        admin_user = cache.get(cache_key)
        if admin_user is None:
            # 1 query dengan OR — tidak perlu 2 query terpisah
            admin_user = (
                Tamu.objects.filter(is_admin=True).first()
                or Tamu.objects.filter(nik='admin').first()
            )
            if admin_user:
                cache.set(cache_key, admin_user, _ADMIN_USER_CACHE_TTL)
    return admin_user


def invalidate_admin_cache(tamu_id=None):
    """
    Hapus cache admin saat profil atau data instansi berubah.
    Panggil ini di view yang menyimpan perubahan profil admin atau instansi.
    """
    cache.delete('instansi_utama')
    cache.delete('admin_user_primary')
    if tamu_id:
        cache.delete(f'admin_user_{tamu_id}')


# ─────────────────────────────────────────────────────────────────────────────


def get_admin_name(request):
    """Helper untuk mendapatkan nama admin yang sedang login.
    Menggunakan _get_cached_admin_user agar tidak query ulang.
    """
    if request.user.is_authenticated:
        return request.user.first_name or request.user.username
    tamu_id = request.session.get('tamu_id')
    if tamu_id:
        admin_user = _get_cached_admin_user(tamu_id)
        if admin_user:
            return admin_user.name
    return "Administrator"


def get_admin_context(request):
    """Helper untuk mengambil context standar portal admin.

    Sebelumnya: 3–4 query DB setiap halaman (Instansi + Tamu is_admin + Tamu nik='admin' + get_admin_name).
    Sesudah   : semua di-cache (Redis/LocMemCache), DB hanya diakses saat cache miss (TTL 5–10 menit).
    """
    instansi = _get_cached_instansi()

    if not instansi:
        instansi = {
            'nama': 'Diskominfosantik Kabupaten Bekasi',
            'status_operasional': 'Aktif',
            'jumlah_petugas': 8,
            'kapasitas_maksimal': 20,
        }

    tamu_id    = request.session.get('tamu_id') if not request.user.is_authenticated else None
    admin_user = _get_cached_admin_user(tamu_id)

    profile_pic_url = None
    if admin_user and admin_user.profile_picture:
        try:
            profile_pic_url = f"{admin_user.profile_picture.url}?v={admin_user.registration_date.timestamp()}"
        except Exception:
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
    """Context dasar untuk halaman tamu.

    Notifikasi diambil sekali (1 query) lalu dihitung di Python,
    menghindari query ganda dengan context_processors.py.
    Hasilnya disimpan di request._tamu_notifications agar context
    processor bisa re-use tanpa query kedua.
    """
    from ..models import Notification

    # 1 query: ambil semua notifikasi tamu (5 terbaru cukup untuk dropdown)
    # sekaligus bisa hitung unread dari slice ini
    recent_notifications = list(
        Notification.objects
        .filter(recipient_id=str(tamu.pk), recipient_type='tamu')
        .order_by('-created_at')[:5]
    )

    # Hitung unread dari hasil query di atas (tanpa query tambahan)
    unread_count = sum(1 for n in recent_notifications if n.status == 'unread')

    # Jika unread lebih banyak dari 5 (ada di luar slice), fallback ke count query.
    # Kasus ini jarang terjadi; satu query ekstra hanya saat semua 5 item unread.
    if unread_count >= 5:
        unread_count = Notification.objects.filter(
            recipient_id=str(tamu.pk),
            recipient_type='tamu',
            status='unread'
        ).count()

    return {
        'tamu': tamu,
        'user_name': tamu.name,
        'user_email': tamu.email,
        'user_logged_in': True,
        'active_page': active_page,
        'unread_notifications_count': unread_count,
        'recent_notifications': recent_notifications,
    }
