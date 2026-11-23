"""
URL configuration for bukudigital project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path, reverse
from django.conf import settings
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from guest_book.views.media import protected_media_view


def _django_admin_login_gate(request):
    """Alihkan seluruh login `/admin/login/` ke Portal Admin yang menegakkan 2FA TOTP."""
    login_url = reverse('tamu:admin_login')
    next_url = (request.GET.get('next') or request.POST.get('next') or '').strip()
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        from urllib.parse import urlencode
        return redirect(f"{login_url}?{urlencode({'next': next_url})}")
    return redirect(login_url)


urlpatterns = [
    path('admin/login/', _django_admin_login_gate, name='django_admin_login_gate'),
    path('admin/', admin.site.urls),
    path('', include('guest_book.urls')),
    re_path(r'^media/(?P<path>.*)$', protected_media_view),
]

handler404 = 'guest_book.views.custom_page_not_found_view'
handler500 = 'guest_book.views.custom_server_error_view'
