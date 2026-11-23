#!/usr/bin/env bash
set -e

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Ensuring cache table exists..."
python manage.py createcachetable || true

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

echo "==> Syncing admin & official pegawai records..."
python manage.py setup_admin || true

echo "==> Starting Daphne server..."
exec daphne -b 0.0.0.0 -p ${PORT:-8000} bukudigital.asgi:application
