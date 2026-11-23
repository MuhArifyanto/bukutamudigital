import io
import json
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from django.conf import settings as app_settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from ..middleware import ADMIN_LAST_ACTIVITY_SESSION_KEY
from ..models import CalendarSettings, Kunjungan, Tamu
from ..utils import build_n8n_chat_response, call_n8n_routing
from .base import BaseSecurityTestCase


def _make_valid_png_bytes():
    # Minimal 1x1 PNG valid header + chunks
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (2, 2), color=(10, 20, 30)).save(buf, format='PNG')
    return buf.getvalue()


def _make_valid_xlsx_bytes(headers, rows):
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class SectionBMediumSecurityFixesTests(BaseSecurityTestCase):
    """Pengujian regresi komprehensif untuk seluruh 7 temuan keamanan Bagian B."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.operator_user = User.objects.create_user(
            username='op_sec_b',
            email='operator.b@bekasikab.go.id',
            password='OperatorPass@2026!',
            is_staff=True,
            is_superuser=False,
        )
        self.operator_tamu = Tamu.objects.create(
            name='Operator B',
            email='operator.b@bekasikab.go.id',
            phone='081200008888',
            password=None,
            is_admin=True,
            admin_role='operator',
            account_status='active',
        )

    def tearDown(self):
        cache.clear()
        super().tearDown()

    # ── B-1: Isolasi Profil Admin (Anti Fallback Lintas Akun) ─────────────────

    def test_b1_admin_profile_update_does_not_overwrite_other_admin(self):
        op_client = Client()
        op_client.force_login(self.operator_user)

        original_primary_name = self.admin_tamu.name
        original_primary_email = self.admin_tamu.email

        resp = op_client.post(
            reverse('tamu:api_update_profile_data'),
            data=json.dumps({
                'name': 'Operator B Updated',
                'email': 'operator.b@bekasikab.go.id',
                'nip': '199001012020011099',
                'jabatan': 'Petugas Loket',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

        self.operator_tamu.refresh_from_db()
        self.admin_tamu.refresh_from_db()
        self.assertEqual(self.operator_tamu.name, 'Operator B Updated')
        self.assertEqual(self.operator_tamu.jabatan, 'Petugas Loket')
        # Profil primary super_admin tidak boleh tersentuh
        self.assertEqual(self.admin_tamu.name, original_primary_name)
        self.assertEqual(self.admin_tamu.email, original_primary_email)

        # Mengubah email ke email milik admin lain harus ditolak 409
        conflict = op_client.post(
            reverse('tamu:api_update_profile_data'),
            data=json.dumps({
                'name': 'Operator Conflict',
                'email': self.admin_tamu.email,
            }),
            content_type='application/json',
        )
        self.assertEqual(conflict.status_code, 409)

    def test_b1_admin_profile_picture_updates_only_own_record(self):
        temp_media = tempfile.mkdtemp()
        try:
            with override_settings(MEDIA_ROOT=temp_media):
                op_client = Client()
                op_client.force_login(self.operator_user)
                png = SimpleUploadedFile('op.png', _make_valid_png_bytes(), content_type='image/png')

                resp = op_client.post(
                    reverse('tamu:api_update_profile_picture'),
                    {'profile_picture': png},
                )
                self.assertEqual(resp.status_code, 200)
                self.operator_tamu.refresh_from_db()
                self.admin_tamu.refresh_from_db()
                self.assertTrue(bool(self.operator_tamu.profile_picture))
                self.assertFalse(bool(self.admin_tamu.profile_picture))
        finally:
            shutil.rmtree(temp_media, ignore_errors=True)

    # ── B-2: Validasi Nomor Telepon & Input Profil / Manual Create ────────────

    def test_b2_tamu_profile_update_validates_phone_and_truncates_instansi(self):
        tamu_client = self.get_client('tamu_a')
        url = reverse('tamu:api_tamu_update_profile_data')

        bad_resp = tamu_client.post(
            url,
            data=json.dumps({'phone': '<img src=x onerror=1>', 'instansi': 'PT Valid'}),
            content_type='application/json',
        )
        self.assertEqual(bad_resp.status_code, 400)
        self.tamu_a.refresh_from_db()
        self.assertNotIn('<img', self.tamu_a.phone)

        ok_resp = tamu_client.post(
            url,
            data=json.dumps({'phone': '+62 812-3456-7890', 'instansi': 'A' * 300}),
            content_type='application/json',
        )
        self.assertEqual(ok_resp.status_code, 200)
        self.tamu_a.refresh_from_db()
        self.assertEqual(self.tamu_a.phone, '+62 812-3456-7890')
        self.assertEqual(len(self.tamu_a.instansi), 255)

    def test_b2_manual_create_rejects_invalid_phone_empty_name_and_bad_nik(self):
        admin_client = self.get_client('admin')
        url = reverse('tamu:admin_kunjungan_manual_create')
        before_count = Kunjungan.objects.count()

        # Telepon XSS ditolak
        admin_client.post(url, {
            'name': 'Tamu Valid',
            'phone': '<script>alert(1)</script>',
            'purpose': 'Koordinasi',
        })
        self.assertEqual(Kunjungan.objects.count(), before_count)

        # Nama terlalu pendek / tujuan kosong ditolak
        admin_client.post(url, {'name': 'A', 'phone': '081234567890', 'purpose': 'Koordinasi'})
        admin_client.post(url, {'name': 'Tamu Valid', 'phone': '081234567890', 'purpose': '   '})
        self.assertEqual(Kunjungan.objects.count(), before_count)

        # NIK bukan 16 digit ditolak
        admin_client.post(url, {'name': 'Tamu Valid', 'nik': '12345', 'phone': '081234567890', 'purpose': 'Koordinasi'})
        self.assertEqual(Kunjungan.objects.count(), before_count)

    # ── B-3: Hardening Kuota & Impor CSV/Excel ────────────────────────────────

    def test_b3_api_update_quota_enforces_valid_bounds(self):
        admin_client = self.get_client('admin')
        url = reverse('tamu:api_update_quota')

        for bad_quota in (-1, 5001, True, 'bukan_angka'):
            r = admin_client.post(
                url,
                data=json.dumps({'date': '2026-12-10', 'quota': bad_quota}),
                content_type='application/json',
            )
            self.assertEqual(r.status_code, 400, msg=f"Kuota tidak valid seharusnya ditolak: {bad_quota!r}")

        ok = admin_client.post(
            url,
            data=json.dumps({'date': '2026-12-10', 'quota': 120}),
            content_type='application/json',
        )
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(CalendarSettings.objects.get(date='2026-12-10').daily_quota, 120)

    def test_b3_import_calendar_and_visits_validate_magic_bytes_limits_and_no_name_collision(self):
        admin_client = self.get_client('admin')
        cal_url = reverse('tamu:api_import_calendar_csv')
        visit_url = reverse('tamu:api_import_visits_excel')

        # 1. Spoofed .xlsx (bukan ZIP/OOXML) ditolak di kedua endpoint impor
        spoof_xlsx = SimpleUploadedFile('fake.xlsx', b'not an excel file', content_type='application/vnd.ms-excel')
        self.assertEqual(admin_client.post(cal_url, {'file': spoof_xlsx}).status_code, 400)
        spoof_xlsx2 = SimpleUploadedFile('fake2.xlsx', b'not an excel file', content_type='application/vnd.ms-excel')
        self.assertEqual(admin_client.post(visit_url, {'file': spoof_xlsx2}).status_code, 400)

        # 2. CSV biner & CSV > 500 baris ditolak di api_import_calendar_csv
        bin_csv = SimpleUploadedFile('bin.csv', b'tanggal,kuota\n\x00\x01\x02', content_type='text/csv')
        self.assertEqual(admin_client.post(cal_url, {'file': bin_csv}).status_code, 400)

        big_csv_rows = ['tanggal,kuota,libur'] + [f'2027-01-01,50,tidak' for _ in range(505)]
        big_csv = SimpleUploadedFile('big.csv', '\n'.join(big_csv_rows).encode('utf-8'), content_type='text/csv')
        self.assertEqual(admin_client.post(cal_url, {'file': big_csv}).status_code, 400)

        # 3. Impor kunjungan valid dengan 2 baris bernama sama dengan self.tamu_a.name
        #    TIDAK boleh menimpa/menggabungkan ke self.tamu_a bila NIK/email tidak cocok
        existing_visits_a = Kunjungan.objects.filter(tamu=self.tamu_a).count()
        xlsx_bytes = _make_valid_xlsx_bytes(
            ['Tanggal', 'Nama Tamu', 'Instansi', 'Keperluan', 'Jam'],
            [
                ['2026-12-15', self.tamu_a.name, 'Instansi X', 'Urusan X', '09:00'],
                ['2026-12-15', self.tamu_a.name, 'Instansi Y', 'Urusan Y', '10:00'],
            ],
        )
        ok_xlsx = SimpleUploadedFile(
            'kunjungan.xlsx',
            xlsx_bytes,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        res_imp = admin_client.post(visit_url, {'file': ok_xlsx})
        self.assertEqual(res_imp.status_code, 200)
        self.assertEqual(Kunjungan.objects.filter(tamu=self.tamu_a).count(), existing_visits_a)
        imported_tamus = Tamu.objects.filter(email__startswith='import_', name=self.tamu_a.name)
        self.assertEqual(imported_tamus.count(), 2)
        for t in imported_tamus:
            self.assertTrue(t.password.startswith('!'))

    # ── B-4: Endpoint Publik /api/holidays/<year>/ ────────────────────────────

    def test_b4_api_google_holidays_validates_year_bounds_and_rate_limit(self):
        client = Client()
        for bad_year in (1999, 2101, 999999):
            r = client.get(reverse('tamu:api_google_holidays', kwargs={'year': bad_year}))
            self.assertEqual(r.status_code, 400)

        with patch('guest_book.utils.get_google_calendar_holidays', return_value=[{'date': '2026-01-01', 'name': 'Tahun Baru'}]):
            for _ in range(30):
                ok = client.get(
                    reverse('tamu:api_google_holidays', kwargs={'year': 2026}),
                    REMOTE_ADDR='198.51.100.91',
                )
                self.assertEqual(ok.status_code, 200)
            blocked = client.get(
                reverse('tamu:api_google_holidays', kwargs={'year': 2026}),
                REMOTE_ADDR='198.51.100.91',
            )
            self.assertEqual(blocked.status_code, 429)

    # ── B-5: Rate Limit Upload Chat & Foto Profil ─────────────────────────────

    def test_b5_upload_rate_limits_for_chat_and_tamu_avatar(self):
        temp_media = tempfile.mkdtemp()
        try:
            with override_settings(MEDIA_ROOT=temp_media):
                png_bytes = _make_valid_png_bytes()

                # Chat upload: batas 15x -> ke-16 ditolak 429
                tamu_client = self.get_client('tamu_a')
                chat_url = reverse('tamu:api_upload_chat_file')
                for idx in range(15):
                    r = tamu_client.post(
                        chat_url,
                        {'file': SimpleUploadedFile(f'c{idx}.png', png_bytes, content_type='image/png')},
                        REMOTE_ADDR='198.51.100.92',
                    )
                    self.assertEqual(r.status_code, 200)
                r_block = tamu_client.post(
                    chat_url,
                    {'file': SimpleUploadedFile('c16.png', png_bytes, content_type='image/png')},
                    REMOTE_ADDR='198.51.100.92',
                )
                self.assertEqual(r_block.status_code, 429)

                # Tamu avatar upload: batas 10x -> ke-11 ditolak 429
                avatar_url = reverse('tamu:api_tamu_update_profile_picture')
                for idx in range(10):
                    r = tamu_client.post(
                        avatar_url,
                        {'profile_picture': SimpleUploadedFile(f'a{idx}.png', png_bytes, content_type='image/png')},
                        REMOTE_ADDR='198.51.100.93',
                    )
                    self.assertEqual(r.status_code, 200)
                r_av_block = tamu_client.post(
                    avatar_url,
                    {'profile_picture': SimpleUploadedFile('a11.png', png_bytes, content_type='image/png')},
                    REMOTE_ADDR='198.51.100.93',
                )
                self.assertEqual(r_av_block.status_code, 429)
        finally:
            shutil.rmtree(temp_media, ignore_errors=True)

    # ── B-6: n8n X-Webhook-Secret & Rate Limit Chatbot AI ─────────────────────

    @override_settings(N8N_WEBHOOK_SECRET='secret-n8n-token-2026', AI_CHAT_RATE_LIMIT_MAX=2, AI_CHAT_RATE_LIMIT_WINDOW=300)
    def test_b6_n8n_sends_secret_header_rejects_bad_scheme_and_rate_limits_ai(self):
        fake_resp = MagicMock()
        fake_resp.status = 200
        fake_resp.read.return_value = b'{"intent": "sapaan", "reply": "Halo!"}'
        fake_resp.__enter__.return_value = fake_resp
        fake_resp.__exit__.return_value = False

        # 1. call_n8n_routing menyertakan header X-Webhook-Secret
        with patch.dict(os.environ, {'N8N_WEBHOOK_URL': 'https://n8n.example.go.id/webhook/route'}), \
                patch('urllib.request.urlopen', return_value=fake_resp) as mock_open:
            res = call_n8n_routing('kunj-1', 'Konsultasi', 'Bidang TIK', timezone.now())
            self.assertIsNotNone(res)
            req_obj = mock_open.call_args[0][0]
            self.assertEqual(req_obj.get_header('X-webhook-secret'), 'secret-n8n-token-2026')

        # 2. Skema URL non-HTTP (file://) ditolak tanpa memanggil urlopen
        with patch.dict(os.environ, {'N8N_WEBHOOK_URL': 'file:///etc/passwd'}), \
                patch('urllib.request.urlopen') as mock_open:
            self.assertIsNone(call_n8n_routing('kunj-2', 'Test'))
            mock_open.assert_not_called()

        # 3. build_n8n_chat_response mengirim X-Webhook-Secret & menegakkan rate limit AI per sesi
        sess_id = f'tamu_{self.tamu_a.pk}'
        with patch.dict(os.environ, {'N8N_WEBHOOK_URL': '', 'N8N_CHAT_WEBHOOK_URL': 'https://n8n.example.go.id/webhook/chat'}), \
                patch('urllib.request.urlopen', return_value=fake_resp) as mock_chat_open:
            r1 = build_n8n_chat_response(str(self.tamu_a.pk), 'Halo', session_id=sess_id)
            self.assertNotEqual(r1['intent'], 'rate_limited')
            chat_req = mock_chat_open.call_args[0][0]
            self.assertEqual(chat_req.get_header('X-webhook-secret'), 'secret-n8n-token-2026')

            r2 = build_n8n_chat_response(str(self.tamu_a.pk), 'Halo lagi', session_id=sess_id)
            self.assertNotEqual(r2['intent'], 'rate_limited')

            # Ke-3 melebihi batas 2 -> langsung rate_limited tanpa memanggil webhook
            calls_before = mock_chat_open.call_count
            r3 = build_n8n_chat_response(str(self.tamu_a.pk), 'Spam pesan', session_id=sess_id)
            self.assertEqual(r3['intent'], 'rate_limited')
            self.assertEqual(mock_chat_open.call_count, calls_before)

    # ── B-7: Zero |safe di Template & Idle Timeout Sesi Admin ─────────────────

    def test_b7_no_safe_filter_in_templates_and_admin_ikm_uses_json_script(self):
        templates_root = Path(app_settings.BASE_DIR) / 'guest_book' / 'templates'
        found_safe = []
        for p in sorted(templates_root.rglob('*.html')):
            text = p.read_text(encoding='utf-8', errors='replace')
            if '|safe' in text:
                found_safe.append(str(p.relative_to(templates_root)))
        self.assertEqual(found_safe, [], f"Filter |safe masih ditemukan di: {found_safe}")

        ikm_html = (templates_root / 'guest_book' / 'admin_ikm.html').read_text(encoding='utf-8')
        self.assertIn('|json_script:"ikm-chart-labels"', ikm_html)
        self.assertIn('|json_script:"ikm-chart-ratings"', ikm_html)

    @override_settings(ADMIN_SESSION_IDLE_TIMEOUT=600)
    def test_b7_admin_idle_timeout_expires_stale_session_and_ignores_passive_poll(self):
        admin_client = self.get_client('admin')

        # 1. Sesi segar diizinkan dan mencatat timestamp pada halaman HTML admin
        ok_resp = admin_client.get(reverse('tamu:admin_dashboard'))
        self.assertEqual(ok_resp.status_code, 200)
        self.assertIsNotNone(admin_client.session.get(ADMIN_LAST_ACTIVITY_SESSION_KEY))

        # 2. Polling pasif (/api/admin/unread-count/) tidak memperpanjang timestamp
        old_but_valid_ts = int(time.time()) - 300
        s = admin_client.session
        s[ADMIN_LAST_ACTIVITY_SESSION_KEY] = old_but_valid_ts
        s.save()
        poll_resp = admin_client.get(reverse('tamu:api_get_unread_count'))
        self.assertEqual(poll_resp.status_code, 200)
        self.assertEqual(admin_client.session.get(ADMIN_LAST_ACTIVITY_SESSION_KEY), old_but_valid_ts)

        # 3. Sesi yang sudah melewati idle timeout (601 detik) ditolak 401 di API
        s = admin_client.session
        s[ADMIN_LAST_ACTIVITY_SESSION_KEY] = int(time.time()) - 650
        s.save()
        api_expired = admin_client.get(reverse('tamu:api_dashboard_stats'))
        self.assertEqual(api_expired.status_code, 401)
        self.assertNotIn('_auth_user_id', admin_client.session)

        # 4. Sesi kedaluwarsa di halaman HTML admin di-redirect ke admin_login
        admin_client2 = self.get_client('admin')
        s2 = admin_client2.session
        s2[ADMIN_LAST_ACTIVITY_SESSION_KEY] = int(time.time()) - 650
        s2.save()
        html_expired = admin_client2.get(reverse('tamu:admin_dashboard'))
        self.assertEqual(html_expired.status_code, 302)
        self.assertEqual(html_expired.url, reverse('tamu:admin_login'))
        self.assertNotIn('_auth_user_id', admin_client2.session)
