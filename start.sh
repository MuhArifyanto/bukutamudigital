#!/usr/bin/env bash
set -e

echo "==> Running collectstatic..."
python manage.py collectstatic --noinput || true

echo "==> Running database migrations..."
python manage.py migrate --noinput

echo "==> Starting Daphne server..."
exec daphne -b 0.0.0.0 -p ${PORT:-8000} bukudigital.asgi:application
