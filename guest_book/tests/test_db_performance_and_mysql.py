"""
Pengujian komprehensif untuk upgrade performa database, struktur ChatRoom,
pengamanan endpoint debug, dan dukungan test engine MySQL 8.0 / CI.
"""

import importlib
import os
import sys
from pathlib import Path
from unittest.mock import patch

from django.conf import settings as app_settings
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.db import connection
from django.test import Client, RequestFactory, SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from guest_book.context_processors import pegawai_notifications_context
from guest_book.models import (
    ChatMessage,
    ChatRoom,
    Departemen,
    Kunjungan,
    KunjunganStatus,
    Pegawai,
    Tamu,
)


class ChatRoomStructureAndCompositeIndexTests(TestCase):
    """Validasi model ChatRoom, index komposit, dan backfill idempoten."""

    def setUp(self):
        cache.clear()
        self.dept = Departemen.objects.create(nama='Bidang Infrastuktur', kode='INFRA')
        self.tamu = Tamu.objects.create(
            name='Tamu Terstruktur',
            email='tamu.room@example.com',
            phone='08123400001',
            instansi='Diskominfo Kota',
            account_status='active',
        )
        self.pegawai = Pegawai.objects.create(
            name='Pegawai Terstruktur',
            username='pegawai.room',
            email='pegawai.room@bekasikab.go.id',
            phone='08123400002',
            department_rel=self.dept,
            password=make_password('Pass12345!'),
            role='staff',
            account_status='active',
        )
        self.kunjungan = Kunjungan.objects.create(
            tamu=self.tamu,
            pegawai=self.pegawai,
            arrival_time=timezone.now(),
            purpose='Audit Keamanan',
            status=KunjunganStatus.DISETUJUI,
        )

    def test_chatmessage_has_composite_unread_and_room_indexes(self):
        index_map = {idx.name: tuple(idx.fields) for idx in ChatMessage._meta.indexes}
        self.assertEqual(index_map.get('idx_chat_session_created'), ('session_id', 'created_at'))
        self.assertEqual(index_map.get('idx_chat_sess_read_sender'), ('session_id', 'is_read', 'sender_type'))
        self.assertEqual(index_map.get('idx_chat_room_created'), ('room', 'created_at'))
        self.assertEqual(index_map.get('idx_chat_room_read_sender'), ('room', 'is_read', 'sender_type'))

    def test_chatmessage_auto_links_structured_chatroom_for_all_conventions(self):
        sid_tamu = ChatRoom.session_id_for_tamu(self.tamu.id)
        sid_peg_admin = ChatRoom.session_id_for_pegawai_admin(self.pegawai.id)
        sid_kunjungan = ChatRoom.session_id_for_kunjungan(self.kunjungan.id)

        msg_tamu = ChatMessage.objects.create(
            session_id=sid_tamu,
            sender_id=str(self.tamu.id),
            sender_type='tamu',
            content='Halo Admin',
        )
        msg_peg = ChatMessage.objects.create(
            session_id=sid_peg_admin,
            sender_id='admin',
            sender_type='admin',
            content='Halo Pegawai',
        )
        msg_kunj = ChatMessage.objects.create(
            session_id=sid_kunjungan,
            sender_id=str(self.tamu.id),
            sender_type='tamu',
            content='Sudah tiba di lobi',
        )
        msg_legacy = ChatMessage.objects.create(
            session_id=f'tamu_{self.tamu.id}',
            sender_id='admin',
            sender_type='admin',
            content='Sesi legacy prefiks tamu_',
        )

        self.assertEqual(msg_tamu.room.room_type, ChatRoom.RoomType.TAMU_ADMIN)
        self.assertEqual(msg_tamu.room.tamu_id, self.tamu.id)
        self.assertIsNotNone(msg_tamu.room.last_message_at)

        self.assertEqual(msg_peg.room.room_type, ChatRoom.RoomType.PEGAWAI_ADMIN)
        self.assertEqual(msg_peg.room.pegawai_id, self.pegawai.id)

        self.assertEqual(msg_kunj.room.room_type, ChatRoom.RoomType.KUNJUNGAN)
        self.assertEqual(msg_kunj.room.kunjungan_id, self.kunjungan.id)
        self.assertEqual(msg_kunj.room.tamu_id, self.tamu.id)
        self.assertEqual(msg_kunj.room.pegawai_id, self.pegawai.id)

        self.assertEqual(msg_legacy.room.room_type, ChatRoom.RoomType.TAMU_ADMIN)
        self.assertEqual(msg_legacy.room.tamu_id, self.tamu.id)

    def test_backfill_migration_helper_links_unlinked_messages_idempotently(self):
        from django.apps import apps
        from django.db import connections

        migration_mod = importlib.import_module(
            'guest_book.migrations.0023_chatroom_and_composite_indexes'
        )

        unlinked_sid = ChatRoom.session_id_for_kunjungan(self.kunjungan.id)
        ChatMessage.objects.bulk_create([
            ChatMessage(
                session_id=unlinked_sid,
                sender_id=str(self.tamu.id),
                sender_type='tamu',
                content='Bulk pesan 1',
                room=None,
            ),
            ChatMessage(
                session_id='custom_non_uuid_room',
                sender_id='tamu-x',
                sender_type='tamu',
                content='Bulk custom room',
                room=None,
            ),
        ])

        schema_editor = connections['default'].schema_editor()
        migration_mod.backfill_chat_rooms(apps, schema_editor)
        migration_mod.backfill_chat_rooms(apps, schema_editor)  # Idempoten

        kunj_room = ChatRoom.objects.get(session_id=unlinked_sid)
        self.assertEqual(kunj_room.kunjungan_id, self.kunjungan.id)
        self.assertEqual(kunj_room.tamu_id, self.tamu.id)
        self.assertEqual(kunj_room.pegawai_id, self.pegawai.id)
        self.assertFalse(ChatMessage.objects.filter(room__isnull=True).exists())


class PegawaiContextAndChatBatchQueryTests(TestCase):
    """Memastikan context processor & pegawai_chat_view tidak melakukan N+1 query per kunjungan."""

    def setUp(self):
        cache.clear()
        self.dept = Departemen.objects.create(nama='Bidang E-Gov', kode='EGOV')
        self.pegawai = Pegawai.objects.create(
            name='Pegawai Batch',
            username='pegawai.batch',
            email='pegawai.batch@bekasikab.go.id',
            phone='08123400010',
            department_rel=self.dept,
            password=make_password('Pass12345!'),
            role='staff',
            account_status='active',
        )
        self.tamu = Tamu.objects.create(
            name='Tamu Banyak Kunjungan',
            email='tamu.banyak@example.com',
            phone='08123400011',
            account_status='active',
        )

        admin_sid = ChatRoom.session_id_for_pegawai_admin(self.pegawai.id)
        ChatMessage.objects.create(
            session_id=admin_sid,
            sender_id='admin',
            sender_type='admin',
            content='Pesan admin belum dibaca',
            is_read=False,
        )

        self.visits = []
        for idx in range(6):
            k = Kunjungan.objects.create(
                tamu=self.tamu,
                pegawai=self.pegawai,
                arrival_time=timezone.now(),
                purpose=f'Koordinasi Proyek #{idx}',
                status=KunjunganStatus.DISETUJUI,
            )
            self.visits.append(k)
            ChatMessage.objects.create(
                session_id=ChatRoom.session_id_for_kunjungan(k.id),
                sender_id=str(self.tamu.id),
                sender_type='tamu',
                content=f'Halo dari kunjungan {idx}',
                is_read=(idx >= 2),  # 2 belum dibaca
            )
            ChatMessage.objects.create(
                session_id=ChatRoom.session_id_for_kunjungan(k.id),
                sender_id=str(self.pegawai.id),
                sender_type='pegawai',
                content=f'Balasan pegawai {idx}',
                is_read=False,  # Dikirim pegawai sendiri -> tidak dihitung unread pegawai
            )

    def test_pegawai_notifications_context_counts_unread_accurately(self):
        req = RequestFactory().get('/pegawai-portal/')
        req._pegawai = self.pegawai
        ctx = pegawai_notifications_context(req)
        # 1 dari admin + 2 dari kunjungan = 3
        self.assertEqual(ctx['pegawai_unread_chat_count'], 3)

    def test_pegawai_chat_view_avoids_n_plus_one_per_kunjungan(self):
        client = Client()
        sess = client.session
        sess['pegawai_id'] = str(self.pegawai.id)
        sess['pegawai_name'] = self.pegawai.name
        sess['pegawai_role'] = self.pegawai.role
        sess.save()

        chat_table = ChatMessage._meta.db_table
        with CaptureQueriesContext(connection) as ctx:
            resp = client.get(reverse('tamu:pegawai_chat'))

        self.assertEqual(resp.status_code, 200)
        chat_selects = [
            q['sql']
            for q in ctx.captured_queries
            if q['sql'].lstrip().upper().startswith('SELECT') and chat_table in q['sql']
        ]
        # Harusnya <= 5 query ke chat_message untuk 7 room (1 admin + 6 kunjungan), bukan >= 14 (N+1)
        self.assertLessEqual(
            len(chat_selects),
            5,
            f"Terdeteksi indikasi N+1 pada pegawai_chat_view: {len(chat_selects)} SELECT queries ke {chat_table}",
        )


class MySQLTestEngineAndCISupportTests(SimpleTestCase):
    """Validasi konfigurasi TEST_DB_ENGINE=mysql di settings.py & pipeline MySQL 8.0 di ci.yml."""

    def tearDown(self):
        import bukudigital.settings as project_settings

        importlib.reload(project_settings)
        super().tearDown()

    def test_settings_switches_to_mysql_test_db_when_env_configured(self):
        import bukudigital.settings as project_settings

        fake_argv = ['manage.py', 'test', 'guest_book']
        with patch.object(sys, 'argv', fake_argv), patch.dict(
            os.environ,
            {
                'APP_ENV': 'local',
                'TEST_DB_ENGINE': 'mysql',
                'DB_NAME': 'bukudigital',
                'TEST_DB_NAME': 'test_bukudigital_ci',
                'DB_HOST': 'mysql',
                'DB_PORT': '3306',
                'DB_USER': 'root',
                'DB_PASSWORD': 'ci_password',
                'DB_SSL_DISABLED': 'True',
            },
            clear=True,
        ):
            importlib.reload(project_settings)
            db_cfg = project_settings.DATABASES['default']
            self.assertEqual(db_cfg['ENGINE'], 'django.db.backends.mysql')
            self.assertEqual(db_cfg['HOST'], 'mysql')
            self.assertNotIn('ssl', db_cfg['OPTIONS'])
            self.assertEqual(db_cfg['TEST']['NAME'], 'test_bukudigital_ci')
            self.assertEqual(db_cfg['TEST']['CHARSET'], 'utf8mb4')
            self.assertEqual(db_cfg['TEST']['COLLATION'], 'utf8mb4_unicode_ci')

    def test_ci_workflow_runs_mysql8_migration_and_test_job(self):
        ci_path = Path(app_settings.BASE_DIR) / '.github' / 'workflows' / 'ci.yml'
        ci_text = ci_path.read_text(encoding='utf-8')
        self.assertIn('mysql-tests:', ci_text)
        self.assertIn('image: mysql:8.0', ci_text)
        self.assertIn('--collation-server=utf8mb4_unicode_ci', ci_text)
        self.assertIn("TEST_DB_ENGINE: 'mysql'", ci_text)
        self.assertIn('python manage.py migrate --noinput', ci_text)
