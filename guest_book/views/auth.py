import os
import json
import logging
import ipaddress
import secrets
from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError
from django.shortcuts import render, redirect
from django.contrib import messages
from django.http import JsonResponse
from django.utils import timezone
from django.templatetags.static import static
from django.views.decorators.debug import sensitive_variables

from ..models import Tamu
from ..forms import TamuLoginForm, TamuRegisterForm

security_logger = logging.getLogger('guest_book.security')


def get_client_ip(request):
    """
    Mengambil IP address klien secara aman di belakang reverse proxy hosting.
    - Hanya mempercayai header forwarded jika REMOTE_ADDR berasal dari proxy/loopback/private IP.
    - Fallback aman ke REMOTE_ADDR jika tidak ada proxy atau format tidak valid.
    """
    remote_addr = (request.META.get('REMOTE_ADDR') or '').strip()
    is_trusted_proxy = False
    if remote_addr:
        try:
            ip_obj = ipaddress.ip_address(remote_addr)
            if ip_obj.is_loopback or ip_obj.is_private:
                is_trusted_proxy = True
        except ValueError:
            pass

    if is_trusted_proxy:
        # 1. Cloudflare connecting IP
        cf_ip = (request.META.get('HTTP_CF_CONNECTING_IP') or '').strip()
        if cf_ip:
            try:
                ipaddress.ip_address(cf_ip)
                return cf_ip
            except ValueError:
                pass

        # 2. X-Forwarded-For (ambil IP publik/klien pertama yang valid)
        x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
        if x_forwarded:
            ips = [i.strip() for i in x_forwarded.split(',') if i.strip()]
            for ip_candidate in ips:
                try:
                    ipaddress.ip_address(ip_candidate)
                    return ip_candidate
                except ValueError:
                    continue

    return remote_addr or '127.0.0.1'


def check_rate_limit(key, max_attempts=5):
    """Cek apakah batas percobaan pada cache terlampaui."""
    try:
        attempts = cache.get(key, 0)
        return attempts >= max_attempts
    except Exception:
        return False


def record_rate_limit_attempt(key, timeout_seconds=900):
    """Tambah 1 percobaan gagal pada cache rate limit."""
    try:
        attempts = cache.get(key, 0)
        cache.set(key, attempts + 1, timeout=timeout_seconds)
    except Exception:
        pass


def clear_rate_limit(key):
    """Reset percobaan pada cache rate limit saat berhasil."""
    try:
        cache.delete(key)
    except Exception:
        pass


def _get_rate_limit_key(ip_address, user_type='all'):
    return f"rl_{user_type}_{ip_address}"


# ============================================================================
# GRID CAPTCHA SERVER-SIDE BANK & VALIDATION (Opsi A: 21 Variasi Server-Bound)
# ============================================================================

PUZZLE_BANK = {
    0: {'label': 'Lampu Lalu Lintas', 'img': 'images/captcha/captcha_0.png', 'correct': [1, 2, 5, 6, 9, 10]},
    1: {'label': 'Penyeberangan Jalan (Zebra Cross)', 'img': 'images/captcha/captcha_1.png', 'correct': [8, 9, 10, 11, 12, 13, 14, 15]},
    2: {'label': 'Sepeda', 'img': 'images/captcha/captcha_2.png', 'correct': [5, 6, 7, 9, 10, 11, 13, 14]},
    3: {'label': 'Mobil', 'img': 'images/captcha/captcha_3.png', 'correct': [5, 6, 7, 9, 10, 11, 13, 14]},
    4: {'label': 'Bus', 'img': 'images/captcha/captcha_4.png', 'correct': [4, 5, 6, 8, 9, 10, 12, 13, 14]},
    5: {'label': 'Sepeda Motor', 'img': 'images/captcha/captcha_5.png', 'correct': [5, 6, 7, 9, 10, 11, 13, 14]},
    6: {'label': 'Hidran Kebakaran', 'img': 'images/captcha/captcha_6.png', 'correct': [5, 6, 9, 10, 13, 14]},
    7: {'label': 'Jembatan', 'img': 'images/captcha/captcha_7.png', 'correct': [4, 5, 6, 7, 8, 9, 10, 11]},
    8: {'label': 'Tangga', 'img': 'images/captcha/captcha_8.png', 'correct': [4, 5, 8, 9, 12, 13, 14]},
    9: {'label': 'Perahu', 'img': 'images/captcha/captcha_9.png', 'correct': [9, 10, 11, 13, 14, 15]},
    10: {'label': 'Wanita Cantik', 'img': 'images/captcha/captcha_10.png', 'correct': [2, 5, 6, 9, 10, 13, 14]},
    # Variasi tambahan / negasi / target spesifik (Opsi A)
    11: {'label': 'Area Bukan Lampu Lalu Lintas (Latar Belakang)', 'img': 'images/captcha/captcha_0.png', 'correct': [0, 3, 4, 7, 8, 11, 12, 13, 14, 15]},
    12: {'label': 'Area Jalan Tanpa Zebra Cross', 'img': 'images/captcha/captcha_1.png', 'correct': [0, 1, 2, 3, 4, 5, 6, 7]},
    13: {'label': 'Roda atau Bagian Bawah Bus', 'img': 'images/captcha/captcha_4.png', 'correct': [12, 13, 14]},
    14: {'label': 'Roda Sepeda Motor', 'img': 'images/captcha/captcha_5.png', 'correct': [13, 14]},
    15: {'label': 'Struktur Atas Jembatan', 'img': 'images/captcha/captcha_7.png', 'correct': [4, 5, 6, 7]},
    16: {'label': 'Air di Sekitar Perahu', 'img': 'images/captcha/captcha_9.png', 'correct': [0, 1, 2, 3, 4, 5, 6, 7, 8]},
    17: {'label': 'Latar Belakang Tanpa Mobil', 'img': 'images/captcha/captcha_3.png', 'correct': [0, 1, 2, 3, 4, 8, 12, 15]},
    18: {'label': 'Bagian Puncak Tangga', 'img': 'images/captcha/captcha_8.png', 'correct': [4, 5]},
    19: {'label': 'Latar Belakang Tanpa Hidran Kebakaran', 'img': 'images/captcha/captcha_6.png', 'correct': [0, 1, 2, 3, 4, 7, 8, 11, 12, 15]},
    20: {'label': 'Latar Belakang Tanpa Sepeda', 'img': 'images/captcha/captcha_2.png', 'correct': [0, 1, 2, 3, 4, 8, 12, 15]},
}


def api_refresh_captcha(request):
    """API untuk menghasilkan puzzle captcha acak baru dan menyimpannya di session server"""
    client_ip = get_client_ip(request)
    rl_key = f"rl_captcha_refresh_{client_ip}"
    if check_rate_limit(rl_key, max_attempts=30):
        return JsonResponse({'success': False, 'message': 'Terlalu banyak permintaan refresh captcha.'}, status=429)

    record_rate_limit_attempt(rl_key, timeout_seconds=900)

    expected_idx = secrets.choice(list(PUZZLE_BANK.keys()))
    puzzle = PUZZLE_BANK[expected_idx]

    request.session['captcha_expected_index'] = expected_idx
    request.session['captcha_issued_at'] = timezone.now().timestamp()

    return JsonResponse({
        'success': True,
        'label': puzzle['label'],
        'imgUrl': static(puzzle['img'])
    })


def validate_grid_captcha(request, selected_tiles_json=None, trajectory_json=None, *args, **kwargs):
    """
    Validasi kustom Grid Selection Captcha:
    1. Mengabaikan puzzle_index kiriman klien; membaca captcha_expected_index dari request.session.
    2. Bersifat sekali pakai (single-use): session.pop('captcha_expected_index') langsung dibersihkan.
    3. Memvalidasi masa berlaku singkat (5 menit / 300 detik).
    4. Menolak jawaban kosong atau sesi tanpa captcha.
    5. Membatasi percobaan gagal dengan rate limit per IP.
    """
    import json

    if not hasattr(request, 'session'):
        return False, "Sesi request tidak valid."

    client_ip = get_client_ip(request)
    rl_key = f"rl_captcha_fail_{client_ip}"

    # Pembatasan laju: maks 5 kali percobaan gagal per 15 menit
    if check_rate_limit(rl_key, max_attempts=5):
        return False, "Terlalu banyak percobaan captcha yang gagal. Silakan tunggu 15 menit."

    # Sekali pakai (single-use): pop dari session segera saat validasi
    expected_idx = request.session.pop('captcha_expected_index', None)
    issued_at = request.session.pop('captcha_issued_at', None)

    if expected_idx is None or issued_at is None:
        record_rate_limit_attempt(rl_key, timeout_seconds=900)
        return False, "Sesi captcha tidak ditemukan atau telah kedaluwarsa. Silakan refresh captcha."

    # Validasi masa berlaku (5 menit = 300 detik)
    now_ts = timezone.now().timestamp()
    if now_ts - float(issued_at) > 300:
        record_rate_limit_attempt(rl_key, timeout_seconds=900)
        return False, "Captcha telah kedaluwarsa (lebih dari 5 menit). Silakan refresh captcha."

    if expected_idx not in PUZZLE_BANK:
        record_rate_limit_attempt(rl_key, timeout_seconds=900)
        return False, "Kategori captcha server tidak valid."

    # Parse ubin terpilih
    try:
        if isinstance(selected_tiles_json, list):
            selected_tiles = selected_tiles_json
        elif isinstance(selected_tiles_json, str):
            selected_tiles = json.loads(selected_tiles_json) if selected_tiles_json else []
        else:
            selected_tiles = []
    except Exception:
        record_rate_limit_attempt(rl_key, timeout_seconds=900)
        return False, "Format pilihan ubin tidak valid."

    if not isinstance(selected_tiles, list) or len(selected_tiles) == 0:
        record_rate_limit_attempt(rl_key, timeout_seconds=900)
        return False, "Jawaban captcha tidak boleh kosong."

    try:
        user_tiles = sorted([int(x) for x in selected_tiles])
    except (TypeError, ValueError):
        record_rate_limit_attempt(rl_key, timeout_seconds=900)
        return False, "Elemen pilihan ubin harus berupa angka."

    # Validasi Trajektori Klik manusia
    if trajectory_json:
        try:
            trajectory = json.loads(trajectory_json) if isinstance(trajectory_json, str) else trajectory_json
            if isinstance(trajectory, list) and len(trajectory) > 2:
                click_times = [float(pt.get('t', 0)) for pt in trajectory if isinstance(pt, dict) and 't' in pt]
                click_times.sort()
                time_diffs = [click_times[i] - click_times[i-1] for i in range(1, len(click_times))]
                if time_diffs:
                    avg_diff = sum(time_diffs) / len(time_diffs)
                    variance = sum((diff - avg_diff) ** 2 for diff in time_diffs) / len(time_diffs)
                    if variance == 0:
                        record_rate_limit_attempt(rl_key, timeout_seconds=900)
                        return False, "Interval klik terlalu stabil (terdeteksi bot)."
        except Exception:
            pass

    # Bandingkan jawaban pengguna dengan kunci jawaban server
    correct_tiles = sorted(PUZZLE_BANK[expected_idx]['correct'])
    if user_tiles != correct_tiles:
        record_rate_limit_attempt(rl_key, timeout_seconds=900)
        return False, "Pilihan gambar belum tepat. Silakan coba lagi."

    # Berhasil! Reset failure rate limit
    clear_rate_limit(rl_key)
    return True, "Validasi captcha berhasil."

def check_login_rate_limit(ip_address, user_type=None, max_attempts=5, timeout_minutes=15):
    """
    Cek apakah IP telah melebihi batas percobaan gagal login.
    Memanfaatkan backend cache terkonfigurasi (DatabaseCache di production, LocMemCache di local),
    serta sinkron dengan record LoginAttempt di database.
    """
    key = _get_rate_limit_key(ip_address, user_type or 'all')
    cache_attempts = 0
    try:
        cache_attempts = cache.get(key, 0)
    except Exception:
        pass
    if cache_attempts >= max_attempts:
        return True

    from ..models import LoginAttempt
    from django.utils import timezone
    from datetime import timedelta
    time_threshold = timezone.now() - timedelta(minutes=timeout_minutes)
    query = LoginAttempt.objects.filter(ip_address=ip_address, success=False, timestamp__gte=time_threshold)
    if user_type:
        query = query.filter(user_type=user_type)
    db_attempts = query.count()

    total = max(cache_attempts, db_attempts)
    return total >= max_attempts

def record_failed_login(ip_address, email='', user_type='all', timeout_seconds=900):
    """
    Catat kegagalan login di cache dan di tabel LoginAttempt.
    """
    key = _get_rate_limit_key(ip_address, user_type)
    try:
        current = cache.get(key, 0)
        cache.set(key, current + 1, timeout=timeout_seconds)
    except Exception:
        pass

    try:
        from ..models import LoginAttempt
        LoginAttempt.objects.create(
            email=email or 'unknown',
            user_type=user_type,
            success=False,
            ip_address=ip_address
        )
    except Exception:
        pass

def clear_failed_login(ip_address, user_type='all'):
    """
    Reset cache percobaan gagal saat login berhasil.
    """
    key = _get_rate_limit_key(ip_address, user_type)
    try:
        cache.delete(key)
    except Exception:
        pass


def login_view(request):
    """View untuk Login Tamu & Admin"""
    from ..models import LoginAttempt
    
    if request.session.get('tamu_id'):
        return redirect('tamu:dashboard')

    form = TamuLoginForm(request.POST or None)
    if request.method == 'POST':
        ip_address = get_client_ip(request)
        username_attempt = request.POST.get('username', '')
        
        # Rate Limiting Check (Max 5 failed attempts in 15 mins via cache & db)
        if check_login_rate_limit(ip_address, user_type='tamu'):
            messages.error(request, "Terlalu banyak upaya masuk yang gagal. Akun/IP Anda ditangguhkan sementara selama 15 menit. Silakan coba lagi nanti.")
            return render(request, 'guest_book/tamu_login.html', {
                'form': form,
                'user_logged_in': False,
            })

        if form.is_valid():
            tamu = form.tamu
            request.session.cycle_key()
            request.session.pop('pegawai_id', None)
            request.session.pop('pegawai_name', None)
            request.session.pop('pegawai_role', None)
            request.session['tamu_id'] = str(tamu.pk)
            
            # Reset rate limit on success
            clear_failed_login(ip_address, user_type='tamu')

            # Record successful login attempt
            LoginAttempt.objects.create(
                email=tamu.email,
                user_type='tamu',
                success=True,
                ip_address=ip_address
            )
            
            messages.success(request, f"Selamat datang kembali, {tamu.name}!")
            return redirect('tamu:dashboard')
        else:
            # Record failed login attempt in both cache and DB
            username = request.POST.get('username')
            email = username or 'unknown'
            if username:
                from django.db.models import Q
                tamu_obj = Tamu.objects.filter(Q(name=username) | Q(email=username)).first()
                if tamu_obj:
                    email = tamu_obj.email
            record_failed_login(ip_address, email=email, user_type='tamu')


    return render(request, 'guest_book/tamu_login.html', {
        'form': form,
        'user_logged_in': False,
    })

def register_view(request):
    """View untuk Registrasi Tamu Baru"""
    if request.session.get('tamu_id'):
        return redirect('tamu:dashboard')

    form = TamuRegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        captcha_selected_tiles = request.POST.get('captcha_selected_tiles')
        captcha_trajectory = request.POST.get('captcha_trajectory')
        
        captcha_success, captcha_err = validate_grid_captcha(request, captcha_selected_tiles, captcha_trajectory)
        if not captcha_success:
            messages.error(request, captcha_err)
            return render(request, 'guest_book/tamu_register.html', {
                'form': form,
                'user_logged_in': False,
            })

        tamu = form.save()
        messages.success(request, "Registrasi berhasil! Silakan masuk menggunakan akun Anda.")
        return redirect('tamu:login')

    return render(request, 'guest_book/tamu_register.html', {
        'form': form,
        'user_logged_in': False,
    })

def logout_view(request):
    """View untuk Logout"""
    request.session.flush()
    messages.success(request, "Anda telah berhasil keluar.")
    return redirect('tamu:login')

from django.views.decorators.csrf import csrf_exempt


def _establish_tamu_session(request, tamu):
    """
    Buat sesi Tamu yang bersih: rotasi session key (anti session fixation),
    hapus kunci peran lain, lalu isi tamu_id.
    """
    request.session.cycle_key()
    for stale_key in ('pegawai_id', 'pegawai_name', 'pegawai_role', 'is_admin', 'is_staff', 'role'):
        request.session.pop(stale_key, None)
    request.session['tamu_id'] = str(tamu.pk)
    request.session.set_expiry(86400)  # Sesi aktif 1 hari

@csrf_exempt
def api_firebase_login(request):
    """API untuk Login/Register via Firebase (Google SSO & Email/Password)"""
    from django.http import JsonResponse
    from django.urls import reverse
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests
    import json
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Hanya menerima metode POST.'}, status=405)

    client_ip = get_client_ip(request)
    rl_key = f"rl_firebase_{client_ip}"

    # Pembatasan laju (Max 5 percobaan gagal per 15 menit)
    if check_rate_limit(rl_key, max_attempts=5):
        return JsonResponse({
            'success': False,
            'message': 'Terlalu banyak percobaan masuk yang gagal. Silakan coba lagi nanti dalam 15 menit.'
        }, status=429)

    try:
        data = json.loads(request.body)
        id_token_str = data.get('id_token')
        
        if not id_token_str:
            record_rate_limit_attempt(rl_key)
            return JsonResponse({'success': False, 'message': 'ID Token tidak ditemukan.'}, status=400)
            
        # Verifikasi token menggunakan Firebase
        firebase_project_id = getattr(settings, 'FIREBASE_PROJECT_ID', None) or os.getenv('FIREBASE_PROJECT_ID', 'bukutamudigital-43ae7')
        id_info = id_token.verify_firebase_token(
            id_token_str, 
            google_requests.Request(), 
            audience=firebase_project_id
        )
        
        email = id_info.get('email')
        uid = id_info.get('sub') # Firebase UID
        
        if not email:
            record_rate_limit_attempt(rl_key)
            return JsonResponse({'success': False, 'message': 'Email tidak valid dari Firebase.'}, status=400)

        # Status verifikasi email dari token (dipakai pada keputusan di bawah)
        email_verified = bool(id_info.get('email_verified', False))
            
        # Dapatkan data tambahan dari payload (jika dikirim untuk pendaftaran)
        name = data.get('name') or id_info.get('name') or email.split('@')[0]
        nik = data.get('nik')
        phone = data.get('phone') or '-'
        instansi = data.get('instansi') or '-'
        registration_type = data.get('registration_type') or 'google_sso'
        
        from ..models import Tamu, LoginAttempt
        
        # Cari tamu berdasarkan email terverifikasi
        tamu = Tamu.objects.filter(email=email).first()
        created = False
        
        if tamu:
            # Periksa status akun (nonaktif atau diblokir wajib ditolak)
            if tamu.account_status != 'active':
                record_rate_limit_attempt(rl_key)
                record_failed_login(client_ip, email=email, user_type='tamu')
                return JsonResponse({
                    'success': False,
                    'message': 'Akun Anda dinonaktifkan atau diblokir. Silakan hubungi Administrator.'
                }, status=403)

            # Email belum terverifikasi hanya boleh membuat sesi bila UID Firebase ini
            # sudah terikat ke akun Tamu tersebut (bukti kepemilikan sebelumnya).
            if not email_verified and not (tamu.google_id and tamu.google_id == uid):
                record_rate_limit_attempt(rl_key)
                return JsonResponse({
                    'success': False,
                    'message': 'Email belum diverifikasi di Firebase. Silakan verifikasi email Anda terlebih dahulu.'
                }, status=403)
        else:
            # Akun baru dari email belum terverifikasi hanya boleh lewat registrasi email
            # (yang tidak membuat sesi, pengguna diarahkan ke halaman login).
            if not email_verified and registration_type != 'firebase_email':
                record_rate_limit_attempt(rl_key)
                return JsonResponse({
                    'success': False,
                    'message': 'Email belum diverifikasi di Firebase. Silakan verifikasi email Anda terlebih dahulu.'
                }, status=403)
            # Validasi Grid Captcha jika ini adalah registrasi baru secara manual/email
            if registration_type == 'firebase_email':
                captcha_selected_tiles = data.get('captcha_selected_tiles')
                captcha_trajectory = data.get('captcha_trajectory')
                captcha_success, captcha_err = validate_grid_captcha(request, captcha_selected_tiles, captcha_trajectory)
                if not captcha_success:
                    record_rate_limit_attempt(rl_key)
                    return JsonResponse({'success': False, 'message': captcha_err}, status=400)

            # Jika tamu belum terdaftar di MySQL, buat tamu baru (pastikan bukan admin)
            tamu = Tamu.objects.create(
                email=email,
                name=name,
                nik=nik,
                phone=phone,
                instansi=instansi,
                registration_type=registration_type,
                google_id=uid,
                account_status='active',
                is_admin=False
            )
            created = True

        if not created:
            # Jika tamu sudah terdaftar tapi data google_id kosong, perbarui
            if not tamu.google_id:
                tamu.google_id = uid
                tamu.save(update_fields=['google_id'])
            
            # Jika ada update profil opsional yang dikirim saat login
            updated_fields = []
            if nik and not tamu.nik:
                tamu.nik = nik
                updated_fields.append('nik')
            if phone and phone != '-' and tamu.phone == '-':
                tamu.phone = phone
                updated_fields.append('phone')
            if instansi and instansi != '-' and tamu.instansi == '-':
                tamu.instansi = instansi
                updated_fields.append('instansi')
            if updated_fields:
                tamu.save(update_fields=updated_fields)
        
        # Set session untuk Django
        if created and registration_type == 'firebase_email':
            # Jika baru registrasi secara manual/email, jangan set session login, arahkan ke login page
            from django.contrib import messages
            messages.success(request, 'Registrasi berhasil! Silakan masuk menggunakan akun Anda.')
            redirect_url = reverse('tamu:login')
            message = 'Registrasi berhasil. Silakan masuk menggunakan akun Anda.'
        else:
            # Sesi bersih: cycle_key, bersihkan kunci peran lain, isi tamu_id
            _establish_tamu_session(request, tamu)

            # Reset rate limit setelah login berhasil
            clear_rate_limit(rl_key)
            clear_failed_login(client_ip, user_type='tamu')

            redirect_url = reverse('tamu:dashboard')
            message = 'Registrasi berhasil.' if created else 'Login berhasil.'
            
            # Tulis ke LoginAttempt untuk keamanan jika login sukses
            LoginAttempt.objects.create(
                email=email,
                user_type='tamu',
                success=True,
                ip_address=client_ip
            )
        
        return JsonResponse({
            'success': True, 
            'redirect_url': redirect_url,
            'message': message
        })
        
    except ValueError:
        record_rate_limit_attempt(rl_key)
        record_failed_login(client_ip, user_type='tamu')
        return JsonResponse({'success': False, 'message': 'Token Firebase tidak valid atau kedaluwarsa.'}, status=401)
    except Exception:
        record_rate_limit_attempt(rl_key)
        return JsonResponse({'success': False, 'message': 'Terjadi kesalahan saat memproses autentikasi.'}, status=400)

VALIDATE_REGISTER_IP_MAX = 15          # permintaan per IP per 15 menit
VALIDATE_REGISTER_IDENTIFIER_MAX = 5   # permintaan per email/NIK per 15 menit
VALIDATE_REGISTER_WINDOW = 900


def api_validate_register(request):
    """
    Cek keunikan email/NIK sebelum registrasi.

    Kompromi UX: pengguna tetap mendapat umpan balik "sudah terdaftar", tetapi
    pesannya tidak membedakan email vs NIK. CSRF aktif, hanya POST, dan dibatasi laju
    per IP serta per identifier (kunci cache memakai hash).
    """
    from django.db.models import Q
    from ..security_utils import hash_identifier, mask_email, mask_nik

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Hanya menerima metode POST.'}, status=405)

    client_ip = get_client_ip(request)
    ip_key = f"rl_vreg_ip_{client_ip}"
    if check_rate_limit(ip_key, max_attempts=VALIDATE_REGISTER_IP_MAX):
        security_logger.warning('Validasi registrasi dibatasi (IP) ip=%s', client_ip)
        return JsonResponse({
            'success': False,
            'message': 'Terlalu banyak permintaan. Silakan coba lagi dalam 15 menit.'
        }, status=429)
    record_rate_limit_attempt(ip_key, timeout_seconds=VALIDATE_REGISTER_WINDOW)

    try:
        data = json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        data = None
    if not isinstance(data, dict):
        return JsonResponse({'success': False, 'message': 'Permintaan tidak valid.'}, status=400)

    email = data.get('email')
    nik = data.get('nik')
    email = email.strip() if isinstance(email, str) else ''
    nik = nik.strip() if isinstance(nik, str) else ''
    if not email or not nik or len(email) > 254 or len(nik) > 32:
        return JsonResponse({'success': False, 'message': 'Email dan NIK wajib diisi.'}, status=400)

    email_key = f"rl_vreg_email_{hash_identifier(email)}"
    nik_key = f"rl_vreg_nik_{hash_identifier(nik)}"
    if (check_rate_limit(email_key, max_attempts=VALIDATE_REGISTER_IDENTIFIER_MAX)
            or check_rate_limit(nik_key, max_attempts=VALIDATE_REGISTER_IDENTIFIER_MAX)):
        security_logger.warning(
            'Validasi registrasi dibatasi (identifier) ip=%s email=%s nik=%s',
            client_ip, mask_email(email), mask_nik(nik),
        )
        return JsonResponse({
            'success': False,
            'message': 'Terlalu banyak permintaan. Silakan coba lagi dalam 15 menit.'
        }, status=429)
    record_rate_limit_attempt(email_key, timeout_seconds=VALIDATE_REGISTER_WINDOW)
    record_rate_limit_attempt(nik_key, timeout_seconds=VALIDATE_REGISTER_WINDOW)

    try:
        already_used = Tamu.objects.filter(Q(email__iexact=email) | Q(nik=nik)).exists()
    except Exception as exc:
        security_logger.error('Validasi registrasi gagal diproses (%s).', type(exc).__name__)
        return JsonResponse({
            'success': False,
            'message': 'Terjadi kesalahan. Silakan coba lagi.'
        }, status=503)

    if already_used:
        security_logger.info(
            'Registrasi dengan data yang sudah terpakai ip=%s email=%s nik=%s',
            client_ip, mask_email(email), mask_nik(nik),
        )
        return JsonResponse({
            'success': False,
            'message': 'Email atau NIK sudah terdaftar. Gunakan data lain atau masuk ke akun Anda.'
        })

    return JsonResponse({'success': True, 'message': 'Validasi berhasil.'})

# ── Login Tamu server-side (email / NIK + password) ──────────────────────────
# Email tidak pernah dikirim ke browser: server mencari Tamu, memanggil Firebase
# (REST, timeout 10 detik), memverifikasi token ID, memeriksa status akun, lalu membuat sesi.

LOGIN_GENERIC_FAILURE = 'Email/NIK atau password salah, atau akun tidak dapat digunakan.'
LOGIN_SERVICE_UNAVAILABLE = 'Layanan autentikasi sedang tidak tersedia. Silakan coba beberapa saat lagi.'
LOGIN_RATE_LIMITED = 'Terlalu banyak percobaan masuk. Silakan coba lagi dalam 15 menit.'
LOGIN_IP_MAX = 10          # percobaan gagal per IP per 15 menit
LOGIN_IDENTIFIER_MAX = 5   # percobaan gagal per identifier per 15 menit
LOGIN_WINDOW_SECONDS = 900
# Akun tiruan: dipakai agar waktu respons untuk identifier yang tidak ada setara dengan yang ada.
_LOGIN_DUMMY_EMAIL = 'tidak-ada@bukutamu.invalid'


@sensitive_variables('password', 'data')
def api_tamu_login(request):
    """Login Tamu dengan email atau NIK + password (diproses di server)."""
    from django.urls import reverse
    from ..models import LoginAttempt
    from .. import firebase_rest
    from ..security_utils import classify_identifier, hash_identifier, mask_identifier

    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Metode tidak diizinkan.'}, status=405)

    client_ip = get_client_ip(request)

    try:
        try:
            data = json.loads(request.body or b'{}')
        except (ValueError, UnicodeDecodeError):
            data = None
        if not isinstance(data, dict):
            return JsonResponse({'success': False, 'message': 'Permintaan tidak valid.'}, status=400)

        raw_identifier = data.get('identifier')
        password = data.get('password')
        if (not isinstance(raw_identifier, str) or not raw_identifier.strip()
                or not isinstance(password, str) or not password or len(password) > 256):
            return JsonResponse({
                'success': False,
                'message': 'Email/NIK dan password wajib diisi.'
            }, status=400)
        del data  # jangan simpan payload (berisi password) lebih lama dari perlu

        raw_identifier = raw_identifier.strip()[:254]
        kind, identifier = classify_identifier(raw_identifier)
        masked_id = mask_identifier(raw_identifier)

        ip_key = f"rl_tlogin_ip_{client_ip}"
        id_key = f"rl_tlogin_id_{hash_identifier(identifier or raw_identifier)}"

        if (check_rate_limit(ip_key, max_attempts=LOGIN_IP_MAX)
                or check_rate_limit(id_key, max_attempts=LOGIN_IDENTIFIER_MAX)):
            security_logger.warning('Login Tamu dibatasi ip=%s id=%s', client_ip, masked_id)
            return JsonResponse({'success': False, 'message': LOGIN_RATE_LIMITED}, status=429)

        def fail(reason):
            record_rate_limit_attempt(ip_key, timeout_seconds=LOGIN_WINDOW_SECONDS)
            record_rate_limit_attempt(id_key, timeout_seconds=LOGIN_WINDOW_SECONDS)
            record_failed_login(client_ip, email=masked_id, user_type='tamu')
            security_logger.warning('Login Tamu gagal ip=%s id=%s alasan=%s', client_ip, masked_id, reason)
            return JsonResponse({'success': False, 'message': LOGIN_GENERIC_FAILURE}, status=401)

        if kind is None:
            return fail('format_identifier')

        # 1. Cari Tamu (email atau NIK yang cocok tepat satu akun)
        tamu = None
        if kind == 'email':
            tamu = Tamu.objects.filter(email__iexact=identifier).first()
        else:
            matches = list(Tamu.objects.filter(nik=identifier)[:2])
            if len(matches) == 1:
                tamu = matches[0]

        # 2. Autentikasi ke Firebase (selalu dipanggil agar waktu respons setara)
        target_email = tamu.email if tamu else _LOGIN_DUMMY_EMAIL
        fb_status, id_token_str = firebase_rest.sign_in_with_password(target_email, password)
        del password
        if fb_status == firebase_rest.UNAVAILABLE:
            return JsonResponse({'success': False, 'message': LOGIN_SERVICE_UNAVAILABLE}, status=503)
        if fb_status != firebase_rest.OK or tamu is None:
            return fail('tidak_ditemukan_atau_password_salah')

        # 3. Verifikasi token ID dan cocokkan identitas dengan data Tamu
        v_status, claims = firebase_rest.verify_id_token(id_token_str)
        if v_status == firebase_rest.UNAVAILABLE:
            return JsonResponse({'success': False, 'message': LOGIN_SERVICE_UNAVAILABLE}, status=503)
        if v_status != firebase_rest.OK:
            return fail('token_tidak_valid')

        token_email = (claims.get('email') or '').strip().lower()
        uid = claims.get('sub')
        if not uid or token_email != (tamu.email or '').strip().lower():
            return fail('identitas_token_tidak_cocok')

        # 4. Status akun diperiksa SEBELUM sesi dibuat
        if tamu.account_status != 'active':
            return fail('akun_tidak_aktif')

        # 5. Ikatan UID Firebase <-> Tamu
        if tamu.google_id:
            if tamu.google_id != uid:
                return fail('uid_tidak_cocok')
        else:
            if not claims.get('email_verified'):
                return fail('email_belum_terverifikasi')
            try:
                tamu.google_id = uid
                tamu.save(update_fields=['google_id'])
            except IntegrityError:
                return fail('uid_bentrok')

        # 6. Berhasil: sesi bersih
        clear_rate_limit(id_key)
        clear_failed_login(client_ip, user_type='tamu')
        _establish_tamu_session(request, tamu)
        LoginAttempt.objects.create(
            email=tamu.email, user_type='tamu', success=True, ip_address=client_ip
        )
        return JsonResponse({
            'success': True,
            'redirect_url': reverse('tamu:dashboard'),
            'message': 'Login berhasil.',
        })

    except Exception as exc:
        # Jangan pernah membocorkan detail/stack (bisa memuat data sensitif) ke klien.
        security_logger.error('Login Tamu gagal diproses (%s).', type(exc).__name__)
        return JsonResponse({'success': False, 'message': LOGIN_SERVICE_UNAVAILABLE}, status=503)

def admin_login_view(request):
    """View untuk Login Khusus Admin"""
    from django.contrib.auth import authenticate, login
    from django.contrib.auth.forms import AuthenticationForm
    from ..models import LoginAttempt, Tamu
    
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('tamu:admin_dashboard')
    
    form = AuthenticationForm()
    
    if request.method == 'POST':
        ip_address = get_client_ip(request)
        from django.utils import timezone
        from datetime import timedelta

        # Rate Limiting Admin Login (Max 5 failed attempts in 15 mins via cache & db)
        if check_login_rate_limit(ip_address, user_type='admin'):
            messages.error(request, "Terlalu banyak percobaan masuk yang gagal. Akses ditangguhkan selama 15 menit.")
            return render(request, 'guest_book/admin_login.html', {
                'form': form,
                'user_logged_in': False,
            })

        post_data = request.POST.copy()
        raw_username = post_data.get('username', '').strip()
        if raw_username and '@' in raw_username:
            from django.contrib.auth.models import User
            user_by_email = User.objects.filter(email__iexact=raw_username).first()
            if user_by_email:
                post_data['username'] = user_by_email.username

        form = AuthenticationForm(request, data=post_data)
        if form.is_valid():
            user = form.get_user()
            if user.is_staff:
                # Find the Tamu admin email to associate with this login attempt
                tamu_admin = Tamu.objects.filter(is_admin=True).first() or Tamu.objects.filter(nik='admin').first()
                admin_email = tamu_admin.email if tamu_admin else user.email
                if not admin_email:
                    admin_email = "admin@bukudigital.local"
                
                # Reset rate limit on success
                clear_failed_login(ip_address, user_type='admin')

                # Record successful login attempt
                LoginAttempt.objects.create(
                    email=admin_email,
                    user_type='admin',
                    success=True,
                    ip_address=ip_address
                )
                
                login(request, user)
                request.session.pop('pegawai_id', None)
                request.session.pop('tamu_id', None)
                messages.success(request, "Selamat datang kembali, Administrator!")
                return redirect('tamu:admin_dashboard')
            else:
                # Record failed attempt (user is not staff/admin)
                record_failed_login(ip_address, email=user.email or user.username, user_type='admin')
                messages.error(request, "Anda tidak memiliki akses ke halaman ini.")
        else:
            # Record failed login attempt (invalid credentials)
            username = request.POST.get('username')
            email = "admin@bukudigital.local"
            if username:
                from django.contrib.auth.models import User
                from django.db.models import Q
                user_obj = User.objects.filter(Q(username=username) | Q(email=username)).first()
                email = user_obj.email if user_obj else username
                if not email or email == "":
                    # Try to fall back to tamu admin email
                    tamu_admin = Tamu.objects.filter(is_admin=True).first() or Tamu.objects.filter(nik='admin').first()
                    if tamu_admin and (username == tamu_admin.name or username == 'admin'):
                        email = tamu_admin.email
                
                if not email:
                    email = "admin@bukudigital.local"
                
            record_failed_login(ip_address, email=email, user_type='admin')

            
    return render(request, 'guest_book/admin_login.html', {
        'form': form,
        'user_logged_in': False,
    })


def tamu_password_reset_request(request):
    """View untuk meminta link reset password tamu"""
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from django.utils.http import urlsafe_base64_encode
    from django.utils.encoding import force_bytes
    from django.contrib.auth.tokens import default_token_generator
    from django.contrib.sites.shortcuts import get_current_site
    from ..forms import TamuPasswordResetForm
    
    form = TamuPasswordResetForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        tamu = Tamu.objects.get(email=email, account_status='active')
        
        # Generate token and uid
        uid = urlsafe_base64_encode(force_bytes(tamu.pk))
        token = default_token_generator.make_token(tamu)
        
        # Send email
        current_site = get_current_site(request)
        mail_subject = 'Reset Password Buku Tamu Digital'
        message = render_to_string('guest_book/registration/password_reset_email.html', {
            'tamu': tamu,
            'domain': current_site.domain,
            'uid': uid,
            'token': token,
            'protocol': 'https' if request.is_secure() else 'http'
        })
        
        # Gunakan email pengirim dari settings jika ada, atau placeholder
        from django.conf import settings
        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', 'Buku Tamu Digital <noreply@example.com>')
        
        # Kirim email di latar belakang menggunakan thread agar tidak memblokir UI (Asynchronous)
        import threading
        threading.Thread(target=send_mail, args=(mail_subject, message, from_email, [email])).start()
        
        return redirect('tamu:password_reset_done')
        
    return render(request, 'guest_book/registration/password_reset_form.html', {'form': form})


def tamu_password_reset_confirm(request, uidb64, token):
    """View untuk memproses password baru tamu"""
    from django.utils.http import urlsafe_base64_decode
    from django.utils.encoding import force_str
    from django.contrib.auth.tokens import default_token_generator
    from django.contrib.auth.hashers import make_password
    from ..forms import TamuSetPasswordForm
    
    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        tamu = Tamu.objects.get(pk=uid, account_status='active')
    except (TypeError, ValueError, OverflowError, Tamu.DoesNotExist):
        tamu = None
        
    if tamu is not None and default_token_generator.check_token(tamu, token):
        form = TamuSetPasswordForm(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            new_password = form.cleaned_data['password1']
            tamu.password = make_password(new_password)
            tamu.save()
            return redirect('tamu:password_reset_complete')
        return render(request, 'guest_book/registration/password_reset_confirm.html', {'form': form, 'validlink': True})
    else:
        return render(request, 'guest_book/registration/password_reset_confirm.html', {'validlink': False})


def pegawai_login_view(request):
    """View untuk Login Khusus Pegawai — autentikasi via email & password custom."""
    from django.contrib.auth.hashers import check_password
    from ..models import Pegawai, LoginAttempt

    # Jika sudah login sebagai pegawai, redirect ke dashboard
    if request.session.get('pegawai_id'):
        return redirect('tamu:pegawai_dashboard')

    if request.method == 'POST':
        login_id = request.POST.get('login_id', '').strip().lower()
        password = request.POST.get('password', '')
        ip       = get_client_ip(request)

        # Rate Limiting Pegawai Login (Max 5 failed attempts in 15 mins via cache & db)
        if check_login_rate_limit(ip, user_type='pegawai'):
            messages.error(request, "Terlalu banyak percobaan masuk yang gagal. Akses ditangguhkan selama 15 menit.")
            return render(request, 'guest_book/pegawai_login.html')

        # Validasi input dasar
        if not login_id or not password:
            messages.error(request, 'Email/Username dan password wajib diisi.')
            return render(request, 'guest_book/pegawai_login.html')

        from django.db.models import Q
        try:
            pegawai = Pegawai.objects.get(Q(email__iexact=login_id) | Q(username__iexact=login_id))
        except Pegawai.DoesNotExist:
            record_failed_login(ip, email=login_id, user_type='pegawai')
            messages.error(request, 'Email/Username atau password yang Anda masukkan salah.')
            return render(request, 'guest_book/pegawai_login.html')

        # Cek status akun - gunakan pesan generik agar tidak membocorkan status akun
        if pegawai.account_status != 'active':
            record_failed_login(ip, email=login_id, user_type='pegawai')
            messages.error(request, 'Email/Username atau password yang Anda masukkan salah.')
            return render(request, 'guest_book/pegawai_login.html')

        # Verifikasi password (hashed dengan Django's check_password)
        password_valid = check_password(password, pegawai.password)
        if not password_valid and pegawai.password and '$' not in pegawai.password and len(pegawai.password) == 64:
            import hashlib
            import hmac
            from django.contrib.auth.hashers import make_password
            legacy_sha256 = hashlib.sha256(password.encode()).hexdigest()
            if hmac.compare_digest(pegawai.password, legacy_sha256):
                password_valid = True
                pegawai.password = make_password(password)
                pegawai.save(update_fields=['password'])

        if not password_valid:
            record_failed_login(ip, email=login_id, user_type='pegawai')
            messages.error(request, 'Email/Username atau password yang Anda masukkan salah.')
            return render(request, 'guest_book/pegawai_login.html')

        # ── Login Berhasil ──
        clear_failed_login(ip, user_type='pegawai')
        from django.utils import timezone as tz
        pegawai.last_login = tz.now()
        pegawai.save(update_fields=['last_login'])

        LoginAttempt.objects.create(
            email=login_id, user_type='pegawai', success=True, ip_address=ip
        )


        # Simpan session pegawai dengan rotasi key untuk mencegah session fixation
        request.session.cycle_key()
        request.session.pop('tamu_id', None)
        request.session['pegawai_id']   = str(pegawai.pk)
        request.session['pegawai_name'] = pegawai.name
        request.session['pegawai_role'] = pegawai.role
        request.session.set_expiry(86400)  # Session aktif 1 hari

        messages.success(request, f'Selamat datang, {pegawai.name}!')
        return redirect('tamu:pegawai_dashboard')

    return render(request, 'guest_book/pegawai_login.html')


def pegawai_logout_view(request):
    """Logout pegawai — flush seluruh sesi untuk keamanan."""
    request.session.flush()
    messages.success(request, 'Anda telah keluar dari Portal Pegawai.')
    return redirect('tamu:pegawai_login')


