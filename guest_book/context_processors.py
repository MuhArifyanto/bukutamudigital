from .models import Notification, Tamu

def notifications_context(request):
    """
    Context processor untuk menyediakan jumlah notifikasi yang belum dibaca.
    """
    unread_count = 0
    
    # Cek jika tamu login
    tamu_id = request.session.get('tamu_id')
    if tamu_id:
        # Cek jika dia admin (berdasarkan NIK 'admin')
        tamu = Tamu.objects.filter(pk=tamu_id).first()
        if tamu and tamu.nik == 'admin':
            unread_count = Notification.objects.filter(recipient_type='admin', status='unread').count()
        elif tamu:
            unread_count = Notification.objects.filter(recipient_id=tamu_id, recipient_type='tamu', status='unread').count()
    
    # Cek jika admin login via Django Auth (Staff)
    elif request.user.is_authenticated and request.user.is_staff:
        unread_count = Notification.objects.filter(recipient_type='admin', status='unread').count()
        
    return {
        'unread_notifications_count': unread_count
    }
