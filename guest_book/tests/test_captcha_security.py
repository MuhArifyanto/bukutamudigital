import json
from datetime import timedelta
from django.urls import reverse
from django.utils import timezone
from django.test import RequestFactory, Client
from django.contrib.sessions.middleware import SessionMiddleware

from .base import BaseSecurityTestCase
from ..views.auth import validate_grid_captcha, PUZZLE_BANK, api_refresh_captcha


class CaptchaSecurityTestCase(BaseSecurityTestCase):
    """
    Test suite keamanan untuk Grid Selection Captcha:
    - Verifikasi jawaban sesuai sesi server diterima.
    - Pembuktian puzzle_index palsu dari klien diabaikan total.
    - Captcha bersifat sekali pakai (anti replay-attack).
    - Captcha yang kedaluwarsa (> 5 menit) ditolak.
    - Jawaban kosong atau sesi tanpa captcha ditolak.
    - Pembatasan laju (Rate Limiting) setelah 5 kali gagal.
    - Endpoint api_refresh_captcha tidak membocorkan kunci jawaban ke klien.
    """

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        self.refresh_url = reverse('tamu:api_refresh_captcha')

    def _create_request_with_session(self, ip='192.0.2.1'):
        request = self.factory.post('/test/', REMOTE_ADDR=ip)
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        return request

    def test_correct_answer_from_session_accepted(self):
        """Jawaban yang sesuai dengan expected index di session diterima."""
        request = self._create_request_with_session()
        target_idx = 0  # Lampu Lalu Lintas: [1, 2, 5, 6, 9, 10]
        request.session['captcha_expected_index'] = target_idx
        request.session['captcha_issued_at'] = timezone.now().timestamp()
        request.session.save()

        correct_tiles = PUZZLE_BANK[target_idx]['correct']
        success, msg = validate_grid_captcha(request, selected_tiles_json=correct_tiles)
        self.assertTrue(success)
        self.assertIn("berhasil", msg)

    def test_client_puzzle_index_ignored(self):
        """puzzle_index dari klien diabaikan; server hanya memverifikasi puzzle di session."""
        request = self._create_request_with_session()
        # Server mengharapkan puzzle 4 (Bus)
        request.session['captcha_expected_index'] = 4
        request.session['captcha_issued_at'] = timezone.now().timestamp()
        request.session.save()

        # Klien mencoba mengelabui dengan mengirim puzzle_index=0 dan jawaban puzzle 0
        fake_client_index = 0
        fake_client_tiles = PUZZLE_BANK[fake_client_index]['correct']

        success, msg = validate_grid_captcha(
            request,
            selected_tiles_json=fake_client_tiles,
            puzzle_index=fake_client_index
        )
        # Harus ditolak karena tidak cocok dengan puzzle 4 di server!
        self.assertFalse(success)
        self.assertIn("belum tepat", msg)

    def test_single_use_replay_attack_rejected(self):
        """Captcha bersifat sekali pakai; penggunaan ulang jawaban yang sama langsung ditolak."""
        request = self._create_request_with_session()
        target_idx = 1
        request.session['captcha_expected_index'] = target_idx
        request.session['captcha_issued_at'] = timezone.now().timestamp()
        request.session.save()

        correct_tiles = PUZZLE_BANK[target_idx]['correct']

        # Percobaan 1: Sukses
        success1, _ = validate_grid_captcha(request, selected_tiles_json=correct_tiles)
        self.assertTrue(success1)

        # Percobaan 2 dengan sesi yang sama tanpa refresh: Gagal (sesi sudah di-pop)
        success2, msg2 = validate_grid_captcha(request, selected_tiles_json=correct_tiles)
        self.assertFalse(success2)
        self.assertIn("tidak ditemukan atau telah kedaluwarsa", msg2)

    def test_expired_captcha_rejected(self):
        """Captcha yang diterbitkan lebih dari 5 menit lalu ditolak kedaluwarsa."""
        request = self._create_request_with_session()
        target_idx = 2
        # Terbit 6 menit yang lalu (360 detik)
        request.session['captcha_expected_index'] = target_idx
        request.session['captcha_issued_at'] = timezone.now().timestamp() - 360
        request.session.save()

        correct_tiles = PUZZLE_BANK[target_idx]['correct']
        success, msg = validate_grid_captcha(request, selected_tiles_json=correct_tiles)
        self.assertFalse(success)
        self.assertIn("kedaluwarsa", msg)

    def test_empty_answer_or_missing_session_rejected(self):
        """Jawaban kosong atau sesi tanpa captcha ditolak."""
        # 1. Sesi tanpa captcha
        request_no_cap = self._create_request_with_session()
        success, msg = validate_grid_captcha(request_no_cap, selected_tiles_json=[1, 2])
        self.assertFalse(success)

        # 2. Jawaban kosong
        request_empty = self._create_request_with_session()
        request_empty.session['captcha_expected_index'] = 0
        request_empty.session['captcha_issued_at'] = timezone.now().timestamp()
        request_empty.session.save()
        success_empty, msg_empty = validate_grid_captcha(request_empty, selected_tiles_json=[])
        self.assertFalse(success_empty)
        self.assertIn("tidak boleh kosong", msg_empty)

    def test_rate_limiting_after_excessive_failed_attempts(self):
        """Setelah 5 kali percobaan gagal dari IP yang sama, request ditolak sementara."""
        test_ip = '203.0.113.88'

        # Lakukan 5 kali percobaan gagal
        for _ in range(5):
            req = self._create_request_with_session(ip=test_ip)
            req.session['captcha_expected_index'] = 0
            req.session['captcha_issued_at'] = timezone.now().timestamp()
            req.session.save()
            validate_grid_captcha(req, selected_tiles_json=[999])

        # Percobaan ke-6 harus langsung diblokir oleh rate limit
        req_blocked = self._create_request_with_session(ip=test_ip)
        req_blocked.session['captcha_expected_index'] = 0
        req_blocked.session['captcha_issued_at'] = timezone.now().timestamp()
        req_blocked.session.save()
        success_blocked, msg_blocked = validate_grid_captcha(req_blocked, selected_tiles_json=[1, 2, 5, 6, 9, 10])
        self.assertFalse(success_blocked)
        self.assertIn("Terlalu banyak percobaan", msg_blocked)

    def test_api_refresh_captcha_returns_metadata_without_answers(self):
        """API refresh captcha mengembalikan label & imgUrl tanpa membocorkan kunci jawaban."""
        client = Client()
        resp = client.get(self.refresh_url)
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertTrue(data.get('success'))
        self.assertIn('label', data)
        self.assertIn('imgUrl', data)
        # Kunci jawaban TIDAK BOLEH dikirim ke klien
        self.assertNotIn('correct', data)
        self.assertNotIn('puzzle_index', data)
        self.assertNotIn('id', data)

        # Di sesi server harus tersimpan expected_index dan waktu terbit
        session = client.session
        self.assertIn('captcha_expected_index', session)
        self.assertIn('captcha_issued_at', session)
