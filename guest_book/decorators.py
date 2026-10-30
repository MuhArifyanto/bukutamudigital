"""
Decorators untuk role-based access control
"""
from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from .models import Pegawai


def pegawai_login_required(view_func):
    """
    Decorator untuk memastikan pegawai sudah login
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        pegawai_id = request.session.get('pegawai_id')
        if not pegawai_id:
            messages.error(request, "Silakan login terlebih dahulu.")
            return redirect('tamu:pegawai_login')
        
        try:
            pegawai = Pegawai.objects.get(pk=pegawai_id, account_status='active')
            request.pegawai = pegawai
            request._pegawai = pegawai
        except Pegawai.DoesNotExist:
            request.session.flush()
            messages.error(request, "Akun tidak ditemukan atau tidak aktif.")
            return redirect('tamu:pegawai_login')
            
        return view_func(request, *args, **kwargs)
    return wrapper


def pegawai_role_required(allowed_roles):
    """
    Decorator untuk memastikan pegawai memiliki role yang diizinkan
    
    Usage:
        @pegawai_role_required(['admin', 'manager'])
        def some_view(request):
            ...
    
    Args:
        allowed_roles: list atau tuple dari role yang diizinkan
                      contoh: ['admin', 'manager', 'supervisor']
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            pegawai_id = request.session.get('pegawai_id')
            
            if not pegawai_id:
                messages.error(request, "Silakan login terlebih dahulu.")
                return redirect('tamu:pegawai_login')
            
            try:
                pegawai = Pegawai.objects.get(pk=pegawai_id, account_status='active')
                request.pegawai = pegawai
                request._pegawai = pegawai
                
                # Check if pegawai has required role
                if pegawai.role not in allowed_roles:
                    messages.error(
                        request, 
                        f"Akses ditolak. Halaman ini memerlukan role: {', '.join(allowed_roles)}"
                    )
                    return redirect('tamu:pegawai_dashboard')
                    
            except Pegawai.DoesNotExist:
                request.session.flush()
                messages.error(request, "Akun tidak ditemukan atau tidak aktif.")
                return redirect('tamu:pegawai_login')
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def has_permission(pegawai, required_role_level):
    """
    Helper function untuk mengecek permission berdasarkan level role
    
    Role hierarchy (dari rendah ke tinggi):
    staff < supervisor < manager < admin
    
    Args:
        pegawai: Instance model Pegawai
        required_role_level: Minimum role level yang diperlukan
                           contoh: 'supervisor' akan allow supervisor, manager, dan admin
    
    Returns:
        Boolean: True jika pegawai memiliki permission
    """
    ROLE_HIERARCHY = {
        'staff': 1,
        'supervisor': 2,
        'manager': 3,
        'admin': 4,
    }
    
    current_level = ROLE_HIERARCHY.get(pegawai.role, 0)
    required_level = ROLE_HIERARCHY.get(required_role_level, 0)
    
    return current_level >= required_level


def get_role_display(role):
    """
    Helper function untuk mendapatkan display name dari role
    """
    ROLE_DISPLAY = {
        'staff': 'Staff',
        'supervisor': 'Supervisor',
        'manager': 'Manager',
        'admin': 'Admin',
    }
    return ROLE_DISPLAY.get(role, role.title())


def get_role_badge_class(role):
    """
    Helper function untuk mendapatkan CSS class untuk badge role
    """
    ROLE_BADGE_CLASS = {
        'staff': 'badge-secondary',
        'supervisor': 'badge-info',
        'manager': 'badge-primary',
        'admin': 'badge-danger',
    }
    return ROLE_BADGE_CLASS.get(role, 'badge-secondary')
