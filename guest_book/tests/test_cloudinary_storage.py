from django.test import TestCase, override_settings
from django.core.files.storage import default_storage, FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from unittest.mock import patch
from .base import BaseSecurityTestCase
from ..storage import DynamicMediaCloudinaryStorage


class CloudinaryStorageTestCase(BaseSecurityTestCase):
    """
    Test suite untuk konfigurasi penyimpanan Cloudinary (Tugas B):
    1. DynamicMediaCloudinaryStorage mengklasifikasikan ekstensi gambar vs raw dokumen (PDF, Office).
    2. Mode lokal tanpa CLOUDINARY_URL tetap menggunakan FileSystemStorage tanpa error.
    3. Upload file PDF dan gambar menghasilkan URL yang valid.
    4. Penanganan kegagalan koneksi storage mengembalikan pesan aman tanpa stack trace.
    """

    def test_dynamic_storage_resource_types(self):
        """Memastikan storage secara otomatis membedakan gambar, video, dan dokumen raw."""
        storage = DynamicMediaCloudinaryStorage()

        # Gambar
        self.assertEqual(storage._get_resource_type("profiles/avatar.jpg"), "image")
        self.assertEqual(storage._get_resource_type("profiles/avatar.png"), "image")
        self.assertEqual(storage._get_resource_type("profiles/avatar.webp"), "image")
        self.assertEqual(storage._get_resource_type("profiles/vector.svg"), "image")

        # Dokumen Office & PDF (harus 'raw' agar tidak ditolak sebagai invalid image oleh Cloudinary)
        self.assertEqual(storage._get_resource_type("chat_attachments/laporan.pdf"), "raw")
        self.assertEqual(storage._get_resource_type("chat_attachments/proposal.docx"), "raw")
        self.assertEqual(storage._get_resource_type("chat_attachments/rekap.xlsx"), "raw")
        self.assertEqual(storage._get_resource_type("chat_attachments/arsip.doc"), "raw")

        # Video
        self.assertEqual(storage._get_resource_type("chat_attachments/panduan.mp4"), "video")

    def test_local_fallback_uses_filesystem_storage(self):
        """Saat CLOUDINARY_URL tidak ada, default_storage adalah FileSystemStorage."""
        self.assertIsInstance(default_storage, FileSystemStorage)
        url = default_storage.url("chat_attachments/test.pdf")
        self.assertTrue(url.startswith("/media/") or url.startswith("http"))

    def test_upload_chat_image_and_pdf_in_local(self):
        """Endpoint upload chat berhasil memproses file gambar dan file PDF valid."""
        client = self.get_client('tamu_a')
        endpoint = reverse('tamu:api_upload_chat_file')

        # 1. Upload Gambar PNG Valid
        png_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        png_file = SimpleUploadedFile("avatar.png", png_content, content_type="image/png")
        res_png = client.post(endpoint, {'file': png_file})
        self.assertEqual(res_png.status_code, 200)
        data_png = res_png.json()
        self.assertTrue(data_png.get('success'))
        self.assertEqual(data_png.get('message_type'), 'image')
        self.assertTrue(data_png.get('file_url'))

        # 2. Upload PDF Valid
        pdf_content = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF'
        pdf_file = SimpleUploadedFile("dokumen.pdf", pdf_content, content_type="application/pdf")
        res_pdf = client.post(endpoint, {'file': pdf_file})
        self.assertEqual(res_pdf.status_code, 200)
        data_pdf = res_pdf.json()
        self.assertTrue(data_pdf.get('success'))
        self.assertEqual(data_pdf.get('message_type'), 'file')
        self.assertTrue(data_pdf.get('file_url'))

    def test_upload_chat_storage_error_handled_gracefully(self):
        """Jika penyimpanan gagal/offline, endpoint mengembalikan status 500 dengan pesan aman tanpa stack trace."""
        client = self.get_client('tamu_a')
        endpoint = reverse('tamu:api_upload_chat_file')

        png_content = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        png_file = SimpleUploadedFile("foto.png", png_content, content_type="image/png")

        # Mock kegagalan storage.save
        with patch('django.core.files.storage.default_storage.save', side_effect=IOError("Simulated Cloudinary Connection Timeout")):
            res = client.post(endpoint, {'file': png_file})
            self.assertEqual(res.status_code, 500)
            data = res.json()
            self.assertFalse(data.get('success'))
            self.assertIn("Gagal mengunggah berkas", data.get('error', ''))
            # Pastikan detail internal / traceback tidak bocor ke klien
            self.assertNotIn("Traceback", data.get('error', ''))
            self.assertNotIn("Simulated Cloudinary Connection Timeout", data.get('error', ''))

    def test_cloudinary_url_format_when_active(self):
        """Memastikan DynamicMediaCloudinaryStorage menghasilkan URL Cloudinary CDN yang valid."""
        storage = DynamicMediaCloudinaryStorage()
        # Saat _get_url dipanggil, harus menghasilkan URL cloudinary
        image_url = storage._get_url("profiles/test_uuid.png")
        raw_url = storage._get_url("chat_attachments/test_uuid.pdf")

        self.assertIn("cloudinary.com", image_url)
        self.assertIn("image/upload", image_url)
        self.assertIn("cloudinary.com", raw_url)
        self.assertIn("raw/upload", raw_url)
