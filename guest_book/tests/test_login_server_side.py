"""
Tes ujung ke ujung login Tamu sisi server (TUGAS 2.1).

Firebase tidak pernah dihubungi sungguhan: requests.post dan verifikasi token
dipalsukan. Nilai NIK/email/password di sini hanya data uji.
"""
import json
import logging
from unittest import mock

import requests
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import NoReverseMatch, reverse

from .base import BaseSecurityTestCase
from .. import firebase_rest
from ..models import Tamu

LOGIN_URL = '/api/auth/login/'
SECRET_PW = 'Sup3r-Rahasia-Uji-9137'
GENERIC = 'Email/NIK atau password salah, atau akun tidak dapat digunakan.'


def _fb_response(status=200, token='tok', error=None):
    resp = mock.Mock()
    resp.status_code = status
    if error is not None:
        resp.json.return_value = {'error': {'message': error}}
    else:
        resp.json.return_value = {'idToken': token}
    return resp


@override_settings(FIREBASE_API_KEY='test-key', FIREBASE_PROJECT_ID='test-project')
class ServerSideLoginTests(BaseSecurityTestCase):

    def setUp(self):
        super().setUp()
        self.client = Client()

    # ── helpers ───────────────────────────────────────────────────────────
    def _claims_for(self, tamu, uid='uid-tamu-a', verified=True, email=None):
        return {'email': email or tamu.email, 'sub': uid, 'email_verified': verified}

    def _login(self, identifier, password=SECRET_PW, client=None):
        client = client or self.client
        return client.post(
            LOGIN_URL,
            data=json.dumps({'identifier': identifier, 'password': password}),
            content_type='application/json',
        )

    def _patch_ok(self, tamu=None, **claim_kwargs):
        tamu = tamu or self.tamu_a
        return (
            mock.patch('guest_book.firebase_rest.requests.post',
                       return_value=_fb_response(200)),
            mock.patch('guest_book.firebase_rest.google_id_token.verify_firebase_token',
                       return_value=self._claims_for(tamu, **claim_kwargs)),
        )

    def _login_ok(self, identifier, tamu=None, **claim_kwargs):
        p1, p2 = self._patch_ok(tamu, **claim_kwargs)
        with p1, p2:
            return self._login(identifier)

    # ── login sah ─────────────────────────────────────────────────────────
    def test_valid_login_with_email(self):
        resp = self._login_ok(self.tamu_a.email)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()['success'])
        self.assertEqual(self.client.session['tamu_id'], str(self.tamu_a.pk))

    def test_valid_login_email_is_case_insensitive(self):
        resp = self._login_ok('  TAMU.A@Example.COM ')
        self.assertEqual(resp.status_code, 200)

    def test_valid_login_with_nik(self):
        resp = self._login_ok(self.tamu_a.nik)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.client.session['tamu_id'], str(self.tamu_a.pk))

    def test_response_never_contains_email(self):
        resp = self._login_ok(self.tamu_a.nik)
        self.assertNotIn(self.tamu_a.email.encode(), resp.content)

    def test_session_key_rotated_and_other_roles_purged(self):
        session = self.client.session
        session['pegawai_id'] = str(self.pegawai.pk)
        session['pegawai_name'] = 'x'
        session['pegawai_role'] = 'staff'
        session['is_admin'] = True
        session.save()
        old_key = self.client.session.session_key

        resp = self._login_ok(self.tamu_a.email)
        self.assertEqual(resp.status_code, 200)
        sess = self.client.session
        self.assertNotEqual(sess.session_key, old_key)
        for stale in ('pegawai_id', 'pegawai_name', 'pegawai_role', 'is_admin'):
            self.assertNotIn(stale, sess)
        self.assertEqual(sess['tamu_id'], str(self.tamu_a.pk))

    def test_unverified_email_unbound_uid_rejected(self):
        resp = self._login_ok(self.tamu_a.email, verified=False)
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn('tamu_id', self.client.session)

    def test_unverified_email_but_bound_uid_allowed(self):
        self.tamu_a.google_id = 'uid-tamu-a'
        self.tamu_a.save()
        resp = self._login_ok(self.tamu_a.email, verified=False)
        self.assertEqual(resp.status_code, 200)

    def test_uid_mismatch_rejected(self):
        self.tamu_a.google_id = 'uid-lain'
        self.tamu_a.save()
        resp = self._login_ok(self.tamu_a.email)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()['message'], GENERIC)
        self.assertNotIn('tamu_id', self.client.session)

    def test_token_email_mismatch_rejected(self):
        resp = self._login_ok(self.tamu_a.email, email='orang.lain@example.com')
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn('tamu_id', self.client.session)

    def test_successful_login_binds_uid(self):
        self._login_ok(self.tamu_a.email)
        self.tamu_a.refresh_from_db()
        self.assertEqual(self.tamu_a.google_id, 'uid-tamu-a')

    # ── kegagalan seragam ─────────────────────────────────────────────────
    def _failure_bodies(self):
        bodies = []
        with mock.patch('guest_book.firebase_rest.requests.post',
                        return_value=_fb_response(400, error='INVALID_PASSWORD')):
            bodies.append(self._login(self.tamu_a.email))                 # password salah
        for code in ('EMAIL_NOT_FOUND', 'TOO_MANY_ATTEMPTS_TRY_LATER',
                     'USER_DISABLED', 'INVALID_LOGIN_CREDENTIALS'):
            cache.clear()
            with mock.patch('guest_book.firebase_rest.requests.post',
                            return_value=_fb_response(400, error=code)):
                bodies.append(self._login(self.tamu_a.email))             # kode Firebase mentah
        cache.clear()
        with mock.patch('guest_book.firebase_rest.requests.post',
                        return_value=_fb_response(400, error='EMAIL_NOT_FOUND')):
            bodies.append(self._login('tidak.ada@example.com'))          # email tidak ada
            bodies.append(self._login('9999999999999999'))               # NIK tidak ada
            bodies.append(self._login('Tamu A'))                         # Nama tidak diterima
            bodies.append(self._login('!!!'))                            # format salah
        return bodies

    def test_all_failures_are_uniform(self):
        bodies = self._failure_bodies()
        for resp in bodies:
            self.assertEqual(resp.status_code, 401)
            self.assertEqual(resp.json(), {'success': False, 'message': GENERIC})
        self.assertEqual(len({r.content for r in bodies}), 1)

    def test_failures_do_not_leak_firebase_codes(self):
        for resp in self._failure_bodies():
            text = resp.content.decode()
            for needle in ('INVALID_PASSWORD', 'EMAIL_NOT_FOUND', 'TOO_MANY', 'USER_DISABLED'):
                self.assertNotIn(needle, text)

    def test_name_login_not_accepted(self):
        with mock.patch('guest_book.firebase_rest.requests.post') as post:
            post.return_value = _fb_response(200)
            resp = self._login(self.tamu_a.name)
        self.assertEqual(resp.status_code, 401)
        self.assertNotIn('tamu_id', self.client.session)

    def test_duplicate_nik_refused(self):
        Tamu.objects.filter(pk=self.tamu_b.pk).update(nik=self.tamu_a.nik)
        resp = self._login_ok(self.tamu_a.nik)
        self.assertEqual(resp.status_code, 401)

    # ── status akun ───────────────────────────────────────────────────────
    def test_inactive_account_rejected(self):
        for status in ('inactive', 'suspended'):
            cache.clear()
            Tamu.objects.filter(pk=self.tamu_a.pk).update(account_status=status)
            resp = self._login_ok(self.tamu_a.email)
            self.assertEqual(resp.status_code, 401)
            self.assertEqual(resp.json()['message'], GENERIC)
            self.assertNotIn('tamu_id', self.client.session)

    # ── kegagalan layanan Firebase ────────────────────────────────────────
    def test_firebase_network_failures_give_503_not_500(self):
        errors = (requests.exceptions.Timeout('x'), requests.exceptions.ConnectionError('x'),
                  requests.exceptions.SSLError('x'), requests.exceptions.RequestException('x'))
        for exc in errors:
            cache.clear()
            with mock.patch('guest_book.firebase_rest.requests.post', side_effect=exc):
                resp = self._login(self.tamu_a.email)
            self.assertEqual(resp.status_code, 503)
            self.assertFalse(resp.json()['success'])
            self.assertNotEqual(resp.json()['message'], GENERIC)
            self.assertNotIn('tamu_id', self.client.session)

    def test_firebase_5xx_gives_503(self):
        with mock.patch('guest_book.firebase_rest.requests.post',
                        return_value=_fb_response(502)):
            resp = self._login(self.tamu_a.email)
        self.assertEqual(resp.status_code, 503)

    def test_certificate_fetch_failure_gives_503(self):
        with mock.patch('guest_book.firebase_rest.requests.post',
                        return_value=_fb_response(200)), \
             mock.patch('guest_book.firebase_rest.google_id_token.verify_firebase_token',
                        side_effect=Exception('cert down')):
            resp = self._login(self.tamu_a.email)
        self.assertEqual(resp.status_code, 503)

    def test_invalid_token_is_uniform_failure(self):
        with mock.patch('guest_book.firebase_rest.requests.post',
                        return_value=_fb_response(200)), \
             mock.patch('guest_book.firebase_rest.google_id_token.verify_firebase_token',
                        side_effect=ValueError('bad')):
            resp = self._login(self.tamu_a.email)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()['message'], GENERIC)

    @override_settings(FIREBASE_API_KEY='')
    def test_missing_api_key_gives_503(self):
        resp = self._login(self.tamu_a.email)
        self.assertEqual(resp.status_code, 503)

    def test_unexpected_exception_gives_503(self):
        with mock.patch('guest_book.firebase_rest.sign_in_with_password',
                        side_effect=RuntimeError(SECRET_PW)):
            resp = self._login(self.tamu_a.email)
        self.assertEqual(resp.status_code, 503)
        self.assertNotIn(SECRET_PW.encode(), resp.content)

    def test_firebase_call_uses_10_second_timeout(self):
        with mock.patch('guest_book.firebase_rest.requests.post',
                        return_value=_fb_response(400, error='INVALID_PASSWORD')) as post:
            self._login(self.tamu_a.email)
        self.assertEqual(post.call_args.kwargs['timeout'], 10)

    # ── rate limit ────────────────────────────────────────────────────────
    def test_per_identifier_rate_limit(self):
        with mock.patch('guest_book.firebase_rest.requests.post',
                        return_value=_fb_response(400, error='INVALID_PASSWORD')):
            for _ in range(5):
                self.assertEqual(self._login(self.tamu_a.email).status_code, 401)
            blocked = self._login(self.tamu_a.email)
            self.assertEqual(blocked.status_code, 429)
            # Login sah pun ditolak selama diblokir
        resp = self._login_ok(self.tamu_a.email)
        self.assertEqual(resp.status_code, 429)
        # Identifier lain tidak terpengaruh
        resp = self._login_ok(self.tamu_b.email, tamu=self.tamu_b, uid='uid-b')
        self.assertEqual(resp.status_code, 200)

    def test_rate_limit_matches_email_and_nik_separately_but_case_insensitive(self):
        with mock.patch('guest_book.firebase_rest.requests.post',
                        return_value=_fb_response(400, error='INVALID_PASSWORD')):
            for variant in ('TAMU.A@example.com', 'tamu.a@EXAMPLE.com', 'Tamu.A@example.com',
                            'tamu.a@example.com', ' tamu.a@example.com '):
                self._login(variant)
            self.assertEqual(self._login('tamu.a@example.com').status_code, 429)

    def test_per_ip_rate_limit(self):
        with mock.patch('guest_book.firebase_rest.requests.post',
                        return_value=_fb_response(400, error='INVALID_PASSWORD')):
            for i in range(10):
                self.assertEqual(self._login(f'orang{i}@example.com').status_code, 401)
            self.assertEqual(self._login('baru@example.com').status_code, 429)

    def test_successful_login_resets_identifier_counter(self):
        with mock.patch('guest_book.firebase_rest.requests.post',
                        return_value=_fb_response(400, error='INVALID_PASSWORD')):
            for _ in range(3):
                self._login(self.tamu_a.email)
        self.assertEqual(self._login_ok(self.tamu_a.email).status_code, 200)
        with mock.patch('guest_book.firebase_rest.requests.post',
                        return_value=_fb_response(400, error='INVALID_PASSWORD')):
            for _ in range(5):
                self.assertEqual(self._login(self.tamu_a.email).status_code, 401)

    def test_cache_keys_do_not_contain_raw_identifier(self):
        with mock.patch('guest_book.firebase_rest.requests.post',
                        return_value=_fb_response(400, error='INVALID_PASSWORD')):
            self._login(self.tamu_a.email)
            self._login(self.tamu_a.nik)
        store = getattr(cache, '_cache', None)
        if store is None:
            self.skipTest('Backend cache tidak dapat diperiksa kuncinya.')
        keys = ' '.join(str(k) for k in store.keys())
        self.assertIn('rl_tlogin_id_', keys)
        self.assertNotIn(self.tamu_a.email, keys)
        self.assertNotIn(self.tamu_a.email.lower(), keys)
        self.assertNotIn(self.tamu_a.nik, keys)

    # ── password tidak boleh masuk log ────────────────────────────────────
    def _capture_logs(self):
        records = []

        class _H(logging.Handler):
            def emit(self, record):
                records.append(record)

        handler = _H(level=logging.DEBUG)
        root = logging.getLogger()
        old_level = root.level
        root.setLevel(logging.DEBUG)
        root.addHandler(handler)

        def done():
            root.removeHandler(handler)
            root.setLevel(old_level)
        return records, done

    def _assert_no_secret(self, records, *secrets):
        formatter = logging.Formatter()
        for rec in records:
            blob = formatter.format(rec)
            try:
                blob += ' ' + rec.getMessage()
            except Exception:
                pass
            blob += ' ' + repr(rec.args) + ' ' + repr(rec.__dict__.get('exc_text'))
            for secret in secrets:
                self.assertNotIn(secret, blob)

    def test_password_never_appears_in_logs(self):
        records, done = self._capture_logs()
        try:
            # sukses
            self._login_ok(self.tamu_a.email)
            self.client = Client()
            cache.clear()
            # password salah (Firebase menolak)
            with mock.patch('guest_book.firebase_rest.requests.post',
                            return_value=_fb_response(400, error='INVALID_PASSWORD')):
                self._login(self.tamu_a.email)
                self._login('tidak.ada@example.com')
            cache.clear()
            # jaringan gagal; pesan exception sengaja memuat password & email
            boom = requests.exceptions.ConnectionError(
                f'gagal https://x?key=test-key pw={SECRET_PW} {self.tamu_a.email}')
            with mock.patch('guest_book.firebase_rest.requests.post', side_effect=boom):
                self._login(self.tamu_a.email)
            cache.clear()
            # exception tak terduga di view
            with mock.patch('guest_book.firebase_rest.sign_in_with_password',
                            side_effect=RuntimeError(SECRET_PW)):
                self._login(self.tamu_a.email)
            cache.clear()
            # token tidak sah
            with mock.patch('guest_book.firebase_rest.requests.post',
                            return_value=_fb_response(200)), \
                 mock.patch('guest_book.firebase_rest.google_id_token.verify_firebase_token',
                            side_effect=ValueError(SECRET_PW)):
                self._login(self.tamu_a.email)
        finally:
            done()

        self.assertTrue(records, 'Seharusnya ada log keamanan yang dihasilkan.')
        self._assert_no_secret(records, SECRET_PW, 'test-key')

    def test_logs_do_not_contain_raw_email_or_nik(self):
        records, done = self._capture_logs()
        try:
            with mock.patch('guest_book.firebase_rest.requests.post',
                            return_value=_fb_response(400, error='INVALID_PASSWORD')):
                self._login(self.tamu_a.email)
                self._login(self.tamu_a.nik)
        finally:
            done()
        self.assertTrue(records)
        self._assert_no_secret(records, self.tamu_a.email, self.tamu_a.nik)

    def test_failed_login_record_stores_masked_identifier(self):
        from ..models import LoginAttempt
        with mock.patch('guest_book.firebase_rest.requests.post',
                        return_value=_fb_response(400, error='INVALID_PASSWORD')):
            self._login(self.tamu_a.email)
            self._login(self.tamu_a.nik)
        for attempt in LoginAttempt.objects.filter(user_type='tamu', success=False):
            self.assertNotIn(self.tamu_a.email, attempt.email)
            self.assertNotIn(self.tamu_a.nik, attempt.email)

    # ── CSRF / metode / endpoint lama ─────────────────────────────────────
    def test_csrf_enforced(self):
        client = Client(enforce_csrf_checks=True)
        resp = self._login(self.tamu_a.email, client=client)
        self.assertEqual(resp.status_code, 403)

    def test_get_not_allowed(self):
        self.assertEqual(self.client.get(LOGIN_URL).status_code, 405)

    def test_malformed_payloads_do_not_500(self):
        for body in ('not json', '[]', '{}', '{"identifier": 5, "password": 6}',
                     '{"identifier": "a@b.co"}'):
            resp = self.client.post(LOGIN_URL, data=body, content_type='application/json')
            self.assertEqual(resp.status_code, 400)

    def test_old_resolve_email_endpoint_is_gone(self):
        for method in ('get', 'post'):
            resp = getattr(self.client, method)('/api/auth/resolve-email/?username=tamu.a@example.com')
            self.assertEqual(resp.status_code, 404)
        with self.assertRaises(NoReverseMatch):
            reverse('tamu:api_resolve_email')

    def test_login_page_has_no_resolve_reference_and_new_hint(self):
        resp = self.client.get(reverse('tamu:login'))
        html = resp.content.decode()
        self.assertNotIn('resolve-email', html)
        self.assertNotIn('Nama Lengkap / Email', html)
        self.assertIn('Email / NIK', html)


class FirebaseRestUnitTests(BaseSecurityTestCase):
    @override_settings(FIREBASE_API_KEY='test-key')
    def test_sign_in_maps_statuses(self):
        cases = [
            (_fb_response(200), firebase_rest.OK),
            (_fb_response(400, error='INVALID_PASSWORD'), firebase_rest.INVALID),
            (_fb_response(429), firebase_rest.INVALID),
            (_fb_response(503), firebase_rest.UNAVAILABLE),
        ]
        for resp, expected in cases:
            with mock.patch('guest_book.firebase_rest.requests.post', return_value=resp):
                status, _ = firebase_rest.sign_in_with_password('a@b.co', 'pw')
            self.assertEqual(status, expected)
