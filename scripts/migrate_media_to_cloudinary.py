"""
scripts/migrate_media_to_cloudinary.py

Skrip untuk memigrasikan file media lokal (di folder media/) ke Cloudinary Storage.
Fitur:
1. Mendukung mode --dry-run (default aktif jika tanpa argumen --apply).
2. TIDAK menggunakan .path pada model FieldFile (karena CloudinaryStorage tidak mendukung .path).
3. Membaca file fisik langsung dari path filesystem lokal MEDIA_ROOT, lalu mengunggah
   ke storage aktif menggunakan ContentFile.
4. Memperbarui referensi di database (Tamu.profile_picture dan ChatMessage.attachment).

PENTING:
- Jangan jalankan skrip ini tanpa memastikan CLOUDINARY_URL sudah terkonfigurasi.
- Selalu jalankan dengan mode simulasi terlebih dahulu:
    python scripts/migrate_media_to_cloudinary.py --dry-run
"""

import os
import sys
import argparse
from pathlib import Path

# Setup Django environment
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'bukudigital.settings')

import django
django.setup()

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from guest_book.models import Tamu, ChatMessage


def migrate_profiles(dry_run=True):
    print("\n[1/2] Memeriksa Foto Profil Tamu...")
    tamus = Tamu.objects.exclude(profile_picture='').exclude(profile_picture__isnull=True)
    count = 0
    migrated = 0

    for tamu in tamus:
        pic_name = str(tamu.profile_picture.name)
        # Jika sudah URL Cloudinary penuh, lewati
        if pic_name.startswith('http://') or pic_name.startswith('https://'):
            continue

        # Cari file di disk lokal
        local_path = settings.MEDIA_ROOT / pic_name
        if not local_path.exists():
            # Coba cari jika disimpan tanpa prefix folder
            alt_path = settings.MEDIA_ROOT / 'profiles' / Path(pic_name).name
            if alt_path.exists():
                local_path = alt_path
            else:
                continue

        count += 1
        print(f"  -> Ditemukan: Tamu ID={tamu.id} ({tamu.name}) | File={local_path.name}")
        if not dry_run:
            try:
                with open(local_path, 'rb') as f:
                    content = f.read()
                # Simpan ke storage Cloudinary
                new_path = f"profiles/{local_path.name}"
                saved_path = default_storage.save(new_path, ContentFile(content))
                tamu.profile_picture.name = saved_path
                tamu.save(update_fields=['profile_picture'])
                migrated += 1
                print(f"     [OK] Berhasil diunggah ke storage: {saved_path}")
            except Exception as e:
                print(f"     [ERROR] Gagal mengunggah: {e}")

    print(f"  Total foto profil lokal: {count} | Berhasil dimigrasi: {migrated}")


def migrate_chat_attachments(dry_run=True):
    print("\n[2/2] Memeriksa Lampiran Chat...")
    chats = ChatMessage.objects.exclude(attachment='').exclude(attachment__isnull=True)
    count = 0
    migrated = 0

    for chat in chats:
        att_name = str(chat.attachment.name)
        if att_name.startswith('http://') or att_name.startswith('https://'):
            continue

        local_path = settings.MEDIA_ROOT / att_name
        if not local_path.exists():
            alt_path = settings.MEDIA_ROOT / 'chat_attachments' / Path(att_name).name
            if alt_path.exists():
                local_path = alt_path
            else:
                continue

        count += 1
        print(f"  -> Ditemukan: Chat ID={chat.id} | File={local_path.name}")
        if not dry_run:
            try:
                with open(local_path, 'rb') as f:
                    content = f.read()
                new_path = f"chat_attachments/{local_path.name}"
                saved_path = default_storage.save(new_path, ContentFile(content))
                chat.attachment.name = saved_path
                chat.save(update_fields=['attachment'])
                migrated += 1
                print(f"     [OK] Berhasil diunggah ke storage: {saved_path}")
            except Exception as e:
                print(f"     [ERROR] Gagal mengunggah: {e}")

    print(f"  Total lampiran chat lokal: {count} | Berhasil dimigrasi: {migrated}")


def main():
    parser = argparse.ArgumentParser(description="Migrasi media lokal ke Cloudinary secara aman")
    parser.add_argument('--apply', action='store_true', help="Terapkan unggah sungguhan (tanpa flag ini hanya dry-run)")
    parser.add_argument('--dry-run', action='store_true', default=True, help="Simulasi tanpa mengunggah/mengubah DB")
    args = parser.parse_args()

    is_dry_run = not args.apply
    if is_dry_run:
        print("=== MODE SIMULASI (DRY-RUN) AKTIF ===")
        print("File tidak akan diunggah dan database tidak akan diubah.")
        print("Gunakan argumen --apply jika ingin mengeksekusi secara nyata.\n")
    else:
        print("=== MODE EKSEKUSI (APPLY) AKTIF ===")
        print("File lokal akan dibaca dan diunggah ke Cloudinary Storage...\n")

    migrate_profiles(dry_run=is_dry_run)
    migrate_chat_attachments(dry_run=is_dry_run)
    print("\nSelesai.")


if __name__ == '__main__':
    main()
