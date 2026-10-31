import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.utils import OperationalError
from guest_book.models import Tamu, Instansi, Admin


class Command(BaseCommand):
    help = "Membuat atau memperbarui akun Administrator untuk produksi/hosting (Render/TiDB Cloud/Lokal)"

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, default=None, help='Username untuk admin')
        parser.add_argument('--password', type=str, default=None, help='Password untuk admin')
        parser.add_argument('--email', type=str, default=None, help='Email untuk admin')

    def handle(self, *args, **options):
        # 0. Cek koneksi database terlebih dahulu
        try:
            connection.ensure_connection()
        except OperationalError as err:
            self.stdout.write(self.style.ERROR("============================================================"))
            self.stdout.write(self.style.ERROR(f"GAGAL KONEKSI DATABASE: {err}"))
            self.stdout.write(self.style.WARNING("MySQL di komputer lokal (Laragon) belum dinyalakan."))
            self.stdout.write(self.style.WARNING("Solusi: Buka aplikasi Laragon, klik tombol 'Start All'."))
            self.stdout.write(self.style.WARNING("Setelah MySQL aktif, jalankan kembali: python manage.py setup_admin"))
            self.stdout.write(self.style.ERROR("============================================================"))
            return

        admin_user_env = options['username'] or os.getenv('ADMIN_USERNAME', 'admin').strip()
        admin_pass_env = options['password'] or os.getenv('ADMIN_PASSWORD', 'AdminBekasi2026!').strip()
        admin_email_env = options['email'] or os.getenv('ADMIN_EMAIL', 'admin@diskominfosantik.bekasikab.go.id').strip()

        # Daftar akun admin yang selalu dipastikan tersedia
        admin_accounts = [
            {
                'username': admin_user_env,
                'email': admin_email_env,
                'password': admin_pass_env,
                'name': 'Administrator',
                'phone': '081234567890',
            },
            {
                'username': 'superadmin',
                'email': 'superadmin@diskominfosantik.bekasikab.go.id',
                'password': admin_pass_env,
                'name': 'Super Administrator',
                'phone': '081234567891',
            }
        ]

        has_errors = False

        # 1. Pastikan Instansi ada (hanya gunakan field yang benar-benar ada di model)
        try:
            instansi, created_inst = Instansi.objects.get_or_create(
                nama="Diskominfosantik Kabupaten Bekasi",
                defaults={
                    'alamat': 'Komplek Perkantoran Pemkab Bekasi, Sukamahi, Cikarang Pusat',
                    'kapasitas_maksimal': 50,
                    'status_operasional': 'Aktif',
                }
            )
            if created_inst:
                self.stdout.write(self.style.SUCCESS(f"Instansi '{instansi.nama}' berhasil dibuat."))
        except Exception as e:
            has_errors = True
            self.stdout.write(self.style.WARNING(f"Peringatan saat periksa Instansi: {e}"))

        # 2. Buat / Perbarui Akun Django User (auth_user)
        for acc in admin_accounts:
            try:
                user = User.objects.filter(username__iexact=acc['username']).first()
                if not user:
                    user = User.objects.create_user(
                        username=acc['username'],
                        email=acc['email'],
                        password=acc['password'],
                        is_staff=True,
                        is_superuser=True,
                        is_active=True,
                    )
                    self.stdout.write(self.style.SUCCESS(f"User Django '{acc['username']}' berhasil dibuat."))
                else:
                    user.set_password(acc['password'])
                    user.email = acc['email']
                    user.is_staff = True
                    user.is_superuser = True
                    user.is_active = True
                    user.save()
                    self.stdout.write(self.style.SUCCESS(f"User Django '{acc['username']}' berhasil diperbarui (password disinkronkan)."))
            except Exception as e:
                has_errors = True
                self.stdout.write(self.style.ERROR(f"Gagal memproses User Django '{acc['username']}': {e}"))

        # 3. Buat / Perbarui di Tabel 'admin' (guest_book.models.Admin)
        # Agar saat user mengecek tabel 'admin' di HeidiSQL / MySQL, datanya tampil
        for acc in admin_accounts:
            try:
                admin_obj = Admin.objects.filter(email__iexact=acc['email']).first()
                if not admin_obj:
                    admin_obj = Admin.objects.create(
                        name=acc['name'],
                        email=acc['email'],
                        phone=acc['phone'],
                        password=make_password(acc['password']),
                        account_status='active',
                    )
                    self.stdout.write(self.style.SUCCESS(f"Tabel admin '{acc['name']}' berhasil dibuat."))
                else:
                    admin_obj.password = make_password(acc['password'])
                    admin_obj.account_status = 'active'
                    admin_obj.name = acc['name']
                    admin_obj.phone = acc['phone']
                    admin_obj.save(update_fields=['password', 'account_status', 'name', 'phone'])
                    self.stdout.write(self.style.SUCCESS(f"Tabel admin '{acc['name']}' berhasil diperbarui."))
            except Exception as e:
                has_errors = True
                self.stdout.write(self.style.WARNING(f"Peringatan saat sinkronisasi tabel admin: {e}"))

        # 4. Pastikan Tamu Admin ada (untuk context portal, foto profil, dan instansi)
        try:
            tamu_admin = Tamu.objects.filter(is_admin=True).first() or Tamu.objects.filter(nik='admin').first()
            if not tamu_admin:
                tamu_admin = Tamu.objects.create(
                    name="Administrator",
                    email=admin_email_env,
                    phone="081234567890",
                    nik="admin",
                    instansi="Diskominfosantik Kabupaten Bekasi",
                    password=make_password(admin_pass_env),
                    is_admin=True,
                    account_status="active",
                    registration_type="manual"
                )
                self.stdout.write(self.style.SUCCESS("Data Tamu Administrator berhasil dibuat."))
            else:
                tamu_admin.is_admin = True
                tamu_admin.account_status = "active"
                tamu_admin.password = make_password(admin_pass_env)
                tamu_admin.save(update_fields=['is_admin', 'account_status', 'password'])
                self.stdout.write(self.style.SUCCESS("Data Tamu Administrator berhasil diperbarui."))
        except Exception as e:
            has_errors = True
            self.stdout.write(self.style.WARNING(f"Peringatan saat sinkronisasi Tamu Admin: {e}"))

        if has_errors:
            self.stdout.write(self.style.ERROR("================================================"))
            self.stdout.write(self.style.ERROR("SETUP SELESAI DENGAN CATATAN/ERROR."))
            self.stdout.write(self.style.ERROR("Sebagian tabel mungkin belum berhasil tersimpan."))
            self.stdout.write(self.style.ERROR("================================================"))
        else:
            self.stdout.write(self.style.SUCCESS("================================================"))
            self.stdout.write(self.style.SUCCESS("SETUP ADMIN BERHASIL TERSIMPAN KE DATABASE!"))
            self.stdout.write(self.style.SUCCESS(f"Username / Akun 1 : {admin_user_env} (Email: {admin_email_env})"))
            self.stdout.write(self.style.SUCCESS("Username / Akun 2 : superadmin (Email: superadmin@diskominfosantik.bekasikab.go.id)"))
            self.stdout.write(self.style.SUCCESS(f"Password          : {admin_pass_env}"))
            self.stdout.write(self.style.SUCCESS("================================================"))
