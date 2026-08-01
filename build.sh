#!/usr/bin/env bash
# Build script untuk Render (set sebagai Build Command di dashboard Render)
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Kumpulkan semua static files ke staticfiles/
python manage.py collectstatic --noinput

# Jalankan migrasi database
python manage.py migrate
