"""
SecurityHeadersMiddleware — HTTP security headers untuk kepatuhan OWASP & UU PDP.

Menambahkan:
- Content-Security-Policy (CSP) kompatibel dengan CDN Bootstrap/Chart.js/Firebase/Cloudinary/WebSocket.
- Referrer-Policy: strict-origin-when-cross-origin
- Permissions-Policy (izin kamera hanya untuk origin sendiri demi pemindaian QR tiket).
"""
import secrets
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout as django_logout
from django.http import JsonResponse
from django.shortcuts import redirect


def build_csp_policy(upgrade_insecure: bool = False, script_nonce: str | None = None) -> str:
    """Bangun string header Content-Security-Policy aplikasi tanpa unsafe-inline pada script-src."""
    script_parts = ["'self'"]
    if script_nonce:
        script_parts.append(f"'nonce-{script_nonce}'")
    script_parts.append(
        "https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://unpkg.com "
        "https://www.gstatic.com https://apis.google.com https://accounts.google.com"
    )
    directives = [
        "default-src 'self'",
        f"script-src {' '.join(script_parts)}",
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com https://fonts.googleapis.com https://unpkg.com",
        "font-src 'self' data: https://fonts.gstatic.com https://cdnjs.cloudflare.com https://cdn.jsdelivr.net",
        "img-src 'self' data: blob: https://res.cloudinary.com https://*.cloudinary.com https://ui-avatars.com https://images.unsplash.com https://upload.wikimedia.org https://*.googleusercontent.com https://www.gstatic.com",
        "media-src 'self' blob: https://assets.mixkit.co https://res.cloudinary.com https://*.cloudinary.com",
        "connect-src 'self' ws: wss: https://identitytoolkit.googleapis.com https://securetoken.googleapis.com https://www.googleapis.com https://*.firebaseio.com https://firebaseinstallations.googleapis.com https://api.cloudinary.com https://cdn.jsdelivr.net",
        "frame-src 'self' https://*.firebaseapp.com https://accounts.google.com",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
    if upgrade_insecure:
        directives.append("upgrade-insecure-requests")
    return "; ".join(directives)


class SecurityHeadersMiddleware:
    """Menambahkan header keamanan CSP (berbasis nonce), Referrer-Policy, dan Permissions-Policy."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        nonce = secrets.token_urlsafe(16)
        request.csp_nonce = nonce
        response = self.get_response(request)

        # Aktifkan upgrade-insecure-requests hanya di HTTPS non-debug agar dev HTTP tidak rusak
        upgrade = (not settings.DEBUG) and request.is_secure()
        response.headers.setdefault(
            'Content-Security-Policy',
            build_csp_policy(upgrade_insecure=upgrade, script_nonce=nonce),
        )
        response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        response.headers.setdefault(
            'Permissions-Policy',
            'camera=(self), microphone=(), geolocation=(), payment=(), usb=()',
        )
        return response


class Admin2FAEnforcementMiddleware:
    """
    Mencegah bypass 2FA Administrator melalui panel bawaan Django (`/admin/`).
    Setiap sesi staff dengan TOTP 2FA aktif wajib sudah terverifikasi 2FA pada sesi
    sebelum dapat mengakses endpoint `/admin/`.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path or ''
        if path.startswith('/admin/') and not path.startswith('/admin/logout'):
            user = getattr(request, 'user', None)
            if user and getattr(user, 'is_authenticated', False) and getattr(user, 'is_staff', False):
                from .views.base import is_admin_2fa_verified

                if not is_admin_2fa_verified(request, user):
                    django_logout(request)
                    messages.warning(
                        request,
                        "Verifikasi 2FA wajib diselesaikan melalui Portal Admin sebelum mengakses Django Admin.",
                    )
                    return redirect('tamu:admin_login')
        return self.get_response(request)


ADMIN_LAST_ACTIVITY_SESSION_KEY = '_admin_last_activity_ts'
_ADMIN_IDLE_PASSIVE_PATHS = (
    '/api/admin/unread-count/',
    '/api/admin/recent-notifications/',
    '/healthz/',
)


class AdminIdleTimeoutMiddleware:
    """
    Menegakkan idle timeout khusus sesi Administrator (default 30 menit).
    - Mengeluarkan admin otomatis bila melebihi settings.ADMIN_SESSION_IDLE_TIMEOUT.
    - Endpoint polling pasif (unread-count/recent-notifications) tidak memperpanjang idle timer.
    - Pembaruan timestamp di-throttle 60 detik agar tidak memicu DB session write di setiap request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        idle_timeout = int(getattr(settings, 'ADMIN_SESSION_IDLE_TIMEOUT', 1800) or 0)
        if idle_timeout <= 0:
            return self.get_response(request)

        user = getattr(request, 'user', None)
        is_staff_session = bool(
            user and getattr(user, 'is_authenticated', False) and getattr(user, 'is_staff', False)
        )
        path = request.path or ''
        is_admin_area = (
            path.startswith('/admin-portal/')
            or path.startswith('/admin/')
            or path.startswith('/api/admin/')
        )

        # Hanya berlaku untuk sesi staff Django atau sesi legacy admin di area admin
        if not is_staff_session and not (is_admin_area and request.session.get(ADMIN_LAST_ACTIVITY_SESSION_KEY)):
            return self.get_response(request)

        # Jangan blokir halaman login/2FA/logout sendiri
        if (
            path.startswith('/admin-portal/login')
            or path.startswith('/admin/login')
            or path.startswith('/admin/logout')
            or path == '/keluar/'
        ):
            return self.get_response(request)

        now_ts = int(time.time())
        last_activity = request.session.get(ADMIN_LAST_ACTIVITY_SESSION_KEY)
        if last_activity is not None:
            try:
                elapsed = now_ts - float(last_activity)
            except (TypeError, ValueError):
                elapsed = 0
            if elapsed > idle_timeout:
                django_logout(request)
                request.session.flush()
                is_api_req = (
                    '/api/' in path
                    or 'application/json' in (request.headers.get('Accept') or '').lower()
                    or request.headers.get('X-Requested-With') == 'XMLHttpRequest'
                )
                if is_api_req:
                    return JsonResponse(
                        {
                            'success': False,
                            'error': 'Sesi administrator telah kedaluwarsa karena tidak aktif. Silakan login kembali.',
                        },
                        status=401,
                    )
                messages.warning(
                    request,
                    'Sesi administrator Anda telah berakhir karena tidak ada aktivitas. Silakan masuk kembali.',
                )
                return redirect('tamu:admin_login')

            # Perbarui timestamp maksimal sekali setiap 60 detik dan abaikan polling pasif
            if elapsed >= 60 and not any(path.startswith(p) for p in _ADMIN_IDLE_PASSIVE_PATHS):
                request.session[ADMIN_LAST_ACTIVITY_SESSION_KEY] = now_ts
        elif '/api/' not in path and not any(path.startswith(p) for p in _ADMIN_IDLE_PASSIVE_PATHS):
            request.session[ADMIN_LAST_ACTIVITY_SESSION_KEY] = now_ts

        return self.get_response(request)
