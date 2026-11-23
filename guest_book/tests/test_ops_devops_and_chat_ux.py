import json
import logging
import re
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

from channels.testing import WebsocketCommunicator
from django.conf import settings as app_settings
from django.core.cache import cache
from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from guest_book.consumers import ChatConsumer, NotificationConsumer
from guest_book.models import (
    ChatMessage,
    Departemen,
    Kunjungan,
    KunjunganStatus,
    LoginAttempt,
    Notification,
    Pegawai,
    Tamu,
)
from guest_book.monitoring import ErrorAlertMiddleware, StructuredJsonFormatter


class _MockScopeApp:
    """ASGI test wrapper untuk menyuntikkan user, session & route kwargs."""

    def __init__(self, consumer_cls, session_id=None, session_data=None, user=None):
        self.consumer_cls = consumer_cls
        self.session_id = session_id
        self.session_data = session_data or {}
        self.user = user

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        if self.session_id:
            scope['url_route'] = {'kwargs': {'session_id': self.session_id}}
        scope['session'] = self.session_data
        if self.user is not None:
            scope['user'] = self.user
        consumer = self.consumer_cls()
        return await consumer(scope, receive, send)


class StructuredLoggingAndHealthcheckTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_structured_json_formatter_outputs_valid_single_line_json(self):
        formatter = StructuredJsonFormatter()
        record = logging.LogRecord(
            name='guest_book.security',
            level=logging.ERROR,
            pathname=__file__,
            lineno=42,
            msg='Lonjakan %s gagal',
            args=('login',),
            exc_info=None,
        )
        record.event_type = 'login_failure_spike_ip'
        record.status_code = 500
        formatted = formatter.format(record)
        self.assertNotIn('\n', formatted)
        parsed = json.loads(formatted)
        self.assertEqual(parsed['level'], 'ERROR')
        self.assertEqual(parsed['logger'], 'guest_book.security')
        self.assertEqual(parsed['message'], 'Lonjakan login gagal')
        self.assertEqual(parsed['event_type'], 'login_failure_spike_ip')
        self.assertEqual(parsed['status_code'], 500)
        self.assertIn('timestamp', parsed)

    def test_logging_and_middleware_and_dockerfile_healthcheck(self):
        self.assertIn('json', app_settings.LOGGING['formatters'])
        self.assertIn('structured', app_settings.LOGGING['formatters'])
        self.assertIn('guest_book.monitoring.ErrorAlertMiddleware', app_settings.MIDDLEWARE)

        dockerfile = (Path(app_settings.BASE_DIR) / 'Dockerfile').read_text(encoding='utf-8')
        self.assertIn('FROM python:3.12-slim', dockerfile)
        self.assertIn('requirements.lock', dockerfile)
        self.assertIn('HEALTHCHECK', dockerfile)
        self.assertIn('/healthz/', dockerfile)

    def test_healthz_degraded_returns_503(self):
        with patch('django.core.cache.cache.set', side_effect=RuntimeError('Redis down')):
            resp = self.client.get(reverse('tamu:healthz'))
        self.assertEqual(resp.status_code, 503)
        data = resp.json()
        self.assertEqual(data['status'], 'degraded')
        self.assertEqual(data['checks']['cache'], 'error')

    @override_settings(
        SECURE_SSL_REDIRECT=True,
        SECURE_REDIRECT_EXEMPT=[r'^healthz/?$'],
        ALLOWED_HOSTS=['bukutamu.diskominfosantik.go.id', '127.0.0.1', 'localhost'],
    )
    def test_healthz_exempt_from_ssl_redirect_and_accepts_loopback_host_in_production(self):
        """
        K-4: Probe HTTP internal Docker/Render ke http://127.0.0.1:8000/healthz/
        tidak boleh terkena 301 redirect ke https:// ataupun 400 DisallowedHost,
        sementara endpoint publik tetap wajib redirect 301 ke https://.
        """
        resp_health = self.client.get('/healthz/', HTTP_HOST='127.0.0.1:8000', secure=False)
        self.assertEqual(resp_health.status_code, 200)
        self.assertEqual(resp_health.json()['status'], 'ok')

        resp_login = self.client.get(
            reverse('tamu:login'),
            HTTP_HOST='bukutamu.diskominfosantik.go.id',
            secure=False,
        )
        self.assertEqual(resp_login.status_code, 301)
        self.assertTrue(resp_login['Location'].startswith('https://'))


class SecurityAndErrorAlertingTests(TestCase):
    def setUp(self):
        cache.clear()
        Notification.objects.all().delete()

    @override_settings(
        LOGIN_SPIKE_WINDOW_SECONDS=300,
        LOGIN_SPIKE_IP_THRESHOLD=3,
        LOGIN_SPIKE_GLOBAL_THRESHOLD=50,
        LOGIN_ALERT_COOLDOWN_SECONDS=600,
        SECURITY_ALERT_WEBHOOK_URL='https://alerts.example.invalid/webhook',
        SECURITY_ALERT_SYNC=True,
    )
    @patch('requests.post')
    def test_login_failure_spike_triggers_throttled_admin_alert_and_webhook(self, mock_post):
        # 1 & 2 gagal -> belum mencapai threshold 3
        for idx in range(2):
            LoginAttempt.objects.create(
                email=f'user{idx}@example.com',
                user_type='admin',
                success=False,
                ip_address='203.0.113.55',
            )
        self.assertEqual(
            Notification.objects.filter(recipient_type='admin', notification_type='system_alert').count(),
            0,
        )
        mock_post.assert_not_called()

        # Ke-3 gagal -> picu 1 alert admin + 1 webhook
        LoginAttempt.objects.create(
            email='victim@example.com',
            user_type='admin',
            success=False,
            ip_address='203.0.113.55',
        )
        alerts = Notification.objects.filter(recipient_type='admin', notification_type='system_alert')
        self.assertEqual(alerts.count(), 1)
        self.assertIn('203.0.113.55', alerts.first().message)
        self.assertNotIn('victim@example.com', alerts.first().message)
        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args.kwargs['json']['event_type'], 'login_failure_spike_ip')

        # Percobaan gagal ke-4 dalam periode cooldown -> ter-throttle, tidak spam
        LoginAttempt.objects.create(
            email='victim@example.com',
            user_type='admin',
            success=False,
            ip_address='203.0.113.55',
        )
        self.assertEqual(alerts.count(), 1)
        self.assertEqual(mock_post.call_count, 1)

    @override_settings(
        SERVER_ERROR_SPIKE_WINDOW_SECONDS=300,
        SERVER_ERROR_SPIKE_THRESHOLD=1,
        SERVER_ERROR_ALERT_COOLDOWN_SECONDS=300,
        SECURITY_ALERT_WEBHOOK_URL='https://alerts.example.invalid/webhook',
        SECURITY_ALERT_SYNC=True,
        SENTRY_DSN='https://public@example.invalid/1',
    )
    @patch('requests.post')
    def test_http_500_middleware_alerts_and_calls_sentry(self, mock_post):
        fake_sentry = types.SimpleNamespace(
            capture_exception=MagicMock(),
            capture_message=MagicMock(),
        )
        scope_cm = MagicMock()
        scope_cm.__enter__.return_value = MagicMock()
        scope_cm.__exit__.return_value = False
        fake_sentry.push_scope = MagicMock(return_value=scope_cm)

        from django.http import Http404

        mw = ErrorAlertMiddleware(lambda req: HttpResponse('OK'))
        req_404 = RequestFactory().get('/tidak-ditemukan/')
        mw.process_exception(req_404, Http404('Not found'))
        self.assertEqual(Notification.objects.filter(recipient_type='admin', notification_type='system_alert').count(), 0)
        mock_post.assert_not_called()

        req = RequestFactory().get('/endpoint-rusak/')

        with patch.dict('sys.modules', {'sentry_sdk': fake_sentry}):
            mw.process_exception(req, RuntimeError('Kegagalan fatal DB'))

        fake_sentry.capture_exception.assert_called_once()
        alerts = Notification.objects.filter(recipient_type='admin', notification_type='system_alert')
        self.assertEqual(alerts.count(), 1)
        self.assertIn('/endpoint-rusak/', alerts.first().message)
        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args.kwargs['json']['event_type'], 'server_error_500_spike')


class DependencyPinningAndDevOpsTests(TestCase):
    def test_requirements_strictly_pinned_and_lockfile_present(self):
        base = Path(app_settings.BASE_DIR)
        req_lines = [
            line.strip()
            for line in (base / 'requirements.txt').read_text(encoding='utf-8').splitlines()
            if line.strip() and not line.strip().startswith('#')
        ]
        self.assertGreaterEqual(len(req_lines), 18)
        for line in req_lines:
            self.assertNotIn('>=', line, f"Batas terbuka terdeteksi di requirements.txt: {line}")
            self.assertNotIn('<=', line, f"Batas terbuka terdeteksi di requirements.txt: {line}")
            self.assertRegex(line, r'^[A-Za-z0-9_.\-]+==[A-Za-z0-9_.\-+]+$')

        lock_path = base / 'requirements.lock'
        self.assertTrue(lock_path.is_file())
        lock_lines = [
            line.strip()
            for line in lock_path.read_text(encoding='utf-8').splitlines()
            if line.strip() and not line.strip().startswith('#')
        ]
        self.assertGreater(len(lock_lines), len(req_lines))
        for line in lock_lines:
            self.assertRegex(line, r'^[A-Za-z0-9_.\-]+==[A-Za-z0-9_.\-+]+$')
        self.assertTrue(any(l.startswith('Django==6.0.8') for l in lock_lines))

    def test_dependabot_and_ci_security_scans_configured(self):
        base = Path(app_settings.BASE_DIR)
        dependabot = (base / '.github' / 'dependabot.yml').read_text(encoding='utf-8')
        self.assertIn('package-ecosystem: "pip"', dependabot)
        self.assertIn('package-ecosystem: "github-actions"', dependabot)

        ci_yml = (base / '.github' / 'workflows' / 'ci.yml').read_text(encoding='utf-8')
        self.assertIn("python-version: '3.12'", ci_yml)
        self.assertIn('requirements.lock', ci_yml)
        self.assertIn('pip-audit', ci_yml)
        self.assertIn('bandit', ci_yml)
        self.assertIn('check --deploy', ci_yml)

    def test_docker_and_pdp_retention_hardening(self):
        base = Path(app_settings.BASE_DIR)

        dockerignore = (base / '.dockerignore').read_text(encoding='utf-8')
        for entry in ('.env', '.git', 'media/', 'scripts/', 'scratch/'):
            self.assertIn(entry, dockerignore)

        dockerfile = (base / 'Dockerfile').read_text(encoding='utf-8')
        self.assertIn('AS builder', dockerfile)
        self.assertIn('AS runtime', dockerfile)
        self.assertIn('USER appuser', dockerfile)
        self.assertIn('ALLOWED_HOSTS=localhost', dockerfile)
        self.assertIn('CSRF_TRUSTED_ORIGINS=https://localhost', dockerfile)
        self.assertIn('exec daphne', dockerfile)
        self.assertIn("'Host': host", dockerfile)
        runtime_section = dockerfile.split('AS runtime', 1)[1]
        self.assertNotIn('gcc', runtime_section)

        pdp_yml = (base / '.github' / 'workflows' / 'pdp-retention.yml').read_text(encoding='utf-8')
        self.assertIn('pip install --no-deps -r requirements.lock', pdp_yml)
        self.assertIn('SECRET_KEY:', pdp_yml)
        self.assertIn('ALLOWED_HOSTS:', pdp_yml)
        self.assertIn('CSRF_TRUSTED_ORIGINS:', pdp_yml)
        self.assertIn('DB_HOST:', pdp_yml)
        self.assertIn('DB_NAME:', pdp_yml)
        self.assertNotIn('DB_ENGINE:', pdp_yml)
        self.assertNotIn('DATABASE_URL:', pdp_yml)


class MultiRoomChatAndGlobalNotificationTests(TransactionTestCase):
    async def test_chat_message_pushes_sidebar_update_via_global_notifications(self):
        """
        Pesan baru di ruang chat Tamu atau Kunjungan harus menyiarkan event
        `chat_sidebar_update` ke kanal `/ws/notifications/` partisipan terkait
        agar sidebar (preview, urutan, badge unread) terbarui real-time tanpa reload.
        """
        from channels.db import database_sync_to_async
        from django.contrib.auth.models import User

        admin_user = await database_sync_to_async(User.objects.create_user)(
            username='admin.multiroom',
            email='admin.multiroom@example.com',
            password='StrongAdminMulti!2026',
            is_staff=True,
        )
        tamu = await database_sync_to_async(Tamu.objects.create)(
            name='Tamu Multiroom',
            email='tamu.multiroom@example.com',
            phone='08123456000',
            instansi='Diskominfo Jabar',
            account_status='active',
        )
        dept = await database_sync_to_async(Departemen.objects.create)(nama='Bidang Aplikasi')
        pegawai = await database_sync_to_async(Pegawai.objects.create)(
            name='Pegawai Multiroom',
            username='pegawai.multiroom',
            email='pegawai.multiroom@example.com',
            phone='08123456001',
            department_rel=dept,
            password='hashed_password',
            account_status='active',
        )
        kunjungan = await database_sync_to_async(Kunjungan.objects.create)(
            tamu=tamu,
            pegawai=pegawai,
            arrival_time=timezone.now(),
            purpose='Koordinasi API',
            status=KunjunganStatus.DISETUJUI,
        )

        tamu_session = f'tamu_{tamu.id}'
        kunjungan_session = f'kunjungan_{kunjungan.id}'

        admin_notif = WebsocketCommunicator(
            _MockScopeApp(NotificationConsumer, session_data={}, user=admin_user),
            '/ws/notifications/',
        )
        pegawai_notif = WebsocketCommunicator(
            _MockScopeApp(NotificationConsumer, session_data={'pegawai_id': str(pegawai.id)}),
            '/ws/notifications/',
        )
        tamu_notif = WebsocketCommunicator(
            _MockScopeApp(NotificationConsumer, session_data={'tamu_id': str(tamu.id)}),
            '/ws/notifications/',
        )

        self.assertTrue((await admin_notif.connect())[0])
        self.assertTrue((await pegawai_notif.connect())[0])
        self.assertTrue((await tamu_notif.connect())[0])

        # 1. Tamu mengirim pesan ke Admin -> Admin NotificationConsumer menerima notification + chat_sidebar_update
        tamu_chat = WebsocketCommunicator(
            _MockScopeApp(ChatConsumer, session_id=tamu_session, session_data={'tamu_id': str(tamu.id)}),
            f'/ws/chat/{tamu_session}/',
        )
        self.assertTrue((await tamu_chat.connect())[0])
        await tamu_chat.send_json_to({'action': 'create', 'message': 'Halo Admin dari room tamu'})
        await tamu_chat.receive_json_from()

        admin_events = [
            await admin_notif.receive_json_from(),
            await admin_notif.receive_json_from(),
        ]
        sidebar_events = [e for e in admin_events if e.get('event_type') == 'chat_sidebar_update']
        self.assertEqual(len(sidebar_events), 1)
        self.assertEqual(sidebar_events[0]['session_id'], tamu_session)
        self.assertEqual(sidebar_events[0]['preview'], 'Halo Admin dari room tamu')
        self.assertTrue(sidebar_events[0]['suppress_toast'])

        await tamu_chat.disconnect()

        # Tamu juga menerima 1 chat_sidebar_update atas pesannya sendiri (untuk sinkronisasi multi-tab)
        tamu_self_ev = await tamu_notif.receive_json_from()
        self.assertEqual(tamu_self_ev.get('event_type'), 'chat_sidebar_update')

        # 2. Tamu mengirim pesan di room kunjungan_{id} -> Pegawai notif menerima notification + chat_sidebar_update, Admin TIDAK
        kunjungan_chat = WebsocketCommunicator(
            _MockScopeApp(ChatConsumer, session_id=kunjungan_session, session_data={'tamu_id': str(tamu.id)}),
            f'/ws/chat/{kunjungan_session}/',
        )
        self.assertTrue((await kunjungan_chat.connect())[0])
        await kunjungan_chat.send_json_to({'action': 'create', 'message': 'Sudah di lobi pak'})
        await kunjungan_chat.receive_json_from()

        peg_events = [
            await pegawai_notif.receive_json_from(),
            await pegawai_notif.receive_json_from(),
        ]
        peg_sidebar = [e for e in peg_events if e.get('event_type') == 'chat_sidebar_update']
        self.assertEqual(len(peg_sidebar), 1)
        self.assertEqual(peg_sidebar[0]['session_id'], kunjungan_session)
        self.assertEqual(peg_sidebar[0]['preview'], 'Sudah di lobi pak')
        self.assertTrue(await admin_notif.receive_nothing())

        await kunjungan_chat.disconnect()
        await admin_notif.disconnect()
        await pegawai_notif.disconnect()
        await tamu_notif.disconnect()

    def test_api_get_chat_messages_returns_room_meta_and_marks_read_without_reload(self):
        tamu = Tamu.objects.create(
            name='Siti Tamu',
            email='siti.tamu@example.com',
            phone='08123456010',
            instansi='Pemkab Bekasi',
            account_status='active',
        )
        other_tamu = Tamu.objects.create(
            name='Orang Lain',
            email='other.tamu@example.com',
            phone='08123456011',
            account_status='active',
        )
        session_id = str(tamu.id)
        ChatMessage.objects.create(
            session_id=session_id,
            sender_id='admin',
            sender_type='admin',
            content='Silakan masuk ke ruang rapat.',
            is_read=False,
        )

        # Akses oleh tamu lain ditolak 403
        forbidden_client = Client()
        s_other = forbidden_client.session
        s_other['tamu_id'] = str(other_tamu.id)
        s_other.save()
        res_403 = forbidden_client.get(reverse('tamu:api_chat_messages'), {'session_id': session_id})
        self.assertEqual(res_403.status_code, 403)

        # Akses oleh tamu sah dengan mark_read=1 mengembalikan room_meta & menandai terbaca
        ok_client = Client()
        s_ok = ok_client.session
        s_ok['tamu_id'] = str(tamu.id)
        s_ok.save()
        res = ok_client.get(reverse('tamu:api_chat_messages'), {'session_id': session_id, 'mark_read': '1'})
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertTrue(payload['success'])
        self.assertEqual(payload['session_id'], session_id)
        self.assertEqual(payload['room_meta']['name'], 'Admin Diskominfosantik')
        self.assertTrue(payload['room_meta']['is_admin_room'])
        self.assertEqual(len(payload['messages']), 1)
        self.assertIn('created_at_iso', payload['messages'][0])
        self.assertFalse(ChatMessage.objects.filter(session_id=session_id, is_read=False).exists())

    def test_chat_templates_use_spa_room_switching_without_reload(self):
        templates_dir = Path(app_settings.BASE_DIR) / 'guest_book' / 'templates' / 'guest_book'
        for tpl_name in ('admin_chat.html', 'pegawai_chat.html', 'tamu_chat.html'):
            html = (templates_dir / tpl_name).read_text(encoding='utf-8')
            self.assertIn('ChatMultiRoomHelper.initMultiRoomChat', html, tpl_name)
            self.assertIn('data-session-id=', html, tpl_name)
            self.assertNotIn('location.href = `?session=', html, tpl_name)

        for base_name in ('admin_base.html', 'pegawai_base.html', 'tamu_base.html'):
            html = (templates_dir / base_name).read_text(encoding='utf-8')
            self.assertIn("new CustomEvent('ws:notification'", html, base_name)
            self.assertIn('chat_sidebar_update', html, base_name)
