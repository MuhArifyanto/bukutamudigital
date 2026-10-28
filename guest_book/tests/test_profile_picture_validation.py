from django.urls import reverse
from django.core.files.uploadedfile import SimpleUploadedFile
from .base import BaseSecurityTestCase
from ..models import Tamu


class ProfilePictureValidationTestCase(BaseSecurityTestCase):
    """
    Test suite untuk validasi keamanan foto profil (Tugas A):
    1. File valid diterima (.jpg, .png, .webp).
    2. File lebih dari 2 MB ditolak.
    3. File .html atau .svg ditolak.
    4. File berekstensi .jpg tetapi isinya bukan gambar ditolak.
    5. Non-login ditolak.
    6. Tamu tidak bisa mengubah foto milik pengguna lain (IDOR prevention).
    """

    def setUp(self):
        super().setUp()
        self.tamu_endpoint = reverse('tamu:api_tamu_update_profile_picture')
        self.admin_endpoint = reverse('tamu:api_update_profile_picture')

    def _get_dummy_image(self, ext='jpg', size=1024):
        """Membuat payload binary gambar valid minimal dengan magic bytes yang sesuai."""
        if ext in ['jpg', 'jpeg']:
            header = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00'
            content = header + b'\x00' * max(0, size - len(header))
            return SimpleUploadedFile(f"avatar.{ext}", content, content_type="image/jpeg")
        elif ext == 'png':
            header = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4'
            content = header + b'\x00' * max(0, size - len(header))
            return SimpleUploadedFile(f"avatar.{ext}", content, content_type="image/png")
        elif ext == 'webp':
            header = b'RIFF\x24\x00\x00\x00WEBPVP8 \x18\x00\x00\x000\x01\x00\x9d\x01*\x01\x00\x01\x00\x00'
            content = header + b'\x00' * max(0, size - len(header))
            return SimpleUploadedFile(f"avatar.{ext}", content, content_type="image/webp")
        else:
            raise ValueError(f"Unsupported ext: {ext}")

    def test_valid_jpg_accepted(self):
        """File valid .jpg diterima dengan HTTP 200 dan menghasilkan URL."""
        client = self.get_client('tamu_a')
        img = self._get_dummy_image('jpg')
        res = client.post(self.tamu_endpoint, {'profile_picture': img})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success'))
        self.assertTrue(data.get('file_url'))

        self.tamu_a.refresh_from_db()
        self.assertTrue(bool(self.tamu_a.profile_picture))
        self.assertTrue(self.tamu_a.profile_picture.name.endswith('.jpg'))

    def test_valid_png_accepted(self):
        """File valid .png diterima dengan HTTP 200."""
        client = self.get_client('tamu_a')
        img = self._get_dummy_image('png')
        res = client.post(self.tamu_endpoint, {'profile_picture': img})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get('success'))

    def test_valid_webp_accepted(self):
        """File valid .webp diterima dengan HTTP 200."""
        client = self.get_client('tamu_a')
        img = self._get_dummy_image('webp')
        res = client.post(self.tamu_endpoint, {'profile_picture': img})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get('success'))

    def test_file_larger_than_2mb_rejected(self):
        """File lebih dari 2 MB ditolak dengan HTTP 400."""
        client = self.get_client('tamu_a')
        # Buat file berukuran 2.2 MB
        oversized = self._get_dummy_image('jpg', size=int(2.2 * 1024 * 1024))
        res = client.post(self.tamu_endpoint, {'profile_picture': oversized})
        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertFalse(data.get('success'))
        self.assertIn('2 MB', data.get('error', ''))

    def test_html_file_rejected(self):
        """File dengan ekstensi .html ditolak dengan HTTP 400."""
        client = self.get_client('tamu_a')
        html_file = SimpleUploadedFile(
            "malicious.html",
            b"<!doctype html><html><body><script>alert(1)</script></body></html>",
            content_type="text/html"
        )
        res = client.post(self.tamu_endpoint, {'profile_picture': html_file})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.json().get('success'))

    def test_svg_file_rejected(self):
        """File dengan ekstensi .svg ditolak dengan HTTP 400."""
        client = self.get_client('tamu_a')
        svg_file = SimpleUploadedFile(
            "vector.svg",
            b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert('xss')</script></svg>",
            content_type="image/svg+xml"
        )
        res = client.post(self.tamu_endpoint, {'profile_picture': svg_file})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(res.json().get('success'))

    def test_fake_jpg_content_rejected(self):
        """File berekstensi .jpg tetapi berisi teks/HTML biasa ditolak karena mismatch magic bytes."""
        client = self.get_client('tamu_a')
        fake_jpg = SimpleUploadedFile(
            "fake.jpg",
            b"Hello world, this is just plain text masquerading as jpeg.",
            content_type="image/jpeg"
        )
        res = client.post(self.tamu_endpoint, {'profile_picture': fake_jpg})
        self.assertEqual(res.status_code, 400)
        data = res.json()
        self.assertFalse(data.get('success'))
        self.assertIn('File signature mismatch', data.get('error', ''))

    def test_non_login_rejected(self):
        """Pengguna anonim yang belum login ditolak (redirect ke halaman login tamu)."""
        client = self.get_client('anon')
        img = self._get_dummy_image('jpg')
        res = client.post(self.tamu_endpoint, {'profile_picture': img})
        # @tamu_login_required me-redirect ke login tamu
        self.assertEqual(res.status_code, 302)
        self.assertIn(reverse('tamu:login'), res.url)

    def test_tamu_cannot_modify_other_user_picture(self):
        """Tamu A tidak bisa mengubah foto milik Tamu B meskipun menyertakan target ID."""
        client_a = self.get_client('tamu_a')
        img = self._get_dummy_image('jpg')

        # Tamu A mengirim post dengan mencoba memalsukan target user_id / tamu_id milik Tamu B
        res = client_a.post(self.tamu_endpoint, {
            'profile_picture': img,
            'id': str(self.tamu_b.id),
            'tamu_id': str(self.tamu_b.id)
        })
        self.assertEqual(res.status_code, 200)

        # Foto Tamu A terbarui
        self.tamu_a.refresh_from_db()
        self.assertTrue(bool(self.tamu_a.profile_picture))

        # Foto Tamu B tetap kosong / tidak tersentuh
        self.tamu_b.refresh_from_db()
        self.assertFalse(bool(self.tamu_b.profile_picture))

    def test_admin_update_profile_picture_validation(self):
        """Endpoint foto profil admin juga menerapkan validasi yang sama."""
        client_admin = self.get_client('admin')

        # 1. Valid JPG diterima
        img = self._get_dummy_image('jpg')
        res = client_admin.post(self.admin_endpoint, {'profile_picture': img})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json().get('success'))

        # 2. File palsu ditolak
        fake = SimpleUploadedFile("avatar.jpg", b"bad content", content_type="image/jpeg")
        res2 = client_admin.post(self.admin_endpoint, {'profile_picture': fake})
        self.assertEqual(res2.status_code, 400)
        self.assertFalse(res2.json().get('success'))
