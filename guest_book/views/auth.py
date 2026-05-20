import os
from django.shortcuts import render, redirect
from django.contrib import messages
from ..models import Tamu
from ..forms import TamuLoginForm, TamuRegisterForm

def login_view(request):
    """View untuk Login Tamu & Admin"""
    from ..models import LoginAttempt
    if request.session.get('tamu_id'):
        return redirect('tamu:dashboard')

    form = TamuLoginForm(request.POST or None)
    if request.method == 'POST':
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
        # Validasi reCAPTCHA (Upgrade)
        recaptcha_response = request.POST.get('g-recaptcha-response')
        import requests
        
        verify_data = {
            'secret': os.getenv('RECAPTCHA_SECRET', '6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe'), # Kunci Rahasia dari .env
            'response': recaptcha_response
        }
        
        try:
            r = requests.post('https://www.google.com/recaptcha/api/siteverify', data=verify_data)
            result = r.json()
            
            if not result.get('success'):
                from django.contrib import messages
                messages.error(request, "Validasi reCAPTCHA gagal. Silakan centang kembali.")
                return render(request, 'guest_book/tamu_register.html', {
                    'form': form,
                    'user_logged_in': False,
                })
        except Exception as e:
            from django.contrib import messages
            messages.error(request, "Gagal menghubungi server reCAPTCHA. Silakan coba lagi.")
            return render(request, 'guest_book/tamu_register.html', {
                'form': form,
                'user_logged_in': False,
            })

        tamu = form.save()
        request.session['tamu_id'] = str(tamu.pk)
        messages.success(request, f"Akun berhasil dibuat. Selamat datang, {tamu.name}!")
        return redirect('tamu:dashboard')

    return render(request, 'guest_book/tamu_register.html', {
        'form': form,
        'user_logged_in': False,
    })

def logout_view(request):
    """View untuk Logout"""
    request.session.flush()
    messages.success(request, "Anda telah berhasil keluar.")
    return redirect('tamu:login')

def api_firebase_login(request):
    """API untuk Login via Firebase (Google SSO)"""
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
        name = id_info.get('name')
        uid = id_info.get('sub') # Firebase UID
        
        if not email:
            return JsonResponse({'success': False, 'message': 'Email tidak valid dari Google.'})
            
        # Cari atau buat user Tamu
        from ..models import Tamu
        tamu, created = Tamu.objects.get_or_create(
            email=email,
            defaults={
                'name': name or email.split('@')[0],
                'registration_type': 'google_sso',
                'google_id': uid,
                'account_status': 'active',
                'phone': '-', # Default karena tidak didapat dari Google SSO dasar
            }
        )
        
        # Tentukan redirect URL dan set session
        if created:
            # Jika baru mendaftar, arahkan ke halaman login
            redirect_url = reverse('tamu:login') + '?registered=true'
            message = 'Registrasi berhasil. Silakan masuk menggunakan Akun Google Anda.'
        else:
            # Jika sudah ada (Login), set session dan arahkan ke dashboard
            request.session['tamu_id'] = str(tamu.pk)
            redirect_url = reverse('tamu:dashboard')
            message = 'Login berhasil.'
            
        return JsonResponse({
            'success': True, 
            'redirect_url': redirect_url,
            'message': message
        })
        
    except ValueError as e:
        return JsonResponse({'success': False, 'message': f'Token tidak valid: {str(e)}'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': f'Terjadi kesalahan: {str(e)}'})

def admin_login_view(request):
    """View untuk Login Khusus Admin"""
    from django.contrib.auth import authenticate, login
    from django.contrib.auth.forms import AuthenticationForm
    from ..models import LoginAttempt, Tamu
    
    if request.user.is_authenticated and request.user.is_staff:
        return redirect('tamu:admin_dashboard')
        
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            user = form.get_user()
            if user.is_staff:
                # Find the Tamu admin email to associate with this login attempt
                tamu_admin = Tamu.objects.filter(is_admin=True).first() or Tamu.objects.filter(nik='admin').first()
                admin_email = tamu_admin.email if tamu_admin else user.email
                if not admin_email:
                    admin_email = "admin@bukudigital.local"
                
                # Record successful login attempt
                LoginAttempt.objects.create(
                    email=admin_email,
                    user_type='admin',
                    success=True,
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                
                login(request, user)
                messages.success(request, "Selamat datang kembali, Administrator!")
                return redirect('tamu:admin_dashboard')
            else:
                # Record failed attempt (user is not staff/admin)
                LoginAttempt.objects.create(
                    email=user.email or user.username,
                    user_type='admin',
                    success=False,
                    ip_address=request.META.get('REMOTE_ADDR')
                )
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
                
                LoginAttempt.objects.create(
                    email=email,
                    user_type='admin',
                    success=False,
                    ip_address=request.META.get('REMOTE_ADDR')
                )
            
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

