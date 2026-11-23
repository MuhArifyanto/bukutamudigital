"""
Utilitas keamanan bersama (tanpa efek samping, aman dipakai di view mana pun).

- hash_identifier / hash_nik : kunci cache & blind-index HMAC-SHA256.
- encrypt_nik / decrypt_nik  : enkripsi simetris Fernet/MultiFernet untuk NIK & secret 2FA.
- generate_totp_secret / verify_totp_code : otentikasi 2FA TOTP (RFC 6238, stdlib-only).
- mask_*                     : versi tersamar NIK/email untuk log.
- classify_identifier        : menentukan apakah input login berupa email atau NIK.
"""
import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import struct
import time
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from django.conf import settings
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone

logger = logging.getLogger(__name__)

_NIK_RE = re.compile(r'^\d{16}$')


def hash_identifier(value):
    """HMAC-SHA256 dari identifier (dinormalisasi). Dipakai sebagai bagian kunci cache."""
    normalized = (value or '').strip().lower()
    return hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        normalized.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def mask_email(email):
    email = (email or '').strip()
    local, sep, domain = email.partition('@')
    if not sep:
        return mask_generic(email)
    return f"{local[:1]}***@{domain}"


def mask_nik(nik):
    nik = (nik or '').strip()
    if len(nik) <= 6:
        return '*' * len(nik)
    return f"{nik[:4]}{'*' * (len(nik) - 6)}{nik[-2:]}"


def mask_generic(value):
    value = (value or '').strip()
    return f"{value[:2]}***" if value else '***'


def mask_identifier(value):
    """Samarkan identifier apa pun (email / NIK / lainnya) untuk keperluan log."""
    value = (value or '').strip()
    if '@' in value:
        return mask_email(value)
    if value.isdigit():
        return mask_nik(value)
    return mask_generic(value)


def classify_identifier(raw):
    """
    Mengembalikan (jenis, nilai_normal) dengan jenis 'email' | 'nik' | None.
    Nama lengkap sengaja TIDAK diterima (tidak unik).
    """
    value = (raw or '').strip() if isinstance(raw, str) else ''
    if not value or len(value) > 254:
        return None, ''
    if '@' in value:
        try:
            validate_email(value)
        except ValidationError:
            return None, ''
        return 'email', value.lower()
    if _NIK_RE.match(value):
        return 'nik', value
    return None, ''


# ── Enkripsi Simetris (Fernet / MultiFernet) & Blind-Index NIK ────────────────

def _coerce_fernet_key(raw_key: str) -> bytes:
    """Pastikan string kunci valid sebagai Fernet key 32-byte URL-safe base64."""
    candidate = raw_key.strip().encode('utf-8')
    try:
        Fernet(candidate)
        return candidate
    except (ValueError, TypeError):
        digest = hashlib.sha256(candidate).digest()
        return base64.urlsafe_b64encode(digest)


def _get_cipher() -> MultiFernet:
    """
    Bangun objek MultiFernet dari settings.NIK_ENCRYPTION_KEY (koma-separated
    untuk mendukung rotasi kunci) atau fallback turunan SECRET_KEY.
    """
    configured = (
        getattr(settings, 'NIK_ENCRYPTION_KEY', None)
        or os.getenv('NIK_ENCRYPTION_KEY', '')
        or ''
    ).strip()
    if configured:
        keys = [
            Fernet(_coerce_fernet_key(part))
            for part in configured.split(',')
            if part.strip()
        ]
        if keys:
            return MultiFernet(keys)

    derived = base64.urlsafe_b64encode(
        hashlib.sha256(f"nik-enc:{settings.SECRET_KEY}".encode('utf-8')).digest()
    )
    return MultiFernet([Fernet(derived)])


def is_encrypted_token(value) -> bool:
    """Deteksi cepat apakah nilai sudah berupa token Fernet (diawali gAAAAA)."""
    return isinstance(value, str) and value.startswith('gAAAAA') and len(value) >= 60


def hash_nik(raw_nik):
    """
    Bangun blind-index HMAC-SHA256 untuk lookup NIK terenkripsi di database.
    Mengembalikan None untuk input None atau string kosong.
    """
    if raw_nik is None:
        return None
    normalized = str(raw_nik).strip()
    if not normalized:
        return None
    hmac_key = (
        getattr(settings, 'NIK_HMAC_KEY', None)
        or os.getenv('NIK_HMAC_KEY', '')
        or settings.SECRET_KEY
    )
    return hmac.new(
        str(hmac_key).encode('utf-8'),
        f"tamu-nik:{normalized}".encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def encrypt_nik(raw_nik):
    """Enkripsi string NIK menggunakan MultiFernet; idempoten untuk token valid."""
    if raw_nik is None:
        return None
    val = str(raw_nik).strip()
    if not val:
        return ''
    cipher = _get_cipher()
    if is_encrypted_token(val):
        try:
            cipher.decrypt(val.encode('ascii'))
            return val
        except (InvalidToken, UnicodeEncodeError):
            pass
    return cipher.encrypt(val.encode('utf-8')).decode('ascii')


def decrypt_nik(stored_value, raise_on_error: bool = False):
    """
    Dekripsi nilai NIK terenkripsi. Baris plaintext legacy (belum berformat token
    Fernet) dikembalikan apa adanya agar aman sebelum/selama migrasi.
    """
    if stored_value is None:
        return None
    val = str(stored_value)
    if not val:
        return ''
    if not is_encrypted_token(val):
        return val
    try:
        return _get_cipher().decrypt(val.encode('ascii')).decode('utf-8')
    except (InvalidToken, UnicodeEncodeError, ValueError) as exc:
        if raise_on_error:
            raise ValueError('Dekripsi NIK gagal: kunci tidak cocok atau token rusak.') from exc
        logger.error("Gagal mendekripsi field NIK terenkripsi: %s", exc.__class__.__name__)
        return ''


def encrypt_secret(raw_secret):
    """Enkripsi secret sensitif (mis. two_fa_secret) dengan MultiFernet."""
    return encrypt_nik(raw_secret)


def decrypt_secret(stored_secret, raise_on_error: bool = False):
    """Dekripsi secret sensitif; kompatibel dengan nilai Base32 plaintext legacy."""
    return decrypt_nik(stored_secret, raise_on_error=raise_on_error)


# ── TOTP 2FA (RFC 6238, tanpa dependensi eksternal) ──────────────────────────

def generate_totp_secret(num_bytes: int = 20) -> str:
    """Buat secret TOTP acak berformat Base32 (160-bit sesuai RFC 4226/6238)."""
    return base64.b32encode(secrets.token_bytes(num_bytes)).decode('ascii').rstrip('=')


def _decode_base32_secret(secret: str) -> bytes:
    clean = re.sub(r'[\s\-]+', '', (secret or '').upper())
    if not clean:
        raise ValueError("Secret TOTP kosong.")
    padding = '=' * (-len(clean) % 8)
    return base64.b32decode(clean + padding, casefold=True)


def _hotp_code(secret: str, counter: int, digits: int = 6) -> str:
    key = _decode_base32_secret(secret)
    msg = struct.pack('>Q', counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code_int % (10 ** digits)).zfill(digits)


def get_totp_code(secret: str, for_time: float = None, period: int = 30, digits: int = 6) -> str:
    """Hitung kode TOTP 6 digit pada timestamp tertentu."""
    ts = time.time() if for_time is None else float(for_time)
    counter = int(ts // period)
    return _hotp_code(secret, counter, digits=digits)


def verify_totp_code(
    secret: str,
    code: str,
    valid_window: int = 1,
    for_time: float = None,
    period: int = 30,
    digits: int = 6,
    replay_scope: str = None,
) -> bool:
    """
    Verifikasi kode OTP 6 digit dengan toleransi +-valid_window interval (30 dtk)
    dan perbandingan constant-time. Bila `replay_scope` diisi, kode pada interval
    waktu yang sama atau lebih lama ditolak (anti-replay sesuai RFC 6238).
    """
    if not secret or not code:
        return False
    clean_code = re.sub(r'[\s\-]+', '', str(code))
    if len(clean_code) != digits or not clean_code.isdigit():
        return False
    try:
        ts = time.time() if for_time is None else float(for_time)
        base_counter = int(ts // period)
        matched_counter = None
        for offset in range(-valid_window, valid_window + 1):
            counter_candidate = base_counter + offset
            candidate = _hotp_code(secret, counter_candidate, digits=digits)
            if hmac.compare_digest(candidate, clean_code):
                matched_counter = counter_candidate
                break
        if matched_counter is None:
            return False

        if replay_scope:
            from django.core.cache import cache

            scope_digest = hashlib.sha256(f"{replay_scope}:{secret}".encode('utf-8')).hexdigest()[:32]
            last_key = f"totp_last_step:{scope_digest}"
            step_key = f"totp_used_step:{scope_digest}:{matched_counter}"
            step_ttl = max((valid_window + 2) * period, 120)

            prev_counter = cache.get(last_key)
            if prev_counter is not None and int(prev_counter) >= matched_counter:
                return False
            if not cache.add(step_key, 1, timeout=step_ttl):
                return False
            cache.set(last_key, matched_counter, timeout=max(step_ttl, 300))

        return True
    except (ValueError, TypeError):
        return False


def build_totp_uri(secret: str, account_name: str, issuer: str = 'BukuTamu Diskominfosantik') -> str:
    """Bangun URI otpauth:// untuk aplikasi Authenticator."""
    label = f"{quote(issuer)}:{quote(account_name)}"
    return (
        f"otpauth://totp/{label}"
        f"?secret={quote(secret)}&issuer={quote(issuer)}&algorithm=SHA1&digits=6&period=30"
    )


def format_totp_secret(secret: str) -> str:
    """Format secret Base32 menjadi blok 4 karakter agar mudah disalin manual."""
    clean = (secret or '').strip().upper()
    return ' '.join(clean[i:i + 4] for i in range(0, len(clean), 4))


class TamuPasswordResetTokenGenerator(PasswordResetTokenGenerator):
    """Token generator reset password khusus model Tamu (tanpa method AbstractBaseUser)."""

    def _make_hash_value(self, user, timestamp):
        login_timestamp = (
            ''
            if getattr(user, 'last_login', None) is None
            else user.last_login.replace(microsecond=0, tzinfo=None)
        )
        email = (getattr(user, 'email', '') or '').strip().lower()
        return f"{user.pk}{getattr(user, 'password', '') or ''}{login_timestamp}{timestamp}{email}"


tamu_reset_token_generator = TamuPasswordResetTokenGenerator()


def revoke_user_sessions(user_type: str, user_id: str, exclude_session_key: str = None) -> int:
    """
    Cabut seluruh sesi Django (django_session) dan AppSession aktif milik pengguna
    saat status akun dinonaktifkan/ditangguhkan atau saat password direset/diubah.
    """
    from django.contrib.sessions.models import Session as DjangoSession
    from .models import Session as AppSession

    target_id = str(user_id or '').strip()
    if not target_id or user_type not in ('tamu', 'pegawai', 'admin'):
        return 0

    matched_keys = []
    try:
        active_qs = DjangoSession.objects.filter(expire_date__gte=timezone.now()).iterator(chunk_size=200)
        for sess in active_qs:
            if exclude_session_key and sess.session_key == exclude_session_key:
                continue
            try:
                data = sess.get_decoded()
            except Exception:
                continue
            if user_type == 'tamu':
                is_match = str(data.get('tamu_id') or '') == target_id
            elif user_type == 'pegawai':
                is_match = str(data.get('pegawai_id') or '') == target_id
            else:
                is_match = (
                    str(data.get('_auth_user_id') or '') == target_id
                    or str(data.get('admin_id') or '') == target_id
                )
            if is_match:
                matched_keys.append(sess.session_key)
    except Exception as exc:
        logger.warning("Gagal memindai sesi Django untuk pencabutan sesi: %s", exc.__class__.__name__)

    revoked_count = 0
    if matched_keys:
        deleted, _ = DjangoSession.objects.filter(session_key__in=matched_keys).delete()
        revoked_count += deleted

    try:
        app_deleted, _ = AppSession.objects.filter(user_type=user_type, user_id=target_id).delete()
        revoked_count += app_deleted
    except Exception as exc:
        logger.warning("Gagal menghapus AppSession untuk %s:%s (%s)", user_type, target_id, exc.__class__.__name__)

    return revoked_count


def verify_pegawai_password(pegawai, raw_password: str, auto_upgrade: bool = True) -> bool:
    """
    Verifikasi password Pegawai (mendukung hash PBKDF2/Argon2 Django dan migrasi SHA-256 legacy).
    """
    from django.contrib.auth.hashers import check_password, make_password

    if not pegawai or not raw_password or not getattr(pegawai, 'password', None):
        return False

    stored = str(pegawai.password)
    if check_password(raw_password, stored):
        return True

    if '$' not in stored and len(stored) == 64:
        legacy_sha256 = hashlib.sha256(raw_password.encode('utf-8')).hexdigest()
        if hmac.compare_digest(stored, legacy_sha256):
            if auto_upgrade:
                pegawai.password = make_password(raw_password)
                pegawai.save(update_fields=['password'])
            return True
    return False
