from django.test import TestCase
from ..models import Tamu
from scripts.normalize_admin_role import normalize_admin_roles


class NormalizeAdminRoleTestCase(TestCase):
    """
    Test suite untuk skrip penyelarasan admin_role (Tugas B):
    1. Mode dry-run tidak mengubah data di database.
    2. Mode apply hanya mengubah admin_role yang diminta (is_admin, status, password tetap utuh).
    3. Perubahan dibatalkan (rollback) jika tidak ada admin aktif yang tersisa.
    """

    def test_dry_run_does_not_modify_data(self):
        """Mode dry-run hanya melaporkan akun tanpa menulis ke database."""
        tamu = Tamu.objects.create(
            name="Admin Lama",
            email="admin.lama@example.com",
            phone="081234567890",
            nik="admin_lama",
            is_admin=True,
            admin_role="super_admin",
            account_status="active"
        )

        result = normalize_admin_roles(apply=False, from_role="super_admin", to_role="operator")
        self.assertEqual(result['mode'], 'dry-run')
        self.assertEqual(result['count'], 1)
        self.assertEqual(len(result['targets']), 1)
        self.assertEqual(result['targets'][0]['id'], str(tamu.id))

        # Verifikasi data di database sama sekali tidak berubah
        tamu.refresh_from_db()
        self.assertEqual(tamu.admin_role, "super_admin")

    def test_apply_modifies_only_admin_role(self):
        """Mode apply mengubah admin_role ke operator tanpa menyentuh is_admin, status, atau password."""
        raw_password = "hashed_sample_password_123"
        tamu = Tamu.objects.create(
            name="Admin Utama",
            email="admin.utama@example.com",
            phone="081234567891",
            nik="admin_utama",
            is_admin=True,
            admin_role="super_admin",
            account_status="active",
            password=raw_password
        )

        result = normalize_admin_roles(apply=True, from_role="super_admin", to_role="operator")
        self.assertEqual(result['mode'], 'apply')
        self.assertEqual(result['count'], 1)

        # Verifikasi field admin_role terupdate
        tamu.refresh_from_db()
        self.assertEqual(tamu.admin_role, "operator")

        # Verifikasi field sensitif lainnya TIDAK tersentuh
        self.assertTrue(tamu.is_admin)
        self.assertEqual(tamu.account_status, "active")
        self.assertEqual(tamu.password, raw_password)

    def test_apply_rollback_if_no_active_admin_remains(self):
        """Jika tidak ada akun admin aktif (is_admin=True, status=active), operasi harus rollback."""
        # Buat satu akun yang bukan admin aktif
        tamu = Tamu.objects.create(
            name="Bukan Admin Aktif",
            email="nonadmin@example.com",
            phone="081234567892",
            nik="nonadmin",
            is_admin=False,  # BUKAN admin aktif
            admin_role="super_admin",
            account_status="inactive"
        )

        # Pastikan tidak ada admin aktif lain di database pengujian
        Tamu.objects.filter(is_admin=True).delete()

        # Operasi harus melempar RuntimeError dan melakukan rollback
        with self.assertRaises(RuntimeError) as ctx:
            normalize_admin_roles(apply=True, from_role="super_admin", to_role="operator")

        self.assertIn("Rollback", str(ctx.exception))

        # Verifikasi data tidak berubah karena di-rollback
        tamu.refresh_from_db()
        self.assertEqual(tamu.admin_role, "super_admin")
