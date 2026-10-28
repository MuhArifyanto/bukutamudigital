#!/usr/bin/env bash
set -e

echo "==> Running migrations..."
python manage.py migrate --noinput

echo "==> Ensuring cache table exists..."
python manage.py createcachetable

echo "==> Collecting static files..."
python manage.py collectstatic --noinput

if [ -n "$ADMIN_INITIAL_PASSWORD" ]; then
  echo "==> Ensuring initial admin exists..."
  python manage.py shell -c "
import os
from django.contrib.auth.models import User
from guest_book.models import Tamu

pw = os.environ['ADMIN_INITIAL_PASSWORD']
email = os.environ.get('ADMIN_EMAIL', 'admin@diskominfosantik.bekasikab.go.id')

if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', email, pw)
    print('CREATED: superuser admin')
else:
    print('SKIPPED: superuser admin sudah ada, password tidak diubah')

if not Tamu.objects.filter(is_admin=True).exists():
    Tamu.objects.create(
        name='Administrator', email=email, phone='081234567890',
        nik='admin', is_admin=True, admin_role='operator',
        account_status='active'
    )
    print('CREATED: Tamu admin record')

"
else
  echo "==> ADMIN_INITIAL_PASSWORD tidak diset, pembuatan admin dilewati"
fi

echo "==> Starting Daphne server..."
exec daphne -b 0.0.0.0 -p ${PORT:-8000} bukudigital.asgi:application