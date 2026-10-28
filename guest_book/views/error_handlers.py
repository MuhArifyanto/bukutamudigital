from django.shortcuts import render
from django.http import JsonResponse, HttpResponseServerError
from django.template import loader
import logging

logger = logging.getLogger(__name__)


def custom_page_not_found_view(request, exception=None):
    """
    Handler 404 Kustom:
    - Jika request ditujukan ke endpoint API (/api/) atau mengharapkan JSON (Accept: application/json),
      kembalikan respons JSON agar klien API tidak menerima HTML.
    - Untuk browser umum, render templates/404.html kustom.
    """
    is_api = (
        request.path.startswith('/api/')
        or request.headers.get('Accept') == 'application/json'
        or 'application/json' in request.META.get('HTTP_ACCEPT', '')
    )
    if is_api:
        return JsonResponse({
            'success': False,
            'error': 'Endpoint tidak ditemukan'
        }, status=404)

    return render(request, '404.html', status=404)


def custom_server_error_view(request):
    """
    Handler 500 Kustom:
    - Jika request ditujukan ke endpoint API (/api/) atau mengharapkan JSON,
      kembalikan respons JSON.
    - Untuk browser umum, render templates/500.html secara mandiri
      tanpa RequestContext / context processor / query database agar tidak terjadi cascade error.
    """
    is_api = (
        request.path.startswith('/api/')
        or request.headers.get('Accept') == 'application/json'
        or 'application/json' in request.META.get('HTTP_ACCEPT', '')
    )
    if is_api:
        return JsonResponse({
            'success': False,
            'error': 'Terjadi gangguan pada server'
        }, status=500)

    try:
        content = loader.render_to_string('500.html')
        return HttpResponseServerError(content)
    except Exception:
        logger.exception("Gagal me-render templates/500.html")
        return HttpResponseServerError(
            "<!DOCTYPE html><html><body><h1>Terjadi Gangguan Server</h1>"
            "<p>Maaf, server sedang mengalami kendala. Silakan kembali ke <a href='/'>Beranda</a>.</p></body></html>"
        )
