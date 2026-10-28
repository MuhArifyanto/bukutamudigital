"""
scripts/normalize_admin_role.py

Skrip utilitas mandiri untuk menyelaraskan nilai admin_role pada akun Tamu admin.
TIDAK dijalankan otomatis oleh start.sh atau proses deployment lainnya.

Penggunaan:
  1. Dry-run (hanya melihat akun yang akan diubah tanpa menulis ke database):
     python scripts/normalize_admin_role.py

  2. Menerapkan perubahan secara permanen (bungkus dalam transaksi atomik):
     python scripts/normalize_admin_role.py --apply
"""

import os
import sys
from pathlib import Path

# Tambahkan direktori root proyek ke sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bukudigital.settings')
import django
django.setup()

from django.db import transaction
from guest_book.models import Tamu


def normalize_admin_roles(apply=False, from_role='super_admin', to_role='operator'):
    """
    Menyelaraskan nilai admin_role dari `from_role` ke `to_role`.

    Args:
        apply (bool): False = mode dry-run (hanya membaca); True = terapkan perubahan.
        from_role (str): Nilai lama yang dicari (default: 'super_admin').
        to_role (str): Nilai baru yang valid di model (default: 'operator').

    Returns:
        dict: Berisi 'mode', 'success', 'count', 'targets', dan 'message'.
    """
    # 1. Cari akun yang memiliki admin_role = from_role
    targets_qs = Tamu.objects.filter(admin_role=from_role)
    count = targets_qs.count()

    details = [
        {
            'id': str(t.id),
            'name': t.name,
            'email': t.email,
            'nik': t.nik,
            'is_admin': t.is_admin,
            'account_status': t.account_status,
            'admin_role': t.admin_role
        }
        for t in targets_qs
    ]

    # Mode Dry-Run (Default): sama sekali tidak melakukan penulisan database
    if not apply:
        return {
            'mode': 'dry-run',
            'success': True,
            'count': count,
            'targets': details,
            'message': f"[DRY-RUN] Ditemukan {count} akun dengan admin_role='{from_role}'. Data TIDAK diubah."
        }

    if count == 0:
        return {
            'mode': 'apply',
            'success': True,
            'count': 0,
            'targets': [],
            'message': f"[APPLY] Tidak ada akun dengan admin_role='{from_role}' yang perlu diperbarui."
        }

    # 2. Mode Apply: jalankan dalam transaksi atomik
    with transaction.atomic():
        # Hanya mengubah field admin_role; tidak menyentuh is_admin, status, atau password
        updated_count = targets_qs.update(admin_role=to_role)

        # 3. Validasi keselamatan: pastikan setelah update tetap ada minimal satu admin aktif
        active_admin_exists = Tamu.objects.filter(is_admin=True, account_status='active').exists()
        if not active_admin_exists:
            transaction.set_rollback(True)
            raise RuntimeError(
                "Penyelarasan dibatalkan (Rollback): Tidak ada akun admin aktif (is_admin=True dan account_status='active') yang tersisa."
            )

    return {
        'mode': 'apply',
        'success': True,
        'count': updated_count,
        'targets': details,
        'message': f"[APPLY] Berhasil memperbarui {updated_count} baris akun menjadi admin_role='{to_role}'."
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Skrip Penyelarasan admin_role pada Sistem Informasi Buku Tamu Digital"
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help="Terapkan perubahan ke database secara permanen. Tanpa flag ini, skrip hanya melakukan simulasi (dry-run)."
    )
    parser.add_argument(
        '--from-role',
        default='super_admin',
        help="Nilai admin_role yang akan diubah (default: super_admin)"
    )
    parser.add_argument(
        '--to-role',
        default='operator',
        help="Nilai admin_role baru yang sah (default: operator)"
    )

    args = parser.parse_args()

    try:
        result = normalize_admin_roles(apply=args.apply, from_role=args.from_role, to_role=args.to_role)
        print("=" * 70)
        print(f"PENYELARASAN ADMIN ROLE - MODE: {result['mode'].upper()}")
        print("=" * 70)
        print(result['message'])
        if result['targets']:
            print("\nDaftar Akun Target:")
            for idx, acc in enumerate(result['targets'], start=1):
                print(f"  {idx}. ID: {acc['id']} | Nama: {acc['name']} | Email: {acc['email']} | is_admin: {acc['is_admin']}")
        print("=" * 70)
    except Exception as exc:
        print(f"\n[ERROR] Operasi dibatalkan: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
