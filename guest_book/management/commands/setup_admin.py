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
        parser.add_argument('--password', type=str, default=None, help='Password untuk admin (wajib untuk pembuatan akun baru)')
        parser.add_argument('--email', type=str, default=None, help='Email untuk admin')
        parser.add_argument(
            '--reset-password',
            action='store_true',
            default=False,
            help='Reset password akun admin yang sudah ada jika --password / ADMIN_PASSWORD diberikan',
        )

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

        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        from django.core.management.base import CommandError

        admin_user_env = (options['username'] or os.getenv('ADMIN_USERNAME', 'admin')).strip()
        admin_pass_env = (
            options['password']
            or os.getenv('ADMIN_PASSWORD')
            or os.getenv('ADMIN_INITIAL_PASSWORD')
            or ''
        ).strip()
        admin_email_env = (
            options['email']
            or os.getenv('ADMIN_EMAIL', 'admin@diskominfosantik.bekasikab.go.id')
        ).strip()
        reset_password = bool(options.get('reset_password'))

        if reset_password and not admin_pass_env:
            raise CommandError(
                'Opsi --reset-password mewajibkan --password atau environment variable ADMIN_PASSWORD.'
            )

        existing_user = User.objects.filter(username__iexact=admin_user_env).first()
        existing_admin_row = Admin.objects.filter(email__iexact=admin_email_env).first()
        needs_password = reset_password or (existing_user is None) or (existing_admin_row is None)

        if admin_pass_env and needs_password:
            try:
                validate_password(admin_pass_env, user=existing_user)
            except ValidationError as exc:
                raise CommandError(
                    f"Password admin tidak memenuhi syarat keamanan: {'; '.join(exc.messages)}"
                )

        # Hanya siapkan satu akun administrator utama (tanpa akun bersama 'superadmin')
        admin_accounts = [
            {
                'username': admin_user_env,
                'email': admin_email_env,
                'password': admin_pass_env,
                'name': 'Administrator',
                'phone': '081234567890',
            },
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
        password_action = 'dipertahankan'
        for acc in admin_accounts:
            try:
                user = User.objects.filter(username__iexact=acc['username']).first()
                if not user:
                    if not acc['password']:
                        self.stderr.write(
                            self.style.WARNING(
                                f"ADMIN_PASSWORD / --password tidak disetel; user Django '{acc['username']}' belum dibuat."
                            )
                        )
                        password_action = 'belum_dibuat_tanpa_password'
                        continue
                    user = User.objects.create_user(
                        username=acc['username'],
                        email=acc['email'],
                        password=acc['password'],
                        is_staff=True,
                        is_superuser=True,
                        is_active=True,
                    )
                    password_action = 'dibuat'
                    self.stdout.write(self.style.SUCCESS(f"User Django '{acc['username']}' berhasil dibuat."))
                else:
                    changed_fields = []
                    if not user.is_staff:
                        user.is_staff = True
                        changed_fields.append('is_staff')
                    if not user.is_superuser:
                        user.is_superuser = True
                        changed_fields.append('is_superuser')
                    if not user.is_active:
                        user.is_active = True
                        changed_fields.append('is_active')
                    if reset_password:
                        user.set_password(acc['password'])
                        changed_fields.append('password')
                        password_action = 'direset'
                    if changed_fields:
                        user.save(update_fields=changed_fields)
                    msg = (
                        f"User Django '{acc['username']}' direset passwordnya."
                        if reset_password
                        else f"User Django '{acc['username']}' sudah ada (password lama dipertahankan)."
                    )
                    self.stdout.write(self.style.SUCCESS(msg))
            except Exception as e:
                has_errors = True
                self.stdout.write(self.style.ERROR(f"Gagal memproses User Django '{acc['username']}': {e}"))

        # 3. Buat / Perbarui di Tabel 'admin' (guest_book.models.Admin)
        # Agar saat user mengecek tabel 'admin' di HeidiSQL / MySQL, datanya tampil
        for acc in admin_accounts:
            try:
                admin_obj = Admin.objects.filter(email__iexact=acc['email']).first()
                if not admin_obj:
                    if not acc['password']:
                        self.stderr.write(
                            self.style.WARNING(
                                f"ADMIN_PASSWORD / --password tidak disetel; tabel admin '{acc['name']}' belum dibuat."
                            )
                        )
                        continue
                    admin_obj = Admin.objects.create(
                        name=acc['name'],
                        email=acc['email'],
                        phone=acc['phone'],
                        password=make_password(acc['password']),
                        account_status='active',
                    )
                    self.stdout.write(self.style.SUCCESS(f"Tabel admin '{acc['name']}' berhasil dibuat."))
                else:
                    changed_fields = []
                    if admin_obj.account_status != 'active':
                        admin_obj.account_status = 'active'
                        changed_fields.append('account_status')
                    if reset_password and acc['password']:
                        admin_obj.password = make_password(acc['password'])
                        changed_fields.append('password')
                    if changed_fields:
                        admin_obj.save(update_fields=changed_fields)
                    msg = (
                        f"Tabel admin '{acc['name']}' direset passwordnya."
                        if reset_password
                        else f"Tabel admin '{acc['name']}' sudah ada (password lama dipertahankan)."
                    )
                    self.stdout.write(self.style.SUCCESS(msg))
            except Exception as e:
                has_errors = True
                self.stdout.write(self.style.WARNING(f"Peringatan saat sinkronisasi tabel admin: {e}"))

        # 4. Pastikan profil Tamu Admin ada (hanya untuk metadata UI/instansi; tanpa password login Tamu)
        try:
            tamu_admin = Tamu.objects.filter(is_admin=True).first() or Tamu.objects.filter(Tamu.nik_lookup_q('admin')).first()
            if not tamu_admin:
                tamu_admin = Tamu.objects.create(
                    name="Administrator",
                    email=admin_email_env,
                    phone="081234567890",
                    nik="admin",
                    instansi="Diskominfosantik Kabupaten Bekasi",
                    password=None,
                    is_admin=True,
                    admin_role="super_admin",
                    account_status="active",
                    registration_type="manual"
                )
                self.stdout.write(self.style.SUCCESS("Data profil Tamu Administrator berhasil dibuat (tanpa kredensial portal tamu)."))
            else:
                changed_fields = []
                if not tamu_admin.is_admin:
                    tamu_admin.is_admin = True
                    changed_fields.append('is_admin')
                if tamu_admin.admin_role != "super_admin":
                    tamu_admin.admin_role = "super_admin"
                    changed_fields.append('admin_role')
                if tamu_admin.account_status != "active":
                    tamu_admin.account_status = "active"
                    changed_fields.append('account_status')
                if tamu_admin.password is not None:
                    tamu_admin.password = None
                    changed_fields.append('password')
                if changed_fields:
                    tamu_admin.save(update_fields=changed_fields)
                self.stdout.write(self.style.SUCCESS("Data profil Tamu Administrator diperbarui (kredensial portal tamu dinonaktifkan)."))
        except Exception as e:
            has_errors = True
            self.stdout.write(self.style.WARNING(f"Peringatan saat sinkronisasi Tamu Admin: {e}"))

        # 5. Inisialisasi Hari Libur dan Akhir Pekan Kalender jika masih kosong di database produksi
        try:
            from guest_book.models import CalendarSettings
            from guest_book.validators import get_default_holiday_status
            from datetime import date, timedelta
            from django.utils import timezone

            if CalendarSettings.objects.count() == 0:
                self.stdout.write("Tabel CalendarSettings kosong. Menginisialisasi kalender libur otomatis...")
                today = timezone.localtime().date()
                start_date = date(today.year, 1, 1)
                end_date = date(today.year + 1, 12, 31)

                records_to_create = []
                cur = start_date
                while cur <= end_date:
                    is_h, h_name = get_default_holiday_status(cur)
                    if is_h:
                        records_to_create.append(CalendarSettings(
                            date=cur,
                            daily_quota=50,
                            is_holiday=True,
                            holiday_name=h_name
                        ))
                    cur += timedelta(days=1)

                if records_to_create:
                    CalendarSettings.objects.bulk_create(records_to_create, ignore_conflicts=True)
                    self.stdout.write(self.style.SUCCESS(f"Berhasil menginisialisasi {len(records_to_create)} hari libur & akhir pekan kalender."))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Peringatan saat inisialisasi kalender: {e}"))

        # 6. Pastikan 17 Pegawai Resmi Diskominfosantik tersinkronisasi ke database
        try:
            from django.core.management import call_command
            call_command('seed_pegawai')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Peringatan saat sinkronisasi pegawai: {e}"))

        if has_errors:
            self.stdout.write(self.style.ERROR("================================================"))
            self.stdout.write(self.style.ERROR("SETUP SELESAI DENGAN CATATAN/ERROR."))
            self.stdout.write(self.style.ERROR("Sebagian tabel mungkin belum berhasil tersimpan."))
            self.stdout.write(self.style.ERROR("================================================"))
        else:
            self.stdout.write(self.style.SUCCESS("================================================"))
            self.stdout.write(self.style.SUCCESS("SETUP ADMIN SELESAI!"))
            self.stdout.write(self.style.SUCCESS(f"Akun Admin Utama  : {admin_user_env} (Email: {admin_email_env})"))
            self.stdout.write(self.style.SUCCESS(f"Status Password   : {password_action} (tidak dicetak demi keamanan)"))
            self.stdout.write(self.style.SUCCESS("================================================"))
