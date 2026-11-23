import json
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.core import mail
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from ..models import CalendarSettings, Kunjungan, Pegawai, Session as AppSession, Tamu
from ..security_utils import tamu_reset_token_generator
from ..validators import JAKARTA_TZ
from ..views.auth import (
    _fallback_rl_clear,
    check_rate_limit,
    clear_rate_limit,
    get_client_ip,
    record_rate_limit_attempt,
)
from .base import BaseSecurityTestCase


class Section2HighRiskSecurityTests(BaseSecurityTestCase):
    """Pengujian regresi komprehensif untuk seluruh perbaikan Section 2 (T-1..T-5)."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.operator_django = User.objects.create_user(
            username='operator_admin',
            email='operator@diskominfosantik.go.id',
            password='OperatorPass@2026!',
            is_staff=True,
            is_superuser=False,
        )
        self.operator_tamu = Tamu.objects.create(
            name='Operator Admin',
            email='operator@diskominfosantik.go.id',
            phone='081211112222',
            nik='3216010101900099',
            password=None,
            is_admin=True,
            admin_role='operator',
            account_status='active',
        )
        self.super_django = User.objects.create_user(
            username='super_role_admin',
            email='superrole@diskominfosantik.go.id',
            password='SuperRolePass@2026!',
            is_staff=True,
            is_superuser=False,
        )
        self.super_tamu = Tamu.objects.create(
            name='Super Role Admin',
            email='superrole@diskominfosantik.go.id',
            phone='081211113333',
            nik='3216010101900098',
            password=None,
            is_admin=True,
            admin_role='super_admin',
            account_status='active',
        )

    def _get_staff_client(self, user):
        client = Client()
        client.force_login(user)
        s = client.session
        s['_admin_2fa_verified_user_id'] = str(user.pk)
        s.save()
        return client

    # ── T-1: Password Reset Tamu ──────────────────────────────────────────────

    def test_t1_tamu_password_reset_no_attribute_error_and_no_enumeration(self):
        reset_url = reverse('tamu:password_reset')
        done_url = reverse('tamu:password_reset_done')

        # 1. Email terdaftar -> sukses tanpa AttributeError & kirim 1 email
        resp_valid = self.client.post(reset_url, {'email': self.tamu_a.email.upper()})
        self.assertRedirects(resp_valid, done_url, fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.tamu_a.email, mail.outbox[0].to)

        # 2. Email tidak terdaftar -> respons identik (302 ke done), tidak kirim email
        mail.outbox.clear()
        resp_unknown = self.client.post(reset_url, {'email': 'tidakada@example.com'})
        self.assertRedirects(resp_unknown, done_url, fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 0)

        # 3. Email akun Tamu is_admin=True -> respons identik (302 ke done), tidak kirim email
        resp_admin = self.client.post(reset_url, {'email': self.super_tamu.email})
        self.assertRedirects(resp_admin, done_url, fetch_redirect_response=False)
        self.assertEqual(len(mail.outbox), 0)

    def test_t1_tamu_password_reset_rate_limit_enforced(self):
        reset_url = reverse('tamu:password_reset')
        for _ in range(5):
            resp = self.client.post(
                reset_url,
                {'email': 'ratelimit@example.com'},
                REMOTE_ADDR='198.51.100.44',
            )
            self.assertEqual(resp.status_code, 302)

        blocked = self.client.post(
            reset_url,
            {'email': 'ratelimit@example.com'},
            REMOTE_ADDR='198.51.100.44',
        )
        self.assertEqual(blocked.status_code, 429)

    def test_t1_tamu_password_reset_confirm_validators_token_reuse_and_session_revoke(self):
        # Buat sesi aktif + AppSession untuk tamu_a
        active_client = self.get_client('tamu_a')
        active_key = active_client.session.session_key
        AppSession.objects.create(
            user_type='tamu',
            user_id=str(self.tamu_a.pk),
            session_token=f'tok_{uuid.uuid4().hex}',
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.assertTrue(Session.objects.filter(session_key=active_key).exists())

        uid = urlsafe_base64_encode(force_bytes(self.tamu_a.pk))
        token = tamu_reset_token_generator.make_token(self.tamu_a)
        confirm_url = reverse('tamu:password_reset_confirm', kwargs={'uidb64': uid, 'token': token})

        # Password lemah ditolak oleh AUTH_PASSWORD_VALIDATORS
        weak_resp = self.client.post(confirm_url, {
            'password1': 'password123',
            'password2': 'password123',
        })
        self.assertEqual(weak_resp.status_code, 200)
        self.tamu_a.refresh_from_db()
        self.assertTrue(check_password('password123', self.tamu_a.password))

        # Password kuat diterima -> update password + revoke seluruh sesi aktif
        ok_resp = self.client.post(confirm_url, {
            'password1': 'ResetAmanTamu#2026!',
            'password2': 'ResetAmanTamu#2026!',
        })
        self.assertRedirects(ok_resp, reverse('tamu:password_reset_complete'), fetch_redirect_response=False)

        self.tamu_a.refresh_from_db()
        self.assertTrue(check_password('ResetAmanTamu#2026!', self.tamu_a.password))
        self.assertFalse(Session.objects.filter(session_key=active_key).exists())
        self.assertFalse(AppSession.objects.filter(user_type='tamu', user_id=self.tamu_a.pk).exists())

        # Token lama tidak bisa dipakai ulang
        reuse_resp = self.client.get(confirm_url)
        self.assertEqual(reuse_resp.status_code, 200)
        self.assertFalse(reuse_resp.context['validlink'])

    # ── T-2: Kredensial Bawaan, Force Change & Seed Non-Destruktif ────────────

    def test_t2_manual_create_sets_unusable_password_no_dummy_default(self):
        admin_client = self._get_staff_client(self.super_django)
        today = timezone.localtime(timezone.now(), JAKARTA_TZ).date()
        CalendarSettings.objects.update_or_create(
            date=today,
            defaults={'daily_quota': 50, 'is_holiday': False},
        )
        resp = admin_client.post(reverse('tamu:admin_kunjungan_manual_create'), {
            'name': 'Walk In Guest',
            'nik': '3216010101900123',
            'phone': '081233334444',
            'email': 'walkin.guest@example.com',
            'instansi': 'Pemkab',
            'pegawai': str(self.pegawai.pk),
            'purpose': 'Konsultasi',
        })
        self.assertEqual(resp.status_code, 302)
        guest = Tamu.objects.filter(email='walkin.guest@example.com').first()
        self.assertIsNotNone(guest)
        self.assertFalse(check_password('manual_login_dummy', guest.password))
        self.assertTrue(guest.password.startswith('!'))

    def test_t2_seed_pegawai_non_destructive_and_no_default_password(self):
        # Akun pegawai dengan custom role/status & email @gmail.com tidak boleh tertimpa/terhapus
        gmail_pegawai = Pegawai.objects.create(
            name='Pegawai Gmail Resmi',
            email='pegawai.resmi@gmail.com',
            username='pegawaigmail',
            phone='081277770001',
            department_rel=self.departemen,
            password=make_password('KuatGmail@2026!'),
            role='staff',
            account_status='active',
        )
        # Buat satu akun resmi dulu dengan role custom dan status nonaktif
        existing_official = Pegawai.objects.create(
            name='Siti Custom',
            email='siti.rahayu@diskominfosantik.go.id',
            username='siti.custom',
            phone='082111000002',
            department_rel=self.departemen,
            password=make_password('CustomPass@2026!'),
            role='manager',
            account_status='inactive',
        )

        # Password lemah pada CLI harus ditolak
        with self.assertRaises(CommandError):
            call_command('seed_pegawai', password='123')

        call_command('seed_pegawai')

        existing_official.refresh_from_db()
        self.assertEqual(existing_official.role, 'manager')
        self.assertEqual(existing_official.account_status, 'inactive')
        self.assertTrue(Pegawai.objects.filter(pk=gmail_pegawai.pk).exists())

        new_official = Pegawai.objects.get(email='ahmad.fauzi@diskominfosantik.go.id')
        self.assertTrue(new_official.must_change_password)
        self.assertFalse(check_password('Diskominfo@2025', new_official.password))

    def test_t2_pegawai_must_change_password_gate_enforced(self):
        self.pegawai.must_change_password = True
        self.pegawai.save(update_fields=['must_change_password'])

        client = Client()
        login_resp = client.post(reverse('tamu:pegawai_login'), {
            'login_id': self.pegawai.email,
            'password': 'password123',
        })
        self.assertRedirects(login_resp, reverse('tamu:pegawai_profile'), fetch_redirect_response=False)

        # Akses ke dashboard ditahan sebelum mengganti password
        dash_resp = client.get(reverse('tamu:pegawai_dashboard'))
        self.assertRedirects(dash_resp, reverse('tamu:pegawai_profile'), fetch_redirect_response=False)

        # Ganti password di profil -> flag cleared & dashboard kembali bisa diakses
        change_resp = client.post(reverse('tamu:pegawai_profile'), {
            'name': self.pegawai.name,
            'phone': self.pegawai.phone,
            'current_password': 'password123',
            'new_password': 'PegawaiStrong#2026!',
        })
        self.assertEqual(change_resp.status_code, 302)
        self.pegawai.refresh_from_db()
        self.assertFalse(self.pegawai.must_change_password)

        dash_after = client.get(reverse('tamu:pegawai_dashboard'))
        self.assertEqual(dash_after.status_code, 200)

    # ── T-3: Proxy IP Spoofing & Rate Limit Atomik ────────────────────────────

    def test_t3_get_client_ip_proxy_and_spoofing_protection(self):
        rf = RequestFactory()

        # 1. Dari IP publik tak tepercaya -> header XFF & CF diabaikan
        req_untrusted = rf.get(
            '/',
            REMOTE_ADDR='198.51.100.25',
            HTTP_X_FORWARDED_FOR='1.2.3.4',
            HTTP_CF_CONNECTING_IP='5.6.7.8',
        )
        self.assertEqual(get_client_ip(req_untrusted), '198.51.100.25')

        # 2. Dari proxy tepercaya (loopback/private) -> ambil hop kanan-ke-kiri non-proxy pertama
        req_proxy = rf.get(
            '/',
            REMOTE_ADDR='10.0.0.5',
            HTTP_X_FORWARDED_FOR='9.9.9.9, 203.0.113.88, 10.0.0.2',
        )
        self.assertEqual(get_client_ip(req_proxy), '203.0.113.88')

        # 3. Header CF-Connecting-IP hanya dipercaya bila TRUST_CF_CONNECTING_IP=True
        with override_settings(TRUST_CF_CONNECTING_IP=False):
            req_cf_off = rf.get(
                '/',
                REMOTE_ADDR='127.0.0.1',
                HTTP_CF_CONNECTING_IP='198.51.100.77',
                HTTP_X_FORWARDED_FOR='203.0.113.10',
            )
            self.assertEqual(get_client_ip(req_cf_off), '203.0.113.10')

        with override_settings(TRUST_CF_CONNECTING_IP=True):
            req_cf_on = rf.get(
                '/',
                REMOTE_ADDR='127.0.0.1',
                HTTP_CF_CONNECTING_IP='198.51.100.77',
                HTTP_X_FORWARDED_FOR='203.0.113.10',
            )
            self.assertEqual(get_client_ip(req_cf_on), '198.51.100.77')

    def test_t3_rate_limit_atomic_and_fail_closed_fallback(self):
        key = 'rl_test_atomic_section2'
        clear_rate_limit(key)
        for _ in range(5):
            record_rate_limit_attempt(key, timeout_seconds=60)
        self.assertTrue(check_rate_limit(key, max_attempts=5))
        clear_rate_limit(key)

        # Jika cache gagal & fail_closed=True -> blokir
        _fallback_rl_clear(key)
        with patch('guest_book.views.auth.cache.get', side_effect=ConnectionError('redis down')):
            self.assertTrue(check_rate_limit(key, max_attempts=5, fail_closed=True))
            self.assertFalse(check_rate_limit(key, max_attempts=5, fail_closed=False))

    # ── T-4: RBAC Super Admin, Revoke Session, Profile Password & POST Logout ─

    def test_t4_rbac_operator_blocked_and_super_admin_allowed(self):
        operator_client = self._get_staff_client(self.operator_django)
        super_client = self._get_staff_client(self.super_django)

        toggle_url = reverse('tamu:api_toggle_user_status', kwargs={'user_id': self.tamu_a.pk})
        role_url = reverse('tamu:admin_pegawai_update_role', kwargs={'pegawai_id': self.pegawai.pk})
        status_url = reverse('tamu:admin_pegawai_update_status', kwargs={'pegawai_id': self.pegawai.pk})

        self.assertEqual(operator_client.post(toggle_url, {'status': 'inactive'}).status_code, 403)
        self.assertEqual(
            operator_client.post(role_url, json.dumps({'role': 'manager'}), content_type='application/json').status_code,
            403,
        )
        self.assertEqual(
            operator_client.post(status_url, json.dumps({'status': 'inactive'}), content_type='application/json').status_code,
            403,
        )

        # Operator mencoba POST admin_instansi -> ditolak & data instansi tidak berubah
        original_nama = self.instansi.nama
        resp_inst = operator_client.post(reverse('tamu:admin_instansi'), {
            'action': 'add_departemen',
            'nama': 'Bidang Ilegal',
            'kode': 'BIL',
        })
        self.assertEqual(resp_inst.status_code, 302)
        from ..models import Departemen
        self.assertFalse(Departemen.objects.filter(nama='Bidang Ilegal').exists())
        self.instansi.refresh_from_db()
        self.assertEqual(self.instansi.nama, original_nama)

        # Super Admin (via Tamu admin_role='super_admin') diizinkan mengubah role pegawai
        ok_role = super_client.post(
            role_url,
            json.dumps({'role': 'manager'}),
            content_type='application/json',
        )
        self.assertEqual(ok_role.status_code, 200)
        self.pegawai.refresh_from_db()
        self.assertEqual(self.pegawai.role, 'manager')

    def test_t4_suspending_tamu_and_pegawai_revokes_active_sessions(self):
        tamu_client = self.get_client('tamu_a')
        tamu_key = tamu_client.session.session_key
        tamu_app = AppSession.objects.create(
            user_type='tamu',
            user_id=str(self.tamu_a.pk),
            session_token=f'tok_{uuid.uuid4().hex}',
            expires_at=timezone.now() + timedelta(hours=1),
        )

        pegawai_client = self.get_client('pegawai')
        pegawai_key = pegawai_client.session.session_key
        pegawai_app = AppSession.objects.create(
            user_type='pegawai',
            user_id=str(self.pegawai.pk),
            session_token=f'tok_{uuid.uuid4().hex}',
            expires_at=timezone.now() + timedelta(hours=1),
        )

        super_client = self._get_staff_client(self.super_django)
        res_tamu = super_client.post(
            reverse('tamu:api_toggle_user_status', kwargs={'user_id': self.tamu_a.pk}),
            {'status': 'suspended'},
        )
        self.assertEqual(res_tamu.status_code, 200)
        self.assertFalse(Session.objects.filter(session_key=tamu_key).exists())
        self.assertFalse(AppSession.objects.filter(pk=tamu_app.pk).exists())

        res_pegawai = super_client.post(
            reverse('tamu:admin_pegawai_update_status', kwargs={'pegawai_id': self.pegawai.pk}),
            json.dumps({'status': 'inactive'}),
            content_type='application/json',
        )
        self.assertEqual(res_pegawai.status_code, 200)
        self.assertFalse(Session.objects.filter(session_key=pegawai_key).exists())
        self.assertFalse(AppSession.objects.filter(pk=pegawai_app.pk).exists())

    def test_t4_pegawai_profile_requires_current_password_validator_and_revokes_other_sessions(self):
        client_main = self.get_client('pegawai')
        client_other = self.get_client('pegawai')
        other_key = client_other.session.session_key
        profile_url = reverse('tamu:pegawai_profile')

        # Current password salah -> tidak mengubah password
        client_main.post(profile_url, {
            'name': self.pegawai.name,
            'phone': self.pegawai.phone,
            'current_password': 'WrongPassword!',
            'new_password': 'PegawaiBaru@2026!',
        })
        self.pegawai.refresh_from_db()
        self.assertTrue(check_password('password123', self.pegawai.password))
        self.assertTrue(Session.objects.filter(session_key=other_key).exists())

        # Password baru terlalu lemah -> ditolak validator
        client_main.post(profile_url, {
            'name': self.pegawai.name,
            'phone': self.pegawai.phone,
            'current_password': 'password123',
            'new_password': '123',
        })
        self.pegawai.refresh_from_db()
        self.assertTrue(check_password('password123', self.pegawai.password))

        # Sukses ganti password -> sesi lain dicabut, sesi aktif tetap jalan
        client_main.post(profile_url, {
            'name': self.pegawai.name,
            'phone': self.pegawai.phone,
            'current_password': 'password123',
            'new_password': 'PegawaiBaru@2026!',
        })
        self.pegawai.refresh_from_db()
        self.assertTrue(check_password('PegawaiBaru@2026!', self.pegawai.password))
        self.assertFalse(Session.objects.filter(session_key=other_key).exists())
        self.assertIsNotNone(client_main.session.get('pegawai_id'))

    def test_t4_templates_use_post_form_for_logout(self):
        tpl_dir = Path(__file__).resolve().parents[1] / 'templates' / 'guest_book'
        for name in ('admin_base.html', 'pegawai_base.html', 'tamu_base.html', 'base.html'):
            content = (tpl_dir / name).read_text(encoding='utf-8')
            self.assertIn('method="post"', content)
            self.assertIn('{% csrf_token %}', content)
            self.assertNotIn('<a href="{% url \'tamu:logout\'', content)
            self.assertNotIn('<a href="{% url \'tamu:pegawai_logout\'', content)

    # ── T-5: Chat Extensions/CSRF, Scan Status, Atomic Quick Checkin, Params ─

    def test_t5_chat_templates_align_extensions_and_csrf_header(self):
        tpl_dir = Path(__file__).resolve().parents[1] / 'templates' / 'guest_book'
        admin_chat = (tpl_dir / 'admin_chat.html').read_text(encoding='utf-8')
        self.assertIn("'X-CSRFToken'", admin_chat)

        for name in ('admin_chat.html', 'pegawai_chat.html', 'tamu_chat.html'):
            html = (tpl_dir / name).read_text(encoding='utf-8')
            self.assertIn(".pdf,", html)
            self.assertIn("'pdf'", html)
            self.assertNotIn(".svg", html)
            self.assertNotIn("'svg'", html)

    def test_t5_api_scan_tiket_allows_only_approved_statuses(self):
        admin_client = self._get_staff_client(self.operator_django)
        scan_url = reverse('tamu:api_scan_tiket')
        kunjungan = Kunjungan.objects.create(
            tamu=self.tamu_a,
            pegawai=self.pegawai,
            purpose='Uji Scan Status',
            arrival_time=timezone.now() + timedelta(hours=2),
            status='menunggu_admin',
        )

        for blocked_status in ('menunggu_admin', 'menunggu_pegawai', 'ditolak_admin', 'ditolak_pegawai'):
            kunjungan.status = blocked_status
            kunjungan.save(update_fields=['status'])
            res = admin_client.post(
                scan_url,
                json.dumps({'code': str(kunjungan.pk)}),
                content_type='application/json',
            )
            self.assertEqual(res.status_code, 400, msg=f"Status {blocked_status} seharusnya ditolak")

        # disetujui_pegawai & disetujui diizinkan check-in
        kunjungan.status = 'disetujui_pegawai'
        kunjungan.save(update_fields=['status'])
        ok_res = admin_client.post(
            scan_url,
            json.dumps({'code': str(kunjungan.pk)}),
            content_type='application/json',
        )
        self.assertEqual(ok_res.status_code, 200)
        kunjungan.refresh_from_db()
        self.assertEqual(kunjungan.status, 'in_progress')

    def test_t5_quick_checkin_rolls_back_tamu_creation_on_quota_or_holiday_error(self):
        admin_client = self._get_staff_client(self.operator_django)
        yesterday = timezone.localtime(timezone.now(), JAKARTA_TZ).date() - timedelta(days=1)
        unique_phone = '081200009999'
        resp = admin_client.post(
            reverse('tamu:api_quick_checkin'),
            json.dumps({
                'name': 'Tamu Rollback',
                'phone': unique_phone,
                'date': yesterday.isoformat(),
                'time': '10:00',
                'purpose': 'Uji Atomik',
            }),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(Tamu.objects.filter(phone=unique_phone).exists())

    def test_t5_dashboard_k_sort_whitelist_and_kalender_bounds(self):
        admin_client = self._get_staff_client(self.operator_django)

        dash_resp = admin_client.get(reverse('tamu:admin_dashboard') + '?k_sort=tamu__password')
        self.assertEqual(dash_resp.status_code, 200)
        self.assertEqual(dash_resp.context['k_sort'], '-arrival_time')

        cal_invalid = admin_client.get(reverse('tamu:admin_kalender') + '?year=999999&month=99')
        self.assertEqual(cal_invalid.status_code, 200)

        cal_non_numeric = admin_client.get(reverse('tamu:admin_kalender') + '?year=abc&month=xyz')
        self.assertEqual(cal_non_numeric.status_code, 200)

    def test_t5_admin_instansi_referer_blocks_external_open_redirect(self):
        super_client = self._get_staff_client(self.super_django)
        resp = super_client.post(
            reverse('tamu:admin_instansi'),
            {
                'action': 'update_instansi',
                'nama': self.instansi.nama,
                'slogan': self.instansi.slogan or '',
                'status_operasional': 'buka',
                'jumlah_petugas': '3',
                'kapasitas_maksimal': '100',
                'jam_buka': '08:00',
                'jam_tutup': '16:00',
                'alamat': self.instansi.alamat or 'Bekasi',
            },
            HTTP_REFERER='https://evil.example/phishing',
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('tamu:admin_instansi'))
