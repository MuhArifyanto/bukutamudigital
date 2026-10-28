import json
from django.urls import reverse
from django.utils import timezone
from django.test import Client

from .base import BaseSecurityTestCase
from ..models import Notification


class ApiNotifikasiSecurityTestCase(BaseSecurityTestCase):
    """
    Test suite keamanan untuk endpoint notifikasi:
    - Mencegah fallback recipient 'admin' untuk request tanpa sesi login (401 Unauthorized).
    - Memastikan kontrol akses Anti-IDOR (403 Forbidden saat user non-admin mengakses notifikasi admin / user lain).
    - Memastikan pembatasan metode HTTP (405 Method Not Allowed untuk non-POST).
    - Memastikan penandaan notifikasi 'read-all' hanya memengaruhi notifikasi milik sendiri.
    - Memastikan proteksi CSRF aktif.
    """

    def setUp(self):
        super().setUp()
        self.url_read_all = reverse('tamu:api_mark_all_notifications_read')
        self.url_read_single = reverse('tamu:api_mark_notification_read')
        self.url_unread_count = reverse('tamu:api_get_unread_count')
        self.url_recent = reverse('tamu:api_get_recent_notifications')

        # Buat notifikasi untuk masing-masing peran
        self.notif_admin = Notification.objects.create(
            recipient_id='admin',
            recipient_type='admin',
            notification_type='system_alert',
            title='Admin Alert',
            message='Notifikasi khusus Administrator',
            status='unread'
        )

        self.notif_tamu_a = Notification.objects.create(
            recipient_id=str(self.tamu_a.id),
            recipient_type='tamu',
            notification_type='visit_registered',
            title='Tamu A Notif',
            message='Notifikasi untuk Tamu A',
            status='unread'
        )

        self.notif_tamu_b = Notification.objects.create(
            recipient_id=str(self.tamu_b.id),
            recipient_type='tamu',
            notification_type='visit_registered',
            title='Tamu B Notif',
            message='Notifikasi untuk Tamu B',
            status='unread'
        )

        self.notif_pegawai = Notification.objects.create(
            recipient_id=str(self.pegawai.id),
            recipient_type='pegawai',
            notification_type='visit_forwarded',
            title='Pegawai Notif',
            message='Notifikasi untuk Pegawai',
            status='unread'
        )

    def test_anonymous_mark_all_read_rejected_with_401(self):
        """Request anonim tanpa sesi ditolak 401 dan tidak mengubah notifikasi admin."""
        anon_client = self.get_client('anon')
        resp = anon_client.post(self.url_read_all)
        self.assertEqual(resp.status_code, 401)
        self.assertFalse(resp.json().get('success'))

        # Notifikasi admin tetap unread!
        self.notif_admin.refresh_from_db()
        self.assertEqual(self.notif_admin.status, 'unread')

    def test_mark_all_read_method_not_allowed(self):
        """GET request ke mark-all ditolak dengan status 405."""
        client = self.get_client('tamu_a')
        resp = client.get(self.url_read_all)
        self.assertEqual(resp.status_code, 405)

    def test_anonymous_mark_single_read_rejected_with_401(self):
        """Request anonim menandai 1 notifikasi ditolak 401."""
        anon_client = self.get_client('anon')
        resp = anon_client.post(
            self.url_read_single,
            data=json.dumps({'notification_id': str(self.notif_admin.id)}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 401)
        self.notif_admin.refresh_from_db()
        self.assertEqual(self.notif_admin.status, 'unread')

    def test_mark_single_read_method_not_allowed(self):
        """GET request ke mark-single ditolak dengan status 405."""
        client = self.get_client('tamu_a')
        resp = client.get(self.url_read_single)
        self.assertEqual(resp.status_code, 405)

    def test_tamu_cannot_mark_admin_notification(self):
        """Tamu tidak boleh menandai notifikasi admin (403 Forbidden)."""
        tamu_client = self.get_client('tamu_a')
        resp = tamu_client.post(
            self.url_read_single,
            data=json.dumps({'notification_id': str(self.notif_admin.id)}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 403)
        self.notif_admin.refresh_from_db()
        self.assertEqual(self.notif_admin.status, 'unread')

    def test_tamu_cannot_mark_other_tamu_notification(self):
        """Tamu A tidak boleh menandai notifikasi Tamu B (403 Forbidden)."""
        tamu_a_client = self.get_client('tamu_a')
        resp = tamu_a_client.post(
            self.url_read_single,
            data=json.dumps({'notification_id': str(self.notif_tamu_b.id)}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 403)
        self.notif_tamu_b.refresh_from_db()
        self.assertEqual(self.notif_tamu_b.status, 'unread')

    def test_pegawai_cannot_mark_admin_or_tamu_notification(self):
        """Pegawai tidak boleh menandai notifikasi Admin atau Tamu (403 Forbidden)."""
        pegawai_client = self.get_client('pegawai')
        # Coba tandai notif admin
        resp_admin = pegawai_client.post(
            self.url_read_single,
            data=json.dumps({'notification_id': str(self.notif_admin.id)}),
            content_type='application/json'
        )
        self.assertEqual(resp_admin.status_code, 403)
        self.notif_admin.refresh_from_db()
        self.assertEqual(self.notif_admin.status, 'unread')

        # Coba tandai notif tamu
        resp_tamu = pegawai_client.post(
            self.url_read_single,
            data=json.dumps({'notification_id': str(self.notif_tamu_a.id)}),
            content_type='application/json'
        )
        self.assertEqual(resp_tamu.status_code, 403)
        self.notif_tamu_a.refresh_from_db()
        self.assertEqual(self.notif_tamu_a.status, 'unread')

    def test_admin_marks_admin_notification_success(self):
        """Admin berhasil menandai notifikasi admin miliknya."""
        admin_client = self.get_client('admin')
        resp = admin_client.post(
            self.url_read_single,
            data=json.dumps({'notification_id': str(self.notif_admin.id)}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get('success'))
        self.notif_admin.refresh_from_db()
        self.assertEqual(self.notif_admin.status, 'read')

    def test_admin_cannot_mark_tamu_notification(self):
        """Admin tidak boleh menandai notifikasi personal milik Tamu (403)."""
        admin_client = self.get_client('admin')
        resp = admin_client.post(
            self.url_read_single,
            data=json.dumps({'notification_id': str(self.notif_tamu_a.id)}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 403)
        self.notif_tamu_a.refresh_from_db()
        self.assertEqual(self.notif_tamu_a.status, 'unread')

    def test_admin_mark_all_read_only_affects_admin(self):
        """Admin mark all read hanya menandai notifikasi admin, notifikasi pihak lain tetap unread."""
        admin_client = self.get_client('admin')
        resp = admin_client.post(self.url_read_all)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get('success'))

        self.notif_admin.refresh_from_db()
        self.assertEqual(self.notif_admin.status, 'read')

        # Tamu dan Pegawai tidak berubah
        self.notif_tamu_a.refresh_from_db()
        self.assertEqual(self.notif_tamu_a.status, 'unread')
        self.notif_tamu_b.refresh_from_db()
        self.assertEqual(self.notif_tamu_b.status, 'unread')
        self.notif_pegawai.refresh_from_db()
        self.assertEqual(self.notif_pegawai.status, 'unread')

    def test_tamu_mark_all_read_only_affects_own_tamu(self):
        """Tamu A mark all read hanya menandai miliknya, admin dan user lain tidak berubah."""
        tamu_a_client = self.get_client('tamu_a')
        resp = tamu_a_client.post(self.url_read_all)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json().get('success'))

        self.notif_tamu_a.refresh_from_db()
        self.assertEqual(self.notif_tamu_a.status, 'read')

        # Admin, Tamu B, dan Pegawai tetap unread
        self.notif_admin.refresh_from_db()
        self.assertEqual(self.notif_admin.status, 'unread')
        self.notif_tamu_b.refresh_from_db()
        self.assertEqual(self.notif_tamu_b.status, 'unread')
        self.notif_pegawai.refresh_from_db()
        self.assertEqual(self.notif_pegawai.status, 'unread')

    def test_unread_count_anonymous_returns_zero(self):
        """Pengguna anonim mendapatkan unread_count: 0 tanpa membocorkan atau default ke admin."""
        anon_client = self.get_client('anon')
        resp = anon_client.get(self.url_unread_count)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get('unread_count'), 0)

    def test_unread_count_isolated_per_role(self):
        """Unread count hanya menghitung notifikasi milik penerima masing-masing."""
        admin_client = self.get_client('admin')
        resp_admin = admin_client.get(self.url_unread_count)
        self.assertEqual(resp_admin.json().get('unread_count'), 1)

        tamu_client = self.get_client('tamu_a')
        resp_tamu = tamu_client.get(self.url_unread_count)
        self.assertEqual(resp_tamu.json().get('unread_count'), 1)

        pegawai_client = self.get_client('pegawai')
        resp_pegawai = pegawai_client.get(self.url_unread_count)
        self.assertEqual(resp_pegawai.json().get('unread_count'), 1)

    def test_csrf_protection_enforced_on_mark_all(self):
        """Memastikan CSRF protection aktif: request POST tanpa CSRF token ditolak 403 oleh Django."""
        csrf_client = Client(enforce_csrf_checks=True)
        # Sesi diset agar lolos autentikasi
        session = csrf_client.session
        session['tamu_id'] = str(self.tamu_a.pk)
        session.save()

        # POST tanpa HTTP_X_CSRFTOKEN atau csrfmiddlewaretoken
        resp = csrf_client.post(self.url_read_all)
        self.assertEqual(resp.status_code, 403)
