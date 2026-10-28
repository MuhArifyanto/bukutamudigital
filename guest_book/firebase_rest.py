"""
Klien Firebase Auth REST untuk login password di sisi server.

Aturan keamanan modul ini:
- Password TIDAK pernah dicatat/di-log. Pesan exception requests bisa memuat URL
  (termasuk API key), jadi yang dicatat hanya NAMA kelas exception.
- Semua kegagalan jaringan ditangani; fungsi tidak melempar exception ke pemanggil.
- Kode error Firebase mentah tidak pernah dikembalikan ke klien (hanya kategori internal).
"""
import logging
import re

import requests
from django.conf import settings
from django.views.decorators.debug import sensitive_variables
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

logger = logging.getLogger('guest_book.security')

SIGN_IN_URL = 'https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword'
FIREBASE_TIMEOUT_SECONDS = 10

# Kategori hasil (internal, tidak diteruskan ke klien)
OK = 'ok'
INVALID = 'invalid'          # kredensial salah / user tidak ada / rate limit Firebase / 4xx lain
UNAVAILABLE = 'unavailable'  # timeout, jaringan, 5xx, konfigurasi hilang

_REASON_RE = re.compile(r'^[A-Z_]{3,60}$')


class _TimeoutRequest(google_requests.Request):
    """Request google-auth dengan timeout default 10 detik (bawaan library 120 detik)."""

    def __call__(self, url, method='GET', body=None, headers=None,
                 timeout=FIREBASE_TIMEOUT_SECONDS, **kwargs):
        return super().__call__(url, method=method, body=body, headers=headers,
                                timeout=timeout, **kwargs)


@sensitive_variables('password', 'payload')
def sign_in_with_password(email, password):
    """
    Panggil Firebase signInWithPassword.
    Return (status, id_token_or_None) dengan status OK / INVALID / UNAVAILABLE.
    """
    api_key = getattr(settings, 'FIREBASE_API_KEY', '') or ''
    if not api_key:
        logger.error('FIREBASE_API_KEY belum dikonfigurasi; login password tidak dapat diproses.')
        return UNAVAILABLE, None

    payload = {'email': email, 'password': password, 'returnSecureToken': True}
    try:
        resp = requests.post(
            SIGN_IN_URL,
            params={'key': api_key},
            json=payload,
            timeout=FIREBASE_TIMEOUT_SECONDS,
        )
    except requests.exceptions.RequestException as exc:
        logger.warning('Firebase tidak dapat dihubungi (%s).', type(exc).__name__)
        return UNAVAILABLE, None
    except Exception as exc:  # pragma: no cover - pengaman terakhir
        logger.warning('Kesalahan tak terduga saat memanggil Firebase (%s).', type(exc).__name__)
        return UNAVAILABLE, None

    if resp.status_code >= 500:
        logger.warning('Firebase membalas status %s.', resp.status_code)
        return UNAVAILABLE, None

    if resp.status_code == 200:
        try:
            token = resp.json().get('idToken')
        except (ValueError, AttributeError):
            logger.warning('Balasan Firebase tidak dapat dibaca.')
            return UNAVAILABLE, None
        if not token:
            logger.warning('Balasan Firebase tidak memuat token.')
            return UNAVAILABLE, None
        return OK, token

    # 4xx: catat hanya kode alasan yang aman (huruf kapital/underscore) untuk diagnosis server.
    reason = 'OTHER'
    try:
        raw = (resp.json().get('error') or {}).get('message') or ''
        candidate = str(raw).split(' : ')[0].strip()
        if _REASON_RE.match(candidate):
            reason = candidate
    except (ValueError, AttributeError):
        pass
    logger.info('Firebase menolak login (status=%s, alasan=%s).', resp.status_code, reason)
    return INVALID, None


def verify_id_token(token):
    """
    Verifikasi token ID (tanda tangan, audience/project, issuer, kedaluwarsa).
    Return (status, claims): OK / INVALID (token tidak sah) / UNAVAILABLE (gagal ambil sertifikat).
    """
    project_id = getattr(settings, 'FIREBASE_PROJECT_ID', '') or ''
    try:
        claims = google_id_token.verify_firebase_token(
            token, _TimeoutRequest(), audience=project_id, clock_skew_in_seconds=10,
        )
    except ValueError:
        logger.warning('Token ID Firebase tidak lolos verifikasi.')
        return INVALID, None
    except Exception as exc:
        logger.warning('Verifikasi token Firebase gagal diproses (%s).', type(exc).__name__)
        return UNAVAILABLE, None
    if not claims:
        return INVALID, None
    return OK, claims
