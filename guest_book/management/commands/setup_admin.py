import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password
from guest_book.models import Tamu, Instansi


class Command(BaseCommand):
    help = "Membuat atau memperbarui akun Administrator untuk produksi/hosting (Render/TiDB Cloud)"

    def add_arguments(self, parser):
        parser.add_argument('--username', type=str, default=None, help='Username untuk admin')
        parser.add_argument('--password', type=str, default=None, help='Password untuk admin')
        parser.add_argument('--email', type=str, default=None, help='Email untuk admin')

    def handle(self, *args, **options):
        admin_user_env = options['username'] or os.getenv('ADMIN_USERNAME', 'admin').strip()
        admin_pass_env = options['password'] or os.getenv('ADMIN_PASSWORD', 'AdminBekasi2026!*').strip()
        admin_email_env = options['email'] or os.getenv('ADMIN_EMAIL', 'admin@diskominfosantik.bekasikab.go.id').strip()

        # Daftar akun admin yang selalu dipastikan tersedia
        admin_accounts = [
            {
                'username': admin_user_env,
                'email': admin_email_env,
                'password': admin_pass_env,
                'name': 'Administrator',
            },
            {
                'username': 'superadmin',
                'email': 'superadmin@diskominfosantik.bekasikab.go.id',
                'password': admin_pass_env,
                'name': 'Super Administrator',
            }
        ]

        # 1. Pastikan Instansi ada
        instansi, created_inst = Instansi.objects.get_or_create(
            nama="Diskominfosantik Kabupaten Bekasi",
            defaults={
                'alamat': 'Komplek Perkantoran Pemkab Bekasi, Sukamahi, Cikarang Pusat',
                'telepon': '021-89970123',
                'email': 'diskominfosantik@bekasikab.go.id',
                'kapasitas_maksimal': 50,
                'status_operasional': 'Aktif',
            }
        )
        if created_inst:
            self.stdout.write(self.style.SUCCESS(f"Instansi '{instansi.nama}' berhasil dibuat."))

        # 2. Buat / Perbarui Akun Django User
        for acc in admin_accounts:
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
                self.stdout.write(self.style.SUCCESS(f"User Django '{acc['username']}' berhasil diperbarui (password di-reset)."))

        # 3. Pastikan Tamu Admin ada
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

        self.stdout.write(self.style.SUCCESS("================================================"))
        self.stdout.write(self.style.SUCCESS("SETUP ADMIN BERHASIL!"))
        self.stdout.write(self.style.SUCCESS(f"Username : {admin_user_env} atau superadmin"))
        self.stdout.write(self.style.SUCCESS(f"Password : {admin_pass_env}"))
        self.stdout.write(self.style.SUCCESS("================================================"))
