from django.urls import reverse
from .base import BaseSecurityTestCase
from ..models import Instansi, Departemen


class AdminInstansiViewTests(BaseSecurityTestCase):
    """
    Test suite untuk admin_instansi_view:
    1. Non-admin (anonim, tamu, pegawai) ditolak dan diarahkan ke login admin.
    2. Admin dapat membuka halaman instansi (status 200).
    3. Admin dapat memperbarui identitas instansi dan data tersimpan di DB.
    4. Admin dapat menambahkan departemen baru.
    """

    def setUp(self):
        super().setUp()
        self.url = reverse('tamu:admin_instansi')

    def test_non_admin_access_rejected(self):
        """Memastikan anonim, tamu biasa, dan pegawai ditolak dari admin_instansi."""
        # Anonim
        res_anon = self.get_client('anon').get(self.url)
        self.assertEqual(res_anon.status_code, 302)
        self.assertIn(reverse('tamu:admin_login'), res_anon.url)

        # Tamu biasa
        res_tamu = self.get_client('tamu_a').get(self.url)
        self.assertEqual(res_tamu.status_code, 302)
        self.assertIn(reverse('tamu:admin_login'), res_tamu.url)

        # Pegawai
        res_pegawai = self.get_client('pegawai').get(self.url)
        self.assertEqual(res_pegawai.status_code, 302)
        self.assertIn(reverse('tamu:admin_login'), res_pegawai.url)

    def test_admin_can_access_view(self):
        """Memastikan admin dapat membuka halaman profil instansi dengan HTTP 200."""
        admin_client = self.get_client('admin')
        res = admin_client.get(self.url)
        self.assertEqual(res.status_code, 200)
        self.assertTemplateUsed(res, 'guest_book/admin_instansi.html')
        self.assertEqual(res.context['active_page'], 'instansi')
        self.assertIn('instansi', res.context)

    def test_admin_update_instansi_saved_correctly(self):
        """Memastikan admin dapat memperbarui data instansi dan tersimpan ke DB."""
        admin_client = self.get_client('admin')
        payload = {
            'action': 'update_instansi',
            'nama': 'Diskominfosantik Kabupaten Bekasi Baru',
            'slogan': 'Maju Bersama Digital',
            'status_operasional': 'Aktif',
            'jumlah_petugas': '12',
            'kapasitas_maksimal': '75',
            'jam_buka': '08:00',
            'jam_tutup': '16:00',
            'alamat': 'Kompleks Pemda Deltamas, Cikarang Pusat',
            'hari_kerja': '0,1,2,3,4'
        }
        res = admin_client.post(self.url, data=payload)
        self.assertEqual(res.status_code, 302)

        # Verifikasi data tersimpan
        self.instansi.refresh_from_db()
        self.assertEqual(self.instansi.nama, 'Diskominfosantik Kabupaten Bekasi Baru')
        self.assertEqual(self.instansi.slogan, 'Maju Bersama Digital')
        self.assertEqual(self.instansi.jumlah_petugas, 12)
        self.assertEqual(self.instansi.kapasitas_maksimal, 75)
        self.assertEqual(self.instansi.alamat, 'Kompleks Pemda Deltamas, Cikarang Pusat')

    def test_admin_add_departemen_saved_correctly(self):
        """Memastikan admin dapat menambahkan bidang/departemen baru."""
        admin_client = self.get_client('admin')
        payload = {
            'action': 'add_departemen',
            'nama': 'Bidang Informasi dan Komunikasi Publik',
            'kode': 'IKP'
        }
        res = admin_client.post(self.url, data=payload)
        self.assertEqual(res.status_code, 302)

        # Verifikasi tersimpan
        dep = Departemen.objects.filter(kode='IKP').first()
        self.assertIsNotNone(dep)
        self.assertEqual(dep.nama, 'Bidang Informasi dan Komunikasi Publik')

    def test_admin_delete_departemen_works_and_protects_active_pegawai(self):
        """Super admin dapat menghapus bidang tanpa pegawai aktif, namun ditolak jika masih ada pegawai aktif."""
        from ..models import AuditLog
        admin_client = self.get_client('admin')

        # 1. Buat bidang kosong lalu hapus -> harus terhapus & tercatat di AuditLog
        unused_dept = Departemen.objects.create(nama='Bidang Sementara', kode='TMP')
        res_del = admin_client.post(self.url, {
            'action': 'delete_departemen',
            'dept_id': str(unused_dept.id),
        })
        self.assertEqual(res_del.status_code, 302)
        self.assertFalse(Departemen.objects.filter(pk=unused_dept.pk).exists())
        self.assertTrue(
            AuditLog.objects.filter(
                action='delete',
                table_name='departemen',
                record_id=str(unused_dept.id),
            ).exists()
        )

        # 2. Bidang yang masih memiliki self.pegawai (active) tidak boleh dihapus
        res_blocked = admin_client.post(self.url, {
            'action': 'delete_departemen',
            'dept_id': str(self.departemen.id),
        })
        self.assertEqual(res_blocked.status_code, 302)
        self.assertTrue(Departemen.objects.filter(pk=self.departemen.pk).exists())

        # 3. ID tidak valid tidak menyebabkan server error 500
        res_invalid = admin_client.post(self.url, {
            'action': 'delete_departemen',
            'dept_id': 'bukan-uuid',
        })
        self.assertEqual(res_invalid.status_code, 302)
