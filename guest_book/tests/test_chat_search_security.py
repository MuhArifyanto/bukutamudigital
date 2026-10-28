"""
Pengujian komprehensif untuk Keamanan & Performa Pencarian Pengguna Chat (TUGAS 3.4).

Memastikan:
1. Akses anonim ditolak (401 Unauthorized).
2. Query < 2 karakter langsung mengembalikan list kosong tanpa menyentuh database (0 DB query).
3. Proteksi IDOR & Privasi: Tamu TIDAK BISA mencari atau melihat data sesama Tamu.
4. Tamu hanya bisa menemukan Pegawai yang memang ditugaskan pada kunjungannya.
5. Admin & Pegawai dapat mencari Tamu dan Pegawai aktif.
6. Optimasi kueri: select_related('department_rel') mencegah query N+1 pada data pegawai.
7. Rate Limiting: pemanggilan berlebih (>30 request/menit) dibatasi dengan HTTP 429.
8. Sanitasi Data: tidak ada NIK, telepon, atau password yang bocor di respons JSON.
"""

from datetime import datetime, date, timedelta, time
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.utils import timezone

from ..models import Tamu, Pegawai, Departemen, Instansi, Kunjungan, KunjunganStatus

SEARCH_URL = reverse('tamu:api_search_users')


class ChatSearchSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cache.clear()
        cls.instansi = Instansi.objects.create(
            nama="Diskominfosantik Kabupaten Bekasi",
            kapasitas_maksimal=50,
            status_operasional="Aktif",
            jam_buka=time(8, 0),
            jam_tutup=time(16, 0),
            hari_kerja="0,1,2,3,4,5,6"
        )
        cls.dept = Departemen.objects.create(nama="Bidang Tata Kelola TIK", kode="TIK")
        cls.pegawai_assigned = Pegawai.objects.create(
            name="Pegawai Ditugaskan",
            username="pegawai_assigned",
            email="assigned@bekasikab.go.id",
            phone="081234567801",
            department_rel=cls.dept,
            role="staff",
            account_status="active",
            password=make_password("password123")
        )
        cls.pegawai_lain = Pegawai.objects.create(
            name="Pegawai Tidak Terhubung",
            username="pegawai_lain",
            email="lain@bekasikab.go.id",
            phone="081234567802",
            department_rel=cls.dept,
            role="staff",
            account_status="active",
            password=make_password("password123")
        )

        cls.admin_user = User.objects.create_user(
            username="admin_chat_sec",
            email="admin_chat@bekasikab.go.id",
            password="adminpassword123",
            is_staff=True
        )

        cls.tamu_pemohon = Tamu.objects.create(
            name="Ahmad Tamu Pemohon",
            email="pemohon@example.com",
            phone="081234567891",
            nik="3216010101010001",
            instansi="PT Solusi Prima",
            account_status="active",
            registration_type="manual"
        )

        cls.tamu_lain = Tamu.objects.create(
            name="Budi Tamu Lain",
            email="budi.rahasia@example.com",
            phone="081234567892",
            nik="3216010101010002",
            instansi="CV Rahasia Negara",
            account_status="active",
            registration_type="manual"
        )

        # Kunjungan menghubungkan tamu_pemohon dengan pegawai_assigned
        cls.kunjungan = Kunjungan.objects.create(
            tamu=cls.tamu_pemohon,
            pegawai=cls.pegawai_assigned,
            arrival_time=timezone.now() + timedelta(days=1),
            status=KunjunganStatus.DISETUJUI,
            purpose="Konsultasi Proyek"
        )

    def setUp(self):
        cache.clear()

    def _login_tamu(self, tamu=None, client=None):
        c = client or self.client
        t = tamu or self.tamu_pemohon
        sess = c.session
        sess['tamu_id'] = str(t.id)
        sess['tamu_name'] = t.name
        sess['user_type'] = 'tamu'
        sess.save()
        return c

    def _login_admin(self, client=None):
        c = client or self.client
        c.force_login(self.admin_user)
        return c

    def _login_pegawai(self, pegawai=None, client=None):
        c = client or self.client
        p = pegawai or self.pegawai_assigned
        sess = c.session
        sess['pegawai_id'] = str(p.id)
        sess['pegawai_name'] = p.name
        sess['user_type'] = 'pegawai'
        sess.save()
        return c

    # ── 1. Otorisasi Anonim ───────────────────────────────────────────────────
    def test_anonymous_user_rejected_401(self):
        """Pengguna belum login harus ditolak 401."""
        resp = self.client.get(f"{SEARCH_URL}?q=Ahmad")
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(resp.json()['success'])

    # ── 2. Proteksi Full Table Scan pada Query Pendek ──────────────────────────
    def test_query_under_two_chars_returns_empty_instantly(self):
        """Query kurang dari 2 karakter langsung mengembalikan [] tanpa query tabel tamu/pegawai."""
        self._login_admin()
        # 2 query berasal dari SessionMiddleware & AuthenticationMiddleware Django, 0 query bisnis (tamu/pegawai)
        with self.assertNumQueries(2):
            resp = self.client.get(f"{SEARCH_URL}?q=a")
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.json()['users'], [])

    # ── 3. Proteksi IDOR & Privasi Tamu ───────────────────────────────────────
    def test_tamu_cannot_search_or_see_other_tamu(self):
        """Tamu TIDAK BOLEH bisa mencari sesama Tamu (mencegah kebocoran data identitas)."""
        self._login_tamu(self.tamu_pemohon)
        # Cari nama tamu lain
        resp = self.client.get(f"{SEARCH_URL}?q=Budi")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data['success'])
        # Hasil harus kosong; tidak boleh menemukan 'Budi Tamu Lain'
        found_types = [u['type'] for u in data['users']]
        self.assertNotIn('tamu', found_types)
        self.assertEqual(len(data['users']), 0)

    def test_tamu_can_only_search_assigned_pegawai(self):
        """Tamu hanya dapat menemukan pegawai yang menangani kunjungannya."""
        self._login_tamu(self.tamu_pemohon)
        # Cari kata kunci 'Pegawai' yang cocok dengan kedua pegawai
        resp = self.client.get(f"{SEARCH_URL}?q=Pegawai")
        self.assertEqual(resp.status_code, 200)
        users = resp.json()['users']
        user_ids = [u['id'] for u in users]

        # Pegawai yang ditugaskan harus muncul
        self.assertIn(str(self.pegawai_assigned.id), user_ids)
        # Pegawai yang tidak terhubung TIDAK BOLEH muncul
        self.assertNotIn(str(self.pegawai_lain.id), user_ids)

    # ── 4. Kemampuan Pencarian Admin & Pegawai ─────────────────────────────────
    def test_admin_can_search_both_tamu_and_pegawai(self):
        """Admin dapat mencari tamu dan pegawai aktif."""
        self._login_admin()

        # Cari tamu
        resp_tamu = self.client.get(f"{SEARCH_URL}?q=Budi")
        self.assertEqual(resp_tamu.status_code, 200)
        tamu_results = resp_tamu.json()['users']
        self.assertTrue(any(u['name'] == 'Budi Tamu Lain' and u['type'] == 'tamu' for u in tamu_results))

        # Cari pegawai
        resp_pegawai = self.client.get(f"{SEARCH_URL}?q=Ditugaskan")
        self.assertEqual(resp_pegawai.status_code, 200)
        pegawai_results = resp_pegawai.json()['users']
        self.assertTrue(any(u['name'] == 'Pegawai Ditugaskan' and u['type'] == 'pegawai' for u in pegawai_results))

    def test_pegawai_search_excludes_self(self):
        """Pegawai yang mencari tidak melihat dirinya sendiri dalam hasil pencarian."""
        self._login_pegawai(self.pegawai_assigned)
        resp = self.client.get(f"{SEARCH_URL}?q=Pegawai")
        self.assertEqual(resp.status_code, 200)
        user_ids = [u['id'] for u in resp.json()['users']]
        # Diri sendiri tidak muncul
        self.assertNotIn(str(self.pegawai_assigned.id), user_ids)
        # Rekan kerja lain muncul
        self.assertIn(str(self.pegawai_lain.id), user_ids)

    # ── 5. Optimasi Kueri & Pencegahan N+1 ─────────────────────────────────────
    def test_admin_search_queries_are_optimized_no_n_plus_one(self):
        """Pencarian pegawai menggunakan select_related('department_rel') sehingga tidak ada N+1 query."""
        self._login_admin()
        # 2 kueri middleware (session + auth) + 1 kueri tamu + 1 kueri pegawai (JOIN departemen) = 4 kueri (TIDAK ADA N+1!)
        with self.assertNumQueries(4):
            resp = self.client.get(f"{SEARCH_URL}?q=Pegawai")
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(len(resp.json()['users']) > 0)

    # ── 6. Sanitasi Respons (Tidak Membocorkan NIK/Telepon/Password) ───────────
    def test_no_sensitive_fields_leaked(self):
        """Respons tidak boleh mengandung NIK, nomor telepon, atau data sensitif lain."""
        self._login_admin()
        resp = self.client.get(f"{SEARCH_URL}?q=Budi")
        self.assertEqual(resp.status_code, 200)
        content_str = resp.content.decode('utf-8')

        # NIK tidak boleh muncul
        self.assertNotIn("3216010101010002", content_str)
        # Nomor telepon tidak boleh muncul
        self.assertNotIn("081234567892", content_str)
        # Password tidak boleh muncul
        self.assertNotIn("pbkdf2", content_str)

    # ── 7. Rate Limiting ──────────────────────────────────────────────────────
    def test_rate_limiting_enforced_after_limit(self):
        """Pemanggilan lebih dari 30 kali dalam semenit harus dibatasi dengan status 429."""
        self._login_admin()
        for i in range(30):
            r = self.client.get(f"{SEARCH_URL}?q=Budi")
            self.assertEqual(r.status_code, 200)

        # Panggilan ke-31 harus kena Rate Limit 429
        blocked_resp = self.client.get(f"{SEARCH_URL}?q=Budi")
        self.assertEqual(blocked_resp.status_code, 429)
        self.assertIn("Terlalu banyak", blocked_resp.json()['error'])
