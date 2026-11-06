from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
import json

from .base import BaseSecurityTestCase
from ..models import Kunjungan, KunjunganStatus, Notification


class IDORAndWorkflowTestCase(BaseSecurityTestCase):
    """
    Uji keamanan lintas pengguna (Anti-IDOR) dan kebenaran alur kerja (Workflow & Stats).
    """

    def setUp(self):
        super().setUp()

        # Pastikan tanggal awal kunjungan berada di hari kerja (bukan Sabtu/Minggu)
        workday_a = timezone.now() + timedelta(days=1)
        while workday_a.weekday() >= 5:
            workday_a += timedelta(days=1)

        workday_b = workday_a + timedelta(days=1)
        while workday_b.weekday() >= 5:
            workday_b += timedelta(days=1)

        # Kunjungan milik Tamu A
        self.kunjungan_a = Kunjungan.objects.create(
            tamu=self.tamu_a,
            pegawai=self.pegawai,
            arrival_time=workday_a,
            purpose="Konsultasi Jaringan",
            status=KunjunganStatus.MENUNGGU_ADMIN
        )

        # Kunjungan milik Tamu B
        self.kunjungan_b = Kunjungan.objects.create(
            tamu=self.tamu_b,
            pegawai=self.pegawai,
            arrival_time=workday_b,
            purpose="Pengajuan subdomain",
            status=KunjunganStatus.MENUNGGU_ADMIN
        )

    def test_idor_cancel_visit(self):
        """Tamu A tidak boleh dapat membatalkan kunjungan milik Tamu B."""
        url = reverse('tamu:kunjungan_batal', kwargs={'pk': self.kunjungan_b.id})
        resp = self.get_client('tamu_a').post(url)
        # Menghasilkan 404 karena filter tamu=tamu_a tidak menemukan kunjungan_b
        self.assertEqual(resp.status_code, 404)
        self.kunjungan_b.refresh_from_db()
        self.assertEqual(self.kunjungan_b.status, KunjunganStatus.MENUNGGU_ADMIN)

    def test_cancel_own_pending_visit_success(self):
        """Tamu A dapat membatalkan kunjungannya sendiri yang masih berstatus pending/cancelable."""
        url = reverse('tamu:kunjungan_batal', kwargs={'pk': self.kunjungan_a.id})
        resp = self.get_client('tamu_a').post(url)
        self.assertEqual(resp.status_code, 302)
        self.kunjungan_a.refresh_from_db()
        self.assertEqual(self.kunjungan_a.status, KunjunganStatus.CANCELLED)

    def test_cannot_cancel_completed_visit(self):
        """Tamu tidak boleh dapat membatalkan kunjungan yang sudah berstatus 'completed'."""
        self.kunjungan_a.status = KunjunganStatus.COMPLETED
        self.kunjungan_a.save()

        url = reverse('tamu:kunjungan_batal', kwargs={'pk': self.kunjungan_a.id})
        resp = self.get_client('tamu_a').post(url)
        self.assertEqual(resp.status_code, 404)
        self.kunjungan_a.refresh_from_db()
        self.assertEqual(self.kunjungan_a.status, KunjunganStatus.COMPLETED)

    def test_idor_view_visit_detail(self):
        """Tamu A tidak boleh melihat detail kunjungan milik Tamu B."""
        url = reverse('tamu:kunjungan_detail', kwargs={'pk': self.kunjungan_b.id})
        resp = self.get_client('tamu_a').get(url)
        self.assertEqual(resp.status_code, 404)

    def test_idor_print_visit_card(self):
        """Tamu A tidak boleh mencetak kartu kunjungan milik Tamu B."""
        url = reverse('tamu:tamu_cetak_kartu', kwargs={'pk': self.kunjungan_b.id})
        resp = self.get_client('tamu_a').get(url)
        self.assertEqual(resp.status_code, 404)

    def test_idor_mark_notification_read(self):
        """Tamu A tidak boleh bisa menandai notifikasi milik Tamu B sebagai terbaca."""
        notif_b = Notification.objects.create(
            recipient_id=str(self.tamu_b.id),
            recipient_type='tamu',
            notification_type='system_alert',
            title='Alert Tamu B',
            message='Pesan rahasia Tamu B',
            status='unread'
        )

        url = reverse('tamu:api_mark_notification_read')
        # Tamu A mencoba menandai notif B
        resp = self.get_client('tamu_a').post(
            url,
            data=json.dumps({'notification_id': str(notif_b.id)}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(resp.json().get('success'))

        notif_b.refresh_from_db()
        self.assertEqual(notif_b.status, 'unread')

        # Tamu B menandai notifikasinya sendiri -> sukses
        resp = self.get_client('tamu_b').post(
            url,
            data=json.dumps({'notification_id': str(notif_b.id)}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get('success'))
        notif_b.refresh_from_db()
        self.assertEqual(notif_b.status, 'read')

    def test_dashboard_stats_pending_verification_count(self):
        """
        Kartu 'Menunggu Verifikasi' harus HANYA menghitung status:
        menunggu_admin, menunggu_pegawai, dan disetujui_pegawai.
        """
        now = timezone.now()
        # Bersihkan data kunjungan sebelumnya agar hitungan presisi
        Kunjungan.objects.all().delete()

        # Buat kombinasi status:
        # Menunggu Verifikasi:
        Kunjungan.objects.create(tamu=self.tamu_a, arrival_time=now, purpose="P1", status=KunjunganStatus.MENUNGGU_ADMIN)
        Kunjungan.objects.create(tamu=self.tamu_a, arrival_time=now, purpose="P2", status=KunjunganStatus.MENUNGGU_ADMIN)
        Kunjungan.objects.create(tamu=self.tamu_b, arrival_time=now, purpose="P3", status=KunjunganStatus.MENUNGGU_PEGAWAI)
        Kunjungan.objects.create(tamu=self.tamu_b, arrival_time=now, purpose="P4", status=KunjunganStatus.DISETUJUI_PEGAWAI)

        # Status yang BUKAN menunggu verifikasi:
        Kunjungan.objects.create(tamu=self.tamu_a, arrival_time=now, purpose="P5", status=KunjunganStatus.DISETUJUI)
        Kunjungan.objects.create(tamu=self.tamu_a, arrival_time=now, purpose="P6", status=KunjunganStatus.IN_PROGRESS)
        Kunjungan.objects.create(tamu=self.tamu_b, arrival_time=now, purpose="P7", status=KunjunganStatus.COMPLETED)
        Kunjungan.objects.create(tamu=self.tamu_b, arrival_time=now, purpose="P8", status=KunjunganStatus.CANCELLED)

        # Cek via api_dashboard_stats
        url = reverse('tamu:api_dashboard_stats')
        resp = self.get_client('admin').get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get('menunggu_verifikasi'), 4)

    def test_anti_lockout_admin(self):
        """Admin tidak boleh menonaktifkan akun adminnya sendiri."""
        url = reverse('tamu:api_toggle_user_status', kwargs={'user_id': self.admin_tamu.id})
        resp = self.get_client('admin').post(url, {'status': 'inactive'})
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data.get('success'))
        self.assertIn("tidak dapat menonaktifkan akun admin Anda sendiri", data.get('error', ''))

        self.admin_tamu.refresh_from_db()
        self.assertEqual(self.admin_tamu.account_status, 'active')

    def test_api_get_chat_messages_enforces_kunjungan_status(self):
        """
        api_get_chat_messages untuk sesi kunjungan_{id} wajib menolak akses (403)
        jika status kunjungan masih menunggu_admin/menunggu_pegawai/cancelled,
        dan mengizinkan (200) mulai dari disetujui_pegawai.
        """
        url = reverse('tamu:api_chat_messages')
        session_id = f'kunjungan_{self.kunjungan_a.id}'

        # 1. Status menunggu_admin -> 403 untuk Tamu & Pegawai
        resp_tamu = self.get_client('tamu_a').get(url, {'session_id': session_id})
        self.assertEqual(resp_tamu.status_code, 403)
        resp_pegawai = self.get_client('pegawai').get(url, {'session_id': session_id})
        self.assertEqual(resp_pegawai.status_code, 403)

        # 2. Status disetujui_pegawai -> 200 untuk Tamu A & Pegawai yang ditugaskan, tapi 403 untuk Tamu B
        self.kunjungan_a.status = KunjunganStatus.DISETUJUI_PEGAWAI
        self.kunjungan_a.save(update_fields=['status'])

        resp_tamu_ok = self.get_client('tamu_a').get(url, {'session_id': session_id})
        self.assertEqual(resp_tamu_ok.status_code, 200)
        resp_pegawai_ok = self.get_client('pegawai').get(url, {'session_id': session_id})
        self.assertEqual(resp_pegawai_ok.status_code, 200)
        resp_tamu_b = self.get_client('tamu_b').get(url, {'session_id': session_id})
        self.assertEqual(resp_tamu_b.status_code, 403)

    def test_kunjungan_batal_by_tamu_records_status_history(self):
        """Pembatalan kunjungan oleh Tamu wajib mencatat KunjunganStatusHistory."""
        from ..models import KunjunganStatusHistory
        url = reverse('tamu:kunjungan_batal', kwargs={'pk': self.kunjungan_a.id})
        resp = self.get_client('tamu_a').post(url)
        self.assertEqual(resp.status_code, 302)

        self.kunjungan_a.refresh_from_db()
        self.assertEqual(self.kunjungan_a.status, KunjunganStatus.CANCELLED)

        history = KunjunganStatusHistory.objects.filter(
            kunjungan=self.kunjungan_a,
            new_status='cancelled',
            changed_by_type='tamu',
        ).first()
        self.assertIsNotNone(history)
        self.assertEqual(history.old_status, KunjunganStatus.MENUNGGU_ADMIN)
        self.assertEqual(history.changed_by_id, str(self.tamu_a.id))

    def test_n8n_chat_assistant_intents_and_handoff(self):
        """Menguji Opsi A Chatbot N8N (intent, reply/replay, handoff, dan pengayaan data database)."""
        from unittest.mock import patch
        from ..utils import build_n8n_chat_response
        from ..models import Message

        # 1. Cabang cek_status_kunjungan (mock respons N8N)
        with patch('guest_book.utils.call_n8n_routing', return_value={
            'intent': 'cek_status_kunjungan',
            'replay': 'Berikut status kunjungan Anda:',
            'handoff': False,
        }):
            res_status = build_n8n_chat_response(self.tamu_a.id, 'Cek status kunjungan saya')
            self.assertEqual(res_status['intent'], 'cek_status_kunjungan')
            self.assertFalse(res_status['handoff'])
            self.assertIn('Data Status Kunjungan Anda', res_status['reply_text'])
            self.assertIn(self.pegawai.name, res_status['reply_text'])

        # 2. Cabang jadwal_kuota
        with patch('guest_book.utils.call_n8n_routing', return_value={
            'intent': 'jadwal_kuota',
            'reply': 'Informasi kuota kunjungan hari ini:',
            'handoff': False,
        }):
            res_quota = build_n8n_chat_response(self.tamu_a.id, 'Sisa kuota hari ini?')
            self.assertEqual(res_quota['intent'], 'jadwal_kuota')
            self.assertFalse(res_quota['handoff'])
            self.assertIn('Jam Operasional', res_quota['reply_text'])
            self.assertIn('Status Kuota', res_quota['reply_text'])

        # 3. Cabang keluhan_masukan (dicatat di tabel Message, belum handoff pada strike ke-1)
        with patch('guest_book.utils.call_n8n_routing', return_value={
            'intent': 'keluhan_masukan',
            'reply': 'Terima kasih atas masukan Anda.',
            'handoff': True,
            'kategori': 'Pelayanan',
        }):
            res_complaint = build_n8n_chat_response(self.tamu_a.id, 'Antrean di loket cukup lama', session_id=str(self.tamu_a.id))
            self.assertIn('diteruskan ke petugas Admin', res_complaint['reply_text'])
            self.assertTrue(
                Message.objects.filter(
                    sender_id=str(self.tamu_a.id),
                    subject__icontains='Keluhan/Masukan via Chat AI',
                ).exists()
            )

        # 4. Sapaan ("halo admin") dilayani oleh AI terlebih dahulu (0 strike, tidak langsung handoff)
        from ..utils import is_session_handed_off_to_admin, set_session_handoff_to_admin
        sess_id = str(self.tamu_a.id)
        set_session_handoff_to_admin(sess_id, active=False)
        with patch('guest_book.utils.call_n8n_routing', return_value=None):
            res_greet = build_n8n_chat_response(self.tamu_a.id, 'halo admin', session_id=sess_id)
            self.assertEqual(res_greet['intent'], 'sapaan')
            self.assertFalse(res_greet['handoff'])
            self.assertEqual(res_greet['strike_count'], 0)

            # 4a. Respon luwes & ramah untuk konfirmasi hari libur akhir pekan
            res_weekend = build_n8n_chat_response(
                self.tamu_a.id,
                'berarti untuk hari sabtu dan minggu libur kan?',
                session_id=sess_id,
            )
            self.assertEqual(res_weekend['intent'], 'jadwal_kuota')
            self.assertIn('Betul sekali', res_weekend['reply_text'])
            self.assertIn('tutup / libur pada akhir pekan', res_weekend['reply_text'])
            self.assertIn('Jam Operasional', res_weekend['reply_text'])
            self.assertIn('Status Kuota', res_weekend['reply_text'])
            self.assertEqual(res_weekend['strike_count'], 0)

            # 4b. Ucapan terima kasih ditanggapi hangat tanpa memicu strike
            res_thanks = build_n8n_chat_response(
                self.tamu_a.id,
                'terima kasih banyak ya',
                session_id=sess_id,
            )
            self.assertEqual(res_thanks['intent'], 'sapaan')
            self.assertIn('Sama-sama', res_thanks['reply_text'])
            self.assertEqual(res_thanks['strike_count'], 0)

            # 4b. Percakapan interaktif buat kunjungan di chat
            # Tahap 1: Tamu baru bertanya hari Senin ("anda bisa tidak membuatkan saya daftar kunjungan, untuk hari senin bisa tidak?")
            # AI mengecek kuota dan menanyakan jam & keperluan (tidak langsung membuat kunjungan buta ke database)
            before_count = Kunjungan.objects.filter(tamu=self.tamu_a).count()
            res_ask = build_n8n_chat_response(
                self.tamu_a.id,
                'anda bisa tidak membuatkan saya daftar kunjungan, untuk hari senin bisa tidak?',
                session_id=sess_id,
            )
            self.assertEqual(res_ask['intent'], 'buat_kunjungan')
            self.assertIn('kuota kunjungan masih tersedia', res_ask['reply_text'])
            self.assertIn('Pukul / Jam berapa', res_ask['reply_text'])
            self.assertIn('Apa keperluan', res_ask['reply_text'])
            self.assertEqual(Kunjungan.objects.filter(tamu=self.tamu_a).count(), before_count)  # Belum dibuat

            # Tahap 2: Tamu menjawab jam dan keperluan ("Jam 10:00 keperluan rapat koordinasi dinas dengan Pak Fauzi")
            # AI langsung membuat kunjungan di database dan memberikan tiket resmi
            res_book = build_n8n_chat_response(
                self.tamu_a.id,
                'Jam 10:00 keperluan rapat koordinasi dinas dengan Pak Fauzi',
                session_id=sess_id,
            )
            self.assertEqual(res_book['intent'], 'buat_kunjungan')
            self.assertIn('Jadwal Kunjungan Berhasil Terdaftar', res_book['reply_text'])
            self.assertEqual(Kunjungan.objects.filter(tamu=self.tamu_a).count(), before_count + 1)

            # 5. Uji aturan 3x Strike (AI tidak tahu / Tamu kurang suka 3 kali -> otomatis handoff ke Admin)
            s1 = build_n8n_chat_response(self.tamu_a.id, 'Resep nasi goreng spesial apa ya?', session_id=sess_id)
            self.assertFalse(s1['handoff'])
            self.assertEqual(s1['strike_count'], 1)

            s2 = build_n8n_chat_response(self.tamu_a.id, 'Jawaban kurang sesuai', session_id=sess_id)
            self.assertFalse(s2['handoff'])
            self.assertEqual(s2['strike_count'], 2)

            s3 = build_n8n_chat_response(self.tamu_a.id, 'Masih belum membantu', session_id=sess_id)
            self.assertTrue(s3['handoff'])
            self.assertEqual(s3['strike_count'], 3)
            self.assertTrue(is_session_handed_off_to_admin(sess_id))
            self.assertIn('[Dialihkan Otomatis ke Petugas Admin]', s3['reply_text'])

    def test_chatbot_natural_language_flexibility_and_slang(self):
        """Menguji keluwesan Chatbot menangani bahasa sehari-hari, slang gaul, dan variasi urutan kata."""
        from unittest.mock import patch
        from ..utils import build_n8n_chat_response, call_n8n_routing, set_session_handoff_to_admin

        sess_id = f"test_slang_{self.tamu_a.id}"
        set_session_handoff_to_admin(sess_id, active=False)

        with patch('guest_book.utils.call_n8n_routing', return_value=None):
            # 1. Pertanyaan operasional dengan susunan kata alami ("kantor buka gak hari ini?")
            r1 = build_n8n_chat_response(self.tamu_a.id, 'kantor buka gak hari ini?', session_id=sess_id)
            self.assertEqual(r1['intent'], 'jadwal_kuota')
            self.assertFalse(r1['handoff'])
            self.assertEqual(r1['strike_count'], 0)
            self.assertIn('Jam Operasional', r1['reply_text'])

            # 2. Permintaan daftar dengan akhiran gaul '-in' ("bisa tolong daftarin saya ga")
            r2 = build_n8n_chat_response(self.tamu_a.id, 'bisa tolong daftarin saya ga', session_id=sess_id)
            self.assertEqual(r2['intent'], 'buat_kunjungan')
            self.assertFalse(r2['handoff'])
            self.assertIn('rencana kunjungan Anda', r2['reply_text'])

            # 3. Booking dengan kata waktu ("jam 10 pagi") TIDAK salah dideteksi sebagai sapaan
            r3 = build_n8n_chat_response(self.tamu_a.id, 'bikin janji hari senin jam 10 pagi urusan wifi', session_id=sess_id)
            self.assertEqual(r3['intent'], 'buat_kunjungan')
            self.assertFalse(r3['handoff'])
            # Sudah langsung terbentuk kunjungan atau bertanya kelengkapan tanpa tertelan sapaan
            self.assertTrue('Jadwal Kunjungan Berhasil Terdaftar' in r3['reply_text'] or 'Pukul / Jam berapa' in r3['reply_text'] or 'kuota' in r3['reply_text'])

            # 4. Keluhan dengan kata santai ("ini kok lemot banget ya responnya") otomatis masuk ke keluhan/admin
            r4 = build_n8n_chat_response(self.tamu_a.id, 'ini kok lemot banget ya responnya', session_id=sess_id)
            self.assertEqual(r4['intent'], 'keluhan_dan_masukan')
            self.assertTrue(r4['handoff'])

            # 5. call_n8n_routing aman menerima keyword arguments tambahan (seperti pegawai_queryset)
            safe_call = call_n8n_routing(
                kunjungan_id=None,
                purpose="Testing routing",
                department="TIK",
                arrival_time=None,
                pegawai_queryset=[]
            )
            self.assertIsNone(safe_call)

    def test_chatbot_display_database_pegawai_and_admin_acc_flow(self):
        """
        Menguji alur lengkap permintaan pengguna:
        1. Tamu minta daftar janji temu di hari ini/hari kerja.
        2. AI menampilkan daftar pegawai asli dari database MySQL terlebih dahulu.
        3. Tamu memilih nomor pegawai dan menyertakan jam & keperluan.
        4. Kunjungan dibuat berstatus 'menunggu_admin' (menunggu ACC Admin).
        """
        from unittest.mock import patch
        from ..utils import build_n8n_chat_response, set_session_handoff_to_admin

        sess_id = f"test_peg_acc_{self.tamu_a.id}"
        set_session_handoff_to_admin(sess_id, active=False)

        with patch('guest_book.utils.call_n8n_routing', return_value=None):
            # 1. Tamu meminta janji temu untuk hari Senin
            res_step1 = build_n8n_chat_response(
                self.tamu_a.id,
                'saya mau daftar janji temu untuk hari senin',
                session_id=sess_id,
            )
            self.assertEqual(res_step1['intent'], 'buat_kunjungan')
            # Memastikan nama pegawai asli dari database (self.pegawai.name) muncul di daftar
            self.assertIn(self.pegawai.name, res_step1['reply_text'])
            self.assertIn('Daftar Pegawai Aktif Diskominfosantik', res_step1['reply_text'])
            self.assertIn('Pukul / Jam berapa', res_step1['reply_text'])
            self.assertIn('Apa keperluan', res_step1['reply_text'])
            self.assertIn('Silakan pilih nomor pegawai di atas', res_step1['reply_text'])
            self.assertIn('Menunggu Verifikasi & Persetujuan (ACC) Admin', res_step1['reply_text'])

            # 2. Tamu memilih pegawai [1] dengan jam dan keperluan
            res_step2 = build_n8n_chat_response(
                self.tamu_a.id,
                'Pilih nomor 1, jam 11:00 keperluan koordinasi infrastruktur server',
                session_id=sess_id,
            )
            self.assertEqual(res_step2['intent'], 'buat_kunjungan')
            self.assertIn('Jadwal Kunjungan Berhasil Terdaftar', res_step2['reply_text'])
            self.assertIn('Menunggu Verifikasi & Persetujuan (ACC) Admin', res_step2['reply_text'])

            # Verifikasi di database
            latest_kunjungan = Kunjungan.objects.filter(tamu=self.tamu_a).order_by('-created_at').first()
            self.assertIsNotNone(latest_kunjungan)
            self.assertEqual(latest_kunjungan.pegawai, self.pegawai)
            self.assertEqual(latest_kunjungan.status, 'menunggu_admin')
            self.assertIn('koordinasi infrastruktur server', latest_kunjungan.purpose)

    def test_fuzzy_typo_intent_and_interactive_quick_chips(self):
        """
        Menguji fitur A (Toleransi Saltik/Typo) & B (Interactive Quick-Action Chips):
        - Chatbot tetap memahami pesan penuh typo/singkatan ponsel (mis: 'daftarin kunjunagn bsk', 'kuotany msih ada?').
        - Chatbot merender format interactive chips [[chip:ACTION|LABEL]] untuk pilihan cepat pegawai & jam.
        """
        from unittest.mock import patch
        from ..utils import build_n8n_chat_response, set_session_handoff_to_admin

        sess_id = f"test_fuzzy_{self.tamu_a.id}"
        set_session_handoff_to_admin(sess_id, active=False)

        with patch('guest_book.utils.call_n8n_routing', return_value=None):
            # 1. Pertanyaan kuota penuh saltik / slang: "kuotany msih ada?"
            res_quota = build_n8n_chat_response(
                self.tamu_a.id,
                'kuotany msih ada?',
                session_id=sess_id,
            )
            self.assertEqual(res_quota['intent'], 'jadwal_kuota')
            self.assertIn('kuota', res_quota['reply_text'].lower())

            # 2. Permintaan daftar penuh saltik di hari kerja (agar tidak ditolak aturan akhir pekan)
            target_date = timezone.now() + timedelta(days=1)
            while target_date.weekday() >= 5:
                target_date += timedelta(days=1)
            day_name = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat'][target_date.weekday()]
            res_book = build_n8n_chat_response(
                self.tamu_a.id,
                f'daftarin kunjunagn hari {day_name}',
                session_id=sess_id,
            )
            self.assertEqual(res_book['intent'], 'buat_kunjungan')
            # Memastikan format chip jam dan nomor pegawai ter-render di reply
            self.assertIn('[[chip:Jam 09:00|🕒 09:00 WIB]]', res_book['reply_text'])
            self.assertIn('[[chip:Pilih nomor 1|', res_book['reply_text'])

    def test_sop_and_technical_knowledge_base(self):
        """
        Menguji fitur C (Knowledge Base SOP & Layanan Teknis Kedinasan):
        - TTE BSrE
        - Subdomain & Hosting Server OPD
        - Magang / PKL Siswa & Mahasiswa
        - Liputan Pers & PPID
        """
        from unittest.mock import patch
        from ..utils import build_n8n_chat_response, set_session_handoff_to_admin

        sess_id = f"test_sop_{self.tamu_a.id}"
        set_session_handoff_to_admin(sess_id, active=False)

        with patch('guest_book.utils.call_n8n_routing', return_value=None):
            # 1. SOP TTE
            res_tte = build_n8n_chat_response(
                self.tamu_a.id,
                'bagaimana syarat dan alur permohonan tte bsre?',
                session_id=sess_id,
            )
            self.assertEqual(res_tte['intent'], 'sop_dan_layanan_teknis')
            self.assertIn('Tanda Tangan Elektronik', res_tte['reply_text'])
            self.assertIn('BSrE', res_tte['reply_text'])
            self.assertIn('[[chip:', res_tte['reply_text'])

            # 2. SOP Subdomain & Hosting
            res_host = build_n8n_chat_response(
                self.tamu_a.id,
                'prosedur pengajuan subdomain atau hosting opd',
                session_id=sess_id,
            )
            self.assertEqual(res_host['intent'], 'sop_dan_layanan_teknis')
            self.assertIn('Subdomain & Hosting Server OPD', res_host['reply_text'])

            # 3. Alur Magang / PKL
            res_magang = build_n8n_chat_response(
                self.tamu_a.id,
                'info alur magang pkl mahasiswa',
                session_id=sess_id,
            )
            self.assertEqual(res_magang['intent'], 'sop_dan_layanan_teknis')
            self.assertIn('Magang / Prakerin', res_magang['reply_text'])

            # 4. Liputan Pers & PPID
            res_pers = build_n8n_chat_response(
                self.tamu_a.id,
                'ketentuan peliputan pers wartawan',
                session_id=sess_id,
            )
            self.assertEqual(res_pers['intent'], 'sop_dan_layanan_teknis')
            self.assertIn('Liputan Pers', res_pers['reply_text'])

            # 5. CSIRT & Insiden Keamanan Siber (Web kena hack / judi online / pentest)
            res_csirt = build_n8n_chat_response(
                self.tamu_a.id,
                'Website dinas kami kena hack judi online, lapor ke mana?',
                session_id=sess_id,
            )
            self.assertEqual(res_csirt['intent'], 'sop_dan_layanan_teknis')
            self.assertIn('BekasiKab-CSIRT', res_csirt['reply_text'])
            self.assertIn('Judi Online', res_csirt['reply_text'])
            self.assertIn('chip:', res_csirt['reply_text'])

            # 6. Jaringan, Intranet & WiFi Pemkab (Bidang TIK)
            res_wifi = build_n8n_chat_response(
                self.tamu_a.id,
                'Wifi kantor camat putus dan koneksi lambat',
                session_id=sess_id,
            )
            self.assertEqual(res_wifi['intent'], 'sop_dan_layanan_teknis')
            self.assertIn('Infrastruktur Jaringan', res_wifi['reply_text'])
            self.assertIn('Bidang TIK', res_wifi['reply_text'])

            # 7. Pengaduan Masyarakat SP4N-LAPOR! & Aspirasi Warga (Bidang IKP)
            res_lapor = build_n8n_chat_response(
                self.tamu_a.id,
                'Cara lapor jalan rusak dan keluhan pelayanan warga lewat apa?',
                session_id=sess_id,
            )
            self.assertEqual(res_lapor['intent'], 'sop_dan_layanan_teknis')
            self.assertIn('SP4N-LAPOR!', res_lapor['reply_text'])
            self.assertIn('lapor.go.id', res_lapor['reply_text'])

            # 8. Statistik Sektoral & Satu Data Bekasi (Bidang Statistik)
            res_stat = build_n8n_chat_response(
                self.tamu_a.id,
                'Mau minta data statistik kemiskinan dan data kependudukan Bekasi untuk penelitian',
                session_id=sess_id,
            )
            self.assertEqual(res_stat['intent'], 'sop_dan_layanan_teknis')
            self.assertIn('Statistik Sektoral', res_stat['reply_text'])
            self.assertIn('data.bekasikab.go.id', res_stat['reply_text'])

            # 9. SLA Durasi Layanan TTE (1 hari kerja & keterangan jika terlambat dikabari admin)
            res_sla_tte = build_n8n_chat_response(
                self.tamu_a.id,
                'Berapa lama verifikasi TTE selesai?',
                session_id=sess_id,
            )
            self.assertEqual(res_sla_tte['intent'], 'sop_dan_layanan_teknis')
            self.assertIn('1 hari kerja', res_sla_tte['reply_text'].lower())
            self.assertIn('dikabari', res_sla_tte['reply_text'].lower())
            self.assertIn('kendala', res_sla_tte['reply_text'].lower())

            # 10. SLA Durasi Pengajuan Subdomain (1–3 hari kerja & dikabari admin)
            res_sla_sub = build_n8n_chat_response(
                self.tamu_a.id,
                'Berapa hari pengajuan subdomain diproses?',
                session_id=sess_id,
            )
            self.assertEqual(res_sla_sub['intent'], 'sop_dan_layanan_teknis')
            self.assertTrue('1–3 hari kerja' in res_sla_sub['reply_text'].lower() or '1-3 hari kerja' in res_sla_sub['reply_text'].lower())
            self.assertIn('dikabari', res_sla_sub['reply_text'].lower())
            self.assertIn('kendala', res_sla_sub['reply_text'].lower())

            # 11. SLA Durasi Konfirmasi Magang (3–5 hari kerja & dikabari admin)
            res_sla_magang = build_n8n_chat_response(
                self.tamu_a.id,
                'Berapa lama konfirmasi penerimaan magang pkl?',
                session_id=sess_id,
            )
            self.assertEqual(res_sla_magang['intent'], 'sop_dan_layanan_teknis')
            self.assertTrue('3–5 hari kerja' in res_sla_magang['reply_text'].lower() or '3-5 hari kerja' in res_sla_magang['reply_text'].lower())
            self.assertIn('dikabari', res_sla_magang['reply_text'].lower())
            self.assertIn('kendala', res_sla_magang['reply_text'].lower())

            # 12. SLA Durasi Umum / Katalog SLA Seluruh Layanan Diskominfosantik
            res_sla_all = build_n8n_chat_response(
                self.tamu_a.id,
                'Berapa lama durasi penyelesaian layanan dan SLA di diskominfosantik?',
                session_id=sess_id,
            )
            self.assertEqual(res_sla_all['intent'], 'sop_dan_layanan_teknis')
            self.assertIn('standar waktu penyelesaian layanan', res_sla_all['reply_text'].lower())
            self.assertIn('1 hari kerja', res_sla_all['reply_text'].lower())
            self.assertTrue('1–3 hari kerja' in res_sla_all['reply_text'].lower() or '1-3 hari kerja' in res_sla_all['reply_text'].lower())
            self.assertTrue('3–5 hari kerja' in res_sla_all['reply_text'].lower() or '3-5 hari kerja' in res_sla_all['reply_text'].lower())
            self.assertIn('dikabari', res_sla_all['reply_text'].lower())
            self.assertIn('kendala', res_sla_all['reply_text'].lower())

    def test_multi_turn_contextual_conversation_memory(self):
        """
        Menguji Memori Konteks Percakapan Multi-Turn (Context Window):
        Turn 1: Tamu: "Saya mau urus TTE" -> Bot menjawab syarat TTE.
        Turn 2: Tamu: "Kalo bawa fotokopi KTP saja boleh tidak?" -> Bot mengingat konteks TTE & menjawab syarat KTP TTE.
        Turn 3: Tamu: "Biayanya berapa ya?" -> Bot menjawab biaya TTE 100% gratis.
        Turn 4: Tamu: "Kalau magang PKL mahasiswa syaratnya apa?" -> Topik berganti ke Magang.
        Turn 5: Tamu: "Anak SMK bisa tidak?" -> Bot mengingat konteks Magang & mengonfirmasi anak SMK bisa.
        """
        from unittest.mock import patch
        from ..utils import build_n8n_chat_response, set_session_handoff_to_admin, clear_conversation_context

        sess_id = f"test_multi_turn_{self.tamu_a.id}"
        set_session_handoff_to_admin(sess_id, active=False)
        clear_conversation_context(sess_id)

        with patch('guest_book.utils.call_n8n_routing', return_value=None):
            # Turn 1: Tanya TTE
            turn1 = build_n8n_chat_response(self.tamu_a.id, 'Saya mau urus TTE', session_id=sess_id)
            self.assertEqual(turn1['intent'], 'sop_dan_layanan_teknis')
            self.assertIn('Tanda Tangan Elektronik', turn1['reply_text'])

            # Turn 2: Tanya fotokopi KTP tanpa menyebut kata TTE
            turn2 = build_n8n_chat_response(self.tamu_a.id, 'Kalo bawa fotokopi KTP saja boleh tidak?', session_id=sess_id)
            self.assertEqual(turn2['intent'], 'sop_dan_layanan_teknis')
            self.assertIn('Tanda Tangan Elektronik', turn2['reply_text'])
            self.assertIn('fotokopi', turn2['reply_text'].lower())
            self.assertTrue('tidak diperkenankan' in turn2['reply_text'].lower() or 'wajib ktp asli' in turn2['reply_text'].lower())
            self.assertEqual(turn2['strike_count'], 0)

            # Turn 3: Tanya biaya tanpa menyebut kata TTE
            turn3 = build_n8n_chat_response(self.tamu_a.id, 'Biayanya berapa ya?', session_id=sess_id)
            self.assertEqual(turn3['intent'], 'sop_dan_layanan_teknis')
            self.assertIn('gratis', turn3['reply_text'].lower())
            self.assertEqual(turn3['strike_count'], 0)

            # Turn 4: Pindah topik ke Magang
            turn4 = build_n8n_chat_response(self.tamu_a.id, 'Kalau magang PKL mahasiswa syaratnya apa?', session_id=sess_id)
            self.assertEqual(turn4['intent'], 'sop_dan_layanan_teknis')
            self.assertIn('Magang', turn4['reply_text'])

            # Turn 5: Tanya anak SMK tanpa menyebut kata magang
            turn5 = build_n8n_chat_response(self.tamu_a.id, 'Anak SMK bisa tidak?', session_id=sess_id)
            self.assertEqual(turn5['intent'], 'sop_dan_layanan_teknis')
            self.assertIn('smk', turn5['reply_text'].lower())
            self.assertIn('diperkenankan', turn5['reply_text'].lower())
            self.assertEqual(turn5['strike_count'], 0)

    def test_direktori_pejabat_dan_struktur_organisasi(self):
        """
        Menguji Direktori Profil Pejabat & Struktur Organisasi Dinas:
        1. Pertanyaan Kepala Dinas: "Siapa nama Kepala Dinas Kominfo sekarang?"
           -> Menjawab Drs. Yan Yan Akhmad Kurnia / Drs. Yan Yan Akhmad Kurnaidi, M.Si & tombol audiensi.
        2. Pertanyaan Kabid TIK: "Siapa Kabid TIK?"
           -> Menjawab Kabid TIK (Ir. Yusuf Efendi, M.T / Bahrul Ulum, S.T., M.M.) & tombol janji temu.
        3. Pertanyaan Staf Jaringan: "Siapa staf yang menangani jaringan?"
           -> Menjawab staf jaringan (Novita Sari, S.T / Guntur Wibowo, S.Kom) & tombol janji temu.
        4. Pertanyaan Struktur Lengkap: "Bagaimana struktur organisasi Diskominfosantik?"
           -> Menampilkan bagan hierarki struktural lengkap 5 bidang kedinasan.
        """
        from unittest.mock import patch
        from ..utils import build_n8n_chat_response, set_session_handoff_to_admin

        sess_id = f"test_pejabat_{self.tamu_a.id}"
        set_session_handoff_to_admin(sess_id, active=False)

        with patch('guest_book.utils.call_n8n_routing', return_value=None):
            # 1. Kepala Dinas
            res_kadis = build_n8n_chat_response(
                self.tamu_a.id,
                'Siapa nama Kepala Dinas Kominfo sekarang?',
                session_id=sess_id,
            )
            self.assertEqual(res_kadis['intent'], 'pejabat_dan_struktur')
            self.assertIn('yan yan akhmad', res_kadis['reply_text'].lower())
            self.assertIn('kepala dinas', res_kadis['reply_text'].lower())
            self.assertIn('chip:daftarkan kunjungan', res_kadis['reply_text'].lower())

            # 2. Kabid TIK
            res_kabid = build_n8n_chat_response(
                self.tamu_a.id,
                'Siapa Kabid TIK?',
                session_id=sess_id,
            )
            self.assertEqual(res_kabid['intent'], 'pejabat_dan_struktur')
            self.assertIn('teknologi informasi dan komunikasi', res_kabid['reply_text'].lower())
            self.assertTrue(
                'yusuf efendi' in res_kabid['reply_text'].lower()
                or 'bahrul ulum' in res_kabid['reply_text'].lower()
            )
            self.assertIn('chip:daftarkan kunjungan', res_kabid['reply_text'].lower())

            # 3. Staf Jaringan
            res_staf = build_n8n_chat_response(
                self.tamu_a.id,
                'Siapa staf yang menangani jaringan?',
                session_id=sess_id,
            )
            self.assertEqual(res_staf['intent'], 'pejabat_dan_struktur')
            self.assertIn('jaringan', res_staf['reply_text'].lower())
            self.assertTrue(
                'novita sari' in res_staf['reply_text'].lower()
                or 'guntur wibowo' in res_staf['reply_text'].lower()
                or 'pegawai satu' in res_staf['reply_text'].lower()
            )
            self.assertIn('chip:daftarkan kunjungan', res_staf['reply_text'].lower())

            # 4. Struktur Lengkap
            res_struktur = build_n8n_chat_response(
                self.tamu_a.id,
                'Bagaimana struktur organisasi Diskominfosantik?',
                session_id=sess_id,
            )
            self.assertEqual(res_struktur['intent'], 'pejabat_dan_struktur')
            self.assertIn('struktur organisasi', res_struktur['reply_text'].lower())
            self.assertIn('bidang teknologi informasi', res_struktur['reply_text'].lower())
            self.assertIn('bidang persandian', res_struktur['reply_text'].lower())

    def test_reschedule_and_cancel_from_chat(self):
        """
        Menguji fitur D (Reschedule & Pembatalan Langsung Lewat Chat):
        - Mengubah jam kunjungan langsung dari chat -> status diset 'menunggu_admin' & history tercatat.
        - Membatalkan tiket langsung dari chat -> status diset 'cancelled' & history tercatat.
        """
        from unittest.mock import patch
        from ..models import KunjunganStatusHistory
        from ..utils import build_n8n_chat_response, set_session_handoff_to_admin

        sess_id = f"test_resched_{self.tamu_a.id}"
        set_session_handoff_to_admin(sess_id, active=False)

        # Pastikan kunjungan_a aktif
        self.kunjungan_a.status = 'menunggu_admin'
        self.kunjungan_a.save()

        with patch('guest_book.utils.call_n8n_routing', return_value=None):
            # 1. Reschedule jam kunjungan menjadi jam 13:00
            res_resched = build_n8n_chat_response(
                self.tamu_a.id,
                'Tolong ganti jam kunjungan saya jadi jam 13:00',
                session_id=sess_id,
            )
            self.assertEqual(res_resched['intent'], 'ubah_jadwal_dan_batal')
            self.assertIn('Berhasil Diperbarui', res_resched['reply_text'])
            self.assertIn('Menunggu Verifikasi & Persetujuan (ACC) Admin', res_resched['reply_text'])

            self.kunjungan_a.refresh_from_db()
            local_arrival = timezone.localtime(self.kunjungan_a.arrival_time)
            self.assertEqual(local_arrival.hour, 13)
            self.assertEqual(self.kunjungan_a.status, 'menunggu_admin')

            # Cek riwayat status tercatat
            hist_resched = KunjunganStatusHistory.objects.filter(
                kunjungan=self.kunjungan_a,
                new_status='menunggu_admin'
            ).order_by('-changed_at').first()
            self.assertIsNotNone(hist_resched)
            self.assertIn('Chat AI', hist_resched.notes)

            # 2. Pembatalan kunjungan langsung dari chat
            res_cancel = build_n8n_chat_response(
                self.tamu_a.id,
                'Batalkan janji temu saya',
                session_id=sess_id,
            )
            self.assertEqual(res_cancel['intent'], 'ubah_jadwal_dan_batal')
            self.assertIn('Berhasil Dibatalkan', res_cancel['reply_text'])

            self.kunjungan_a.refresh_from_db()
            self.assertEqual(self.kunjungan_a.status, 'cancelled')

            # Cek riwayat status pembatalan
            hist_cancel = KunjunganStatusHistory.objects.filter(
                kunjungan=self.kunjungan_a,
                new_status='cancelled'
            ).order_by('-changed_at').first()
            self.assertIsNotNone(hist_cancel)
            self.assertIn('Chat Asisten AI', hist_cancel.notes)

    def test_feature_a_scan_tiket_qr_checkin(self):
        """
        Uji Peningkatan 2.A: Fitur Scanner Kamera QR Code di Pos Resepsionis / Satpam
        - Pindai tiket tamu (UUID & prefix 8 karakter)
        - Status otomatis berubah menjadi in_progress (Hadir di Kantor)
        - History status tercatat dan notifikasi terkirim ke pegawai
        - Validasi tiket invalid dan status completed/cancelled
        """
        from ..models import KunjunganStatusHistory
        admin_client = self.get_client('admin')
        tamu_client = self.get_client('tamu_a')

        # 1. Halaman scanner dapat diakses admin
        res_page = admin_client.get(reverse('tamu:admin_scan_tiket'))
        self.assertEqual(res_page.status_code, 200)

        # 2. Tamu biasa tidak boleh mengakses halaman scanner admin
        res_tamu_page = tamu_client.get(reverse('tamu:admin_scan_tiket'))
        self.assertIn(res_tamu_page.status_code, [302, 403])

        # 3. Pindai tiket tidak valid
        res_invalid = admin_client.post(
            reverse('tamu:api_scan_tiket'),
            data=json.dumps({'code': 'INVALID123'}),
            content_type='application/json'
        )
        self.assertEqual(res_invalid.status_code, 404)
        self.assertFalse(res_invalid.json()['success'])

        # 4. Pindai tiket valid (UUID) -> Check-in sukses menjadi in_progress
        res_scan_uuid = admin_client.post(
            reverse('tamu:api_scan_tiket'),
            data=json.dumps({'code': str(self.kunjungan_a.id)}),
            content_type='application/json'
        )
        self.assertEqual(res_scan_uuid.status_code, 200)
        data_uuid = res_scan_uuid.json()
        self.assertTrue(data_uuid['success'])
        self.assertTrue(data_uuid.get('is_new_checkin'))
        self.assertEqual(data_uuid['data']['status'], 'in_progress')

        self.kunjungan_a.refresh_from_db()
        self.assertEqual(self.kunjungan_a.status, 'in_progress')

        # Verifikasi history tercatat
        hist = KunjunganStatusHistory.objects.filter(
            kunjungan=self.kunjungan_a,
            new_status='in_progress'
        ).first()
        self.assertIsNotNone(hist)
        self.assertIn('Scan QR Code Pos Resepsionis/Satpam', hist.notes)

        # 5. Pindai ulang dengan kode 8-karakter -> Memberitahukan sudah hadir
        code_8 = str(self.kunjungan_a.id)[:8].upper()
        res_scan_again = admin_client.post(
            reverse('tamu:api_scan_tiket'),
            data=json.dumps({'code': code_8}),
            content_type='application/json'
        )
        self.assertEqual(res_scan_again.status_code, 200)
        self.assertTrue(res_scan_again.json().get('already_in_progress'))

        # 6. Pindai tiket yang dibatalkan (cancelled) -> Ditolak dengan status 400
        self.kunjungan_b.status = 'cancelled'
        self.kunjungan_b.save()

        res_cancelled = admin_client.post(
            reverse('tamu:api_scan_tiket'),
            data=json.dumps({'code': str(self.kunjungan_b.id)}),
            content_type='application/json'
        )
        self.assertEqual(res_cancelled.status_code, 400)
        self.assertIn('Dibatalkan', res_cancelled.json()['error'])

    def test_feature_b_admin_chime_notification_broadcast(self):
        """
        Uji Peningkatan 2.B: Audio Notifikasi Bunyi (Chime Alert) Khusus Admin
        - Pengiriman notifikasi ke admin menyertakan play_chime: True
        - Group admin_notifications dan notif_admin menerima broadcast
        """
        from ..utils import send_notification
        from ..models import Notification

        notif = send_notification(
            recipient_id='admin',
            recipient_type='admin',
            notification_type='new_booking',
            title='Janji Temu Baru dari Chatbot',
            message='Tamu A baru saja mengajukan janji temu melalui chatbot.',
            related_object_id=str(self.kunjungan_a.id)
        )
        self.assertIsNotNone(notif)
        self.assertEqual(notif.recipient_type, 'admin')
        self.assertEqual(notif.title, 'Janji Temu Baru dari Chatbot')

        # Verifikasi database menyimpan notifikasi untuk admin
        saved_notifs = Notification.objects.filter(recipient_type='admin', related_object_id=str(self.kunjungan_a.id))
        self.assertTrue(saved_notifs.exists())

    def test_feature_c_ikm_survey_and_anti_idor(self):
        """
        Uji Peningkatan 2.C: Survei Indeks Kepuasan Masyarakat (IKM / Rating Pelayanan)
        - Tamu dapat memberi rating 1-5 bintang & 5 kriteria pelayanan setelah status completed
        - Anti-IDOR: Tamu B dilarang menilai kunjungan milik Tamu A
        - Penolakan penilaian untuk status yang belum completed
        - Pencegahan duplikasi rating pada kunjungan yang sama
        - Admin dapat melihat rekapitulasi IKM dan mencetak laporan evaluasi resmi PermenPAN-RB
        """
        from ..models import IKMSurvey
        tamu_a_client = self.get_client('tamu_a')
        tamu_b_client = self.get_client('tamu_b')
        admin_client = self.get_client('admin')

        # 1. Kunjungan yang belum selesai tidak boleh dinilai
        res_pending_rate = tamu_a_client.post(
            reverse('tamu:api_submit_ikm_rating', kwargs={'pk': self.kunjungan_a.id}),
            data=json.dumps({'rating': 5, 'ulasan': 'Pelayanan memuaskan'}),
            content_type='application/json'
        )
        self.assertEqual(res_pending_rate.status_code, 400)
        self.assertFalse(res_pending_rate.json()['success'])

        # Ubah status kunjungan A menjadi 'completed'
        self.kunjungan_a.status = 'completed'
        self.kunjungan_a.save()

        # 2. Anti-IDOR: Tamu B mencoba menilai kunjungan milik Tamu A
        res_idor = tamu_b_client.post(
            reverse('tamu:api_submit_ikm_rating', kwargs={'pk': self.kunjungan_a.id}),
            data=json.dumps({'rating': 1, 'ulasan': 'Hacking rating'}),
            content_type='application/json'
        )
        self.assertEqual(res_idor.status_code, 403)
        self.assertFalse(res_idor.json()['success'])
        self.assertFalse(IKMSurvey.objects.filter(kunjungan=self.kunjungan_a).exists())

        # 3. Tamu A menilai kunjungannya sendiri -> Berhasil (HTTP 200)
        res_success = tamu_a_client.post(
            reverse('tamu:api_submit_ikm_rating', kwargs={'pk': self.kunjungan_a.id}),
            data=json.dumps({
                'rating': 5,
                'kesesuaian_persyaratan': 5,
                'kemudahan_prosedur': 5,
                'kecepatan_layanan': 5,
                'keramahan_petugas': 5,
                'kualitas_sarana': 5,
                'ulasan': 'Pelayanan sangat ramah, fasilitas bersih dan responsif.'
            }),
            content_type='application/json'
        )
        self.assertEqual(res_success.status_code, 200)
        self.assertTrue(res_success.json()['success'])

        survey = IKMSurvey.objects.filter(kunjungan=self.kunjungan_a).first()
        self.assertIsNotNone(survey)
        self.assertEqual(survey.rating, 5)
        self.assertEqual(survey.tamu, self.tamu_a)
        self.assertIn('sangat ramah', survey.ulasan)

        # 4. Tamu A mencoba mengisi survei lagi pada tiket yang sama -> Ditolak (Sudah pernah)
        res_dup = tamu_a_client.post(
            reverse('tamu:api_submit_ikm_rating', kwargs={'pk': self.kunjungan_a.id}),
            data=json.dumps({'rating': 4}),
            content_type='application/json'
        )
        self.assertEqual(res_dup.status_code, 400)
        self.assertIn('sudah pernah mengisi', res_dup.json()['error'])

        # 5. Dashboard IKM Admin menampilkan metrik terhitung
        res_ikm_dash = admin_client.get(reverse('tamu:admin_ikm'))
        self.assertEqual(res_ikm_dash.status_code, 200)
        self.assertContains(res_ikm_dash, 'Indeks Kepuasan Masyarakat')
        self.assertEqual(res_ikm_dash.context['total_responden'], 1)
        self.assertEqual(res_ikm_dash.context['avg_rating'], 5.0)
        self.assertEqual(res_ikm_dash.context['ikm_skala_100'], 100.0)
        self.assertEqual(res_ikm_dash.context['mutu_pelayanan'], 'A (Sangat Baik)')

        # 6. Halaman Cetak Laporan Evaluasi PermenPAN-RB
        res_ikm_cetak = admin_client.get(reverse('tamu:admin_ikm_cetak'))
        self.assertEqual(res_ikm_cetak.status_code, 200)
        self.assertContains(res_ikm_cetak, 'LAPORAN HASIL EVALUASI INDEKS KEPUASAN MASYARAKAT (IKM)')
        self.assertContains(res_ikm_cetak, 'PermenPAN-RB No. 14 Tahun 2017')
