import json
from django.test import TransactionTestCase
from channels.testing import WebsocketCommunicator
from guest_book.consumers import ChatConsumer, NotificationConsumer


class MockScopeApp:
    """Helper ASGI wrapper untuk menyuntikkan scope session dan url_route pada consumer."""
    def __init__(self, consumer_cls, session_id=None, session_data=None):
        self.consumer_cls = consumer_cls
        self.session_id = session_id
        self.session_data = session_data or {}

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        if self.session_id:
            scope['url_route'] = {'kwargs': {'session_id': self.session_id}}
        scope['session'] = self.session_data
        consumer = self.consumer_cls()
        return await consumer(scope, receive, send)


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
        app = MockScopeApp(ChatConsumer, session_id='tamu_userB', session_data={'tamu_id': 'userA'})
        comm = WebsocketCommunicator(app, '/ws/chat/tamu_userB/')
        connected, code = await comm.connect()
        self.assertFalse(connected)
        self.assertEqual(code, 4003)
        await comm.disconnect()

    async def test_authenticated_admin_connection_accepted(self):
        """Memastikan admin terautentikasi dapat terhubung ke sesi chat."""
        app = MockScopeApp(ChatConsumer, session_id='tamu_userA', session_data={'is_admin': True})
        comm = WebsocketCommunicator(app, '/ws/chat/tamu_userA/')
        connected, code = await comm.connect()
        self.assertTrue(connected)
        self.assertIsNone(code)
        await comm.disconnect()

    async def test_authenticated_tamu_connection_accepted(self):
        """Memastikan tamu terautentikasi dapat terhubung ke sesi chat miliknya."""
        app = MockScopeApp(ChatConsumer, session_id='tamu_userA', session_data={'tamu_id': 'userA'})
        comm = WebsocketCommunicator(app, '/ws/chat/tamu_userA/')
        connected, code = await comm.connect()
        self.assertTrue(connected)
        self.assertIsNone(code)
        await comm.disconnect()

    async def test_chat_message_delivered_to_correct_recipients(self):
        """Memastikan pesan chat hanya terkirim ke partisipan di room yang sama."""
        # Dua user di room 'tamu_userA'
        admin_comm = WebsocketCommunicator(
            MockScopeApp(ChatConsumer, session_id='tamu_userA', session_data={'is_admin': True}),
            '/ws/chat/tamu_userA/'
        )
        tamu_comm = WebsocketCommunicator(
            MockScopeApp(ChatConsumer, session_id='tamu_userA', session_data={'tamu_id': 'userA'}),
            '/ws/chat/tamu_userA/'
        )
        # Satu user di room berbeda 'tamu_userB'
        other_comm = WebsocketCommunicator(
            MockScopeApp(ChatConsumer, session_id='tamu_userB', session_data={'tamu_id': 'userB'}),
            '/ws/chat/tamu_userB/'
        )

        a_conn, _ = await admin_comm.connect()
        t_conn, _ = await tamu_comm.connect()
        o_conn, _ = await other_comm.connect()
        self.assertTrue(a_conn and t_conn and o_conn)

        # Tamu mengirim pesan ke room 'tamu_userA'
        await tamu_comm.send_json_to({
            'action': 'create',
            'message': 'Halo Admin, saya butuh informasi.',
            'sender_id': 'userA',
            'sender_type': 'tamu'
        })

        # Partisipan di room 'tamu_userA' menerima pesan
        t_recv = await tamu_comm.receive_json_from()
        a_recv = await admin_comm.receive_json_from()
        self.assertEqual(t_recv['message'], 'Halo Admin, saya butuh informasi.')
        self.assertEqual(a_recv['message'], 'Halo Admin, saya butuh informasi.')

        # User di room 'tamu_userB' tidak boleh menerima pesan tersebut
        other_received_nothing = await other_comm.receive_nothing()
        self.assertTrue(other_received_nothing)

        await admin_comm.disconnect()
        await tamu_comm.disconnect()
        await other_comm.disconnect()

    async def test_chat_consumer_ping_pong(self):
        """Memastikan ChatConsumer merespons pesan ping dengan pong."""
        app = MockScopeApp(ChatConsumer, session_id='tamu_userA', session_data={'tamu_id': 'userA'})
        comm = WebsocketCommunicator(app, '/ws/chat/tamu_userA/')
        connected, _ = await comm.connect()
        self.assertTrue(connected)

        await comm.send_json_to({'action': 'ping'})
        response = await comm.receive_json_from()
        self.assertEqual(response.get('action'), 'pong')

        await comm.disconnect()

    async def test_notification_consumer_ping_pong(self):
        """Memastikan NotificationConsumer merespons pesan ping dengan pong."""
        app = MockScopeApp(NotificationConsumer, session_data={'tamu_id': 'userA'})
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

        app = MockScopeApp(ChatConsumer, session_id='tamu_userA', session_data={'tamu_id': 'userA'})
        comm = WebsocketCommunicator(app, '/ws/chat/tamu_userA/')
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
        self.assertEqual(recv['sender_id'], 'userA')
        self.assertEqual(recv['sender_type'], 'tamu')

        # Di database, pesan tersimpan sebagai tamu
        msg = await database_sync_to_async(
            ChatMessage.objects.filter(session_id='tamu_userA').order_by('-created_at').first
        )()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.sender_id, 'userA')
        self.assertEqual(msg.sender_type, 'tamu')

        await comm.disconnect()

    async def test_authenticated_admin_sends_as_admin(self):
        """Memastikan admin yang sah terautentikasi mengirim pesan sebagai admin."""
        app = MockScopeApp(ChatConsumer, session_id='tamu_userA', session_data={'is_admin': True})
        comm = WebsocketCommunicator(app, '/ws/chat/tamu_userA/')
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
        app = MockScopeApp(ChatConsumer, session_id='tamu_userA', session_data={'tamu_id': 'userA'})
        comm = WebsocketCommunicator(app, '/ws/chat/tamu_userA/')
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
        app = MockScopeApp(ChatConsumer, session_id='tamu_userA', session_data={'tamu_id': 'userA'})
        comm = WebsocketCommunicator(app, '/ws/chat/tamu_userA/')
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

        # Buat pesan asli milik admin di database
        admin_msg = await database_sync_to_async(ChatMessage.objects.create)(
            session_id='tamu_userA',
            sender_id='admin',
            sender_type='admin',
            content='Instruksi resmi admin.'
        )

        app = MockScopeApp(ChatConsumer, session_id='tamu_userA', session_data={'tamu_id': 'userA'})
        comm = WebsocketCommunicator(app, '/ws/chat/tamu_userA/')
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
