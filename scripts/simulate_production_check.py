"""
scripts/simulate_production_check.py
Simulasi pemeriksaan kesiapan deployment produksi (manage.py check --deploy)
dengan variabel lingkungan simulasi produksi.
"""

import os
import subprocess
import sys

def main():
    print("=" * 70)
    print("SIMULASI PENGECEKAN DEPLOYMENT PRODUKSI (Django check --deploy)")
    print("=" * 70)

    env = os.environ.copy()
    env['APP_ENV'] = 'production'
    env['SECRET_KEY'] = 'django-prod-test-key-!@#$%-random-secure-production-key-50-characters-long-safe-example'
    env['ALLOWED_HOSTS'] = 'bukutamu.diskominfosantik.bekasikab.go.id,localhost'
    env['CSRF_TRUSTED_ORIGINS'] = 'https://bukutamu.diskominfosantik.bekasikab.go.id,https://localhost'
    env['FIREBASE_WEBHOOK_SECRET'] = 'prod-webhook-token-sample-secure'
    env['USE_PROXY_SSL_HEADER'] = 'True'
    env['SECURE_HSTS_SECONDS'] = '3600'

    cmd = [sys.executable, 'manage.py', 'check', '--deploy']
    result = subprocess.run(cmd, env=env)
    print("\n" + "=" * 70)
    print(f"Hasil Eksekusi: Exit Code {result.returncode}")
    print("=" * 70)

if __name__ == '__main__':
    main()
