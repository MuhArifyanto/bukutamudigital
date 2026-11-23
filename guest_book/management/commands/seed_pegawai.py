# -*- coding: utf-8 -*-
import os

from django.contrib.auth.hashers import make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from guest_book.models import Departemen, Pegawai, Kunjungan

DATA_PEGAWAI = [
    {
        'departemen': 'Bidang E-Government',
        'pegawai': [
            {
                'name': 'Drs. Ahmad Fauzi, M.Kom',
                'email': 'ahmad.fauzi@diskominfosantik.go.id',
                'username': 'ahmad.fauzi',
                'nip': '197605152003121005',
                'jabatan': 'Kepala Bidang E-Government',
                'role': 'manager',
                'phone': '082111000001',
            },
            {
                'name': 'Siti Rahayu, S.Kom',
                'email': 'siti.rahayu@diskominfosantik.go.id',
                'username': 'siti.rahayu',
                'nip': '198903022015042002',
                'jabatan': 'Analis Sistem Informasi',
                'role': 'staff',
                'phone': '082111000002',
            },
            {
                'name': 'Budi Santoso, S.T',
                'email': 'budi.santoso@diskominfosantik.go.id',
                'username': 'budi.santoso',
                'nip': '199001152019031004',
                'jabatan': 'Pengembang Perangkat Lunak',
                'role': 'staff',
                'phone': '082111000003',
            },
        ]
    },
    {
        'departemen': 'Bidang Informasi dan Komunikasi Publik',
        'pegawai': [
            {
                'name': 'Ir. Dewi Kartika, M.Si',
                'email': 'dewi.kartika@diskominfosantik.go.id',
                'username': 'dewi.kartika',
                'nip': '197812102005012010',
                'jabatan': 'Kepala Bidang Informasi dan Komunikasi Publik',
                'role': 'manager',
                'phone': '082111000004',
            },
            {
                'name': 'Rudi Hermawan, S.Sos',
                'email': 'rudi.hermawan@diskominfosantik.go.id',
                'username': 'rudi.hermawan',
                'nip': '198507012010011003',
                'jabatan': 'Pengelola Informasi Publik',
                'role': 'staff',
                'phone': '082111000005',
            },
            {
                'name': 'Fitri Handayani, S.I.Kom',
                'email': 'fitri.handayani@diskominfosantik.go.id',
                'username': 'fitri.handayani',
                'nip': '199205202016042001',
                'jabatan': 'Penyusun Konten Media',
                'role': 'staff',
                'phone': '082111000006',
            },
        ]
    },
    {
        'departemen': 'Bidang Persandian',
        'pegawai': [
            {
                'name': 'Kolonel (Purn) Hendra Wijaya, M.T',
                'email': 'hendra.wijaya@diskominfosantik.go.id',
                'username': 'hendra.wijaya',
                'nip': '197404231999031002',
                'jabatan': 'Kepala Bidang Persandian',
                'role': 'manager',
                'phone': '082111000007',
            },
            {
                'name': 'Maya Kurniawati, S.Kom',
                'email': 'maya.kurniawati@diskominfosantik.go.id',
                'username': 'maya.kurniawati',
                'nip': '199010112015042003',
                'jabatan': 'Analis Keamanan Siber',
                'role': 'staff',
                'phone': '082111000008',
            },
        ]
    },
    {
        'departemen': 'Bidang Statistik',
        'pegawai': [
            {
                'name': 'Dr. Agus Priyono, M.Stat',
                'email': 'agus.priyono@diskominfosantik.go.id',
                'username': 'agus.priyono',
                'nip': '197309182001121008',
                'jabatan': 'Kepala Bidang Statistik',
                'role': 'manager',
                'phone': '082111000009',
            },
            {
                'name': 'Rina Susanti, S.Stat',
                'email': 'rina.susanti@diskominfosantik.go.id',
                'username': 'rina.susanti',
                'nip': '199107252016042002',
                'jabatan': 'Statistisi Ahli Pertama',
                'role': 'staff',
                'phone': '082111000010',
            },
            {
                'name': 'Doni Prasetyo, S.Si',
                'email': 'doni.prasetyo@diskominfosantik.go.id',
                'username': 'doni.prasetyo',
                'nip': '199308102019031005',
                'jabatan': 'Pengolah Data Statistik',
                'role': 'staff',
                'phone': '082111000011',
            },
        ]
    },
    {
        'departemen': 'Bidang Teknologi Informasi dan Komunikasi',
        'pegawai': [
            {
                'name': 'Ir. Yusuf Efendi, M.T',
                'email': 'yusuf.efendi@diskominfosantik.go.id',
                'username': 'yusuf.efendi',
                'nip': '197711202004121001',
                'jabatan': 'Kepala Bidang Teknologi Informasi dan Komunikasi',
                'role': 'manager',
                'phone': '082111000012',
            },
            {
                'name': 'Novita Sari, S.T',
                'email': 'novita.sari@diskominfosantik.go.id',
                'username': 'novita.sari',
                'nip': '198812012013042003',
                'jabatan': 'Administrator Jaringan',
                'role': 'staff',
                'phone': '082111000013',
            },
            {
                'name': 'Guntur Wibowo, S.Kom',
                'email': 'guntur.wibowo@diskominfosantik.go.id',
                'username': 'guntur.wibowo',
                'nip': '199406302018031002',
                'jabatan': 'Teknisi Infrastruktur TIK',
                'role': 'staff',
                'phone': '082111000014',
            },
        ]
    },
    {
        'departemen': 'Sekretariat',
        'pegawai': [
            {
                'name': 'Dra. Lestari Wulandari, M.AP',
                'email': 'lestari.wulandari@diskominfosantik.go.id',
                'username': 'lestari.wulandari',
                'nip': '197601082000122005',
                'jabatan': 'Sekretaris',
                'role': 'supervisor',
                'phone': '082111000015',
            },
            {
                'name': 'Bagas Nugroho, S.AP',
                'email': 'bagas.nugroho@diskominfosantik.go.id',
                'username': 'bagas.nugroho',
                'nip': '199209142017031001',
                'jabatan': 'Pengelola Kepegawaian',
                'role': 'staff',
                'phone': '082111000016',
            },
            {
                'name': 'Anisa Putri, A.Md',
                'email': 'anisa.putri@diskominfosantik.go.id',
                'username': 'anisa.putri',
                'nip': '199508202018042001',
                'jabatan': 'Pengadministrasi Umum',
                'role': 'staff',
                'phone': '082111000017',
            },
        ]
    },
]

DUMMY_EMAILS = {
    'tya@gmail.com',
    'hasbih@gmail.com',
    'dimas@gmail.com',
    'herman@gmail.com',
    'agus@gmail.com',
    'firman@gmail.com',
    'bayu@gmail.com',
}

DUMMY_NAMES = {
    'lutpiah',
    'hasbi ardiansyah',
    'dimas',
    'suherman',
    'agus susanto',
    'firmansyah',
    'dimas anugrah',
    'bayu aji',
}

class Command(BaseCommand):
    help = "Sinkronisasi data 17 pegawai resmi Diskominfosantik secara aman dan non-destruktif."

    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            dest='password',
            default='',
            help='Password awal opsional untuk akun pegawai baru (wajib diganti saat login pertama). Default dari env PEGAWAI_DEFAULT_PASSWORD atau akun tanpa password.',
        )
        parser.add_argument(
            '--sync-existing',
            action='store_true',
            help='Perbarui profil (nama, username, NIP, jabatan, telepon, bidang) pada pegawai resmi yang sudah ada tanpa menimpa role/account_status.',
        )
        parser.add_argument(
            '--reset-passwords',
            action='store_true',
            help='Reset password pegawai resmi yang sudah ada ke --password / PEGAWAI_DEFAULT_PASSWORD dengan must_change_password=True.',
        )
        parser.add_argument(
            '--prune-dummy',
            action='store_true',
            help='Hapus akun dummy lama secara eksplisit (opt-in; tidak aktif secara default).',
        )

    def handle(self, *args, **options):
        self.stdout.write("Memulai sinkronisasi data 17 Pegawai Resmi Diskominfosantik...")

        raw_password = (options.get('password') or os.environ.get('PEGAWAI_DEFAULT_PASSWORD') or '').strip()
        if raw_password:
            try:
                validate_password(raw_password)
            except ValidationError as exc:
                raise CommandError(f"Password tidak memenuhi kebijakan keamanan: {' '.join(exc.messages)}")

        if options.get('reset_passwords') and not raw_password:
            raise CommandError("Opsi --reset-passwords membutuhkan --password atau environment variable PEGAWAI_DEFAULT_PASSWORD.")

        sync_existing = bool(options.get('sync_existing'))
        reset_passwords = bool(options.get('reset_passwords'))
        prune_dummy = bool(options.get('prune_dummy'))

        # 1. Pastikan setiap Departemen dan 17 Pegawai Resmi ada
        created_count = 0
        updated_count = 0
        skipped_count = 0
        official_emails_lower = set()
        first_official_by_dept = {}

        for dept_data in DATA_PEGAWAI:
            dept_nama = dept_data['departemen']
            dept, _ = Departemen.objects.get_or_create(
                nama=dept_nama,
                defaults={'kode': dept_nama[:3].upper()}
            )

            for p_data in dept_data['pegawai']:
                official_emails_lower.add(p_data['email'].strip().lower())
                initial_hash = make_password(raw_password) if raw_password else make_password(None)
                pegawai, created = Pegawai.objects.get_or_create(
                    email=p_data['email'],
                    defaults={
                        'name': p_data['name'],
                        'username': p_data['username'],
                        'nip': p_data['nip'],
                        'jabatan': p_data['jabatan'],
                        'role': p_data['role'],
                        'phone': p_data['phone'],
                        'department_rel': dept,
                        'department': dept_nama,
                        'password': initial_hash,
                        'must_change_password': True,
                        'account_status': 'active',
                    }
                )

                if created:
                    created_count += 1
                elif sync_existing or reset_passwords:
                    changed_fields = []
                    if sync_existing:
                        pegawai.name = p_data['name']
                        pegawai.username = p_data['username']
                        pegawai.nip = p_data['nip']
                        pegawai.jabatan = p_data['jabatan']
                        pegawai.phone = p_data['phone']
                        pegawai.department_rel = dept
                        pegawai.department = dept_nama
                        changed_fields.extend([
                            'name', 'username', 'nip', 'jabatan',
                            'phone', 'department_rel', 'department',
                        ])
                    if reset_passwords:
                        pegawai.password = make_password(raw_password)
                        pegawai.must_change_password = True
                        changed_fields.extend(['password', 'must_change_password'])
                    if changed_fields:
                        pegawai.save(update_fields=changed_fields)
                        updated_count += 1
                else:
                    skipped_count += 1

                if dept_nama not in first_official_by_dept:
                    first_official_by_dept[dept_nama] = pegawai

        self.stdout.write(self.style.SUCCESS(
            f"Sinkronisasi Pegawai Resmi Selesai: {created_count} dibuat, {updated_count} diperbarui, {skipped_count} dipertahankan."
        ))

        # 2. Pembersihan akun dummy HANYA jika administrator secara eksplisit memberi flag --prune-dummy
        deleted_count = 0
        if prune_dummy:
            for p in list(Pegawai.objects.select_related('department_rel').all()):
                p_email_lower = (p.email or '').strip().lower()
                p_name_lower = (p.name or '').strip().lower()

                is_dummy = (
                    p_email_lower in DUMMY_EMAILS
                    or p_name_lower in DUMMY_NAMES
                    or (p_email_lower.endswith('@gmail.com') and p_email_lower not in official_emails_lower)
                )
                if is_dummy:
                    dept_name = p.department_rel.nama if p.department_rel else p.department
                    replacement = (
                        first_official_by_dept.get(dept_name)
                        or next(iter(first_official_by_dept.values()), None)
                    )
                    if replacement:
                        Kunjungan.objects.filter(pegawai=p).update(pegawai=replacement)

                    deleted_name = p.name
                    deleted_email = p.email
                    p.delete()
                    deleted_count += 1
                    self.stdout.write(self.style.WARNING(f"   - Dihapus pegawai dummy: {deleted_name} ({deleted_email})"))

            if deleted_count > 0:
                self.stdout.write(self.style.SUCCESS(f"Berhasil membersihkan {deleted_count} akun pegawai dummy lama."))

        total = Pegawai.objects.filter(account_status='active').count()
        self.stdout.write(self.style.SUCCESS(f"Total Pegawai Aktif Sekarang: {total} orang."))

