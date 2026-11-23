import importlib
import json
import os
import uuid
from unittest.mock import patch

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, clear_url_caches, reverse
from django.utils import timezone

from guest_book.consumers import ChatConsumer
from guest_book.models import ChatMessage, Departemen, Kunjungan, Notification, Pegawai, Tamu
from guest_book.tests.test_websocket_consumers import MockScopeApp
from guest_book.utils import is_session_handed_off_to_admin, set_session_handoff_to_admin
from guest_book.views.base import clamp_page_size


class AdminChatSearchXssTests(TestCase):
    """Memastikan hasil pencarian kontak di admin_chat.html melakukan escaping HTML dan URL encoding."""

    def test_admin_chat_template_escapes_search_user_fields(self):
        tmpl_path = os.path.join(
            settings.BASE_DIR, 'guest_book', 'templates', 'guest_book', 'admin_chat.html'
        )
        with open(tmpl_path, 'r', encoding='utf-8') as f:
            source = f.read()

        self.assertIn('encodeURIComponent(query)', source)
        self.assertIn('escapeHtml(String(user.name', source)
        self.assertIn('escapeHtml(String(user.email || user.role', source)
        self.assertNotIn('${user.name}', source)


class WebSocketResetAiTests(TransactionTestCase):
    """Memastikan action reset_ai di ChatConsumer tidak lagi dead-code dan menjaga otorisasi."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    async def test_tamu_reset_ai_clears_handoff_and_replies_success(self):
        tamu = await database_sync_to_async(Tamu.objects.create)(
            name='Tamu Reset AI',
            email='reset_ai@example.com',
            phone='081234567890',
            account_status='active',
        )
        session_id = f'tamu_{tamu.id}'
        set_session_handoff_to_admin(session_id, active=True)
        self.assertTrue(is_session_handed_off_to_admin(session_id))

        app = MockScopeApp(ChatConsumer, session_id=session_id, session_data={'tamu_id': str(tamu.id)})
        comm = WebsocketCommunicator(app, f'/ws/chat/{session_id}/')
        connected, _ = await comm.connect()
        self.assertTrue(connected)

        await comm.send_to(text_data=json.dumps({'action': 'reset_ai'}))
        response = json.loads(await comm.receive_from())

        self.assertEqual(response['action'], 'reset_ai')
        self.assertTrue(response['success'])
        self.assertFalse(response['handoff_active'])
        self.assertFalse(is_session_handed_off_to_admin(session_id))
        await comm.disconnect()


class PaginationClampAndBatchReadTests(TestCase):
    """Memastikan page_size dibatasi aman dan penandaan is_read dilakukan secara batch."""

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='admin_p2',
            email='admin_p2@example.com',
            password='Str0ngAdm1n!P2_2026',
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )
        self.client = Client()
        self.client.force_login(self.admin_user)

    def test_clamp_page_size_helper_bounds(self):
        self.assertEqual(clamp_page_size('999999', default=50, max_size=100), 100)
        self.assertEqual(clamp_page_size('-10', default=50, max_size=100), 1)
        self.assertEqual(clamp_page_size('0', default=50, max_size=100), 1)
        self.assertEqual(clamp_page_size('bukan_angka', default=50, max_size=100), 50)
        self.assertEqual(clamp_page_size(None, default=5, max_size=50), 5)
        self.assertEqual(clamp_page_size('25', default=5, max_size=50), 25)

    def test_chat_messages_clamps_page_size_and_marks_read_in_single_batch_update(self):
        session_id = 'tamu_batch_room'
        for idx in range(12):
            ChatMessage.objects.create(
                session_id=session_id,
                sender_id='tamu-1',
                sender_type='tamu',
                content=f'Pesan ke-{idx}',
                is_read=False,
            )

        chat_table = ChatMessage._meta.db_table
        with CaptureQueriesContext(connection) as ctx:
            resp = self.client.get(
                reverse('tamu:api_get_chat_messages'),
                {'session_id': session_id, 'page_size': '999999'},
            )

        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload['success'])
        self.assertEqual(len(payload['messages']), 12)
        self.assertEqual(
            ChatMessage.objects.filter(session_id=session_id, is_read=False).count(),
            0,
        )
        update_queries = [
            q['sql']
            for q in ctx.captured_queries
            if q['sql'].lstrip().upper().startswith('UPDATE') and chat_table in q['sql']
        ]
        self.assertEqual(len(update_queries), 1, f"Seharusnya tepat 1 batch UPDATE, ditemukan {len(update_queries)}")

    def test_recent_notifications_and_visits_by_date_clamp_extreme_page_size(self):
        for i in range(60):
            Notification.objects.create(
                recipient_id='admin',
                recipient_type='admin',
                notification_type='visit_registered',
                title=f'Notif {i}',
                message='Isi notif',
                status='unread',
            )

        notif_resp = self.client.get(
            reverse('tamu:api_get_recent_notifications'),
            {'page_size': '999999'},
        )
        self.assertEqual(notif_resp.status_code, 200)
        self.assertEqual(len(notif_resp.json()['notifications']), 50)

        notif_bad = self.client.get(
            reverse('tamu:api_get_recent_notifications'),
            {'page_size': 'abc'},
        )
        self.assertEqual(notif_bad.status_code, 200)
        self.assertEqual(len(notif_bad.json()['notifications']), 5)

        visits_resp = self.client.get(
            reverse('tamu:api_get_visits_by_date'),
            {'date': '2026-11-14', 'page_size': '999999'},
        )
        self.assertEqual(visits_resp.status_code, 200)
        self.assertTrue(visits_resp.json()['success'])


class ErrorMaskingTests(TestCase):
    """Memastikan exception internal tidak dibocorkan via str(e) di respons API."""

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='admin_err',
            email='admin_err@example.com',
            password='Str0ngAdm1n!Err2026',
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )
        self.client = Client()
        self.client.force_login(self.admin_user)
        self.dept = Departemen.objects.create(nama='Bidang TIK')
        self.pegawai = Pegawai.objects.create(
            name='Pegawai Uji',
            email='pegawai_uji@example.com',
            nip='199001012020011001',
            phone='081200000001',
            department_rel=self.dept,
            role='staf',
        )
        self.tamu = Tamu.objects.create(
            name='Tamu Uji',
            email='tamu_uji@example.com',
            phone='081200000002',
        )

    @patch('guest_book.models.CalendarSettings.objects.get_or_create', side_effect=RuntimeError('SECRET_DB_DSN_LEAK'))
    def test_api_update_quota_hides_internal_exception(self, _mock):
        resp = self.client.post(
            reverse('tamu:api_update_quota'),
            data=json.dumps({'date': '2026-11-14', 'quota': 10}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn('SECRET_DB_DSN_LEAK', resp.content.decode('utf-8'))

    @patch('guest_book.models.ChatMessage.objects.get', side_effect=RuntimeError('SECRET_DB_DSN_LEAK'))
    def test_api_delete_chat_message_hides_internal_exception(self, _mock):
        resp = self.client.post(
            reverse('tamu:api_delete_chat_message', kwargs={'message_id': uuid.uuid4()})
        )
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn('SECRET_DB_DSN_LEAK', resp.content.decode('utf-8'))

    @patch('guest_book.models.Pegawai.objects.get', side_effect=RuntimeError('SECRET_DB_DSN_LEAK'))
    def test_admin_pegawai_update_endpoints_hide_internal_exception(self, _mock):
        role_resp = self.client.post(
            reverse('tamu:admin_pegawai_update_role', kwargs={'pegawai_id': self.pegawai.id}),
            data=json.dumps({'role': 'staf'}),
            content_type='application/json',
        )
        status_resp = self.client.post(
            reverse('tamu:admin_pegawai_update_status', kwargs={'pegawai_id': self.pegawai.id}),
            data=json.dumps({'status': 'active'}),
            content_type='application/json',
        )
        self.assertEqual(role_resp.status_code, 500)
        self.assertEqual(status_resp.status_code, 500)
        self.assertNotIn('SECRET_DB_DSN_LEAK', role_resp.content.decode('utf-8'))
        self.assertNotIn('SECRET_DB_DSN_LEAK', status_resp.content.decode('utf-8'))

    @patch('guest_book.models.Tamu.objects.get', side_effect=RuntimeError('SECRET_DB_DSN_LEAK'))
    def test_api_toggle_user_status_hides_internal_exception(self, _mock):
        resp = self.client.post(
            reverse('tamu:api_toggle_user_status', kwargs={'user_id': self.tamu.id}),
            {'status': 'active'},
        )
        self.assertEqual(resp.status_code, 500)
        self.assertNotIn('SECRET_DB_DSN_LEAK', resp.content.decode('utf-8'))


class DebugEndpointsDisabledInProdTests(TestCase):
    """Memastikan endpoint debug hanya terdaftar saat DEBUG=True, return 404 saat DEBUG=False, dan mendukung pagination."""

    DEBUG_PATHS = [
        '/api/debug/counts/',
        '/admin-portal/api/debug-calendar/',
    ]

    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='admin_dbg',
            email='admin_dbg@example.com',
            password='Str0ngAdm1n!Dbg2026',
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )

    @staticmethod
    def _reload_urlconfs():
        import bukudigital.urls as root_urls
        import guest_book.urls as app_urls

        clear_url_caches()
        importlib.reload(app_urls)
        importlib.reload(root_urls)
        clear_url_caches()

    def tearDown(self):
        self._reload_urlconfs()
        super().tearDown()

    def test_debug_routes_not_registered_and_return_404_when_debug_false(self):
        with override_settings(DEBUG=False):
            self._reload_urlconfs()
            anon = Client()
            auth_admin = Client()
            auth_admin.force_login(self.admin_user)

            for name in ('tamu:api_debug_counts', 'tamu:api_debug_calendar_settings'):
                with self.assertRaises(NoReverseMatch):
                    reverse(name)

            for url in self.DEBUG_PATHS:
                self.assertEqual(anon.get(url).status_code, 404)
                self.assertEqual(auth_admin.get(url).status_code, 404)

    def test_debug_decorator_blocks_when_debug_flipped_false_at_runtime(self):
        """Defense-in-depth: walau route debug sudah dimuat, decorator tetap mengembalikan 404 saat DEBUG=False."""
        with override_settings(DEBUG=True):
            self._reload_urlconfs()
            urls = [
                reverse('tamu:api_debug_counts'),
                reverse('tamu:api_debug_calendar_settings'),
            ]
            with override_settings(DEBUG=False):
                anon = Client()
                auth_admin = Client()
                auth_admin.force_login(self.admin_user)
                for url in urls:
                    self.assertEqual(anon.get(url).status_code, 404)
                    self.assertEqual(auth_admin.get(url).status_code, 404)

    def test_debug_endpoints_work_only_for_admin_when_debug_true_with_pagination(self):
        tamu = Tamu.objects.create(
            name='Tamu Debug',
            email='tamu.debug@example.com',
            phone='08123456700',
            account_status='active',
        )
        now = timezone.now()
        Kunjungan.objects.bulk_create([
            Kunjungan(
                tamu=tamu,
                arrival_time=now,
                purpose=f'Debug Pagination #{i}',
                status=Kunjungan.Status.MENUNGGU_ADMIN,
            )
            for i in range(5)
        ])

        with override_settings(DEBUG=True):
            self._reload_urlconfs()
            urls = [
                reverse('tamu:api_debug_counts'),
                reverse('tamu:api_debug_calendar_settings'),
            ]
            anon = Client()
            auth_admin = Client()
            auth_admin.force_login(self.admin_user)

            for url in urls:
                self.assertEqual(anon.get(url).status_code, 302)
                self.assertEqual(auth_admin.get(url).status_code, 200)

            paged = auth_admin.get(urls[0], {'page': '2', 'page_size': '2'})
            self.assertEqual(paged.status_code, 200)
            payload = paged.json()
            self.assertTrue(payload['success'])
            self.assertEqual(payload['count'], 5)
            self.assertEqual(len(payload['data']), 2)
            self.assertEqual(payload['pagination']['current_page'], 2)
            self.assertEqual(payload['pagination']['total_pages'], 3)
            self.assertTrue(payload['pagination']['has_next'])
            self.assertTrue(payload['pagination']['has_previous'])

            clamped = auth_admin.get(urls[0], {'page_size': '999999'})
            self.assertEqual(clamped.json()['pagination']['page_size'], 100)
