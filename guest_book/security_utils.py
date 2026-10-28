"""
Utilitas keamanan bersama (tanpa efek samping, aman dipakai di view mana pun).

- hash_identifier  : kunci cache rate limit berbasis HMAC (tidak menyimpan nilai mentah).
- mask_*           : versi tersamar NIK/email untuk log.
- classify_identifier : menentukan apakah input login berupa email atau NIK.
"""
import hashlib
import hmac
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

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
