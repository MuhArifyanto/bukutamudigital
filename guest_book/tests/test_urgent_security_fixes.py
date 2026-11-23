import importlib
import io
import json
import os
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

import bukudigital.settings as settings_module
from guest_book.forms import TamuLoginForm
from guest_book.models import Admin, AuditLog, Tamu
from guest_book.views.auth import _establish_tamu_session


class CloudinaryDefaultRemovalTests(TestCase):
    """Memastikan settings.py tidak lagi menyimpan credential default Cloudinary."""

    def test_settings_cloudinary_url_empty_when_env_unset(self):
        original_env = os.environ.copy()
        try:
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop('CLOUDINARY_URL', None)
                with patch('dotenv.load_dotenv'):
                    reloaded = importlib.reload(settings_module)
                    self.assertEqual(reloaded.CLOUDINARY_URL, '')
        finally:
            os.environ.clear()
            os.environ.update(original_env)
            importlib.reload(settings_module)

    def test_settings_file_contains_no_hardcoded_cloudinary_credentials(self):
        settings_path = os.path.join(settings.BASE_DIR, 'bukudigital', 'settings.py')
        with open(settings_path, 'r', encoding='utf-8') as f:
            source = f.read()
        self.assertNotIn('cloudinary://', source)


class SetupAdminHardeningTests(TestCase):
    """Memastikan setup_admin tidak memakai password default lemah, tidak membuat superadmin, dan tidak menimpa password."""

    def test_setup_admin_skips_user_creation_without_password_env_and_never_creates_superadmin(self):
        out = io.StringIO()
        err = io.StringIO()
        clean_env = {k: v for k, v in os.environ.items() if k not in ('ADMIN_PASSWORD', 'ADMIN_INITIAL_PASSWORD')}
        with patch.dict(os.environ, clean_env, clear=True):
            call_command('setup_admin', stdout=out, stderr=err)

        self.assertFalse(User.objects.filter(username__iexact='admin').exists())
        self.assertFalse(User.objects.filter(username__iexact='superadmin').exists())
        self.assertEqual(Admin.objects.count(), 0)
        tamu_admin = Tamu.objects.filter(is_admin=True).first()
        self.assertIsNotNone(tamu_admin)
        self.assertIsNone(tamu_admin.password)
        self.assertIn('tidak disetel', err.getvalue())

    def test_setup_admin_creates_with_env_without_printing_password_and_preserves_existing(self):
        strong_pw = 'Str0ngAdm1n!Bekasi26'
        out = io.StringIO()
        with patch.dict(os.environ, {'ADMIN_PASSWORD': strong_pw}, clear=False):
            call_command('setup_admin', stdout=out)

        self.assertNotIn(strong_pw, out.getvalue())
        self.assertFalse(User.objects.filter(username__iexact='superadmin').exists())

        user = User.objects.get(username='admin')
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password(strong_pw))

        admin_row = Admin.objects.get(email='admin@diskominfosantik.bekasikab.go.id')
        self.assertTrue(check_password(strong_pw, admin_row.password))

        tamu_admin = Tamu.objects.get(is_admin=True)
        self.assertIsNone(tamu_admin.password)

        # Ubah password manual lalu jalankan setup_admin ulang TANPA --reset-password
        custom_pw = 'Cu$tomManualAdm1n!99'
        user.set_password(custom_pw)
        user.save()
        admin_row.password = make_password(custom_pw)
        admin_row.save()

        out2 = io.StringIO()
        with patch.dict(os.environ, {'ADMIN_PASSWORD': 'AttemptOverwrite!2026'}, clear=False):
            call_command('setup_admin', stdout=out2)

        user.refresh_from_db()
        admin_row.refresh_from_db()
        self.assertTrue(user.check_password(custom_pw))
        self.assertTrue(check_password(custom_pw, admin_row.password))

        # Dengan --reset-password, barulah password diperbarui
        reset_pw = 'ResetAdm1n!2026OK'
        out3 = io.StringIO()
        call_command('setup_admin', reset_password=True, password=reset_pw, stdout=out3)
        user.refresh_from_db()
        admin_row.refresh_from_db()
        self.assertTrue(user.check_password(reset_pw))
        self.assertTrue(check_password(reset_pw, admin_row.password))
        self.assertNotIn(reset_pw, out3.getvalue())

    def test_setup_admin_rejects_weak_password_and_reset_without_password(self):
        clean_env = {k: v for k, v in os.environ.items() if k not in ('ADMIN_PASSWORD', 'ADMIN_INITIAL_PASSWORD')}
        with patch.dict(os.environ, clean_env, clear=True):
            with self.assertRaises(CommandError):
                call_command('setup_admin', reset_password=True)
            with self.assertRaises(CommandError):
                call_command('setup_admin', password='123')


class AdminBlockedFromTamuLoginTests(TestCase):
    """Memastikan akun is_admin=True atau nik='admin' ditolak di seluruh jalur login Tamu."""

    def setUp(self):
        cache.clear()
        self.raw_pw = 'AdminLegacyTamu!2026'
        self.tamu_admin = Tamu.objects.create(
            name='Administrator Portal',
            email='admin-portal@example.com',
            phone='081234567890',
            nik='admin',
            instansi='Diskominfosantik',
            password=make_password(self.raw_pw),
            is_admin=True,
            account_status='active',
        )
        self.tamu_admin_with_nik = Tamu.objects.create(
            name='Operator Admin',
            email='operator-admin@example.com',
            phone='081234567891',
            nik='3216000000000099',
            instansi='Diskominfosantik',
            password=make_password(self.raw_pw),
            is_admin=True,
            account_status='active',
        )

    def tearDown(self):
        cache.clear()

    def test_tamu_login_form_and_login_view_block_admin(self):
        for identifier in ('admin-portal@example.com', 'operator-admin@example.com', '3216000000000099'):
            form = TamuLoginForm(data={'username': identifier, 'password': self.raw_pw})
            self.assertFalse(form.is_valid(), f"Form login tamu seharusnya menolak {identifier}")

            client = Client()
            resp = client.post(reverse('tamu:login'), {'username': identifier, 'password': self.raw_pw})
            self.assertEqual(resp.status_code, 200)
            self.assertNotIn('tamu_id', client.session)

    @patch('requests.post')
    def test_api_tamu_login_blocks_admin_without_calling_firebase(self, mock_firebase_post):
        client = Client()
        for identifier in ('admin-portal@example.com', 'operator-admin@example.com', '3216000000000099'):
            resp = client.post(
                reverse('tamu:api_tamu_login'),
                data=json.dumps({'identifier': identifier, 'password': self.raw_pw}),
                content_type='application/json',
            )
            self.assertEqual(resp.status_code, 401)
            self.assertFalse(resp.json()['success'])
            self.assertNotIn('tamu_id', client.session)
        mock_firebase_post.assert_not_called()

    @patch('google.oauth2.id_token.verify_firebase_token')
    def test_api_firebase_login_blocks_admin(self, mock_verify):
        mock_verify.return_value = {
            'uid': 'firebase-admin-uid',
            'email': 'admin-portal@example.com',
            'email_verified': True,
        }
        client = Client()
        resp = client.post(
            reverse('tamu:api_firebase_login'),
            data=json.dumps({'id_token': 'dummy-valid-token'}),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json()['success'])
        self.assertNotIn('tamu_id', client.session)

    def test_establish_tamu_session_rejects_admin(self):
        client = Client()
        session = client.session
        session.save()
        from django.test import RequestFactory
        req = RequestFactory().get('/')
        req.session = session
        with self.assertRaises(ValueError):
            _establish_tamu_session(req, self.tamu_admin)


class ApiChangePasswordTests(TestCase):
    """Memastikan api_change_password memverifikasi password lama, kekuatan sandi, dan memperbarui auth.User."""

    def setUp(self):
        self.old_pw = 'OldAdm1n!Pass2026'
        self.user = User.objects.create_user(
            username='admin_test',
            email='admin_test@example.com',
            password=self.old_pw,
            is_staff=True,
            is_superuser=True,
            is_active=True,
        )
        self.admin_row = Admin.objects.create(
            name='Admin Test',
            email='admin_test@example.com',
            phone='081234567890',
            password=make_password(self.old_pw),
            account_status='active',
        )
        self.tamu_admin = Tamu.objects.create(
            name='Admin Test',
            email='admin_test@example.com',
            phone='081234567890',
            nik='admin',
            password=make_password(self.old_pw),
            is_admin=True,
            account_status='active',
        )
        self.url = reverse('tamu:api_change_password')

    def test_requires_authentication(self):
        resp = self.client.post(self.url, {'old_password': self.old_pw, 'new_password': 'NewAdm1n!Pass2026'})
        self.assertIn(resp.status_code, (302, 401, 403))

    def test_rejects_missing_or_wrong_old_password(self):
        self.client.force_login(self.user)

        resp_missing = self.client.post(self.url, {'new_password': 'NewAdm1n!Pass2026'})
        self.assertEqual(resp_missing.status_code, 400)
        self.assertFalse(resp_missing.json()['success'])

        resp_wrong = self.client.post(
            self.url,
            {
                'old_password': 'SalahPassword!99',
                'new_password': 'NewAdm1n!Pass2026',
                'confirm_password': 'NewAdm1n!Pass2026',
            },
        )
        self.assertEqual(resp_wrong.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_pw))

    def test_rejects_mismatch_confirm_and_weak_password(self):
        self.client.force_login(self.user)

        resp_mismatch = self.client.post(
            self.url,
            {
                'old_password': self.old_pw,
                'new_password': 'NewAdm1n!Pass2026',
                'confirm_password': 'BedaAdm1n!Pass2026',
            },
        )
        self.assertEqual(resp_mismatch.status_code, 400)

        resp_weak = self.client.post(
            self.url,
            {
                'old_password': self.old_pw,
                'new_password': '123456',
                'confirm_password': '123456',
            },
        )
        self.assertEqual(resp_weak.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_pw))

    def test_valid_password_change_updates_django_user_admin_table_and_preserves_session(self):
        self.client.force_login(self.user)
        new_pw = 'SuperStr0ng!New2026'
        resp = self.client.post(
            self.url,
            {
                'old_password': self.old_pw,
                'new_password': new_pw,
                'confirm_password': new_pw,
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])

        self.user.refresh_from_db()
        self.admin_row.refresh_from_db()
        self.tamu_admin.refresh_from_db()

        self.assertTrue(self.user.check_password(new_pw))
        self.assertFalse(self.user.check_password(self.old_pw))
        self.assertTrue(check_password(new_pw, self.admin_row.password))
        self.assertIsNone(self.tamu_admin.password)
        self.assertTrue(
            AuditLog.objects.filter(table_name='auth_user', action='update', record_id=str(self.user.pk)).exists()
        )
        # Sesi admin tetap aktif setelah penggantian password
        profil_resp = self.client.get(reverse('tamu:admin_profil'))
        self.assertEqual(profil_resp.status_code, 200)


@override_settings(FIREBASE_WEBHOOK_SECRET='webhook-secret-token-2026')
class WebhookDeleteUserTests(TestCase):
    """Memastikan api_webhook_delete_user aman terhadap NULL lookup, mass delete, dan tidak pernah menghapus admin."""

    def setUp(self):
        self.url = reverse('tamu:api_webhook_delete_user')
        self.headers = {'HTTP_AUTHORIZATION': 'Bearer webhook-secret-token-2026'}

    def test_rejects_unauthorized_requests(self):
        resp_missing = self.client.post(
            self.url, data=json.dumps({'email': 'a@example.com'}), content_type='application/json'
        )
        self.assertEqual(resp_missing.status_code, 401)

        resp_wrong = self.client.post(
            self.url,
            data=json.dumps({'email': 'a@example.com'}),
            content_type='application/json',
            HTTP_AUTHORIZATION='Bearer wrong-token',
        )
        self.assertEqual(resp_wrong.status_code, 401)

    def test_email_only_payload_does_not_delete_other_null_google_id_users(self):
        victim = Tamu.objects.create(
            name='Victim User', email='victim@example.com', phone='0811111111', google_id=None
        )
        innocent1 = Tamu.objects.create(
            name='Innocent One', email='innocent1@example.com', phone='0822222222', google_id=None
        )
        innocent2 = Tamu.objects.create(
            name='Innocent Two', email='innocent2@example.com', phone='0833333333', google_id=''
        )

        resp = self.client.post(
            self.url,
            data=json.dumps({'email': 'VICTIM@example.com', 'uid': None}),
            content_type='application/json',
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])
        self.assertFalse(Tamu.objects.filter(pk=victim.pk).exists())
        self.assertTrue(Tamu.objects.filter(pk=innocent1.pk).exists())
        self.assertTrue(Tamu.objects.filter(pk=innocent2.pk).exists())

    def test_never_deletes_admin_record(self):
        admin_tamu = Tamu.objects.create(
            name='Admin Protected',
            email='admin-protected@example.com',
            phone='0899999999',
            nik='admin',
            google_id='uid-admin-1',
            is_admin=True,
        )
        resp = self.client.post(
            self.url,
            data=json.dumps({'uid': 'uid-admin-1', 'email': 'admin-protected@example.com'}),
            content_type='application/json',
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Tamu.objects.filter(pk=admin_tamu.pk).exists())

    def test_ambiguous_selector_matching_multiple_users_returns_409(self):
        u1 = Tamu.objects.create(
            name='User One', email='u1@example.com', phone='0811111111', google_id='uid-u1'
        )
        u2 = Tamu.objects.create(
            name='User Two', email='u2@example.com', phone='0822222222', google_id='uid-u2'
        )
        resp = self.client.post(
            self.url,
            data=json.dumps({'uid': 'uid-u1', 'email': 'u2@example.com'}),
            content_type='application/json',
            **self.headers,
        )
        self.assertEqual(resp.status_code, 409)
        self.assertFalse(resp.json()['success'])
        self.assertTrue(Tamu.objects.filter(pk=u1.pk).exists())
        self.assertTrue(Tamu.objects.filter(pk=u2.pk).exists())

