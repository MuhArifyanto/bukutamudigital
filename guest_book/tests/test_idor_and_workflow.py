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

        # Kunjungan milik Tamu A
        self.kunjungan_a = Kunjungan.objects.create(
            tamu=self.tamu_a,
            pegawai=self.pegawai,
            arrival_time=timezone.now() + timedelta(days=1),
            purpose="Konsultasi Jaringan",
            status=KunjunganStatus.MENUNGGU_ADMIN
        )

        # Kunjungan milik Tamu B
        self.kunjungan_b = Kunjungan.objects.create(
            tamu=self.tamu_b,
            pegawai=self.pegawai,
            arrival_time=timezone.now() + timedelta(days=2),
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
