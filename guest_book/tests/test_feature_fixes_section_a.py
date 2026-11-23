import json
import shutil
import tempfile
from datetime import timedelta
from pathlib import Path

from django.contrib.auth.hashers import check_password, make_password
from django.contrib.sessions.models import Session as DjangoSession
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, override_settings
from django.urls import reverse
from django.utils import timezone

from ..models import (
    AuditLog,
    ChatMessage,
    ChatRoom,
    Departemen,
    IKMSurvey,
    Kunjungan,
    KunjunganNote,
    Message,
    Notification,
    Session as AppSession,
    Tamu,
)
from .base import BaseSecurityTestCase


class SectionAFeatureBugFixesTests(BaseSecurityTestCase):
    """Pengujian regresi untuk perbaikan Bagian A: Chat Pegawai, Hapus Bidang, & Hak Data UU PDP."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.kunjungan_a = Kunjungan.objects.create(
            tamu=self.tamu_a,
            pegawai=self.pegawai,
            purpose='Konsultasi Layanan Digital',
            arrival_time=timezone.now() + timedelta(days=2),
            status='disetujui',
            notes='Catatan internal sensitif',
            admin_notes='Catatan admin rahasia',
        )

    def tearDown(self):
        cache.clear()
        super().tearDown()

    # ── 1. Chat Real-Time Tamu <-> Pegawai (/chat/pegawai/<uuid>/) ────────────

    def test_tamu_chat_pegawai_handles_chatconsumer_payload_without_action_create(self):
        """
        tamu_chat_pegawai.html wajib merender payload broadcast ChatConsumer.chat_message()
        yang tidak memiliki field action='create', menangani edit/delete, dan tetap patuh CSP.
        """
        client = self.get_client('tamu_a')
        url = reverse('tamu:tamu_chat_pegawai', kwargs={'kunjungan_id': self.kunjungan_a.pk})
        resp = client.get(url)
        self.assertEqual(resp.status_code, 200)

        html = resp.content.decode('utf-8')
        self.assertNotIn("if (data.action === 'create') appendMessage(data)", html)
        self.assertIn("typeof data.message === 'string' && data.sender_type", html)
        self.assertIn("data.action === 'edit' || data.action === 'delete'", html)
        self.assertIn("ev.code === 4003", html)

    # ── 2. Hapus Bidang/Departemen di Manajemen Instansi ──────────────────────

    def test_admin_instansi_delete_departemen_and_empty_name_guard(self):
        admin_client = self.get_client('admin')
        url = reverse('tamu:admin_instansi')

        # Nama kosong tidak boleh membuat Departemen baru
        count_before = Departemen.objects.count()
        res_empty = admin_client.post(url, {'action': 'add_departemen', 'nama': '   ', 'kode': 'X'})
        self.assertEqual(res_empty.status_code, 302)
        self.assertEqual(Departemen.objects.count(), count_before)

        # Operator (non-super_admin) tidak boleh menghapus bidang
        from django.contrib.auth.models import User
        operator = User.objects.create_user(
            username='op_instansi_del',
            email='op.instansi@diskominfosantik.go.id',
            password='OperatorPass@2026!',
            is_staff=True,
            is_superuser=False,
        )
        Tamu.objects.create(
            name='Operator Instansi',
            email='op.instansi@diskominfosantik.go.id',
            phone='081211119999',
            is_admin=True,
            admin_role='operator',
            account_status='active',
        )
        op_client = Client()
        op_client.force_login(operator)
        unused = Departemen.objects.create(nama='Bidang Uji Hapus', kode='UJI')

        op_resp = op_client.post(url, {'action': 'delete_departemen', 'dept_id': str(unused.pk)})
        self.assertEqual(op_resp.status_code, 302)
        self.assertTrue(Departemen.objects.filter(pk=unused.pk).exists())

        # Super Admin berhasil menghapus bidang kosong
        ok_resp = admin_client.post(url, {'action': 'delete_departemen', 'dept_id': str(unused.pk)})
        self.assertEqual(ok_resp.status_code, 302)
        self.assertFalse(Departemen.objects.filter(pk=unused.pk).exists())

    # ── 3. Hak Data Pribadi UU PDP: Ekspor Data Mandiri ───────────────────────

    def test_tamu_export_personal_data_scoped_headers_audit_and_rate_limit(self):
        # Data milik Tamu A dan data milik Tamu B (untuk memastikan isolasi ketat / anti-IDOR)
        kunjungan_b = Kunjungan.objects.create(
            tamu=self.tamu_b,
            pegawai=self.pegawai,
            purpose='Rahasia Tamu B',
            arrival_time=timezone.now() + timedelta(days=3),
            status='disetujui',
        )
        completed_a = Kunjungan.objects.create(
            tamu=self.tamu_a,
            pegawai=self.pegawai,
            purpose='Kunjungan Selesai A',
            arrival_time=timezone.now() - timedelta(days=1),
            status='completed',
        )
        IKMSurvey.objects.create(tamu=self.tamu_a, kunjungan=completed_a, rating=5, ulasan='Sangat puas')
        ChatMessage.objects.create(
            session_id=ChatRoom.session_id_for_tamu(self.tamu_a.pk),
            sender_id=str(self.tamu_a.pk),
            sender_type='tamu',
            content='Halo Admin dari Tamu A',
        )
        ChatMessage.objects.create(
            session_id=ChatRoom.session_id_for_tamu(self.tamu_b.pk),
            sender_id=str(self.tamu_b.pk),
            sender_type='tamu',
            content='Pesan Rahasia Tamu B',
        )
        Message.objects.create(
            sender_id=str(self.tamu_a.pk),
            sender_type='tamu',
            subject='Pertanyaan A',
            content='Isi pesan A',
        )
        Notification.objects.create(
            recipient_id=str(self.tamu_a.pk),
            recipient_type='tamu',
            notification_type='system_alert',
            title='Notif A',
            message='Halo A',
        )

        url = reverse('tamu:tamu_export_personal_data')
        # Anonim ditolak -> redirect login
        self.assertEqual(self.get_client('anon').get(url).status_code, 302)

        client_a = self.get_client('tamu_a')
        resp = client_a.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertIn('attachment; filename="data_pribadi_tamu_', resp['Content-Disposition'])
        self.assertEqual(resp['Cache-Control'], 'no-store, private')
        self.assertEqual(resp['X-Content-Type-Options'], 'nosniff')

        data = json.loads(resp.content.decode('utf-8'))
        self.assertEqual(data['profile']['email'], self.tamu_a.email)
        self.assertEqual(data['profile']['nik'], '3216010101010001')
        self.assertNotIn('password', data['profile'])
        self.assertNotIn('nik_hash', data['profile'])
        self.assertEqual(len(data['kunjungan']), 2)
        self.assertEqual(len(data['ikm_surveys']), 1)
        self.assertEqual(len(data['chat_messages']), 1)
        self.assertEqual(len(data['messages']), 1)
        self.assertEqual(len(data['notifications']), 1)

        # Pastikan nol kebocoran data Tamu B
        raw_body = resp.content.decode('utf-8')
        self.assertNotIn('Rahasia Tamu B', raw_body)
        self.assertNotIn('Pesan Rahasia Tamu B', raw_body)
        self.assertNotIn(str(kunjungan_b.pk), raw_body)

        # AuditLog tercatat
        self.assertTrue(
            AuditLog.objects.filter(
                user_id=str(self.tamu_a.pk),
                user_type='tamu',
                table_name='pdp_data_export',
            ).exists()
        )

        # Rate limit (total 5x diizinkan, ke-6 -> 429)
        for _ in range(4):
            self.assertEqual(client_a.get(url).status_code, 200)
        self.assertEqual(client_a.get(url).status_code, 429)

    # ── 4. Hak Data Pribadi UU PDP: Penghapusan / Anonimisasi Akun Mandiri ────

    def test_tamu_delete_account_validations_and_full_pdp_erasure(self):
        temp_media = tempfile.mkdtemp()
        try:
            with override_settings(MEDIA_ROOT=temp_media):
                url = reverse('tamu:tamu_delete_account')
                client_a = self.get_client('tamu_a')
                other_client_a = self.get_client('tamu_a')
                other_sess_key = other_client_a.session.session_key
                app_sess = AppSession.objects.create(
                    user_type='tamu',
                    user_id=str(self.tamu_a.pk),
                    session_token='tok-delete-pdp-test',
                    expires_at=timezone.now() + timedelta(hours=1),
                )

                # Tambahkan foto profil, catatan kunjungan, chat, pesan, notifikasi
                self.tamu_a.profile_picture.save(
                    'avatar_del.png',
                    SimpleUploadedFile('avatar_del.png', b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'),
                    save=True,
                )
                avatar_path = Path(temp_media) / self.tamu_a.profile_picture.name
                self.assertTrue(avatar_path.is_file())

                KunjunganNote.objects.create(
                    kunjungan=self.kunjungan_a,
                    author_id=str(self.pegawai.pk),
                    author_type='pegawai',
                    content='Catatan sensitif pertemuan',
                )
                ChatMessage.objects.create(
                    session_id=ChatRoom.session_id_for_tamu(self.tamu_a.pk),
                    sender_id=str(self.tamu_a.pk),
                    sender_type='tamu',
                    content='Chat pribadi tamu A',
                )
                Message.objects.create(
                    sender_id=str(self.tamu_a.pk),
                    sender_type='tamu',
                    subject='Pesan A',
                    content='Isi pesan pribadi A',
                )
                Notification.objects.create(
                    recipient_id=str(self.tamu_a.pk),
                    recipient_type='tamu',
                    notification_type='system_alert',
                    title='Notif A',
                    message='Notifikasi A',
                )

                # GET ditolak 405
                self.assertEqual(client_a.get(url).status_code, 405)

                # Konfirmasi bukan HAPUS -> batal hapus
                res_bad_confirm = client_a.post(url, {'confirm_text': 'TIDAK', 'current_password': 'password123'})
                self.assertEqual(res_bad_confirm.status_code, 302)
                self.tamu_a.refresh_from_db()
                self.assertEqual(self.tamu_a.account_status, 'active')

                # Kata sandi salah -> batal hapus
                res_bad_pw = client_a.post(url, {'confirm_text': 'HAPUS', 'current_password': 'wrongpassword'})
                self.assertEqual(res_bad_pw.status_code, 302)
                self.tamu_a.refresh_from_db()
                self.assertEqual(self.tamu_a.account_status, 'active')

                # Konfirmasi & kata sandi benar -> hapus/anonimkan permanen
                res_ok = client_a.post(url, {'confirm_text': 'hapus', 'current_password': 'password123'})
                self.assertRedirects(res_ok, reverse('tamu:login'), fetch_redirect_response=False)

                self.tamu_a.refresh_from_db()
                self.assertEqual(self.tamu_a.account_status, 'inactive')
                self.assertTrue(self.tamu_a.email.endswith('@redacted.local'))
                self.assertTrue(self.tamu_a.name.startswith('Tamu Anonim ('))
                self.assertIsNone(self.tamu_a.nik)
                self.assertIsNone(self.tamu_a.nik_hash)
                self.assertIsNone(self.tamu_a.instansi)
                self.assertEqual(self.tamu_a.phone, '-')
                self.assertFalse(check_password('password123', self.tamu_a.password))
                self.assertFalse(avatar_path.exists())

                # Kunjungan aktif dibatalkan & catatan sensitif diredaksi
                self.kunjungan_a.refresh_from_db()
                self.assertEqual(self.kunjungan_a.status, 'cancelled')
                self.assertIn('UU PDP', self.kunjungan_a.notes)
                self.assertEqual(KunjunganNote.objects.filter(kunjungan=self.kunjungan_a).count(), 0)
                self.assertEqual(
                    ChatMessage.objects.filter(session_id=ChatRoom.session_id_for_tamu(self.tamu_a.pk)).count(),
                    0,
                )
                self.assertEqual(Message.objects.filter(sender_id=str(self.tamu_a.pk)).count(), 0)
                self.assertEqual(Notification.objects.filter(recipient_id=str(self.tamu_a.pk)).count(), 0)

                # Seluruh sesi dicabut
                self.assertIsNone(client_a.session.get('tamu_id'))
                self.assertFalse(DjangoSession.objects.filter(session_key=other_sess_key).exists())
                self.assertFalse(AppSession.objects.filter(pk=app_sess.pk).exists())

                # AuditLog tercatat
                self.assertTrue(
                    AuditLog.objects.filter(
                        user_id=str(self.tamu_a.pk),
                        user_type='tamu',
                        action='delete',
                        table_name='tamu',
                    ).exists()
                )
        finally:
            shutil.rmtree(temp_media, ignore_errors=True)

    def test_tamu_passwordless_sso_can_delete_account_with_confirmation(self):
        sso_tamu = Tamu.objects.create(
            name='Tamu SSO',
            email='tamu.sso@example.com',
            phone='081234500001',
            google_id='google-uid-sso-delete',
            password=make_password(None),
            registration_type='google_sso',
            account_status='active',
        )
        c = Client()
        s = c.session
        s['tamu_id'] = str(sso_tamu.pk)
        s.save()

        # Halaman profil tidak menampilkan input current_password untuk akun SSO tanpa sandi lokal
        prof = c.get(reverse('tamu:profil'))
        self.assertEqual(prof.status_code, 200)
        self.assertFalse(prof.context['has_local_password'])
        self.assertIn(reverse('tamu:tamu_export_personal_data'), prof.content.decode('utf-8'))
        self.assertIn(reverse('tamu:tamu_delete_account'), prof.content.decode('utf-8'))

        res = c.post(reverse('tamu:tamu_delete_account'), {'confirm_text': 'HAPUS'})
        self.assertRedirects(res, reverse('tamu:login'), fetch_redirect_response=False)
        sso_tamu.refresh_from_db()
        self.assertEqual(sso_tamu.account_status, 'inactive')
        self.assertIsNone(sso_tamu.google_id)
