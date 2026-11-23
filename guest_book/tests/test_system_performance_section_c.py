import json
import re
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.conf import settings as app_settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from guest_book.models import (
    Admin,
    AuditLog,
    ChatMessage,
    ChatRoom,
    Departemen,
    Instansi,
    Kunjungan,
    Pegawai,
    Tamu,
)
from guest_book.views.base import record_audit_log


def _normalize_pkg(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name.strip()).lower()


class DeployScriptsAndLineEndingsTests(TestCase):
    """C-1: Konsistensi skrip deploy non-Docker dan normalisasi LF."""

    def test_deploy_scripts_use_lf_and_consistent_commands(self):
        base = Path(app_settings.BASE_DIR)

        for fname in ('build.sh', 'start.sh', 'Procfile'):
            raw = (base / fname).read_bytes()
            self.assertNotIn(b'\r', raw, f"{fname} masih mengandung akhiran CRLF (\\r).")

        build_sh = (base / 'build.sh').read_text(encoding='utf-8')
        self.assertIn('pip install --no-deps -r requirements.lock', build_sh)
        self.assertNotIn('pip install -r requirements.txt', build_sh)
        self.assertIn('python manage.py migrate --noinput', build_sh)
        self.assertIn('python manage.py createcachetable || true', build_sh)
        self.assertIn('python manage.py setup_admin || true', build_sh)

        start_sh = (base / 'start.sh').read_text(encoding='utf-8')
        self.assertIn('python manage.py migrate --noinput', start_sh)
        self.assertIn('python manage.py createcachetable || true', start_sh)
        self.assertIn('python manage.py setup_admin || true', start_sh)
        self.assertIn('exec daphne', start_sh)
        self.assertNotIn("admin_role='operator'", start_sh)
        self.assertNotIn('manage.py shell -c', start_sh)

        procfile = (base / 'Procfile').read_text(encoding='utf-8').strip()
        self.assertEqual(procfile, 'web: bash start.sh')


class DependencySyncTests(TestCase):
    """C-2: Sinkronisasi versi paket di requirements.txt & requirements.lock."""

    def _parse_pins(self, path: Path) -> dict[str, str]:
        pins = {}
        for line in path.read_text(encoding='utf-8').splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            name, ver = stripped.split('==', 1)
            pins[_normalize_pkg(name)] = ver
        return pins

    def test_requirements_and_lockfile_synced_to_patched_versions(self):
        base = Path(app_settings.BASE_DIR)
        req_pins = self._parse_pins(base / 'requirements.txt')
        lock_pins = self._parse_pins(base / 'requirements.lock')

        self.assertEqual(req_pins.get('django'), '6.0.8')
        self.assertEqual(req_pins.get('cryptography'), '50.0.1')
        self.assertEqual(req_pins.get('pillow'), '13.0.0')

        for pkg, version in req_pins.items():
            self.assertIn(pkg, lock_pins, f"Paket {pkg} tidak ditemukan di requirements.lock")
            self.assertEqual(
                lock_pins[pkg],
                version,
                f"Ketidakcocokan versi untuk {pkg}: requirements.txt={version} vs requirements.lock={lock_pins[pkg]}",
            )


class QueryPerformanceAndBoundsTests(TestCase):
    """C-3: Hilangkan N+1 query dan batasi jumlah baris pada halaman cetak & chat."""

    def setUp(self):
        cache.clear()
        self.client = Client()
        self.staff_user = User.objects.create_superuser(
            username='admin_perf',
            email='admin.perf@bekasikab.go.id',
            password='StrongPassword123!',
            first_name='Admin Perf',
        )
        self.admin_record = Admin.objects.create(
            name='Admin Perf',
            email='admin.perf@bekasikab.go.id',
            phone='081234567890',
            password=self.staff_user.password,
            account_status='active',
        )
        self.admin_tamu = Tamu.objects.create(
            name='Admin Perf',
            email='admin.perf@bekasikab.go.id',
            phone='081234567890',
            is_admin=True,
            admin_role='super_admin',
            account_status='active',
        )
        Instansi.objects.create(nama='Diskominfosantik Kab Bekasi')
        self.client.force_login(self.staff_user)

    def _create_audit_batch(self, count: int, prefix: str):
        for i in range(count):
            t = Tamu.objects.create(
                name=f'Tamu {prefix} {i}',
                email=f'tamu_{prefix}_{i}@example.com',
                phone=f'08120000{i:04d}',
                account_status='active',
            )
            p = Pegawai.objects.create(
                name=f'Pegawai {prefix} {i}',
                email=f'peg_{prefix}_{i}@bekasikab.go.id',
                phone=f'08130000{i:04d}',
                account_status='active',
            )
            AuditLog.objects.create(
                user_id=str(t.id),
                user_type='tamu',
                action='create',
                table_name='kunjungan',
                record_id=f'rec-t-{prefix}-{i}',
            )
            AuditLog.objects.create(
                user_id=str(p.id),
                user_type='pegawai',
                action='update',
                table_name='kunjungan',
                record_id=f'rec-p-{prefix}-{i}',
            )
        AuditLog.objects.create(
            user_id=str(self.staff_user.pk),
            user_type='admin',
            action='update',
            table_name='auth_user',
            record_id=str(self.staff_user.pk),
        )
        AuditLog.objects.create(
            user_id=str(self.admin_record.id),
            user_type='admin',
            action='delete',
            table_name='departemen',
            record_id='dep-1',
        )

    def test_audit_log_view_and_pdf_have_no_n_plus_1_and_respect_limits(self):
        # Warm up cache for get_admin_context
        self._create_audit_batch(2, 'small')
        self.client.get(reverse('tamu:admin_audit_log'))

        with CaptureQueriesContext(connection) as q_small:
            resp_small = self.client.get(reverse('tamu:admin_audit_log'))
        self.assertEqual(resp_small.status_code, 200)

        with CaptureQueriesContext(connection) as q_pdf_small:
            resp_pdf_small = self.client.get(reverse('tamu:admin_audit_log_cetak_pdf'))
        self.assertEqual(resp_pdf_small.status_code, 200)

        # Tambah banyak log dari entitas berbeda: jumlah query tidak boleh naik linear (N+1)
        self._create_audit_batch(8, 'large')

        with CaptureQueriesContext(connection) as q_large:
            resp_large = self.client.get(reverse('tamu:admin_audit_log'))
        self.assertEqual(resp_large.status_code, 200)
        self.assertEqual(
            len(q_small),
            len(q_large),
            f"Terdeteksi N+1 pada admin_audit_log_view: small={len(q_small)}, large={len(q_large)}",
        )

        with CaptureQueriesContext(connection) as q_pdf_large:
            resp_pdf_large = self.client.get(reverse('tamu:admin_audit_log_cetak_pdf'))
        self.assertEqual(resp_pdf_large.status_code, 200)
        self.assertEqual(
            len(q_pdf_small),
            len(q_pdf_large),
            f"Terdeteksi N+1 pada admin_audit_log_cetak_pdf: small={len(q_pdf_small)}, large={len(q_pdf_large)}",
        )

        resolved_names = {log.user_name for log in resp_pdf_large.context['logs_all']}
        self.assertIn('Tamu large 0', resolved_names)
        self.assertIn('Pegawai large 0', resolved_names)
        self.assertIn('Admin Perf', resolved_names)

        # Uji filter & clamp limit cetak PDF audit log
        resp_limited = self.client.get(reverse('tamu:admin_audit_log_cetak_pdf') + '?action=create&limit=3')
        self.assertEqual(resp_limited.status_code, 200)
        self.assertEqual(len(resp_limited.context['logs_all']), 3)
        self.assertTrue(all(log.action == 'create' for log in resp_limited.context['logs_all']))

        resp_clamped = self.client.get(reverse('tamu:admin_audit_log_cetak_pdf') + '?limit=99999')
        self.assertEqual(resp_clamped.status_code, 200)
        self.assertEqual(resp_clamped.context['print_limit'], 1000)

    def test_kunjungan_cetak_pdf_uses_select_related_and_clamps_limit(self):
        def _add_visits(count: int, tag: str):
            for i in range(count):
                dept = Departemen.objects.create(nama=f'Bidang {tag} {i}', kode=f'B{tag[:2]}{i}')
                peg = Pegawai.objects.create(
                    name=f'Pegawai Kunjungan {tag} {i}',
                    email=f'pk_{tag}_{i}@bekasikab.go.id',
                    phone=f'08140000{i:04d}',
                    department_rel=dept,
                    account_status='active',
                )
                tamu = Tamu.objects.create(
                    name=f'Tamu Kunjungan {tag} {i}',
                    email=f'tk_{tag}_{i}@example.com',
                    phone=f'08150000{i:04d}',
                    instansi=f'Instansi {tag} {i}',
                    account_status='active',
                )
                Kunjungan.objects.create(
                    tamu=tamu,
                    pegawai=peg,
                    purpose=f'Koordinasi {tag} {i}',
                    status='completed' if i % 2 == 0 else 'disetujui',
                    arrival_time=timezone.now() - timedelta(hours=i),
                )

        _add_visits(2, 's')
        # Warm up cached admin context
        self.client.get(reverse('tamu:admin_kunjungan_cetak_pdf'))

        with CaptureQueriesContext(connection) as q_small:
            r_small = self.client.get(reverse('tamu:admin_kunjungan_cetak_pdf'))
        self.assertEqual(r_small.status_code, 200)

        _add_visits(8, 'l')
        with CaptureQueriesContext(connection) as q_large:
            r_large = self.client.get(reverse('tamu:admin_kunjungan_cetak_pdf'))
        self.assertEqual(r_large.status_code, 200)
        self.assertEqual(
            len(q_small),
            len(q_large),
            f"Terdeteksi N+1 pada admin_kunjungan_cetak_pdf: small={len(q_small)}, large={len(q_large)}",
        )
        self.assertContains(r_large, 'Bidang l 0')

        # Uji filter status & limit
        r_filtered = self.client.get(reverse('tamu:admin_kunjungan_cetak_pdf') + '?status=completed&limit=2')
        self.assertEqual(r_filtered.status_code, 200)
        self.assertEqual(len(r_filtered.context['kunjungan_all']), 2)
        self.assertTrue(all(k.status == 'completed' for k in r_filtered.context['kunjungan_all']))

        r_clamped = self.client.get(reverse('tamu:admin_kunjungan_cetak_pdf') + '?limit=50000')
        self.assertEqual(r_clamped.status_code, 200)
        self.assertEqual(r_clamped.context['print_limit'], 1000)

    def test_pegawai_chat_view_bounds_messages_to_latest_50_in_chronological_order(self):
        pegawai = Pegawai.objects.create(
            name='Pegawai Chat Limit',
            email='pegawai.chatlimit@bekasikab.go.id',
            phone='081233334444',
            account_status='active',
            must_change_password=False,
        )

        session_id = ChatRoom.session_id_for_pegawai_admin(pegawai.id)
        room = ChatRoom.resolve_or_create_for_session(session_id)
        base_time = timezone.now() - timedelta(minutes=100)
        objs = []
        for idx in range(1, 66):
            objs.append(
                ChatMessage(
                    room=room,
                    session_id=session_id,
                    sender_type='admin',
                    sender_id='admin',
                    content=f'Pesan ke-{idx}',
                )
            )
        created = ChatMessage.objects.bulk_create(objs)
        for idx, msg in enumerate(created, start=1):
            ChatMessage.objects.filter(pk=msg.pk).update(created_at=base_time + timedelta(minutes=idx))

        pegawai_client = Client()
        sess = pegawai_client.session
        sess['pegawai_id'] = str(pegawai.id)
        sess.save()

        resp = pegawai_client.get(reverse('tamu:pegawai_chat') + f'?session={session_id}')
        self.assertEqual(resp.status_code, 200)
        msgs = resp.context['messages_list']
        self.assertEqual(len(msgs), 50)
        self.assertEqual(msgs[0].content, 'Pesan ke-16')
        self.assertEqual(msgs[-1].content, 'Pesan ke-65')


class AdminNotificationPreferencesDBTests(TestCase):
    """C-4: Preferensi notifikasi admin disimpan di database (Admin model), bukan disk."""

    def setUp(self):
        cache.clear()
        self.user_a = User.objects.create_superuser(
            username='admin_a',
            email='admin.a@bekasikab.go.id',
            password='StrongPassword123!',
            first_name='Admin A',
        )
        self.user_b = User.objects.create_superuser(
            username='admin_b',
            email='admin.b@bekasikab.go.id',
            password='StrongPassword123!',
            first_name='Admin B',
        )
        self.admin_a = Admin.objects.create(
            name='Admin A',
            email='admin.a@bekasikab.go.id',
            phone='081211112222',
            password=self.user_a.password,
            account_status='active',
        )
        self.admin_b = Admin.objects.create(
            name='Admin B',
            email='admin.b@bekasikab.go.id',
            phone='081233334444',
            password=self.user_b.password,
            account_status='active',
        )

    def test_notification_preferences_persisted_per_admin_in_db_not_disk(self):
        pref_file = Path(app_settings.BASE_DIR) / 'guest_book' / 'admin_preferences.json'
        self.assertFalse(pref_file.exists())

        client_a = Client()
        client_a.force_login(self.user_a)

        resp = client_a.post(
            reverse('tamu:api_update_notification_settings'),
            data=json.dumps({'email_notif': False, 'push_notif': True}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body['success'])
        self.assertFalse(body['email_notif_enabled'])
        self.assertTrue(body['push_notif_enabled'])
        self.assertFalse(pref_file.exists(), "admin_preferences.json tidak boleh dibuat lagi di disk.")

        self.admin_a.refresh_from_db()
        self.admin_b.refresh_from_db()
        self.assertFalse(self.admin_a.email_notif_enabled)
        self.assertTrue(self.admin_a.push_notif_enabled)
        # Admin B tetap pada nilai defaultnya (isolasi antar akun)
        self.assertTrue(self.admin_b.email_notif_enabled)
        self.assertFalse(self.admin_b.push_notif_enabled)

        # Profil admin A membaca dari DB
        prof_a = client_a.get(reverse('tamu:admin_profil'))
        self.assertEqual(prof_a.status_code, 200)
        self.assertFalse(prof_a.context['email_notif_enabled'])
        self.assertTrue(prof_a.context['push_notif_enabled'])

        # Profil admin B tetap membaca nilai milik admin B
        client_b = Client()
        client_b.force_login(self.user_b)
        prof_b = client_b.get(reverse('tamu:admin_profil'))
        self.assertEqual(prof_b.status_code, 200)
        self.assertTrue(prof_b.context['email_notif_enabled'])
        self.assertFalse(prof_b.context['push_notif_enabled'])

        # Payload non-boolean ditolak
        bad_resp = client_a.post(
            reverse('tamu:api_update_notification_settings'),
            data=json.dumps({'email_notif': 'yes'}),
            content_type='application/json',
        )
        self.assertEqual(bad_resp.status_code, 400)


class CodeHygieneTests(TestCase):
    """C-5: record_audit_log memakai logger.error dan tidak ada file uji sisa."""

    def test_record_audit_log_uses_logger_error_not_print(self):
        base_py = (Path(app_settings.BASE_DIR) / 'guest_book' / 'views' / 'base.py').read_text(encoding='utf-8')
        self.assertNotIn('print(f"Error recording audit log', base_py)

        with patch('guest_book.models.AuditLog.objects.create', side_effect=RuntimeError('DB failure')), \
             patch('guest_book.views.base.logger.error') as mock_log_error:
            record_audit_log('1', 'admin', 'update', 'tamu', 'rec-1')
            mock_log_error.assert_called_once()

    def test_stray_files_removed(self):
        base = Path(app_settings.BASE_DIR)
        self.assertFalse((base / 'test.html').exists())
        self.assertFalse((base / 'guest_book' / 'admin_preferences.json').exists())
