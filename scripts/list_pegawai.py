import os, sys, django
sys.path.insert(0, r'c:\bukudigital')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bukudigital.settings')
django.setup()
from guest_book.models import Pegawai

print(f"{'Nama':<42} {'Username':<25} {'Email':<50} {'Bidang'}")
print('-' * 160)
for p in Pegawai.objects.select_related('department_rel').order_by('department_rel__nama','name'):
    dept = p.department_rel.nama if p.department_rel else '-'
    username = p.username or '-'
    print(f"{p.name:<42} {username:<25} {p.email:<50} {dept}")
