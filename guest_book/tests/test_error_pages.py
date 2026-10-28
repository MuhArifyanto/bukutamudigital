from django.test import TestCase, Client, override_settings
from django.template import loader
from django.test.client import RequestFactory
from ..views.error_handlers import custom_page_not_found_view, custom_server_error_view


class ErrorPagesTestCase(TestCase):
    """
    Test suite untuk Halaman Error 404 dan 500 (Tugas B):
    1. URL non-existent mengembalikan 404 dengan template kustom saat DEBUG=False.
    2. Isi halaman 404 tidak membocorkan detail teknis (traceback, path server, versi).
    3. Request API / JSON ke endpoint 404 mengembalikan respons JSON, bukan HTML.
    4. Template 500 bersifat mandiri tanpa query database atau context processor.
    5. Request API / JSON pada error 500 menghasilkan JSON yang aman.
    """

    def setUp(self):
        self.client = Client()
        self.rf = RequestFactory()

    @override_settings(DEBUG=False)
    def test_404_browser_renders_custom_template_without_leak(self):
        """Request browser ke URL yang tidak ada mengembalikan 404 dengan template kustom."""
        response = self.client.get('/halaman-yang-jelas-tidak-ada-998877/')
        self.assertEqual(response.status_code, 404)
        
        content = response.content.decode('utf-8')
        # Memastikan teks halaman kustom tampil
        self.assertIn("Halaman Tidak Ditemukan", content)
        self.assertIn("Kembali ke Beranda", content)
        self.assertIn('href="/"', content)

        # Memastikan tidak ada kebocoran teknis
        self.assertNotIn("Traceback", content)
        self.assertNotIn("Django Version", content)
        self.assertNotIn("C:\\", content)
        self.assertNotIn("/var/www", content)
        self.assertNotIn("WSGIRequest", content)

    @override_settings(DEBUG=False)
    def test_404_api_returns_json(self):
        """Request path /api/ yang tidak ada mengembalikan respons JSON 404."""
        response = self.client.get('/api/endpoint-yang-tidak-pernah-ada-12345/')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers.get('Content-Type'), 'application/json')
        
        data = response.json()
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'Endpoint tidak ditemukan')

    @override_settings(DEBUG=False)
    def test_404_json_accept_header_returns_json(self):
        """Request dengan header Accept: application/json mengembalikan JSON 404."""
        response = self.client.get(
            '/path-random-tidak-ada/',
            HTTP_ACCEPT='application/json'
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.headers.get('Content-Type'), 'application/json')
        data = response.json()
        self.assertFalse(data.get('success'))

    def test_500_template_renders_standalone(self):
        """Template 500.html dapat di-render mandiri tanpa context processor / database."""
        content = loader.render_to_string('500.html')
        self.assertIn("Terjadi Gangguan Server", content)
        self.assertIn("Kembali ke Beranda", content)
        self.assertIn('href="/"', content)
        # Pastikan tidak ada tag template unparsed
        self.assertNotIn("{%", content)
        self.assertNotIn("%}", content)
        self.assertNotIn("Traceback", content)

    def test_500_custom_view_api_returns_json(self):
        """Handler 500 untuk request API mengembalikan respons JSON."""
        request = self.rf.get('/api/some-internal-failure/')
        response = custom_server_error_view(request)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.headers.get('Content-Type'), 'application/json')
        import json
        data = json.loads(response.content.decode('utf-8'))
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error'), 'Terjadi gangguan pada server')

    def test_500_custom_view_browser_returns_html(self):
        """Handler 500 untuk browser mengembalikan HTML mandiri tanpa membocorkan info sistem."""
        request = self.rf.get('/some-page/')
        response = custom_server_error_view(request)
        self.assertEqual(response.status_code, 500)
        content = response.content.decode('utf-8')
        self.assertIn("Terjadi Gangguan Server", content)
        self.assertIn("Kembali ke Beranda", content)
        self.assertNotIn("Traceback", content)
