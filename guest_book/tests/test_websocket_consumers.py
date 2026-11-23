import json
from django.test import TransactionTestCase
from channels.testing import WebsocketCommunicator
from guest_book.consumers import ChatConsumer, NotificationConsumer


class MockScopeApp:
    """Helper ASGI wrapper untuk menyuntikkan scope user, session dan url_route pada consumer."""
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


async def _create_active_chat_actors():
    from channels.db import database_sync_to_async
    from django.contrib.auth.models import User
    from guest_book.models import Tamu

    admin_user = await database_sync_to_async(User.objects.create_user)(
        username='wsadmin',
        email='wsadmin@example.com',
        password='StrongWsAdmin!Password2026',
        is_staff=True,
    )
    tamu_a = await database_sync_to_async(Tamu.objects.create)(
        name='Tamu A',
        email='tamu.a.ws@example.com',
        phone='08120000111',
        account_status='active',
    )
    tamu_b = await database_sync_to_async(Tamu.objects.create)(
        name='Tamu B',
        email='tamu.b.ws@example.com',
        phone='08120000222',
        account_status='active',
    )
    return admin_user, tamu_a, tamu_b


class WebSocketConsumerTests(TransactionTestCase):
    """
    Test suite untuk WebSocket Consumer (Django Channels):
    1. Pengguna anonim ditolak (code 4003).
    2. Tamu yang tidak berhak mengakses ruang obrolan lain ditolak (code 4003).
    3. Admin terautentikasi diterima di sesi chat mana pun.
    4. Tamu terautentikasi diterima di sesi chat miliknya sendiri.
    5. Pesan chat hanya terkirim ke penerima di ruang yang benar (isolasi room group).
    6. Keep-alive ping/pong ditangani dengan benar tanpa error.
    """

    async def test_anonymous_connection_rejected(self):
        """Memastikan koneksi anonim (tanpa session) ditolak dengan close code 4003."""
        app = MockScopeApp(ChatConsumer, session_id='tamu_user99', session_data={})
        comm = WebsocketCommunicator(app, '/ws/chat/tamu_user99/')
        connected, code = await comm.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)
        await comm.disconnect()

    async def test_unauthorized_tamu_connection_rejected(self):
        """Memastikan Tamu A tidak dapat terhubung ke sesi chat Tamu B."""
        _, tamu_a, tamu_b = await _create_active_chat_actors()
        app = MockScopeApp(
            ChatConsumer,
            session_id=f'tamu_{tamu_b.id}',
            session_data={'tamu_id': str(tamu_a.id)},
        )
        comm = WebsocketCommunicator(app, f'/ws/chat/tamu_{tamu_b.id}/')
        connected, code = await comm.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)
        await comm.disconnect()

    async def test_authenticated_admin_connection_accepted(self):
        """Memastikan admin terautentikasi dapat terhubung ke sesi chat."""
        admin_user, tamu_a, _ = await _create_active_chat_actors()
        app = MockScopeApp(
            ChatConsumer,
            session_id=f'tamu_{tamu_a.id}',
            session_data={},
            user=admin_user,
        )
        comm = WebsocketCommunicator(app, f'/ws/chat/tamu_{tamu_a.id}/')
        connected, code = await comm.connect()
        self.assertTrue(connected)
        self.assertIsNone(code)
        await comm.disconnect()

    async def test_authenticated_tamu_connection_accepted(self):
        """Memastikan tamu terautentikasi dapat terhubung ke sesi chat miliknya."""
        _, tamu_a, _ = await _create_active_chat_actors()
        app = MockScopeApp(
            ChatConsumer,
            session_id=f'tamu_{tamu_a.id}',
            session_data={'tamu_id': str(tamu_a.id)},
        )
        comm = WebsocketCommunicator(app, f'/ws/chat/tamu_{tamu_a.id}/')
        connected, code = await comm.connect()
        self.assertTrue(connected)
        self.assertIsNone(code)
        await comm.disconnect()

    async def test_chat_message_delivered_to_correct_recipients(self):
        """Memastikan pesan chat hanya terkirim ke partisipan di room yang sama."""
        admin_user, tamu_a, tamu_b = await _create_active_chat_actors()
        room_a = f'tamu_{tamu_a.id}'
        room_b = f'tamu_{tamu_b.id}'
        admin_comm = WebsocketCommunicator(
            MockScopeApp(ChatConsumer, session_id=room_a, session_data={}, user=admin_user),
            f'/ws/chat/{room_a}/'
        )
        tamu_comm = WebsocketCommunicator(
            MockScopeApp(ChatConsumer, session_id=room_a, session_data={'tamu_id': str(tamu_a.id)}),
            f'/ws/chat/{room_a}/'
        )
        other_comm = WebsocketCommunicator(
            MockScopeApp(ChatConsumer, session_id=room_b, session_data={'tamu_id': str(tamu_b.id)}),
            f'/ws/chat/{room_b}/'
        )

        a_conn, _ = await admin_comm.connect()
        t_conn, _ = await tamu_comm.connect()
        o_conn, _ = await other_comm.connect()
        self.assertTrue(a_conn and t_conn and o_conn)

        # Tamu mengirim pesan ke room A
        await tamu_comm.send_json_to({
            'action': 'create',
            'message': 'Halo Admin, saya butuh informasi.',
            'sender_id': str(tamu_a.id),
            'sender_type': 'tamu'
        })

        # Partisipan di room A menerima pesan
        t_recv = await tamu_comm.receive_json_from()
        a_recv = await admin_comm.receive_json_from()
        self.assertEqual(t_recv['message'], 'Halo Admin, saya butuh informasi.')
        self.assertEqual(a_recv['message'], 'Halo Admin, saya butuh informasi.')

        # User di room B tidak boleh menerima pesan tersebut
        other_received_nothing = await other_comm.receive_nothing()
        self.assertTrue(other_received_nothing)

        await admin_comm.disconnect()
        await tamu_comm.disconnect()
        await other_comm.disconnect()

    async def test_chat_consumer_ping_pong(self):
        """Memastikan ChatConsumer merespons pesan ping dengan pong."""
        _, tamu_a, _ = await _create_active_chat_actors()
        app = MockScopeApp(ChatConsumer, session_id=f'tamu_{tamu_a.id}', session_data={'tamu_id': str(tamu_a.id)})
        comm = WebsocketCommunicator(app, f'/ws/chat/tamu_{tamu_a.id}/')
        connected, _ = await comm.connect()
        self.assertTrue(connected)

        await comm.send_json_to({'action': 'ping'})
        response = await comm.receive_json_from()
        self.assertEqual(response.get('action'), 'pong')

        await comm.disconnect()

    async def test_notification_consumer_ping_pong(self):
        """Memastikan NotificationConsumer merespons pesan ping dengan pong."""
        _, tamu_a, _ = await _create_active_chat_actors()
        app = MockScopeApp(NotificationConsumer, session_data={'tamu_id': str(tamu_a.id)})
        comm = WebsocketCommunicator(app, '/ws/notifications/')
        connected, _ = await comm.connect()
        self.assertTrue(connected)

        await comm.send_json_to({'action': 'ping'})
        response = await comm.receive_json_from()
        self.assertEqual(response.get('action'), 'pong')

        await comm.disconnect()

    async def test_tamu_impersonation_payload_forced_to_real_identity(self):
        """
        Memastikan jika klien Tamu mencoba mengirim payload sender_type='admin'
        dan sender_id='admin', server mengabaikannya dan tetap menyimpannya
        sebagai Tamu dengan ID aslinya.
        """
        from guest_book.models import ChatMessage
        from channels.db import database_sync_to_async

        _, tamu_a, _ = await _create_active_chat_actors()
        room_a = f'tamu_{tamu_a.id}'
        app = MockScopeApp(ChatConsumer, session_id=room_a, session_data={'tamu_id': str(tamu_a.id)})
        comm = WebsocketCommunicator(app, f'/ws/chat/{room_a}/')
        connected, _ = await comm.connect()
        self.assertTrue(connected)

        # Tamu mencoba berpura-pura menjadi admin lewat payload
        await comm.send_json_to({
            'action': 'create',
            'message': 'Pesan dipalsukan seolah dari admin',
            'sender_id': 'admin',
            'sender_type': 'admin'
        })

        recv = await comm.receive_json_from()
        # Broadcast harus tetap memuat identitas asli tamu
        self.assertEqual(recv['sender_id'], str(tamu_a.id))
        self.assertEqual(recv['sender_type'], 'tamu')

        # Di database, pesan tersimpan sebagai tamu
        msg = await database_sync_to_async(
            ChatMessage.objects.filter(session_id=room_a).order_by('-created_at').first
        )()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.sender_id, str(tamu_a.id))
        self.assertEqual(msg.sender_type, 'tamu')

        await comm.disconnect()

    async def test_authenticated_admin_sends_as_admin(self):
        """Memastikan admin yang sah terautentikasi mengirim pesan sebagai admin."""
        admin_user, tamu_a, _ = await _create_active_chat_actors()
        room_a = f'tamu_{tamu_a.id}'
        app = MockScopeApp(ChatConsumer, session_id=room_a, session_data={}, user=admin_user)
        comm = WebsocketCommunicator(app, f'/ws/chat/{room_a}/')
        connected, _ = await comm.connect()
        self.assertTrue(connected)

        await comm.send_json_to({
            'action': 'create',
            'message': 'Halo, ini balasan resmi dari Admin.'
        })

        recv = await comm.receive_json_from()
        self.assertEqual(recv['sender_id'], 'admin')
        self.assertEqual(recv['sender_type'], 'admin')

        await comm.disconnect()

    async def test_unknown_action_rejected(self):
        """Memastikan action di luar create/edit/delete ditolak tanpa membuat crash."""
        _, tamu_a, _ = await _create_active_chat_actors()
        room_a = f'tamu_{tamu_a.id}'
        app = MockScopeApp(ChatConsumer, session_id=room_a, session_data={'tamu_id': str(tamu_a.id)})
        comm = WebsocketCommunicator(app, f'/ws/chat/{room_a}/')
        connected, _ = await comm.connect()
        self.assertTrue(connected)

        await comm.send_json_to({
            'action': 'inject_exploit',
            'message': 'test'
        })

        recv = await comm.receive_json_from()
        self.assertEqual(recv.get('action'), 'error')
        self.assertIn('tidak dikenal', recv.get('message', ''))

        await comm.disconnect()

    async def test_message_validation_empty_and_too_long(self):
        """Memastikan pesan kosong dan pesan > 2000 karakter ditolak oleh server."""
        _, tamu_a, _ = await _create_active_chat_actors()
        room_a = f'tamu_{tamu_a.id}'
        app = MockScopeApp(ChatConsumer, session_id=room_a, session_data={'tamu_id': str(tamu_a.id)})
        comm = WebsocketCommunicator(app, f'/ws/chat/{room_a}/')
        connected, _ = await comm.connect()
        self.assertTrue(connected)

        # 1. Pesan kosong / whitespace
        await comm.send_json_to({
            'action': 'create',
            'message': '   '
        })
        err1 = await comm.receive_json_from()
        self.assertEqual(err1.get('action'), 'error')
        self.assertIn('tidak boleh kosong', err1.get('message', ''))

        # 2. Pesan terlalu panjang (> 2000 karakter)
        long_text = 'A' * 2005
        await comm.send_json_to({
            'action': 'create',
            'message': long_text
        })
        err2 = await comm.receive_json_from()
        self.assertEqual(err2.get('action'), 'error')
        self.assertIn('terlalu panjang', err2.get('message', ''))

        await comm.disconnect()

    async def test_tamu_cannot_edit_or_delete_other_user_message(self):
        """Memastikan Tamu tidak dapat mengedit atau menghapus pesan milik pihak lain (Admin/Pegawai)."""
        from guest_book.models import ChatMessage
        from channels.db import database_sync_to_async

        _, tamu_a, _ = await _create_active_chat_actors()
        room_a = f'tamu_{tamu_a.id}'

        # Buat pesan asli milik admin di database
        admin_msg = await database_sync_to_async(ChatMessage.objects.create)(
            session_id=room_a,
            sender_id='admin',
            sender_type='admin',
            content='Instruksi resmi admin.'
        )

        app = MockScopeApp(ChatConsumer, session_id=room_a, session_data={'tamu_id': str(tamu_a.id)})
        comm = WebsocketCommunicator(app, f'/ws/chat/{room_a}/')
        connected, _ = await comm.connect()
        self.assertTrue(connected)

        # 1. Coba edit pesan admin
        await comm.send_json_to({
            'action': 'edit',
            'message_id': str(admin_msg.id),
            'message': 'Teks diedit oleh tamu'
        })
        err_edit = await comm.receive_json_from()
        self.assertEqual(err_edit.get('action'), 'error')
        self.assertIn('tidak memiliki izin', err_edit.get('message', ''))

        # 2. Coba delete pesan admin
        await comm.send_json_to({
            'action': 'delete',
            'message_id': str(admin_msg.id)
        })
        err_del = await comm.receive_json_from()
        self.assertEqual(err_del.get('action'), 'error')
        self.assertIn('tidak memiliki izin', err_del.get('message', ''))

        # Pastikan konten di database tidak berubah
        fresh_msg = await database_sync_to_async(ChatMessage.objects.get)(id=admin_msg.id)
        self.assertEqual(fresh_msg.content, 'Instruksi resmi admin.')
        self.assertEqual(fresh_msg.message_type, 'text')

        await comm.disconnect()

    async def test_anonymous_notification_consumer_rejected(self):
        """Memastikan koneksi anonim ke NotificationConsumer ditolak dengan code 4003."""
        app = MockScopeApp(NotificationConsumer, session_data={})
        comm = WebsocketCommunicator(app, '/ws/notifications/')
        connected, code = await comm.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)
        await comm.disconnect()

    async def test_kunjungan_chat_notifies_pegawai_and_tamu_instead_of_admin(self):
        """
        Saat Tamu mengirim pesan di sesi kunjungan_{id}, notifikasi dikirim ke Pegawai (bukan Admin).
        Saat Pegawai mengirim pesan di sesi kunjungan_{id}, notifikasi dikirim ke Tamu (bukan Admin).
        """
        from channels.db import database_sync_to_async
        from django.utils import timezone
        from guest_book.models import Tamu, Pegawai, Kunjungan, KunjunganStatus, Notification

        tamu = await database_sync_to_async(Tamu.objects.create)(
            name='Tamu Chat Kunjungan',
            email='tamu.chat.kunjungan@example.com',
            phone='081234567890',
            account_status='active'
        )
        pegawai = await database_sync_to_async(Pegawai.objects.create)(
            name='Pegawai Chat Kunjungan',
            username='pegawai.chat',
            email='pegawai.chat@example.com',
            phone='081234567891',
            password='hashed_password',
            account_status='active'
        )
        kunjungan = await database_sync_to_async(Kunjungan.objects.create)(
            tamu=tamu,
            pegawai=pegawai,
            arrival_time=timezone.now(),
            purpose='Diskusi Teknis',
            status=KunjunganStatus.DISETUJUI
        )
        session_id = f'kunjungan_{kunjungan.id}'

        # 1. Tamu mengirim pesan -> Pegawai yang menerima notifikasi
        tamu_comm = WebsocketCommunicator(
            MockScopeApp(ChatConsumer, session_id=session_id, session_data={'tamu_id': str(tamu.id)}),
            f'/ws/chat/{session_id}/'
        )
        t_conn, _ = await tamu_comm.connect()
        self.assertTrue(t_conn)

        await tamu_comm.send_json_to({
            'action': 'create',
            'message': 'Selamat pagi Pak/Bu Pegawai.'
        })
        await tamu_comm.receive_json_from()

        pegawai_notif = await database_sync_to_async(
            Notification.objects.filter(
                recipient_id=str(pegawai.id),
                recipient_type='pegawai',
                related_object_id=session_id
            ).first
        )()
        self.assertIsNotNone(pegawai_notif)
        self.assertIn('Selamat pagi Pak/Bu Pegawai.', pegawai_notif.message)

        admin_notif_count = await database_sync_to_async(
            Notification.objects.filter(recipient_type='admin', related_object_id=session_id).count
        )()
        self.assertEqual(admin_notif_count, 0)
        await tamu_comm.disconnect()

        # 2. Pegawai mengirim pesan -> Tamu yang menerima notifikasi
        pegawai_comm = WebsocketCommunicator(
            MockScopeApp(ChatConsumer, session_id=session_id, session_data={'pegawai_id': str(pegawai.id)}),
            f'/ws/chat/{session_id}/'
        )
        p_conn, _ = await pegawai_comm.connect()
        self.assertTrue(p_conn)

        await pegawai_comm.send_json_to({
            'action': 'create',
            'message': 'Selamat pagi, silakan langsung ke lantai 2.'
        })
        await pegawai_comm.receive_json_from()

        tamu_notif = await database_sync_to_async(
            Notification.objects.filter(
                recipient_id=str(tamu.id),
                recipient_type='tamu',
                related_object_id=session_id
            ).first
        )()
        self.assertIsNotNone(tamu_notif)
        self.assertIn('lantai 2', tamu_notif.message)
        await pegawai_comm.disconnect()

    async def test_suspended_users_and_forged_session_flags_rejected_on_ws(self):
        """Akun suspended/inactive maupun session flag palsu wajib ditolak (4003) di kedua consumer."""
        from channels.db import database_sync_to_async
        from guest_book.models import Tamu, Pegawai

        suspended_tamu = await database_sync_to_async(Tamu.objects.create)(
            name='Suspended Tamu',
            email='suspended.ws@example.com',
            phone='08120000999',
            account_status='suspended',
        )
        inactive_pegawai = await database_sync_to_async(Pegawai.objects.create)(
            name='Inactive Pegawai',
            username='inactive.pegawai.ws',
            email='inactive.pegawai@example.com',
            phone='08120000998',
            password='hashed_password',
            account_status='inactive',
        )

        cases = [
            (ChatConsumer, f'/ws/chat/tamu_{suspended_tamu.id}/', f'tamu_{suspended_tamu.id}', {'tamu_id': str(suspended_tamu.id)}),
            (ChatConsumer, f'/ws/chat/pegawai_admin_{inactive_pegawai.id}/', f'pegawai_admin_{inactive_pegawai.id}', {'pegawai_id': str(inactive_pegawai.id)}),
            (ChatConsumer, '/ws/chat/tamu_fake/', 'tamu_fake', {'is_admin': True}),
            (ChatConsumer, '/ws/chat/tamu_fake/', 'tamu_fake', {'role': 'super_admin'}),
            (NotificationConsumer, '/ws/notifications/', None, {'tamu_id': str(suspended_tamu.id)}),
            (NotificationConsumer, '/ws/notifications/', None, {'pegawai_id': str(inactive_pegawai.id)}),
            (NotificationConsumer, '/ws/notifications/', None, {'is_admin': True}),
        ]
        for consumer_cls, path, sid, sess in cases:
            comm = WebsocketCommunicator(
                MockScopeApp(consumer_cls, session_id=sid, session_data=sess),
                path,
            )
            connected, code = await comm.connect()
            self.assertFalse(connected, f'Seharusnya ditolak untuk {path} sess={sess}')
            self.assertEqual(code, 4003)
            await comm.disconnect()

    async def test_ws_rejects_svg_and_ignores_client_spoofed_file_url(self):
        """ChatConsumer menolak .svg / path traversal dan mengabaikan file_url palsu kiriman klien."""
        _, tamu_a, _ = await _create_active_chat_actors()
        room = f'tamu_{tamu_a.id}'
        comm = WebsocketCommunicator(
            MockScopeApp(ChatConsumer, session_id=room, session_data={'tamu_id': str(tamu_a.id)}),
            f'/ws/chat/{room}/',
        )
        connected, _ = await comm.connect()
        self.assertTrue(connected)

        # 1. File .svg ditolak
        await comm.send_json_to({
            'action': 'create',
            'message': 'xss.svg',
            'message_type': 'image',
            'file_path': 'chat_attachments/xss.svg',
            'file_url': 'javascript:alert(1)',
        })
        err_svg = await comm.receive_json_from()
        self.assertEqual(err_svg.get('action'), 'error')

        # 2. Path di luar chat_attachments/ dengan file_url XSS ditolak
        await comm.send_json_to({
            'action': 'create',
            'message': 'evil.png',
            'message_type': 'image',
            'file_path': '../evil.png',
            'file_url': 'javascript:alert(document.cookie)',
        })
        err_path = await comm.receive_json_from()
        self.assertEqual(err_path.get('action'), 'error')

        # 3. Pesan text dengan file_url javascript: tidak boleh menyiarkan file_url
        await comm.send_json_to({
            'action': 'create',
            'message': 'Pesan teks biasa',
            'message_type': 'text',
            'file_url': 'javascript:alert(1)',
        })
        ok_msg = await comm.receive_json_from()
        self.assertIsNone(ok_msg.get('file_url'))

        # 4. Jika akun disuspend saat koneksi WebSocket masih terbuka, pengiriman pesan berikutnya langsung memutus koneksi (4003)
        from channels.db import database_sync_to_async
        tamu_a.account_status = 'suspended'
        await database_sync_to_async(tamu_a.save)(update_fields=['account_status'])
        await comm.send_json_to({
            'action': 'create',
            'message': 'Pesan setelah akun disuspend',
        })
        close_event = await comm.receive_output()
        self.assertEqual(close_event.get('type'), 'websocket.close')
        self.assertEqual(close_event.get('code'), 4003)

        await comm.disconnect()
