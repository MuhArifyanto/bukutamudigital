import logging

from .models import Notification
from django.utils import timezone
import os
from django.core.cache import cache

logger = logging.getLogger(__name__)

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
        
        # Tentukan grup per-user agar notifikasi hanya diterima oleh user yang tepat.
        # Harus sinkron dengan NotificationConsumer.connect() di consumers.py.
        if recipient_type == 'admin':
            group_name = 'notif_admin'
        elif recipient_type == 'tamu':
            group_name = f'notif_tamu_{recipient_id}'
        else:  # pegawai
            group_name = f'notif_pegawai_{recipient_id}'

        async_to_sync(channel_layer.group_send)(
            group_name,
            {
                'type': 'send_notification',
                'data': {
                    'title': title,
                    'message': message,
                    'created_at': timezone.localtime(notif.created_at).strftime('%H:%M') if getattr(notif, 'created_at', None) else timezone.localtime(timezone.now()).strftime('%H:%M'),
                    'notification_type': notification_type,
                    'related_object_id': str(related_object_id) if related_object_id else None,
                    'unread_count': unread_count
                }
            }
        )
    except Exception as e:
        logger.warning("Error sending WebSocket notification: %s", e)
        
    return notif

def get_google_calendar_holidays(year):
    """
    Mengambil data libur nasional dari Google Calendar API dengan Redis cache.

    Cache key: bukudigital:holidays:{year}
    TTL: 30 hari — data libur tahunan tidak berubah sering.
    Fallback: in-memory LocMemCache saat development tanpa Redis.
    Sebelumnya cache disimpan sebagai file JSON di disk (cache/holidays_{year}.json)
    yang terhapus setiap server restart di Render.
    """
    CACHE_KEY = f'holidays_{year}'
    CACHE_TTL = 60 * 60 * 24 * 30  # 30 hari

    # 1. Coba ambil dari Redis cache (atau LocMemCache saat dev)
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached

    holidays = []

    # 2. Ambil dari Google Calendar API
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        client_email = os.getenv("GOOGLE_CLIENT_EMAIL")
        private_key  = os.getenv("GOOGLE_PRIVATE_KEY")

        if not client_email or not private_key:
            logger.warning("Kredensial Google (Email/Private Key) tidak ditemukan di .env")
            return None

        # Perbaiki format newline pada private_key dari .env
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
            "client_x509_cert_url": (
                f"https://www.googleapis.com/robot/v1/metadata/x509/"
                f"{client_email.replace('@', '%40')}"
            ),
        }

        SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
        creds   = service_account.Credentials.from_service_account_info(
            credentials_info, scopes=SCOPES
        )
        service = build('calendar', 'v3', credentials=creds)

        calendar_id = 'id.indonesian#holiday@group.v.calendar.google.com'
        events_result = service.events().list(
            calendarId=calendar_id,
            timeMin=f'{year}-01-01T00:00:00Z',
            timeMax=f'{year}-12-31T23:59:59Z',
            singleEvents=True,
            orderBy='startTime',
        ).execute()

        for event in events_result.get('items', []):
            start = event['start'].get('date') or event['start'].get('dateTime')
            holidays.append({
                'date': start[:10],
                'name': event.get('summary', 'Hari Libur'),
            })

        # Simpan ke cache — bertahan 30 hari lintas restart server
        cache.set(CACHE_KEY, holidays, CACHE_TTL)
        return holidays

    except Exception as e:
        logger.exception("Error fetching Google Calendar: %s", e)
        return None


# ============================================================================
# N8N INTEGRATION — Auto-Routing Kunjungan via AI
# ============================================================================

def call_n8n_routing(kunjungan_id, purpose, pegawai_queryset):
    """
    Kirim tujuan kunjungan ke N8N Webhook agar AI (Gemini/Groq) bisa
    merekomendasikan pegawai yang paling sesuai.

    Args:
        kunjungan_id (UUID): ID kunjungan yang baru dibuat.
        purpose (str): Tujuan kunjungan dari form tamu.
        pegawai_queryset (QuerySet): Queryset Pegawai aktif (sudah di-select_related dept).

    Returns:
        dict | None: Hasil routing dari N8N, atau None jika gagal/timeout.
        Format sukses: {'pegawai_id': 'uuid', 'bidang': 'Nama Bidang',
                        'confidence': 'high'|'medium'|'low', 'alasan': '...'}
    """
    import requests
    import json

    webhook_url = os.getenv('N8N_WEBHOOK_URL')
    webhook_secret = os.getenv('N8N_WEBHOOK_SECRET', '')

    if not webhook_url:
        logger.warning("N8N_WEBHOOK_URL tidak dikonfigurasi di .env. Auto-routing dilewati.")
        return None

    # Siapkan daftar pegawai untuk dikirim ke N8N
    pegawai_list = []
    for p in pegawai_queryset:
        bidang = ''
        if p.department_rel:
            bidang = p.department_rel.nama
        elif p.department:
            bidang = p.department
        pegawai_list.append({
            'id': str(p.id),
            'nama': p.name,
            'jabatan': p.jabatan or '',
            'bidang': bidang,
        })

    if not pegawai_list:
        logger.warning("Tidak ada pegawai aktif untuk auto-routing.")
        return None

    payload = {
        'kunjungan_id': str(kunjungan_id),
        'tujuan': purpose,
        'pegawai_tersedia': pegawai_list,
    }

    headers = {
        'Content-Type': 'application/json',
        'X-Webhook-Secret': webhook_secret,
    }

    try:
        response = requests.post(
            webhook_url,
            data=json.dumps(payload),
            headers=headers,
            timeout=10,  # Maks 10 detik — jika N8N lambat, tidak memblokir user
        )
        response.raise_for_status()
        result = response.json()

        # Validasi minimal: pastikan ada pegawai_id di response
        if isinstance(result, list):
            result = result[0] if result else {}

        if result.get('pegawai_id'):
            logger.info(
                "N8N routing sukses untuk kunjungan %s → pegawai %s (confidence: %s)",
                kunjungan_id, result['pegawai_id'], result.get('confidence', 'unknown')
            )
            return result
        else:
            logger.warning("N8N response tidak mengandung pegawai_id: %s", result)
            return None

    except requests.exceptions.Timeout:
        logger.warning("N8N Webhook timeout (>10s) untuk kunjungan %s. Auto-routing dilewati.", kunjungan_id)
        return None
    except requests.exceptions.ConnectionError:
        logger.warning("Tidak bisa terhubung ke N8N (%s). Auto-routing dilewati.", webhook_url)
        return None
    except Exception as e:
        logger.exception("Error memanggil N8N Webhook untuk kunjungan %s: %s", kunjungan_id, e)
        return None


def validate_uploaded_file(file_obj, max_size_bytes=2 * 1024 * 1024, allowed_extensions=None):
    """
    Validasi berkas upload secara aman dan terpusat:
    - Ukuran maksimum (diperiksa sebelum membaca konten penuh ke memori).
    - Whitelist ekstensi (misal: jpg, jpeg, png, webp).
    - Sanitasi nama dari path traversal.
    - Deteksi skrip berbahaya (XSS, PHP, shell, SVG injection).
    - Validasi magic bytes / file signature sesuai ekstensi.
    - Randomize nama file dengan UUID hex unik.

    Returns:
        (is_valid: bool, error_message: str | None, safe_filename: str | None)
    """
    if not file_obj:
        return False, "File tidak ditemukan", None

    # 1. Cek ukuran file sebelum membaca konten
    if getattr(file_obj, 'size', 0) > max_size_bytes:
        max_mb = max_size_bytes / (1024 * 1024)
        max_mb_str = f"{int(max_mb)}" if max_mb.is_integer() else f"{max_mb:.1f}"
        return False, f"Ukuran file melebihi batas maksimum {max_mb_str} MB", None

    # 2. Ekstrak dan whitelist ekstensi
    original_name = os.path.basename(getattr(file_obj, 'name', '') or '')
    ext = original_name.split('.')[-1].lower() if '.' in original_name else ''
    if not ext:
        return False, "Format file tidak memiliki ekstensi yang valid", None

    if allowed_extensions is not None:
        allowed_lower = [e.lower().lstrip('.') for e in allowed_extensions]
        if ext not in allowed_lower:
            return False, "Format file tidak diizinkan untuk alasan keamanan", None

    # 3. Baca 512 byte awal untuk analisis keamanan & magic bytes
    header = file_obj.read(512)
    file_obj.seek(0)

    # Deteksi teks mencurigakan / script injection
    header_lower = header.lower()
    dangerous_signatures = [b'<script', b'<html', b'<?php', b'<%', b'<!doctype', b'<svg', b'xmlns=']
    if any(sig in header_lower for sig in dangerous_signatures):
        return False, "Konten file terdeteksi tidak aman", None

    # 4. Validasi Magic Bytes / File Signatures
    valid_signature = False
    if ext in ['jpg', 'jpeg'] and header.startswith(b'\xff\xd8\xff'):
        valid_signature = True
    elif ext == 'png' and header.startswith(b'\x89PNG\r\n\x1a\n'):
        valid_signature = True
    elif ext == 'webp' and len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        valid_signature = True
    elif ext == 'pdf' and header.startswith(b'%PDF'):
        valid_signature = True
    elif ext in ['docx', 'xlsx'] and header.startswith(b'PK\x03\x04'):
        valid_signature = True
    elif ext in ['doc', 'xls'] and (header.startswith(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1') or header.startswith(b'PK\x03\x04')):
        valid_signature = True

    if not valid_signature:
        return False, "Tipe berkas tidak sesuai dengan ekstensinya (File signature mismatch).", None

    # 5. Buat nama aman dengan UUID untuk mencegah path traversal dan benturan nama
    import uuid
    safe_name = f"{uuid.uuid4().hex}.{ext}"
    file_obj.name = safe_name

    return True, None, safe_name

