from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from datetime import timedelta
import uuid

from ..models import Tamu, Pegawai, Departemen, Instansi, Kunjungan, KunjunganStatus, Notification, ChatMessage


class BaseSecurityTestCase(TestCase):
    """
    Base Test Case yang menyiapkan 4 peran:
    1. Anonim (tanpa sesi)
    2. Tamu A (tamu_id milik Tamu A)
    3. Tamu B (tamu_id milik Tamu B - untuk uji IDOR)
    4. Pegawai (pegawai_id milik Pegawai)
    5. Admin (Django User staff dan Tamu dengan is_admin=True)
    """

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        cache.clear()

        # 1. Instansi utama

        self.instansi = Instansi.objects.create(
            nama="Diskominfosantik Kabupaten Bekasi",
            kapasitas_maksimal=50,
            status_operasional="Aktif"
        )

        # 2. Departemen
        self.departemen = Departemen.objects.create(
            nama="Bidang TIK",
            kode="TIK"
        )

        # 3. Tamu A
        self.tamu_a = Tamu.objects.create(
            name="Tamu A",
            email="tamu.a@example.com",
            phone="081234567890",
            nik="3216010101010001",
            instansi="PT Alpha",
            password=make_password("password123"),
            account_status="active",
            registration_type="manual"
        )

        # 4. Tamu B (untuk uji IDOR)
        self.tamu_b = Tamu.objects.create(
            name="Tamu B",
            email="tamu.b@example.com",
            phone="081234567891",
            nik="3216010101010002",
            instansi="PT Beta",
            password=make_password("password123"),
            account_status="active",
            registration_type="manual"
        )

        # 5. Pegawai
        self.pegawai = Pegawai.objects.create(
            name="Pegawai Satu",
            username="pegawai1",
            email="pegawai1@bekasikab.go.id",
            phone="081234567892",
            department_rel=self.departemen,
            password=make_password("password123"),
            role="staff",
            account_status="active"
        )

        # 6. Admin (Django Auth Staff + Tamu is_admin)
        self.admin_django = User.objects.create_user(
            username="admin_user",
            email="admin@bekasikab.go.id",
            password="adminpassword123",
            is_staff=True,
            is_superuser=True
        )
        self.admin_tamu = Tamu.objects.create(
            name="Administrator",
            email="admin@bekasikab.go.id",
            phone="081234567899",
            nik="admin",
            instansi="Diskominfosantik",
            password=make_password("adminpassword123"),
            is_admin=True,
            account_status="active",
            registration_type="manual"
        )

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()
        super().tearDown()

    def get_client(self, role='anon'):

        """
        Mengembalikan test client dengan sesi yang sesuai untuk role yang diminta.
        """
        client = Client()
        if role == 'anon':
            return client

        if role == 'admin':
            client.force_login(self.admin_django)
            session = client.session
            session['tamu_id'] = str(self.admin_tamu.pk)
            session['is_admin'] = True
            session.save()
            return client

        session = client.session
        if role == 'tamu_a':
            session['tamu_id'] = str(self.tamu_a.pk)
        elif role == 'tamu_b':
            session['tamu_id'] = str(self.tamu_b.pk)
        elif role == 'pegawai':
            session['pegawai_id'] = str(self.pegawai.pk)
            session['pegawai_name'] = self.pegawai.name
            session['pegawai_role'] = self.pegawai.role
        else:
            raise ValueError(f"Unknown role: {role}")

        session.save()
        return client

