#!/usr/bin/env bash
set -e

echo "==> Running collectstatic..."
python manage.py collectstatic --noinput || true

echo "==> Running database migrations..."
python manage.py migrate --noinput

echo "==> Ensuring default admin superuser exists..."
python manage.py shell -c "
from django.contrib.auth.models import User
from guest_book.models import Tamu

# 1. Create Django auth superuser (admin / admin123)
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@diskominfosantik.bekasikab.go.id', 'admin123')
    print('CREATED: Superuser admin (password: admin123)')
else:
    u = User.objects.get(username='admin')
    u.set_password('admin123')
    u.is_staff = True
    u.is_superuser = True
    u.save()
    print('UPDATED: Superuser admin password set to admin123')

# 2. Create Tamu admin profile if missing
if not Tamu.objects.filter(nik='admin').exists() and not Tamu.objects.filter(is_admin=True).exists():
    Tamu.objects.create(
        name='Super Admin',
        email='admin@diskominfosantik.bekasikab.go.id',
        phone='081234567890',
        nik='admin',
        is_admin=True,
        admin_role='super_admin',
        account_status='active'
    )
    print('CREATED: Tamu admin record')
"

echo "==> Starting Daphne server..."
exec daphne -b 0.0.0.0 -p ${PORT:-8000} bukudigital.asgi:application
