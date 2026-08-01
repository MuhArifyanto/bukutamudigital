import os
from django.shortcuts import render, redirect
from django.contrib import messages
from ..models import Tamu
from ..forms import TamuLoginForm, TamuRegisterForm

def validate_grid_captcha(puzzle_index, selected_tiles_json, trajectory_json):
    """
    Validasi kustom Grid Selection Captcha:
    1. Mencocokkan ubin yang dipilih dengan kunci jawaban berdasarkan indeks puzzle (0-10).
    2. Memvalidasi trajektori klik (selisih waktu antar klik manusia, tidak instan).
    """
    import json

    # Kunci jawaban ubin benar untuk masing-masing dari 11 indeks puzzle (grid 4x4)
    PUZZLE_KEYS = {
        0: [1, 2, 5, 6, 9, 10],            # Lampu Lalu Lintas
        1: [8, 9, 10, 11, 12, 13, 14, 15], # Penyeberangan Jalan (Zebra Cross)
        2: [5, 6, 7, 9, 10, 11, 13, 14],   # Sepeda
        3: [5, 6, 7, 9, 10, 11, 13, 14],   # Mobil
        4: [4, 5, 6, 8, 9, 10, 12, 13, 14],# Bus
        5: [5, 6, 7, 9, 10, 11, 13, 14],   # Sepeda Motor
        6: [5, 6, 9, 10, 13, 14],          # Hidran Kebakaran
        7: [4, 5, 6, 7, 8, 9, 10, 11],     # Jembatan
        8: [4, 5, 8, 9, 12, 13, 14],       # Tangga
        9: [9, 10, 11, 13, 14, 15],        # Perahu
        10: [2, 5, 6, 9, 10, 13, 14],      # Wanita Cantik
    }

    try:
        puzzle_idx = int(puzzle_index)
    except (TypeError, ValueError):
        return False, "Indeks captcha tidak valid."

    if puzzle_idx not in PUZZLE_KEYS:
        return False, "Kategori captcha tidak dikenal."

    # Parse ubin terpilih
    try:
        selected_tiles = json.loads(selected_tiles_json) if selected_tiles_json else []
    except Exception:
        return False, "Format pilihan ubin tidak valid."

    if not isinstance(selected_tiles, list):
        return False, "Data ubin terpilih tidak valid."

    # Konversi ubin terpilih ke integer dan urutkan
    try:
        selected_tiles = sorted([int(x) for x in selected_tiles])
    except (TypeError, ValueError):
        return False, "Elemen pilihan ubin harus berupa angka."

    # Cocokkan dengan kunci jawaban
    correct_tiles = sorted(PUZZLE_KEYS[puzzle_idx])
    if selected_tiles != correct_tiles:
        return False, "Pilihan gambar belum tepat. Silakan coba lagi."

    # Validasi Trajektori Klik untuk keamanan bot
    if not trajectory_json:
        return False, "Data klik tidak terdeteksi (potensi bypass)."

    try:
        trajectory = json.loads(trajectory_json)
    except Exception:
        return False, "Data klik rusak."

    if not isinstance(trajectory, list):
        return False, "Format data klik tidak valid."

    # Jika kunci jawaban butuh mengklik ubin, pastikan ada klik terekam
    if len(correct_tiles) > 0:
        if len(trajectory) < len(correct_tiles):
            return False, "Pergerakan klik terlalu minim (terdeteksi bot)."
        
        # Validasi selisih waktu antar klik
        click_times = [float(pt.get('t', 0)) for pt in trajectory if 't' in pt]
        click_times.sort()
        
        time_diffs = []
        for i in range(1, len(click_times)):
            time_diffs.append(click_times[i] - click_times[i-1])
            
        if time_diffs:
            # Jika semua selisih waktu klik sama persis (perfect click intervals), anggap bot
            avg_diff = sum(time_diffs) / len(time_diffs)
            variance = sum((diff - avg_diff) ** 2 for diff in time_diffs) / len(time_diffs)
            if variance == 0 and len(time_diffs) > 2:
                return False, "Interval klik terlalu stabil (terdeteksi bot)."

    return True, "Validasi captcha berhasil."



def login_view(request):
    """View untuk Login Tamu & Admin"""
    from ..models import LoginAttempt
    from django.utils import timezone
    from datetime import timedelta
    
    if request.session.get('tamu_id'):
        return redirect('tamu:dashboard')

    form = TamuLoginForm(request.POST or None)
    if request.method == 'POST':
        ip_address = request.META.get('REMOTE_ADDR')
        username_attempt = request.POST.get('username', '')
        
        # Rate Limiting Check (Max 5 failed attempts in 15 mins)
        time_threshold = timezone.now() - timedelta(minutes=15)
        failed_attempts = LoginAttempt.objects.filter(
            ip_address=ip_address,
            success=False,
            timestamp__gte=time_threshold
        ).count()
        
        if failed_attempts >= 5:
            messages.error(request, "Terlalu banyak upaya masuk yang gagal. Akun/IP Anda ditangguhkan sementara selama 15 menit. Silakan coba lagi nanti.")
            return render(request, 'guest_book/tamu_login.html', {
                'form': form,
                'user_logged_in': False,
            })

        if form.is_valid():
            tamu = form.tamu
            request.session['tamu_id'] = str(tamu.pk)
            
            # Record successful login attempt
            LoginAttempt.objects.create(
                email=tamu.email,
                user_type='tamu',
                success=True,
                ip_address=request.META.get('REMOTE_ADDR')
            )
            
            messages.success(request, f"Selamat datang kembali, {tamu.name}!")
            return redirect('tamu:dashboard')
        else:
            # Record failed login attempt
            username = request.POST.get('username')
            if username:
                from django.db.models import Q
                tamu_obj = Tamu.objects.filter(Q(name=username) | Q(email=username)).first()
                email = tamu_obj.email if tamu_obj else username
                LoginAttempt.objects.create(
                    email=email,
                    user_type='tamu',
                    success=False,
                    ip_address=request.META.get('REMOTE_ADDR')
                )

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
        # Validasi Grid Captcha (Upgrade)
        captcha_puzzle_index = request.POST.get('captcha_puzzle_index')
        captcha_selected_tiles = request.POST.get('captcha_selected_tiles')
        captcha_trajectory = request.POST.get('captcha_trajectory')
        
        captcha_success, captcha_err = validate_grid_captcha(captcha_puzzle_index, captcha_selected_tiles, captcha_trajectory)
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

@csrf_exempt
def api_firebase_login(request):
    """API untuk Login/Register via Firebase (Google SSO & Email/Password)"""
    from django.http import JsonResponse
    from django.urls import reverse
    from google.oauth2 import id_token
    from google.auth.transport import requests as google_requests
    import json
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Hanya menerima metode POST.'})

        
    try:
        data = json.loads(request.body)
        id_token_str = data.get('id_token')
        
        if not id_token_str:
            return JsonResponse({'success': False, 'message': 'ID Token tidak ditemukan.'})
            
        # Verifikasi token menggunakan Firebase
        id_info = id_token.verify_firebase_token(
            id_token_str, 
            google_requests.Request(), 
            audience='bukutamudigital-43ae7'
        )
        
        email = id_info.get('email')
        uid = id_info.get('sub') # Firebase UID
        
        if not email:
            return JsonResponse({'success': False, 'message': 'Email tidak valid dari Firebase.'})
            
        # Dapatkan data tambahan dari payload (jika dikirim untuk pendaftaran)
        name = data.get('name') or id_info.get('name') or email.split('@')[0]
        nik = data.get('nik')
        phone = data.get('phone') or '-'
        instansi = data.get('instansi') or '-'
        registration_type = data.get('registration_type') or 'google_sso'
        
        from ..models import Tamu
        
        # Validasi Grid Captcha jika ini adalah registrasi baru secara manual/email
        if not Tamu.objects.filter(email=email).exists() and registration_type == 'firebase_email':
            captcha_puzzle_index = data.get('captcha_puzzle_index')
            captcha_selected_tiles = data.get('captcha_selected_tiles')
            captcha_trajectory = data.get('captcha_trajectory')
            captcha_success, captcha_err = validate_grid_captcha(captcha_puzzle_index, captcha_selected_tiles, captcha_trajectory)
            if not captcha_success:
                return JsonResponse({'success': False, 'message': captcha_err})
        
        # Cari tamu berdasarkan email
        tamu = Tamu.objects.filter(email=email).first()
        created = False
        
        if not tamu:
            # Jika tamu belum terdaftar di MySQL, buat tamu baru
            tamu = Tamu.objects.create(
                email=email,
                name=name,
                nik=nik,
                phone=phone,
                instansi=instansi,
                registration_type=registration_type,
                google_id=uid,
                account_status='active'
            )
            created = True
        else:
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
            request.session['tamu_id'] = str(tamu.pk)
            redirect_url = reverse('tamu:dashboard')
            message = 'Registrasi berhasil.' if created else 'Login berhasil.'
            
            # Tulis ke LoginAttempt untuk keamanan jika login sukses
            from ..models import LoginAttempt
            LoginAttempt.objects.create(
                email=email,
                user_type='tamu',
                success=True,
                ip_address=request.META.get('REMOTE_ADDR')
            )
        
        return JsonResponse({
            'success': True, 
            'redirect_url': redirect_url,
            'message': message
        })
        
    except ValueError as e:
        return JsonResponse({'success': False, 'message': f'Token tidak valid: {str(e)}'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Terjadi kesalahan: {str(e)}'})

@csrf_exempt
def api_validate_register(request):
    """API untuk memvalidasi keunikan email dan NIK di MySQL sebelum membuat user di Firebase"""
    from django.http import JsonResponse
    import json
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Hanya menerima metode POST.'})

        
    try:
        data = json.loads(request.body)
        email = data.get('email')
        nik = data.get('nik')
        
        if not email or not nik:
            return JsonResponse({'success': False, 'message': 'Email dan NIK wajib diisi.'})
            
        from ..models import Tamu
        if Tamu.objects.filter(email=email).exists():
            return JsonResponse({
                'success': False, 
                'message': 'Email ini sudah terdaftar di sistem kami.'
            })
            
        if Tamu.objects.filter(nik=nik).exists():
            return JsonResponse({
                'success': False, 
                'message': 'NIK ini sudah terdaftar di sistem kami.'
            })
            
        return JsonResponse({'success': True, 'message': 'Validasi berhasil.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Terjadi kesalahan: {str(e)}'})

def api_resolve_email(request):
    """API untuk mencocokkan Nama Lengkap atau NIK tamu dengan Email terdaftarnya untuk login Firebase"""
    from django.http import JsonResponse
    from django.db.models import Q
    
    if request.method != 'GET':
        return JsonResponse({'success': False, 'message': 'Hanya menerima metode GET.'})
        
    username = request.GET.get('username', '').strip()
    if not username:
        return JsonResponse({'success': False, 'message': 'Username tidak boleh kosong.'})
        
    # Jika sudah berupa email, langsung kembalikan email tersebut
    if '@' in username:
        return JsonResponse({'success': True, 'email': username})
        
    from ..models import Tamu
    # Cari berdasarkan nama atau nik
    tamu = Tamu.objects.filter(Q(name__iexact=username) | Q(nik=username)).first()
    if tamu:
        return JsonResponse({'success': True, 'email': tamu.email})
        
    return JsonResponse({
        'success': False, 
        'message': 'Akun tidak ditemukan. Silakan pastikan Nama/NIK Anda benar, atau masuk menggunakan email.'
    })

def admin_login_view(request):
    """View untuk Login Khusus Admin"""
    from django.contrib.auth import authenticate, login
    from django.contrib.auth.forms import AuthenticationForm
    from ..models import LoginAttempt, Tamu
    import traceback
    from django.http import HttpResponse

    try:
        if request.user.is_authenticated and request.user.is_staff:
            return redirect('tamu:admin_dashboard')
            
        if request.method == 'POST':
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
                    
                    # Record successful login attempt
                    try:
                        LoginAttempt.objects.create(
                            email=admin_email,
                            user_type='admin',
                            success=True,
                            ip_address=request.META.get('REMOTE_ADDR')
                        )
                    except Exception:
                        pass
                    
                    login(request, user)
                    messages.success(request, "Selamat datang kembali, Administrator!")
                    return redirect('tamu:admin_dashboard')
                else:
                    # Record failed attempt (user is not staff/admin)
                    try:
                        LoginAttempt.objects.create(
                            email=user.email or user.username,
                            user_type='admin',
                            success=False,
                            ip_address=request.META.get('REMOTE_ADDR')
                        )
                    except Exception:
                        pass
                    messages.error(request, "Anda tidak memiliki akses ke halaman ini.")
            else:
                # Record failed login attempt (invalid credentials)
                username = request.POST.get('username')
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
                    
                    try:
                        LoginAttempt.objects.create(
                            email=email,
                            user_type='admin',
                            success=False,
                            ip_address=request.META.get('REMOTE_ADDR')
                        )
                    except Exception:
                        pass
        else:
            form = AuthenticationForm(request)
                
        return render(request, 'guest_book/admin_login.html', {
            'form': form,
            'user_logged_in': False,
        })
    except Exception as e:
        error_details = traceback.format_exc()
        return HttpResponse(f"<h3>Error in Admin Login View:</h3><pre>{error_details}</pre>", status=500)


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
        
        send_mail(mail_subject, message, from_email, [email])
        
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

