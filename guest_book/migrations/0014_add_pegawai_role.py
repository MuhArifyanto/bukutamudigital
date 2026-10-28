# Generated migration for adding role field to Pegawai model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('guest_book', '0013_optimize_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='pegawai',
            name='role',
            field=models.CharField(
                choices=[
                    ('staff', 'Staff'),
                    ('supervisor', 'Supervisor'),
                    ('manager', 'Manager'),
                    ('admin', 'Admin')
                ],
                default='staff',
                max_length=20,
                verbose_name='Role'
            ),
        ),
        migrations.AddField(
            model_name='pegawai',
            name='nip',
            field=models.CharField(
                blank=True,
                max_length=50,
                null=True,
                verbose_name='NIP'
            ),
        ),
        migrations.AddField(
            model_name='pegawai',
            name='jabatan',
            field=models.CharField(
                blank=True,
                max_length=100,
                null=True,
                verbose_name='Jabatan'
            ),
        ),
        migrations.AddIndex(
            model_name='pegawai',
            index=models.Index(fields=['role'], name='pegawai_role_idx'),
        ),
    ]
