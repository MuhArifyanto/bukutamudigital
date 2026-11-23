"""
Custom Media Storage Backends (Lokal Signed URL & Cloudinary Signed URL).
"""
import hashlib
import os
import posixpath
from urllib.parse import quote

import cloudinary
from cloudinary_storage.storage import MediaCloudinaryStorage
from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner

MEDIA_SIGNER_SALT = 'bukudigital-media-url'


def normalize_media_path(name: str) -> str:
    """Normalisasi path relatif media dan tolak upaya path traversal."""
    if not name or not isinstance(name, str):
        raise ValueError("Path media kosong.")
    cleaned = name.replace('\\', '/').lstrip('/')
    normalized = posixpath.normpath(cleaned)
    if (
        not normalized
        or normalized in ('.', '..')
        or normalized.startswith('../')
        or normalized.startswith('/')
        or '\x00' in normalized
    ):
        raise ValueError("Path media tidak valid.")
    return normalized


def _path_digest(normalized_path: str) -> str:
    return hashlib.sha256(normalized_path.encode('utf-8')).hexdigest()


def sign_media_path(name: str) -> str:
    """
    Buat token tanda tangan berbatas waktu (TimestampSigner) yang terikat
    secara kriptografis ke path media tertentu.
    """
    normalized = normalize_media_path(name)
    signer = TimestampSigner(salt=MEDIA_SIGNER_SALT)
    signed = signer.sign(_path_digest(normalized))
    # signed berbentuk "<sha256>:<ts>:<hmac>"; kembalikan "<ts>:<hmac>" agar URL ringkas
    return signed.split(':', 1)[1]


def verify_media_signature(name: str, token: str, max_age=None) -> bool:
    """Verifikasi token signed URL media beserta masa berlaku (TTL)."""
    if not token or not isinstance(token, str) or ':' not in token:
        return False
    try:
        normalized = normalize_media_path(name)
    except ValueError:
        return False

    ttl = getattr(settings, 'MEDIA_SIGNED_URL_TTL', 3600) if max_age is None else max_age
    signer = TimestampSigner(salt=MEDIA_SIGNER_SALT)
    candidate = f"{_path_digest(normalized)}:{token}"
    try:
        signer.unsign(candidate, max_age=ttl)
        return True
    except (BadSignature, SignatureExpired):
        return False


class SignedLocalMediaStorage(FileSystemStorage):
    """
    FileSystemStorage lokal yang otomatis menandatangani URL dengan TimestampSigner
    sehingga berkas sensitif di /media/ tidak dapat diakses tanpa tanda tangan valid.
    """

    def url(self, name):
        base_url = super().url(name)
        sig = sign_media_path(name)
        sep = '&' if '?' in base_url else '?'
        return f"{base_url}{sep}sig={quote(sig, safe=':_-')}"


class DynamicMediaCloudinaryStorage(MediaCloudinaryStorage):
    """
    Menggunakan resource_type 'raw' untuk dokumen Office/PDF, 'video' untuk video,
    dan 'image' untuk gambar, serta menghasilkan Signed URL (s--...--) saat
    api_secret Cloudinary tersedia.
    """
    IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'ico', 'svg'}
    VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv', 'webm'}

    def _get_resource_type(self, name):
        ext = os.path.splitext(name)[1].lower().lstrip('.')
        if ext in self.IMAGE_EXTENSIONS:
            return 'image'
        if ext in self.VIDEO_EXTENSIONS:
            return 'video'
        return 'raw'

    def _get_url(self, name):
        prefixed = self._prepend_prefix(name)
        res_type = self._get_resource_type(name)
        cloudinary_resource = cloudinary.CloudinaryResource(
            prefixed,
            default_resource_type=res_type,
        )
        has_secret = bool(getattr(cloudinary.config(), 'api_secret', None))
        return cloudinary_resource.build_url(secure=True, sign_url=has_secret)
