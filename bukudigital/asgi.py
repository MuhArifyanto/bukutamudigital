"""
ASGI config for bukudigital project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

from collections import deque
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bukudigital.settings')
django.setup()

from asgiref.sync import SyncToAsync, ThreadSensitiveContext
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
import guest_book.routing


class PersistentHTTPThreadPoolWrapper:
    """
    Pool LIFO (Most-Recently-Used) ThreadSensitiveContext persisten untuk HTTP ASGI.

    Tanpa wrapper ini, ASGIHandler Django membuat ThreadSensitiveContext baru
    (beserta OS thread baru) di setiap request HTTP lalu mematikan thread tersebut
    saat request selesai. Akibatnya, koneksi database persistent (CONN_MAX_AGE)
    di threading.local() selalu terbuang dan setiap perpindahan halaman harus
    melakukan handshake TCP + TLS + autentikasi baru ke TiDB Cloud (~3-4 detik).

    Dengan LIFO pool persisten:
    - Request HTTP berurutan memakai kembali thread yang sama yang sudah memiliki
      koneksi SSL TiDB Cloud terbuka (0 ms koneksi baru).
    - Request HTTP paralel mengambil worker thread berikutnya dari pool tanpa
      saling memblokir.
    """

    def __init__(self, app, pool_size: int = 4):
        self.app = app
        self._pool_size = max(1, int(pool_size))
        self._pool = deque(ThreadSensitiveContext() for _ in range(self._pool_size))

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)

        ctx = self._pool.pop() if self._pool else ThreadSensitiveContext()
        token = SyncToAsync.thread_sensitive_context.set(ctx)
        try:
            return await self.app(scope, receive, send)
        finally:
            SyncToAsync.thread_sensitive_context.reset(token)
            if len(self._pool) < self._pool_size * 2:
                self._pool.append(ctx)


django_http_app = PersistentHTTPThreadPoolWrapper(
    get_asgi_application(),
    pool_size=int(os.getenv('ASGI_DB_THREAD_POOL_SIZE', '4')),
)

application = ProtocolTypeRouter({
    "http": django_http_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                guest_book.routing.websocket_urlpatterns
            )
        )
    ),
})
