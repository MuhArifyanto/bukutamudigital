from .models import Notification
from django.utils import timezone
import os
import json
from django.conf import settings

def send_notification(recipient_id, recipient_type, notification_type, title, message, related_object_id=None):
    """Kirim notifikasi ke pengguna tertentu."""
    notif = Notification.objects.create(
        recipient_id=str(recipient_id),
        recipient_type=recipient_type,
        notification_type=notification_type,
        title=title,
        message=message,
        related_object_id=str(related_object_id) if related_object_id else None,
        status='unread'
    )
    
    # Trigger WebSocket Notification
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        
        channel_layer = get_channel_layer()
        
        # Hitung unread count untuk recipient
        unread_count = Notification.objects.filter(recipient_id=str(recipient_id), status='unread').count()
        
        # Tentukan grup berdasarkan recipient_type (admin atau tamu)
        group_name = f'notifications_{recipient_type}'
        
        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'send_notification',
                'data': {
                    'title': title,
                    'message': message,
                    'created_at': timezone.localtime(notif.created_at).strftime('%H:%M') if hasattr(notif, 'created_at') else timezone.now().strftime('%H:%M'),
                    'notification_type': notification_type,
                    'related_object_id': str(related_object_id) if related_object_id else None,
                    'unread_count': unread_count
                }
            }
        )
    except Exception as e:
        print(f"Error sending WebSocket notification: {e}")
        
    return notif

def get_google_calendar_holidays(year):
    """
    Mengambil data libur nasional dari Google Calendar API dengan Caching.
    """
    cache_dir = os.path.join(settings.BASE_DIR, 'cache')
    if not os.path.exists(cache_dir): os.makedirs(cache_dir)
    cache_path = os.path.join(cache_dir, f'holidays_{year}.json')
    
    # 1. Coba ambil dari Cache (Sangat Cepat)
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r') as f:
                return json.load(f)
        except: pass

    holidays = []
    
    # 2. Ambil dari Google API (Menggunakan Environment Variables)
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        client_email = os.getenv("GOOGLE_CLIENT_EMAIL")
        private_key = os.getenv("GOOGLE_PRIVATE_KEY")
        
        if not client_email or not private_key:
            print("Peringatan: Kredensial Google (Email/Private Key) tidak ditemukan di .env")
            return None

        # Perbaiki format baris baru (newline) pada private_key yang dibaca dari .env
        # python-dotenv mungkin sudah membacanya dengan benar, tetapi replace('\\n', '\n') 
        # adalah jaring pengaman tambahan jika string lolos dengan karakter literal \n
        private_key = private_key.replace('\\n', '\n')

        credentials_info = {
            "type": "service_account",
            "project_id": os.getenv("GOOGLE_PROJECT_ID"),
            "private_key_id": "",
            "private_key": private_key,
            "client_email": client_email,
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": f"https://www.googleapis.com/robot/v1/metadata/x509/{client_email.replace('@', '%40')}"
        }
        
        SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
        creds = service_account.Credentials.from_service_account_info(credentials_info, scopes=SCOPES)
        service = build('calendar', 'v3', credentials=creds)

        calendar_id = 'id.indonesian#holiday@group.v.calendar.google.com'
        time_min = f'{year}-01-01T00:00:00Z'
        time_max = f'{year}-12-31T23:59:59Z'

        events_result = service.events().list(
            calendarId=calendar_id, 
            timeMin=time_min, 
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])
        for event in events:
            start = event['start'].get('date') or event['start'].get('dateTime')
            holidays.append({
                'date': start[:10],
                'name': event.get('summary', 'Hari Libur')
            })
        
        # Simpan ke Cache untuk penggunaan berikutnya
        with open(cache_path, 'w') as f:
            json.dump(holidays, f)
            
        return holidays
    except Exception as e:
        print(f"Error fetching Google Calendar: {e}")
        return None
