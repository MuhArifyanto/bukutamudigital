"""
Permission Manager untuk kontrol akses berbasis role pada approval workflow.
"""

from django.core.exceptions import PermissionDenied


class PermissionManager:
    """
    Manajemen permission terpusat untuk approval workflow.
    """
    
    # Hierarki role: staff < supervisor < manager < admin
    ROLE_HIERARCHY = {
        'staff': 1,
        'supervisor': 2,
        'manager': 3,
        'admin': 4,
    }
    
    @classmethod
    def can_forward_to_pegawai(cls, user_type):
        """Admin dapat meneruskan request ke Pegawai."""
        return user_type == 'admin'
    
    @classmethod
    def can_approve_reject(cls, pegawai, kunjungan):
        """
        Pegawai dapat approve/reject jika mereka adalah pegawai yang di-assign.
        """
        if not pegawai or not kunjungan.pegawai:
            return False
        return str(pegawai.id) == str(kunjungan.pegawai.id)
    
    @classmethod
    def can_give_acc(cls, user_type):
        """Admin dapat memberikan ACC final."""
        return user_type == 'admin'
    
    @classmethod
    def can_update_progress_status(cls, user_type):
        """Admin dapat update ke in_progress atau completed."""
        return user_type == 'admin'
    
    @classmethod
    def can_cancel(cls, user_type):
        """Admin dapat membatalkan request."""
        return user_type == 'admin'
    
    @classmethod
    def can_view_department_requests(cls, pegawai):
        """
        Supervisor, Manager, dan Admin pegawai dapat melihat semua request untuk departemen mereka.
        """
        if not pegawai or not hasattr(pegawai, 'role'):
            return False
        return cls.ROLE_HIERARCHY.get(pegawai.role, 0) >= cls.ROLE_HIERARCHY['supervisor']
    
    @classmethod
    def can_access_chat_pegawai_tamu(cls, kunjungan):
        """
        Pegawai dan Tamu dapat chat mulai dari disetujui_pegawai hingga completed.
        """
        from .models import KunjunganStatus
        return kunjungan.status in [
            KunjunganStatus.DISETUJUI_PEGAWAI,
            KunjunganStatus.DISETUJUI,
            KunjunganStatus.IN_PROGRESS,
            KunjunganStatus.COMPLETED,
        ]
    
    @classmethod
    def can_access_chat_pegawai_admin(cls, user_type):
        """
        Pegawai dan Admin dapat chat kapan saja.
        """
        return user_type in ['pegawai', 'admin']
    
    @classmethod
    def check_permission(cls, permission_name, **kwargs):
        """
        Generic permission checker.
        
        Raises PermissionDenied jika check gagal.
        """
        method_name = f"can_{permission_name}"
        if not hasattr(cls, method_name):
            raise ValueError(f"Unknown permission: {permission_name}")
        
        method = getattr(cls, method_name)
        result = method(**kwargs)
        
        if not result:
            raise PermissionDenied(f"Anda tidak memiliki izin: {permission_name}")
        
        return True
