"""
Script untuk mengisi username kosong pada akun pegawai lama.
"""
import os, sys, django
sys.path.insert(0, r'c:\bukudigital')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bukudigital.settings')
django.setup()

from guest_book.models import Pegawai

# Pegawai tanpa username
tanpa_username = Pegawai.objects.filter(username__isnull=True) | Pegawai.objects.filter(username='')

print(f"Ditemukan {tanpa_username.count()} akun tanpa username:")

for p in tanpa_username:
    # Generate username dari email (bagian sebelum @)
    base_username = p.email.split('@')[0].lower().replace('.', '.')
    
    # Pastikan tidak ada duplikasi
    candidate = base_username
    counter = 2
    while Pegawai.objects.filter(username=candidate).exclude(pk=p.pk).exists():
        candidate = f"{base_username}{counter}"
        counter += 1
    
    p.username = candidate
    p.save(update_fields=['username'])
    print(f"  Set username '{candidate}' untuk: {p.name} ({p.email})")

print("\nSelesai! Semua akun kini memiliki username.\n")
print(f"{'Nama':<42} {'Username':<25} {'Email':<50} {'Bidang'}")
print('-' * 160)
for p in Pegawai.objects.select_related('department_rel').order_by('department_rel__nama','name'):
    dept = p.department_rel.nama if p.department_rel else '-'
    print(f"{p.name:<42} {p.username or '-':<25} {p.email:<50} {dept}")
