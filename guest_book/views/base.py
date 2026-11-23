from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.core.cache import cache
from functools import wraps
from ..models import Tamu, Instansi

def get_tamu_from_session(request):
    """Ambil objek Tamu aktif dari session, atau bersihkan session bila nonaktif/tidak valid."""
    tamu_id = request.session.get('tamu_id')
    if not tamu_id:
        return None
    try:
        return Tamu.objects.get(pk=tamu_id, account_status='active')
    except Exception:
        request.session.pop('tamu_id', None)
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

ADMIN_2FA_VERIFIED_SESSION_KEY = '_admin_2fa_verified_user_id'


def _admin_email_for_user(auth_user):
    """Kembalikan email deterministik milik staff user tanpa fallback lintas akun."""
    email = (getattr(auth_user, 'email', None) or '').strip().lower()
    if email:
        return email
    username = (getattr(auth_user, 'username', None) or '').strip().lower()
    return f"{username}@staff.bukudigital.local" if username else ''


def is_admin_2fa_verified(request, auth_user=None) -> bool:
    """Pastikan administrator yang mengaktifkan 2FA telah lolos tantangan TOTP pada sesi ini."""
    user = auth_user if auth_user is not None else getattr(request, 'user', None)
    if not (user and getattr(user, 'is_authenticated', False) and getattr(user, 'is_staff', False) and getattr(user, 'is_active', True)):
        return False

    admin_record = resolve_admin_record(user)
    if admin_record and admin_record.two_fa_enabled:
        from ..security_utils import decrypt_secret

        if admin_record.two_fa_secret and decrypt_secret(admin_record.two_fa_secret):
            return request.session.get(ADMIN_2FA_VERIFIED_SESSION_KEY) == str(user.pk)
        return False
    return True


def check_is_admin(request):
    """
    Helper untuk memverifikasi apakah request berasal dari Administrator
    (baik Django staff auth dengan verifikasi 2FA maupun Tamu dengan flag is_admin=True).
    Returns: (is_admin: bool, admin_id: str | None)
    """
    if request.user.is_authenticated and request.user.is_staff and request.user.is_active:
        if not is_admin_2fa_verified(request, request.user):
            return False, None
        return True, str(request.user.id)
    
    tamu_id = request.session.get('tamu_id')
    if tamu_id:
        tamu = Tamu.objects.filter(id=tamu_id, is_admin=True, account_status='active').first()
        if tamu:
            # Jika email tamu berkorespondensi dengan Admin ber-2FA aktif, tolak akses tanpa sesi staff + 2FA
            if tamu.email:
                from ..models import Admin
                if Admin.objects.filter(email__iexact=tamu.email, account_status='active', two_fa_enabled=True).exists():
                    return False, None
            return True, str(tamu.id)
    
    return False, None


def check_is_super_admin(request):
    """
    Verifikasi apakah admin memiliki hak Super Admin (is_superuser atau Tamu admin_role='super_admin').
    Operator biasa (`is_staff=True, is_superuser=False, admin_role='operator'`) ditolak.
    Returns: (is_super: bool, admin_id: str | None)
    """
    is_admin, admin_id = check_is_admin(request)
    if not is_admin:
        return False, None

    user = getattr(request, 'user', None)
    if user and user.is_authenticated and user.is_staff and user.is_active:
        if getattr(user, 'is_superuser', False):
            return True, admin_id
        if getattr(user, 'email', None):
            tamu_profile = Tamu.objects.filter(
                email__iexact=user.email,
                is_admin=True,
                account_status='active',
            ).first()
            if tamu_profile and tamu_profile.admin_role == 'super_admin':
                return True, admin_id
        return False, admin_id

    tamu_id = request.session.get('tamu_id')
    if tamu_id:
        tamu_profile = Tamu.objects.filter(
            id=tamu_id,
            is_admin=True,
            account_status='active',
            admin_role='super_admin',
        ).first()
        if tamu_profile:
            return True, str(tamu_profile.id)

    return False, admin_id


def super_admin_required(view_func):
    """Decorator: batasi akses ke Super Admin (mengembalikan 403/redirect untuk Operator)."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        is_admin, _ = check_is_admin(request)
        if not is_admin:
            messages.error(request, "Akses khusus Administrator. Silakan login.")
            return redirect('tamu:admin_login')
        is_super, _ = check_is_super_admin(request)
        if not is_super:
            messages.error(request, "Tindakan ini memerlukan hak akses Super Admin.")
            return redirect('tamu:admin_dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper

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


import logging

logger = logging.getLogger(__name__)


def safe_cache_get(key, default=None):
    """Ambil data dari cache secara aman tanpa pernah melempar exception."""
    try:
        return cache.get(key, default)
    except Exception as e:
        logger.warning(f"safe_cache_get error for {key}: {e}")
        return default


def safe_cache_set(key, value, timeout=None):
    """Simpan data ke cache secara aman."""
    try:
        cache.set(key, value, timeout)
    except Exception as e:
        logger.warning(f"safe_cache_set error for {key}: {e}")


def safe_cache_delete(key):
    """Hapus kunci dari cache secara aman."""
    try:
        cache.delete(key)
    except Exception as e:
        logger.warning(f"safe_cache_delete error for {key}: {e}")


def _get_cached_instansi():
    """Ambil Instansi dari cache; fallback ke DB jika miss."""
    instansi = safe_cache_get('instansi_utama')
    if instansi is None:
        try:
            instansi = Instansi.objects.first()
        except Exception:
            instansi = None
        if instansi:
            safe_cache_set('instansi_utama', instansi, _INSTANSI_CACHE_TTL)
    return instansi


def resolve_admin_tamu_profile(request, create_if_missing=False):
    """
    Resolusi profil Tamu(is_admin=True) khusus milik administrator yang sedang login.
    TIDAK pernah melakukan fallback ke record admin pertama milik akun lain.
    """
    import uuid as _uuid

    user = getattr(request, 'user', None)
    if (
        user
        and getattr(user, 'is_authenticated', False)
        and getattr(user, 'is_staff', False)
        and getattr(user, 'is_active', False)
    ):
        email = _admin_email_for_user(user)
        if not email:
            return None
        profile = Tamu.objects.filter(
            email__iexact=email,
            is_admin=True,
            account_status='active',
        ).first()
        if profile or not create_if_missing:
            return profile
        if Tamu.objects.filter(email__iexact=email).exists():
            return None
        full_name = (getattr(user, 'get_full_name', lambda: '')() or user.username or 'Administrator')[:255]
        return Tamu.objects.create(
            name=full_name,
            email=email,
            phone='-',
            password=None,
            is_admin=True,
            admin_role='super_admin' if getattr(user, 'is_superuser', False) else 'operator',
            account_status='active',
            registration_type='manual',
        )

    tamu_id = request.session.get('tamu_id')
    if tamu_id:
        try:
            _uuid.UUID(str(tamu_id))
            return Tamu.objects.filter(
                pk=tamu_id,
                is_admin=True,
                account_status='active',
            ).first()
        except (ValueError, TypeError):
            return None
    return None


def _get_cached_admin_user(tamu_id=None, auth_user=None):
    """
    Ambil objek profil admin Tamu dari cache secara terisolasi per akun admin.
    """
    if auth_user is not None and getattr(auth_user, 'is_authenticated', False):
        cache_key = f'admin_user_staff_{auth_user.pk}'
        admin_user = safe_cache_get(cache_key)
        if admin_user is None:
            try:
                email = _admin_email_for_user(auth_user)
                if email:
                    admin_user = Tamu.objects.filter(
                        email__iexact=email,
                        is_admin=True,
                        account_status='active',
                    ).first()
                if admin_user:
                    safe_cache_set(cache_key, admin_user, _ADMIN_USER_CACHE_TTL)
            except Exception as e:
                logger.warning(f"Error fetching staff admin profile: {e}")
                admin_user = None
        return admin_user

    cache_key = f'admin_user_{tamu_id}' if tamu_id else 'admin_user_primary'
    admin_user = safe_cache_get(cache_key)

    if admin_user is None:
        try:
            if tamu_id:
                admin_user = Tamu.objects.filter(pk=tamu_id, is_admin=True, account_status='active').first()
            else:
                admin_user = (
                    Tamu.objects.filter(is_admin=True, account_status='active').first()
                    or Tamu.objects.filter(Tamu.nik_lookup_q('admin'), account_status='active').first()
                )
            if admin_user:
                safe_cache_set(cache_key, admin_user, _ADMIN_USER_CACHE_TTL)
        except Exception as e:
            logger.warning(f"Error fetching admin user: {e}")
            admin_user = None

    return admin_user


def invalidate_admin_cache(tamu_id=None, staff_user_id=None):
    """
    Hapus cache admin saat profil atau data instansi berubah.
    Panggil ini di view yang menyimpan perubahan profil admin atau instansi.
    """
    safe_cache_delete('instansi_utama')
    safe_cache_delete('admin_user_primary')
    if tamu_id:
        safe_cache_delete(f'admin_user_{tamu_id}')
    if staff_user_id:
        safe_cache_delete(f'admin_user_staff_{staff_user_id}')


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

    if getattr(request, 'user', None) and request.user.is_authenticated and request.user.is_staff:
        admin_user = _get_cached_admin_user(auth_user=request.user)
    else:
        tamu_id = request.session.get('tamu_id')
        admin_user = _get_cached_admin_user(tamu_id=tamu_id)

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
        logger.error("Error recording audit log: %s", e, exc_info=True)

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


def clamp_page_size(raw_value, default=50, min_size=1, max_size=100):
    """Konversi dan batasi parameter page_size agar aman dari nilai ekstrem atau non-numerik."""
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        return default
    return max(min_size, min(parsed, max_size))


def resolve_admin_record(auth_user=None, create_if_missing=False):
    """Temukan record Admin aktif yang berkorespondensi langsung dengan staff auth_user."""
    from ..models import Admin

    if not (
        auth_user
        and getattr(auth_user, 'is_authenticated', False)
        and getattr(auth_user, 'is_staff', False)
        and getattr(auth_user, 'is_active', True)
    ):
        return None

    target_email = _admin_email_for_user(auth_user)
    if not target_email:
        return None

    admin_record = Admin.objects.filter(email__iexact=target_email, account_status='active').first()

    if admin_record is None and create_if_missing:
        display_name = (
            (auth_user.get_full_name() if hasattr(auth_user, 'get_full_name') else '')
            or getattr(auth_user, 'username', None)
            or 'Administrator'
        )
        admin_record = Admin.objects.create(
            name=display_name,
            email=target_email,
            phone='-',
            password=getattr(auth_user, 'password', None) or '!',
            account_status='active',
        )
    return admin_record


def healthz_view(request):
    """Endpoint healthcheck ringan untuk monitoring uptime & readiness (DB + Cache)."""
    from django.db import connection
    from django.http import JsonResponse

    checks = {'database': 'ok', 'cache': 'ok'}
    healthy = True

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        checks['database'] = 'error'
        healthy = False

    probe_key = '_healthz_probe'
    try:
        cache.set(probe_key, '1', 10)
        if cache.get(probe_key) != '1':
            checks['cache'] = 'error'
            healthy = False
    except Exception:
        checks['cache'] = 'error'
        healthy = False

    return JsonResponse(
        {
            'status': 'ok' if healthy else 'degraded',
            'checks': checks,
        },
        status=200 if healthy else 503,
    )
