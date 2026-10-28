"""
guest_book/tests/test_settings_and_env.py
Pengujian otomatis untuk mode environment (local vs production),
validasi start-up production, penguncian DEBUG, dan status cookie secure.
"""

import os
import unittest
from unittest.mock import patch
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase


class SettingsAndEnvTestCase(SimpleTestCase):
    """
    Test isolasi konfigurasi settings.py untuk memastikan
    kebijakan keamanan local vs production berjalan sesuai spesifikasi.
    """

    def test_production_mode_fails_without_secret_key(self):
        """Mode production harus menolak start (raise ImproperlyConfigured) jika SECRET_KEY kosong."""
        with patch.dict(os.environ, {
            'APP_ENV': 'production',
            'SECRET_KEY': '',
            'ALLOWED_HOSTS': 'example.com',
            'CSRF_TRUSTED_ORIGINS': 'https://example.com',
        }, clear=True):
            with self.assertRaises(ImproperlyConfigured) as ctx:
                import importlib
                import bukudigital.settings as app_settings
                importlib.reload(app_settings)
            self.assertIn("SECRET_KEY wajib diset", str(ctx.exception))

    def test_production_mode_fails_without_allowed_hosts(self):
        """Mode production harus menolak start jika ALLOWED_HOSTS kosong."""
        with patch.dict(os.environ, {
            'APP_ENV': 'production',
            'SECRET_KEY': 'some-secure-test-key-1234567890-production',
            'ALLOWED_HOSTS': '',
            'CSRF_TRUSTED_ORIGINS': 'https://example.com',
        }, clear=True):
            with self.assertRaises(ImproperlyConfigured) as ctx:
                import importlib
                import bukudigital.settings as app_settings
                importlib.reload(app_settings)
            self.assertIn("ALLOWED_HOSTS wajib diset", str(ctx.exception))

    def test_production_mode_fails_without_csrf_trusted_origins(self):
        """Mode production harus menolak start jika CSRF_TRUSTED_ORIGINS kosong."""
        with patch.dict(os.environ, {
            'APP_ENV': 'production',
            'SECRET_KEY': 'some-secure-test-key-1234567890-production',
            'ALLOWED_HOSTS': 'example.com',
            'CSRF_TRUSTED_ORIGINS': '',
        }, clear=True):
            with self.assertRaises(ImproperlyConfigured) as ctx:
                import importlib
                import bukudigital.settings as app_settings
                importlib.reload(app_settings)
            self.assertIn("CSRF_TRUSTED_ORIGINS wajib diset", str(ctx.exception))

    def test_production_mode_locks_debug_to_false(self):
        """Di mode production, DEBUG selalu False meskipun ada DEBUG=True di env."""
        with patch.dict(os.environ, {
            'APP_ENV': 'production',
            'SECRET_KEY': 'prod-key-1234567890-prod-key-1234567890-secure',
            'ALLOWED_HOSTS': 'example.com',
            'CSRF_TRUSTED_ORIGINS': 'https://example.com',
            'FIREBASE_WEBHOOK_SECRET': 'test-firebase',
            'DEBUG': 'True',  # Mencoba menyalakan debug
        }, clear=True):
            import importlib
            import bukudigital.settings as app_settings
            importlib.reload(app_settings)

            self.assertFalse(app_settings.DEBUG)
            self.assertTrue(app_settings.SESSION_COOKIE_SECURE)
            self.assertTrue(app_settings.CSRF_COOKIE_SECURE)
            self.assertTrue(app_settings.SECURE_SSL_REDIRECT)
            self.assertEqual(app_settings.X_FRAME_OPTIONS, 'DENY')
            self.assertEqual(app_settings.CACHES['default']['BACKEND'], 'django.core.cache.backends.db.DatabaseCache')

    def test_local_mode_allows_debug_and_disables_secure_cookies(self):
        """Di mode local, DEBUG diizinkan True dan cookie secure dimatikan untuk HTTP localhost."""
        with patch.dict(os.environ, {
            'APP_ENV': 'local',
            'DEBUG': 'True',
        }, clear=True):
            import importlib
            import bukudigital.settings as app_settings
            importlib.reload(app_settings)

            self.assertTrue(app_settings.DEBUG)
            self.assertFalse(app_settings.SESSION_COOKIE_SECURE)
            self.assertFalse(app_settings.CSRF_COOKIE_SECURE)
            self.assertFalse(app_settings.SECURE_SSL_REDIRECT)
            self.assertIn('127.0.0.1', app_settings.ALLOWED_HOSTS)
            self.assertIn('localhost', app_settings.ALLOWED_HOSTS)
            self.assertEqual(app_settings.CACHES['default']['BACKEND'], 'django.core.cache.backends.locmem.LocMemCache')

    def test_proxy_ssl_header_enabled_when_env_true(self):
        """Saat USE_PROXY_SSL_HEADER='True' di production, SECURE_PROXY_SSL_HEADER harus aktif."""
        with patch.dict(os.environ, {
            'APP_ENV': 'production',
            'SECRET_KEY': 'prod-key-1234567890-prod-key-1234567890-secure',
            'ALLOWED_HOSTS': 'bukutamu.onrender.com',
            'CSRF_TRUSTED_ORIGINS': 'https://bukutamu.onrender.com',
            'FIREBASE_WEBHOOK_SECRET': 'test-firebase-token',
            'USE_PROXY_SSL_HEADER': 'True',
        }, clear=True):
            import importlib
            import bukudigital.settings as app_settings
            importlib.reload(app_settings)

            self.assertEqual(app_settings.SECURE_PROXY_SSL_HEADER, ('HTTP_X_FORWARDED_PROTO', 'https'))

    def test_proxy_ssl_header_disabled_when_env_false(self):
        """Saat USE_PROXY_SSL_HEADER='False' di production, SECURE_PROXY_SSL_HEADER harus None."""
        with patch.dict(os.environ, {
            'APP_ENV': 'production',
            'SECRET_KEY': 'prod-key-1234567890-prod-key-1234567890-secure',
            'ALLOWED_HOSTS': 'bukutamu.onrender.com',
            'CSRF_TRUSTED_ORIGINS': 'https://bukutamu.onrender.com',
            'FIREBASE_WEBHOOK_SECRET': 'test-firebase-token',
            'USE_PROXY_SSL_HEADER': 'False',
        }, clear=True):
            import importlib
            import bukudigital.settings as app_settings
            importlib.reload(app_settings)

            self.assertIsNone(app_settings.SECURE_PROXY_SSL_HEADER)

    def test_websocket_allowed_hosts_validator_configured(self):
        """Routing WebSocket di asgi.py harus dibungkus dengan AllowedHostsOriginValidator."""
        from channels.security.websocket import OriginValidator
        from bukudigital.asgi import application

        self.assertIn('websocket', application.application_mapping)
        ws_app = application.application_mapping['websocket']
        self.assertIsInstance(ws_app, OriginValidator)
        self.assertTrue(hasattr(ws_app, 'validate_origin'))

    def tearDown(self):
        # Kembalikan modul settings ke state default setelah reload
        import importlib
        import bukudigital.settings as app_settings
        importlib.reload(app_settings)
        super().tearDown()

