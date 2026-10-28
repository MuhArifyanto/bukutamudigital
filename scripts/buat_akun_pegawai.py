"""
Script untuk membuat akun Pegawai untuk setiap bidang di Diskominfosantik.
Jalankan: python manage.py shell < scripts/buat_akun_pegawai.py
atau: python manage.py runscript buat_akun_pegawai
"""

import os
import sys
import django

# Setup Django
os.chdir(r'c:\bukudigital')
sys.path.insert(0, r'c:\bukudigital')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bukudigital.settings')
django.setup()

from django.contrib.auth.hashers import make_password
from guest_book.models import Departemen, Pegawai

# ── Data Bidang & Pegawai ────────────────────────────────────────────────────
# Format: (nama_departemen, nama_pegawai, email, nip, jabatan, role)
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

DEFAULT_PASSWORD = 'Diskominfo@2025'

print("=" * 60)
print("BUAT AKUN PEGAWAI DISKOMINFOSANTIK")
print("=" * 60)

created_count = 0
skipped_count = 0

for dept_data in DATA_PEGAWAI:
    dept_nama = dept_data['departemen']
    
    # Dapatkan atau buat departemen
    dept, dept_created = Departemen.objects.get_or_create(
        nama=dept_nama,
        defaults={'kode': dept_nama[:3].upper()}
    )
    if dept_created:
        print(f"\n✅ Departemen baru dibuat: {dept_nama}")
    else:
        print(f"\n📁 Departemen sudah ada: {dept_nama}")
    
    for p_data in dept_data['pegawai']:
        if Pegawai.objects.filter(email=p_data['email']).exists():
            print(f"   ⚠️  Skip (sudah ada): {p_data['name']} - {p_data['email']}")
            skipped_count += 1
            continue
        
        pegawai = Pegawai.objects.create(
            name=p_data['name'],
            email=p_data['email'],
            username=p_data['username'],
            phone=p_data['phone'],
            nip=p_data['nip'],
            jabatan=p_data['jabatan'],
            role=p_data['role'],
            department_rel=dept,
            department=dept_nama,
            password=make_password(DEFAULT_PASSWORD),
            account_status='active',
        )
        print(f"   ✅ Dibuat: {p_data['name']} ({p_data['email']}) | {p_data['jabatan']}")
        created_count += 1

print("\n" + "=" * 60)
print(f"SELESAI: {created_count} akun dibuat, {skipped_count} akun dilewati.")
print(f"Password default: {DEFAULT_PASSWORD}")
print("=" * 60)
print("\nDaftar Akun:")
print(f"{'Nama':<45} {'Email':<45} {'Bidang'}")
print("-" * 130)
for p in Pegawai.objects.select_related('department_rel').order_by('department_rel__nama', 'name'):
    print(f"{p.name:<45} {p.email:<45} {p.department_rel.nama if p.department_rel else '-'}")
