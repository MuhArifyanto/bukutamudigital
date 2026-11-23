"""
Comprehensive Regression & Security Tests untuk Stage 3 (Skalabilitas & Kepatuhan):
1. Admin 2FA TOTP (Setup, Enable, Challenge Login, Rate-Limit, Disable).
2. SecurityHeadersMiddleware (CSP, Referrer-Policy, Permissions-Policy), HSTS 1 tahun & Redis config.
3. Office/PDF Magic Bytes & Signed URL Media (Lokal + Cloudinary).
4. Enkripsi NIK di database + Blind-Index + Key Rotation + Migration helper.
5. Kebijakan Retensi & Anonimisasi Data UU PDP (`purge_expired_pdp_data`).
6. Monitoring `/healthz/` & Konfigurasi Logging / CI workflows.
"""
import importlib
import io
import os
import re
from datetime import timedelta
from pathlib import Path
import shutil
import tempfile
from unittest import mock
import zipfile

import cloudinary
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

import bukudigital.settings as app_settings
from guest_book.models import (
    Admin,
    AuditLog,
    ChatMessage,
    Departemen,
    Instansi,
    Kunjungan,
    KunjunganNote,
    LoginAttempt,
    Notification,
    Pegawai,
    Session as AppSession,
    Tamu,
)
from guest_book.security_utils import (
    decrypt_nik,
    encrypt_nik,
    encrypt_secret,
    get_totp_code,
    hash_nik,
    is_encrypted_token,
    verify_totp_code,
)
from guest_book.storage import DynamicMediaCloudinaryStorage, sign_media_path
from guest_book.utils import validate_uploaded_file


def _make_ooxml_bytes(root_folder: str, inner_file: str, xml_body: bytes = b'<root/>') -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', b'<?xml version="1.0"?><Types/>')
        zf.writestr(f'{root_folder}/{inner_file}', xml_body)
    return buf.getvalue()


class AdminTwoFactorAuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.staff_user = User.objects.create_user(
            username='admin2fa',
            email='admin2fa@diskominfosantik.local',
            password='StrongAdminPass!2026',
            is_staff=True,
            is_superuser=True,
        )
        self.admin_record = Admin.objects.create(
            name='Administrator 2FA',
            email='admin2fa@diskominfosantik.local',
            phone='081234567890',
            password=self.staff_user.password,
            account_status='active',
        )
        self.tamu_admin = Tamu.objects.create(
            name='Administrator',
            email='admin2fa@diskominfosantik.local',
            phone='081234567890',
            nik='admin',
            is_admin=True,
            account_status='active',
        )

    def tearDown(self):
        cache.clear()

    def test_setup_enable_verify_and_disable_2fa_flow(self):
        # 1. Login tanpa 2FA berhasil langsung masuk dashboard
        resp = self.client.post(
            reverse('tamu:admin_login'),
            {'username': 'admin2fa', 'password': 'StrongAdminPass!2026'},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('tamu:admin_dashboard'))
        self.assertIn('_auth_user_id', self.client.session)

        # 2. Setup secret 2FA
        setup_resp = self.client.post(reverse('tamu:api_admin_2fa_setup'))
        self.assertEqual(setup_resp.status_code, 200)
        setup_data = setup_resp.json()
        self.assertTrue(setup_data['success'])
        secret = setup_data['secret']
        self.assertTrue(setup_data['otpauth_uri'].startswith('otpauth://totp/'))

        # 3. Kode OTP atau password salah ditolak saat aktivasi
        missing_pw_enable = self.client.post(
            reverse('tamu:api_admin_2fa_enable'),
            data=f'{{"otp_code": "{get_totp_code(secret)}"}}',
            content_type='application/json',
        )
        self.assertEqual(missing_pw_enable.status_code, 400)

        wrong_pw_enable = self.client.post(
            reverse('tamu:api_admin_2fa_enable'),
            data=f'{{"otp_code": "{get_totp_code(secret)}", "password": "SalahPassword!"}}',
            content_type='application/json',
        )
        self.assertEqual(wrong_pw_enable.status_code, 403)

        bad_enable = self.client.post(
            reverse('tamu:api_admin_2fa_enable'),
            data='{"otp_code": "000000", "password": "StrongAdminPass!2026"}',
            content_type='application/json',
        )
        self.assertEqual(bad_enable.status_code, 400)
        self.admin_record.refresh_from_db()
        self.assertFalse(self.admin_record.two_fa_enabled)

        # 4. Kode OTP benar + password benar mengaktifkan 2FA & mengenkripsi secret di DB
        valid_otp = get_totp_code(secret)
        ok_enable = self.client.post(
            reverse('tamu:api_admin_2fa_enable'),
            data=f'{{"otp_code": "{valid_otp}", "password": "StrongAdminPass!2026"}}',
            content_type='application/json',
        )
        self.assertEqual(ok_enable.status_code, 200)
        self.admin_record.refresh_from_db()
        self.assertTrue(self.admin_record.two_fa_enabled)
        self.assertTrue(is_encrypted_token(self.admin_record.two_fa_secret))
        self.assertNotEqual(self.admin_record.two_fa_secret, secret)

        # 5. Logout, lalu login ulang -> harus tertahan di tantangan 2FA
        self.client.logout()
        step1 = self.client.post(
            reverse('tamu:admin_login'),
            {'username': 'admin2fa', 'password': 'StrongAdminPass!2026'},
        )
        self.assertEqual(step1.status_code, 302)
        self.assertEqual(step1.url, reverse('tamu:admin_verify_2fa'))
        self.assertNotIn('_auth_user_id', self.client.session)
        self.assertIn('pending_2fa_user_id', self.client.session)

        # Akses dashboard sebelum verifikasi 2FA masih ditolak
        dash = self.client.get(reverse('tamu:admin_dashboard'))
        self.assertEqual(dash.status_code, 302)

        # 6. OTP salah saat login ditolak
        wrong_otp = '999999' if valid_otp != '999999' else '111111'
        bad_verify = self.client.post(
            reverse('tamu:admin_verify_2fa'),
            {'otp_code': wrong_otp},
        )
        self.assertEqual(bad_verify.status_code, 400)
        self.assertNotIn('_auth_user_id', self.client.session)

        # 7. OTP benar menyelesaikan login admin & audit log tercatat
        ok_verify = self.client.post(
            reverse('tamu:admin_verify_2fa'),
            {'otp_code': get_totp_code(secret)},
        )
        self.assertEqual(ok_verify.status_code, 302)
        self.assertEqual(ok_verify.url, reverse('tamu:admin_dashboard'))
        self.assertIn('_auth_user_id', self.client.session)
        self.assertNotIn('pending_2fa_user_id', self.client.session)
        self.assertTrue(AuditLog.objects.filter(table_name='admin', record_id=str(self.admin_record.id)).exists())

        # 8. Disable 2FA dengan password salah ditolak, password benar berhasil
        bad_dis = self.client.post(
            reverse('tamu:api_admin_2fa_disable'),
            data='{"password": "wrong-password"}',
            content_type='application/json',
        )
        self.assertEqual(bad_dis.status_code, 403)
        ok_dis = self.client.post(
            reverse('tamu:api_admin_2fa_disable'),
            data='{"password": "StrongAdminPass!2026"}',
            content_type='application/json',
        )
        self.assertEqual(ok_dis.status_code, 200)
        self.admin_record.refresh_from_db()
        self.assertFalse(self.admin_record.two_fa_enabled)
        self.assertIsNone(self.admin_record.two_fa_secret)

    def test_2fa_verification_rate_limit_blocks_brute_force(self):
        secret = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'
        self.admin_record.two_fa_enabled = True
        self.admin_record.two_fa_secret = encrypt_secret(secret)
        self.admin_record.save()

        self.client.post(
            reverse('tamu:admin_login'),
            {'username': 'admin2fa', 'password': 'StrongAdminPass!2026'},
        )
        bad_code = '000000' if get_totp_code(secret) != '000000' else '111111'
        for _ in range(5):
            r = self.client.post(reverse('tamu:admin_verify_2fa'), {'otp_code': bad_code})
            self.assertEqual(r.status_code, 400)

        locked = self.client.post(reverse('tamu:admin_verify_2fa'), {'otp_code': get_totp_code(secret)})
        self.assertEqual(locked.status_code, 429)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_verify_totp_helper_respects_window(self):
        secret = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'
        now_ts = 1794580000.0
        code_now = get_totp_code(secret, for_time=now_ts)
        self.assertTrue(verify_totp_code(secret, code_now, valid_window=1, for_time=now_ts))
        self.assertTrue(verify_totp_code(secret, code_now, valid_window=1, for_time=now_ts + 30))
        self.assertFalse(verify_totp_code(secret, code_now, valid_window=1, for_time=now_ts + 120))

    def test_totp_replay_blocked_within_window_and_on_login(self):
        secret = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'
        now_ts = 1794580000.0
        code_now = get_totp_code(secret, for_time=now_ts)
        code_prev = get_totp_code(secret, for_time=now_ts - 30)

        # Dengan replay_scope, OTP yang sama maupun interval lebih lama wajib ditolak
        self.assertTrue(
            verify_totp_code(secret, code_now, valid_window=1, for_time=now_ts, replay_scope='unit_admin_1')
        )
        self.assertFalse(
            verify_totp_code(secret, code_now, valid_window=1, for_time=now_ts + 30, replay_scope='unit_admin_1')
        )
        self.assertFalse(
            verify_totp_code(secret, code_prev, valid_window=1, for_time=now_ts, replay_scope='unit_admin_1')
        )

        # Uji anti-replay saat login admin
        self.admin_record.two_fa_enabled = True
        self.admin_record.two_fa_secret = encrypt_secret(secret)
        self.admin_record.save()

        otp = get_totp_code(secret)
        self.client.post(
            reverse('tamu:admin_login'),
            {'username': 'admin2fa', 'password': 'StrongAdminPass!2026'},
        )
        ok_resp = self.client.post(reverse('tamu:admin_verify_2fa'), {'otp_code': otp})
        self.assertEqual(ok_resp.status_code, 302)
        self.assertEqual(ok_resp.url, reverse('tamu:admin_dashboard'))

        # Login kedua memakai OTP yang sama dalam jendela 90 detik harus ditolak
        self.client.logout()
        self.client.post(
            reverse('tamu:admin_login'),
            {'username': 'admin2fa', 'password': 'StrongAdminPass!2026'},
        )
        replay_resp = self.client.post(reverse('tamu:admin_verify_2fa'), {'otp_code': otp})
        self.assertEqual(replay_resp.status_code, 400)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_django_admin_cannot_bypass_2fa_and_hides_sensitive_fields(self):
        from django.contrib import admin as django_admin
        from guest_book.views.base import resolve_admin_record

        secret = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'
        self.admin_record.two_fa_enabled = True
        self.admin_record.two_fa_secret = encrypt_secret(secret)
        self.admin_record.save()

        # 1. /admin/login/ dialihkan ke Portal Admin yang menegakkan 2FA (GET & POST)
        get_login = self.client.get('/admin/login/?next=/admin/')
        self.assertEqual(get_login.status_code, 302)
        self.assertTrue(get_login.url.startswith(reverse('tamu:admin_login')))

        post_login = self.client.post(
            '/admin/login/',
            {'username': 'admin2fa', 'password': 'StrongAdminPass!2026'},
        )
        self.assertEqual(post_login.status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

        # 2. Sesi staff tanpa verifikasi 2FA diblokir di /admin/ & /admin-portal/
        self.client.force_login(self.staff_user)
        admin_resp = self.client.get('/admin/')
        self.assertEqual(admin_resp.status_code, 302)
        self.assertEqual(admin_resp.url, reverse('tamu:admin_login'))
        self.assertNotIn('_auth_user_id', self.client.session)

        # 3. Setelah lolos 2FA, /admin/ dapat diakses dan field rahasia tersembunyi
        self.client.post(
            reverse('tamu:admin_login'),
            {'username': 'admin2fa', 'password': 'StrongAdminPass!2026'},
        )
        self.client.post(reverse('tamu:admin_verify_2fa'), {'otp_code': get_totp_code(secret)})
        ok_admin = self.client.get('/admin/')
        self.assertEqual(ok_admin.status_code, 200)

        # Pastikan ModelAdmin tidak mengekspos password / two_fa_secret / session_token
        for model_cls, secret_field in (
            (Tamu, 'password'),
            (Pegawai, 'password'),
            (Admin, 'two_fa_secret'),
            (Admin, 'password'),
            (AppSession, 'session_token'),
        ):
            ma = django_admin.site._registry[model_cls]
            self.assertIn(secret_field, ma.exclude or ())

        # 4. Tidak ada fallback lintas akun pada resolve_admin_record / change-password / disable-2fa
        second_staff = User.objects.create_user(
            username='admin_kedua',
            email='admin.kedua@diskominfosantik.local',
            password='SecondAdmin!Pass2026',
            is_staff=True,
        )
        self.assertIsNone(resolve_admin_record(second_staff, create_if_missing=False))
        self.assertIsNone(resolve_admin_record(None, create_if_missing=True))

        # Sesi tamu is_admin tanpa user Django tidak bisa mengubah password/menonaktifkan 2FA superuser
        legacy_client = Client()
        s = legacy_client.session
        s['tamu_id'] = str(self.tamu_admin.id)
        s.save()
        pw_res = legacy_client.post(
            reverse('tamu:api_change_password'),
            {
                'old_password': 'StrongAdminPass!2026',
                'new_password': 'NewStrongPass!2026',
                'confirm_password': 'NewStrongPass!2026',
            },
        )
        self.assertIn(pw_res.status_code, (302, 403))

        # 5. Lockout 2FA global per user tetap aktif meski IP berganti
        lock_client = Client()
        lock_client.post(
            reverse('tamu:admin_login'),
            {'username': 'admin2fa', 'password': 'StrongAdminPass!2026'},
        )
        bad_code = '000000' if get_totp_code(secret) != '000000' else '111111'
        for i in range(10):
            r = lock_client.post(
                reverse('tamu:admin_verify_2fa'),
                {'otp_code': bad_code},
                REMOTE_ADDR=f'198.51.100.{i + 1}',
            )
            self.assertEqual(r.status_code, 400)
        locked = lock_client.post(
            reverse('tamu:admin_verify_2fa'),
            {'otp_code': get_totp_code(secret)},
            REMOTE_ADDR='198.51.100.250',
        )
        self.assertEqual(locked.status_code, 429)


class SecurityHeadersAndRedisSettingsTests(TestCase):
    def tearDown(self):
        importlib.reload(app_settings)

    def test_csp_referrer_and_permissions_headers_present(self):
        for route_name in ('tamu:landing', 'tamu:login', 'tamu:admin_login'):
            resp = self.client.get(reverse(route_name))
            self.assertEqual(resp.status_code, 200)
            csp = resp.headers.get('Content-Security-Policy', '')
            self.assertIn("default-src 'self'", csp)
            self.assertIn("object-src 'none'", csp)
            self.assertIn("frame-ancestors 'none'", csp)

            script_src_match = re.search(r"script-src\s+([^;]+)", csp)
            self.assertIsNotNone(script_src_match)
            script_src = script_src_match.group(1)
            self.assertNotIn("'unsafe-inline'", script_src)
            nonce_match = re.search(r"'nonce-([^']+)'", script_src)
            self.assertIsNotNone(nonce_match)
            nonce = nonce_match.group(1)

            body = resp.content.decode('utf-8', errors='replace')
            # Minimal satu inline script memakai nonce yang cocok dengan header CSP
            if route_name in ('tamu:landing', 'tamu:login', 'tamu:admin_login'):
                self.assertIn(f'nonce="{nonce}"', body)

            self.assertEqual(resp.headers.get('Referrer-Policy'), 'strict-origin-when-cross-origin')
            self.assertIn('camera=(self)', resp.headers.get('Permissions-Policy', ''))

    def test_all_templates_strict_csp_compliant(self):
        templates_root = Path(app_settings.BASE_DIR) / 'guest_book' / 'templates'
        html_comment_re = re.compile(r"<!--.*?-->", re.DOTALL)
        django_comment_re = re.compile(r"\{#.*?#\}", re.DOTALL)
        script_block_re = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.DOTALL | re.IGNORECASE)
        on_attr_re = re.compile(r"""(?<!\w)on([a-z]{2,20})\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)""", re.IGNORECASE)

        bad_scripts = []
        bad_on_attrs = []
        for tpl_path in sorted(templates_root.rglob('*.html')):
            text = tpl_path.read_text(encoding='utf-8', errors='replace')
            stripped = django_comment_re.sub('', html_comment_re.sub('', text))

            def _check_script(match):
                attrs = match.group(1) or ''
                has_src = bool(re.search(r"\bsrc\s*=", attrs, re.IGNORECASE))
                has_nonce = 'nonce="{{ csp_nonce }}"' in attrs or "nonce='{{ csp_nonce }}'" in attrs
                if not has_src and not has_nonce:
                    bad_scripts.append(str(tpl_path.relative_to(templates_root)))
                return f"<script {attrs}></script>"

            html_only = script_block_re.sub(_check_script, stripped)
            for tag_m in re.finditer(r"<([a-zA-Z][a-zA-Z0-9:-]*)\b([^>]*)>", html_only):
                for on_m in on_attr_re.finditer(tag_m.group(2)):
                    bad_on_attrs.append((str(tpl_path.relative_to(templates_root)), on_m.group(0)))

        self.assertEqual(bad_scripts, [], f"Ditemukan <script> inline tanpa nonce CSP: {bad_scripts}")
        self.assertEqual(bad_on_attrs, [], f"Ditemukan atribut inline on*= HTML: {bad_on_attrs}")

    def test_production_hsts_1_year_and_redis_activation(self):
        env = {
            'APP_ENV': 'production',
            'DJANGO_SECRET_KEY': 'unit-test-strong-secret-key-at-least-32-chars!!',
            'ALLOWED_HOSTS': 'bukutamu.example.go.id',
            'CSRF_TRUSTED_ORIGINS': 'https://bukutamu.example.go.id',
            'REDIS_URL': 'redis://127.0.0.1:6379/1',
            'FORCE_REDIS_TEST': 'True',
            'USE_REDIS_CACHE': 'True',
            'USE_REDIS_CHANNEL_LAYER': 'True',
        }
        with mock.patch.dict(os.environ, env, clear=True):
            reloaded = importlib.reload(app_settings)
            self.assertEqual(reloaded.SECURE_HSTS_SECONDS, 31536000)
            self.assertTrue(reloaded.SECURE_HSTS_INCLUDE_SUBDOMAINS)
            self.assertTrue(reloaded.SECURE_HSTS_PRELOAD)
            self.assertIn(r'^healthz/?$', getattr(reloaded, 'SECURE_REDIRECT_EXEMPT', []))
            self.assertEqual(
                reloaded.CACHES['default']['BACKEND'],
                'django.core.cache.backends.redis.RedisCache',
            )
            self.assertEqual(reloaded.CACHES['default']['LOCATION'], 'redis://127.0.0.1:6379/1')
            self.assertEqual(
                reloaded.CHANNEL_LAYERS['default']['BACKEND'],
                'channels_redis.core.RedisChannelLayer',
            )


class DocumentMagicBytesAndSignedMediaTests(TestCase):
    def setUp(self):
        self.temp_media = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_media, ignore_errors=True)

    def test_valid_and_spoofed_documents_magic_bytes(self):
        pdf_ok = SimpleUploadedFile('surat.pdf', b'%PDF-1.4\n1 0 obj\n<<>>\nendobj', content_type='application/pdf')
        doc_ok = SimpleUploadedFile('surat.doc', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'\x00' * 32)
        xls_ok = SimpleUploadedFile('data.xls', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'\x00' * 32)
        docx_ok = SimpleUploadedFile('laporan.docx', _make_ooxml_bytes('word', 'document.xml'))
        xlsx_ok = SimpleUploadedFile('rekap.xlsx', _make_ooxml_bytes('xl', 'workbook.xml'))

        for f in (pdf_ok, doc_ok, xls_ok, docx_ok, xlsx_ok):
            ok, err, _ = validate_uploaded_file(
                f, allowed_extensions=['pdf', 'doc', 'docx', 'xls', 'xlsx']
            )
            self.assertTrue(ok, f"Seharusnya valid untuk {f.name}: {err}")
            self.assertEqual(f.tell(), 0)

        spoof_pdf = SimpleUploadedFile('palsu.pdf', b'<script>alert(1)</script>')
        spoof_doc = SimpleUploadedFile('palsu.doc', b'MZ\x90\x00not_ole2')
        spoof_docx = SimpleUploadedFile('palsu.docx', b'not a zip at all')
        wrong_ooxml = SimpleUploadedFile('tertukar.docx', _make_ooxml_bytes('xl', 'workbook.xml'))
        zip_bomb = SimpleUploadedFile('bomb.docx', _make_ooxml_bytes('word', 'document.xml', b'A' * (26 * 1024 * 1024)))

        for bad in (spoof_pdf, spoof_doc, spoof_docx, wrong_ooxml):
            ok, err, _ = validate_uploaded_file(
                bad, allowed_extensions=['pdf', 'doc', 'docx', 'xls', 'xlsx']
            )
            self.assertFalse(ok, f"Seharusnya ditolak: {bad.name}")
            self.assertIn('signature mismatch', err.lower())

        ok_bomb, err_bomb, _ = validate_uploaded_file(
            zip_bomb,
            max_size_bytes=5 * 1024 * 1024,
            allowed_extensions=['docx'],
        )
        self.assertFalse(ok_bomb)
        self.assertIn('dekompresi', err_bomb.lower())

    def test_signed_local_media_enforces_signature_and_prevents_tampering(self):
        with override_settings(MEDIA_ROOT=self.temp_media, MEDIA_SIGNED_URL_TTL=3600):
            Path(self.temp_media, 'profiles').mkdir(parents=True, exist_ok=True)
            img_path = Path(self.temp_media, 'profiles', 'avatar.png')
            img_path.write_bytes(b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR')

            Path(self.temp_media, 'chat_attachments').mkdir(parents=True, exist_ok=True)
            pdf_path = Path(self.temp_media, 'chat_attachments', 'dokumen.pdf')
            pdf_path.write_bytes(b'%PDF-1.4\n%test')

            signed_img_url = default_storage.url('profiles/avatar.png')
            self.assertIn('?sig=', signed_img_url)

            # Tanpa signature -> 403
            self.assertEqual(self.client.get('/media/profiles/avatar.png').status_code, 403)
            # Signature rusak -> 403
            self.assertEqual(self.client.get('/media/profiles/avatar.png?sig=abc:invalid').status_code, 403)
            # Reuse signature file lain -> 403
            other_sig = sign_media_path('chat_attachments/dokumen.pdf')
            self.assertEqual(self.client.get(f'/media/profiles/avatar.png?sig={other_sig}').status_code, 403)
            # Path traversal -> 403
            self.assertEqual(self.client.get(f'/media/../settings.py?sig={other_sig}').status_code, 403)

            # Signature valid untuk image -> 200 & nosniff
            ok_img = self.client.get(signed_img_url)
            self.assertEqual(ok_img.status_code, 200)
            self.assertEqual(ok_img.headers.get('X-Content-Type-Options'), 'nosniff')
            ok_img.close()

            # Signature valid untuk dokumen PDF -> attachment & nosniff
            signed_pdf_url = default_storage.url('chat_attachments/dokumen.pdf')
            ok_pdf = self.client.get(signed_pdf_url)
            self.assertEqual(ok_pdf.status_code, 200)
            self.assertIn('attachment', ok_pdf.headers.get('Content-Disposition', ''))
            self.assertEqual(ok_pdf.headers.get('X-Content-Type-Options'), 'nosniff')
            ok_pdf.close()

            # Signature kedaluwarsa -> 403
            with override_settings(MEDIA_SIGNED_URL_TTL=-1):
                expired = self.client.get(signed_img_url)
                self.assertEqual(expired.status_code, 403)

    def test_cloudinary_signed_url_when_api_secret_configured(self):
        prev = (cloudinary.config().cloud_name, cloudinary.config().api_key, cloudinary.config().api_secret)
        try:
            cloudinary.config(cloud_name='demo-cloud', api_key='111222', api_secret='super-secret-xyz')
            storage = DynamicMediaCloudinaryStorage()
            url = storage._get_url('chat_attachments/laporan_rahasia.pdf')
            self.assertIn('https://res.cloudinary.com/demo-cloud/raw/upload/', url)
            self.assertIn('/s--', url)
        finally:
            cloudinary.config(cloud_name=prev[0], api_key=prev[1], api_secret=prev[2])


class NikEncryptionAndMigrationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.tamu = Tamu.objects.create(
            name='Budi Santoso',
            email='budi.pdp@example.com',
            phone='081299990000',
            nik='3216010101010099',
            account_status='active',
        )

    def test_nik_encrypted_at_rest_and_transparent_lookup_works(self):
        with connection.cursor() as cursor:
            raw_id = self.tamu._meta.pk.get_db_prep_value(self.tamu.pk, connection)
            cursor.execute("SELECT nik, nik_hash FROM tamu WHERE id = %s", [raw_id])
            raw_nik, raw_hash = cursor.fetchone()

        self.assertTrue(is_encrypted_token(raw_nik))
        self.assertNotIn('3216010101010099', raw_nik)
        self.assertEqual(raw_hash, hash_nik('3216010101010099'))

        # Baca via ORM otomatis mendekripsi
        loaded = Tamu.objects.get(Tamu.nik_lookup_q('3216010101010099'))
        self.assertEqual(loaded.nik, '3216010101010099')

        # Batch update sinkron dengan nik_hash
        Tamu.objects.filter(pk=self.tamu.pk).update(nik='3216010101010088')
        found_after_update = Tamu.objects.filter(Tamu.nik_lookup_q('3216010101010088')).first()
        self.assertIsNotNone(found_after_update)
        self.assertEqual(found_after_update.nik, '3216010101010088')

    def test_key_rotation_with_multifernet_and_wrong_key_isolation(self):
        key_old = 'old-nik-key-secret-material'
        key_new = 'new-nik-key-secret-material'
        with override_settings(NIK_ENCRYPTION_KEY=key_old):
            token = encrypt_nik('3216777766665555')

        # Rotasi dengan "key_new,key_old" tetap bisa mendekripsi data lama
        with override_settings(NIK_ENCRYPTION_KEY=f"{key_new},{key_old}"):
            self.assertEqual(decrypt_nik(token), '3216777766665555')

        # Kunci salah tidak bisa mendekripsi plaintext
        with override_settings(NIK_ENCRYPTION_KEY=key_new):
            with self.assertRaises(ValueError):
                decrypt_nik(token, raise_on_error=True)

    def test_migration_0022_data_helpers_encrypt_and_decrypt(self):
        mig = importlib.import_module('guest_book.migrations.0022_tamu_nik_encryption_and_hash')
        legacy_tamu = Tamu.objects.create(
            name='Legacy Plaintext',
            email='legacy@example.com',
            phone='0811111111',
            nik='3216123412341234',
        )
        raw_id = legacy_tamu._meta.pk.get_db_prep_value(legacy_tamu.pk, connection)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE tamu SET nik = %s, nik_hash = NULL WHERE id = %s",
                ['3216123412341234', raw_id],
            )

        from types import SimpleNamespace
        from django.apps import apps as global_apps

        fake_editor = SimpleNamespace(
            connection=connection,
            quote_name=connection.ops.quote_name,
        )
        mig.encrypt_existing_niks(global_apps, fake_editor)
        with connection.cursor() as cursor_check:
            cursor_check.execute("SELECT nik, nik_hash FROM tamu WHERE id = %s", [raw_id])
            enc_val, h_val = cursor_check.fetchone()
        self.assertTrue(is_encrypted_token(enc_val))
        self.assertEqual(h_val, hash_nik('3216123412341234'))

        mig.decrypt_existing_niks(global_apps, fake_editor)
        with connection.cursor() as cursor_check:
            cursor_check.execute("SELECT nik, nik_hash FROM tamu WHERE id = %s", [raw_id])
            plain_val, null_hash = cursor_check.fetchone()
        self.assertEqual(plain_val, '3216123412341234')
        self.assertIsNone(null_hash)


class PdpRetentionCommandTests(TestCase):
    def setUp(self):
        self.temp_media = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_media, ignore_errors=True)

    def test_purge_expired_pdp_data_dry_run_and_execute(self):
        with override_settings(MEDIA_ROOT=self.temp_media):
            now = timezone.now()
            old_visit_dt = now - timedelta(days=400)
            old_inactive_dt = now - timedelta(days=800)

            admin_tamu = Tamu.objects.create(
                name='Admin System', email='admin.sys@example.com', phone='0811', nik='admin', is_admin=True
            )
            Tamu.objects.filter(pk=admin_tamu.pk).update(registration_date=old_inactive_dt, last_login=old_inactive_dt)

            old_tamu = Tamu.objects.create(
                name='Tamu Lama Banget',
                email='lama.banget@example.com',
                phone='08123456789',
                nik='3216000011112222',
                instansi='PT Lama',
            )
            Tamu.objects.filter(pk=old_tamu.pk).update(registration_date=old_inactive_dt, last_login=old_inactive_dt)

            active_tamu = Tamu.objects.create(
                name='Tamu Aktif Baru',
                email='aktif.baru@example.com',
                phone='08199999999',
                nik='3216000033334444',
            )

            old_visit = Kunjungan.objects.create(
                tamu=old_tamu,
                arrival_time=old_inactive_dt,
                purpose='Konsultasi Lama',
                status=Kunjungan.Status.COMPLETED,
                notes='Catatan pribadi lama',
                admin_notes='Catatan internal sensitif',
            )
            KunjunganNote.objects.create(
                kunjungan=old_visit, author_id=str(admin_tamu.id), author_type='admin', content='Catatan detail'
            )

            recent_visit = Kunjungan.objects.create(
                tamu=active_tamu,
                arrival_time=now - timedelta(days=5),
                purpose='Kunjungan Baru',
                status=Kunjungan.Status.COMPLETED,
                notes='Masih dalam masa retensi',
            )

            old_file = SimpleUploadedFile('rahasia.pdf', b'%PDF-1.4\nsecret')
            old_chat = ChatMessage.objects.create(
                session_id=str(old_tamu.id),
                sender_id=str(old_tamu.id),
                sender_type='tamu',
                content='Chat lama',
                attachment=old_file,
            )
            ChatMessage.objects.filter(pk=old_chat.pk).update(created_at=old_visit_dt)
            old_att_name = old_chat.attachment.name
            self.assertTrue(default_storage.exists(old_att_name))

            old_attempt = LoginAttempt.objects.create(email='x@example.com', user_type='tamu', success=False)
            LoginAttempt.objects.filter(pk=old_attempt.pk).update(timestamp=old_visit_dt)

            old_notif = Notification.objects.create(
                recipient_id=str(old_tamu.id),
                recipient_type='tamu',
                notification_type='system_alert',
                title='Lama',
                message='Sudah dibaca',
                status='read',
            )
            Notification.objects.filter(pk=old_notif.pk).update(created_at=old_visit_dt)

            AppSession.objects.create(
                user_id=str(old_tamu.id),
                user_type='tamu',
                session_token='expired-token-123',
                expires_at=now - timedelta(hours=2),
            )

            # 1. Dry-run tidak mengubah apa pun
            call_command('purge_expired_pdp_data', '--dry-run')
            self.assertEqual(ChatMessage.objects.count(), 1)
            self.assertTrue(default_storage.exists(old_att_name))
            old_tamu.refresh_from_db()
            self.assertEqual(old_tamu.nik, '3216000011112222')

            # 2. Eksekusi nyata membersihkan & menganonimkan data kedaluwarsa saja
            call_command('purge_expired_pdp_data')
            self.assertEqual(ChatMessage.objects.count(), 0)
            self.assertFalse(default_storage.exists(old_att_name))
            self.assertEqual(LoginAttempt.objects.count(), 0)
            self.assertEqual(Notification.objects.count(), 0)
            self.assertEqual(AppSession.objects.count(), 0)
            self.assertEqual(KunjunganNote.objects.count(), 0)

            old_visit.refresh_from_db()
            self.assertIn('UU PDP', old_visit.notes)
            recent_visit.refresh_from_db()
            self.assertEqual(recent_visit.notes, 'Masih dalam masa retensi')

            old_tamu.refresh_from_db()
            self.assertTrue(old_tamu.email.endswith('@redacted.local'))
            self.assertIsNone(old_tamu.nik)
            self.assertIsNone(old_tamu.nik_hash)

            # Admin & tamu aktif tidak pernah disentuh
            admin_tamu.refresh_from_db()
            self.assertEqual(admin_tamu.nik, 'admin')
            active_tamu.refresh_from_db()
            self.assertEqual(active_tamu.nik, '3216000033334444')

            self.assertTrue(AuditLog.objects.filter(table_name='pdp_retention').exists())


class HealthzAndLoggingTests(TestCase):
    def test_healthz_endpoint_returns_ok_json(self):
        resp = self.client.get(reverse('tamu:healthz'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data['status'], 'ok')
        self.assertEqual(data['checks']['database'], 'ok')
        self.assertEqual(data['checks']['cache'], 'ok')

    def test_logging_and_ci_workflows_configured(self):
        self.assertIn('guest_book.security', app_settings.LOGGING['loggers'])
        self.assertIn('django.security', app_settings.LOGGING['loggers'])
        base_dir = Path(app_settings.BASE_DIR)
        self.assertTrue((base_dir / '.github' / 'workflows' / 'ci.yml').is_file())
        self.assertTrue((base_dir / '.github' / 'workflows' / 'pdp-retention.yml').is_file())
