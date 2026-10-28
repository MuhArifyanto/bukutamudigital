"""
Migrasi: Backfill dan deprecate field 'department' (legacy) pada model Pegawai.

Langkah migrasi ini:
1. Data Operation (RunPython): Menyalin nilai field 'department' (CharField legacy)
   ke 'department_rel' (ForeignKey ke Departemen) jika nama departemen cocok,
   untuk semua pegawai yang department_rel masih NULL.
2. AlterField: Menambahkan komentar deprecation pada field 'department' via db_comment
   agar DBA mengetahui field ini akan dihapus di masa mendatang.

NOTE: Field 'department' TIDAK dihapus dalam migrasi ini untuk menjaga backward
compatibility dengan kode yang mungkin masih membacanya. Hapus field tersebut
setelah semua referensi kode sudah menggunakan 'department_rel'.
"""

from django.db import migrations, models
import django.db.models.deletion


def backfill_department_rel(apps, schema_editor):
    """
    Salin nilai department (CharField) ke department_rel (FK ke Departemen)
    berdasarkan kecocokan nama. Pegawai yang sudah punya department_rel dilewati.
    """
    Pegawai = apps.get_model('guest_book', 'Pegawai')
    Departemen = apps.get_model('guest_book', 'Departemen')

    # Build lookup name → Departemen instance
    dept_map = {d.nama.strip().lower(): d for d in Departemen.objects.all()}

    to_update = []
    for pegawai in Pegawai.objects.filter(department_rel__isnull=True).exclude(department=''):
        key = (pegawai.department or '').strip().lower()
        dept = dept_map.get(key)
        if dept:
            pegawai.department_rel = dept
            to_update.append(pegawai)

    if to_update:
        Pegawai.objects.bulk_update(to_update, ['department_rel'])


def noop(apps, schema_editor):
    """Reverse: no-op — data tidak di-rollback secara otomatis."""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('guest_book', '0018_add_ditolak_admin_status'),
    ]

    operations = [
        # 1. Backfill department_rel dari department legacy
        migrations.RunPython(backfill_department_rel, reverse_code=noop),

        # 2. Tandai field 'department' sebagai deprecated via db_comment
        migrations.AlterField(
            model_name='pegawai',
            name='department',
            field=models.CharField(
                max_length=255,
                null=True,
                blank=True,
                db_comment='DEPRECATED: Gunakan department_rel (ForeignKey ke Departemen). Field ini akan dihapus di migrasi berikutnya.',
            ),
        ),
    ]
