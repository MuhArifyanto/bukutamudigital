"""
Protected Media View — menyajikan berkas lokal /media/ hanya jika URL memiliki
signed token (`?sig=...`) yang valid dan belum kedaluwarsa.
"""
import mimetypes
from pathlib import Path

from django.conf import settings
from django.http import (
    FileResponse,
    Http404,
    HttpResponseForbidden,
    HttpResponseNotAllowed,
)

from ..storage import normalize_media_path, verify_media_signature

_SAFE_INLINE_IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}


def protected_media_view(request, path):
    """Serve berkas dari MEDIA_ROOT hanya bila tanda tangan URL valid."""
    if request.method not in ('GET', 'HEAD'):
        return HttpResponseNotAllowed(['GET', 'HEAD'])

    sig = request.GET.get('sig', '')
    if not verify_media_signature(path, sig):
        return HttpResponseForbidden('Tanda tangan akses media tidak valid atau sudah kedaluwarsa.')

    try:
        rel_path = normalize_media_path(path)
    except ValueError:
        return HttpResponseForbidden('Path media tidak valid.')

    media_root = Path(settings.MEDIA_ROOT).resolve()
    target_path = (media_root / rel_path).resolve()

    try:
        target_path.relative_to(media_root)
    except ValueError:
        return HttpResponseForbidden('Akses di luar direktori media ditolak.')

    if not target_path.is_file():
        raise Http404('Berkas media tidak ditemukan.')

    ext = target_path.suffix.lower()
    content_type, _ = mimetypes.guess_type(str(target_path))
    if not content_type:
        content_type = 'application/octet-stream'

    as_attachment = ext not in _SAFE_INLINE_IMAGE_EXTS
    response = FileResponse(
        open(target_path, 'rb'),
        content_type=content_type,
        as_attachment=as_attachment,
        filename=target_path.name if as_attachment else '',
    )
    response['X-Content-Type-Options'] = 'nosniff'
    response['Cache-Control'] = 'private, max-age=300'
    return response
