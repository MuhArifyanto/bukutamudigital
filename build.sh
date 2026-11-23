#!/usr/bin/env bash
# Build script untuk Render (set sebagai Build Command di dashboard Render)
set -o errexit

# Install dependencies secara deterministik dari lockfile
pip install --no-deps -r requirements.lock

# Kumpulkan semua static files ke staticfiles/
python manage.py collectstatic --noinput

# Jalankan migrasi database
python manage.py migrate --noinput

# Pastikan tabel cache database terbuat di production
python manage.py createcachetable || true

# Buat / pastikan akun administrator siap digunakan di hosting
python manage.py setup_admin || true
