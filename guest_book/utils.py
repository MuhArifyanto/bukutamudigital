"""
Helper functions untuk guest_book app.
Termasuk: audit logging, validasi file, query kalender, web routing n8n.
"""
import os
import json
import logging
from datetime import datetime, date, timedelta
from django.utils import timezone
from django.core.cache import cache

from .models import Notification

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
        if channel_layer:
            target_groups = ['admin_notifications', 'notif_admin'] if recipient_type == 'admin' else [
                f"notifications_{recipient_type}_{recipient_id}",
                f"notif_{recipient_type}_{recipient_id}"
            ]
            payload = {
                'id': str(notif.id),
                'title': notif.title,
                'message': notif.message,
                'created_at': notif.created_at.strftime('%H:%M'),
                'notification_type': notif.notification_type,
                'related_object_id': notif.related_object_id,
                'play_chime': True,
            }
            try:
                payload['unread_count'] = Notification.objects.filter(recipient_id=str(recipient_id), status='unread').count()
            except Exception:
                pass

            for grp in target_groups:
                async_to_sync(channel_layer.group_send)(
                    grp,
                    {
                        'type': 'notification_message',
                        'data': payload,
                        'notification': payload,
                    }
                )
    except Exception as e:
        logger.warning(f"Gagal mengirim WebSocket notification: {e}")

    return notif


def record_audit_log(user_id, user_type, action, table_name, record_id, old_value=None, new_value=None, ip_address=None):
    """Mencatat aktivitas ke AuditLog."""
    try:
        from .models import AuditLog
        AuditLog.objects.create(
            user_id=str(user_id) if user_id else None,
            user_type=user_type,
            action=action,
            table_name=table_name,
            record_id=str(record_id) if record_id else None,
            old_value=old_value,
            new_value=new_value,
            ip_address=ip_address
        )
    except Exception as e:
        logger.error(f"Gagal mencatat audit log: {e}")


def validate_uploaded_file(file_obj, max_size_bytes=5 * 1024 * 1024, allowed_extensions=None):
    """
    Validasi file upload: ukuran dan ekstensi.
    Mengembalikan (is_valid: bool, error_message: str, safe_filename: str)
    """
    import uuid

    if not file_obj:
        return False, "File tidak boleh kosong.", ""

    # Cek ukuran
    if file_obj.size > max_size_bytes:
        max_mb = max_size_bytes // (1024 * 1024)
        return False, f"Ukuran file melebihi batas maksimum {max_mb} MB.", ""

    # Cek ekstensi
    raw_name = getattr(file_obj, 'name', '') or ''
    ext = raw_name.split('.')[-1].lower() if '.' in raw_name else ''

    if allowed_extensions:
        allowed = [e.lower().lstrip('.') for e in allowed_extensions]
        if ext not in allowed:
            return False, f"Ekstensi file .{ext} tidak diizinkan. Hanya: {', '.join(allowed)}.", ""

    # Validasi magic bytes / signature untuk file gambar (keamanan upload)
    if ext in ['jpg', 'jpeg', 'png', 'webp']:
        try:
            header = file_obj.read(16)
            file_obj.seek(0)
            if ext in ['jpg', 'jpeg']:
                if not header.startswith(b'\xff\xd8\xff'):
                    return False, "File signature mismatch: File bukan format JPEG/JPG yang valid.", ""
            elif ext == 'png':
                if not header.startswith(b'\x89PNG\r\n\x1a\n'):
                    return False, "File signature mismatch: File bukan format PNG yang valid.", ""
            elif ext == 'webp':
                if not (header.startswith(b'RIFF') and len(header) >= 12 and header[8:12] == b'WEBP'):
                    return False, "File signature mismatch: File bukan format WEBP yang valid.", ""
        except Exception:
            file_obj.seek(0)
            return False, "File signature mismatch: Gagal membaca file yang diunggah.", ""

    # Generate nama aman
    safe_name = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
    return True, "", safe_name


def get_google_calendar_holidays(year):
    """
    Ambil hari libur nasional Indonesia secara real-time dan otomatis dari:
    1. Google Calendar REST API v3 (jika ada GOOGLE_CALENDAR_API_KEY)
    2. Google Calendar Public iCal Feed resmi Indonesia (bebas API key, real-time dari Google)
    3. Daftar hari libur nasional komprehensif sebagai fallback offline.
    """
    cache_key = f"holidays_{year}"
    cached = safe_cache_get(cache_key)
    if cached:
        return cached

    holidays = []
    import urllib.request
    import re
    import json

    api_key = os.getenv('GOOGLE_CALENDAR_API_KEY')
    if api_key:
        try:
            calendar_id = 'id.indonesian#holiday@group.v.calendar.google.com'
            time_min = f"{year}-01-01T00:00:00Z"
            time_max = f"{year}-12-31T23:59:59Z"
            url = (
                f"https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events"
                f"?key={api_key}&timeMin={time_min}&timeMax={time_max}&singleEvents=true"
            )
            req = urllib.request.Request(url, headers={'User-Agent': 'BukuDigital/1.0'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            for item in data.get('items', []):
                start = item.get('start', {})
                dt = start.get('date') or (start.get('dateTime', '')[:10])
                if dt and dt.startswith(str(year)):
                    holidays.append({
                        'date': dt,
                        'name': item.get('summary', 'Hari Libur Nasional')
                    })
        except Exception as e:
            logger.warning(f"Gagal mengambil hari libur Google Calendar API: {e}")

    # Jika belum berhasil (tanpa API key atau API error), gunakan feed iCal resmi Google Calendar Indonesia
    if not holidays:
        try:
            ical_url = 'https://calendar.google.com/calendar/ical/id.indonesian%23holiday%40group.v.calendar.google.com/public/basic.ics'
            req = urllib.request.Request(ical_url, headers={'User-Agent': 'Mozilla/5.0 (compatible; BukuDigital/1.0)'})
            with urllib.request.urlopen(req, timeout=5) as resp:
                content = resp.read().decode('utf-8', errors='ignore')

            seen = set()
            year_str = str(year)
            for ev in content.split('BEGIN:VEVENT')[1:]:
                dtstart = re.search(r'DTSTART(?:;VALUE=DATE)?:(\d{8})', ev)
                summary = re.search(r'SUMMARY:(.+?)(?:\r\n|\n)', ev)
                if dtstart and summary:
                    d_raw = dtstart.group(1)
                    if d_raw.startswith(year_str):
                        date_str = f"{d_raw[:4]}-{d_raw[4:6]}-{d_raw[6:8]}"
                        name = summary.group(1).strip()
                        if date_str not in seen:
                            seen.add(date_str)
                            holidays.append({'date': date_str, 'name': name})
            holidays.sort(key=lambda x: x['date'])
        except Exception as e:
            logger.warning(f"Gagal mengambil hari libur iCal Google Calendar: {e}")

    # Fallback offline komprehensif jika jaringan terputus
    if not holidays:
        holidays = _fallback_holidays(year)

    safe_cache_set(cache_key, holidays, timeout=86400 * 7)  # 7 hari
    return holidays


def _fallback_holidays(year):
    """Daftar hari libur nasional statis sebagai fallback offline."""
    base_holidays = [
        {'date': f"{year}-01-01", 'name': 'Tahun Baru Masehi'},
        {'date': f"{year}-05-01", 'name': 'Hari Buruh Internasional'},
        {'date': f"{year}-06-01", 'name': 'Hari Lahir Pancasila'},
        {'date': f"{year}-08-17", 'name': 'Hari Kemerdekaan RI'},
        {'date': f"{year}-12-25", 'name': 'Hari Raya Natal'},
    ]
    known_2026 = [
        {'date': '2026-01-16', 'name': 'Isra Mikraj Nabi Muhammad'},
        {'date': '2026-02-16', 'name': 'Cuti Bersama Tahun Baru Imlek'},
        {'date': '2026-02-17', 'name': 'Tahun Baru Imlek'},
        {'date': '2026-03-18', 'name': 'Cuti Bersama Hari Suci Nyepi'},
        {'date': '2026-03-19', 'name': 'Hari Suci Nyepi'},
        {'date': '2026-03-20', 'name': 'Cuti Bersama Idul Fitri'},
        {'date': '2026-03-21', 'name': 'Hari Raya Idul Fitri'},
        {'date': '2026-03-22', 'name': 'Hari Raya Idul Fitri'},
        {'date': '2026-03-23', 'name': 'Cuti Bersama Idul Fitri'},
        {'date': '2026-03-24', 'name': 'Cuti Bersama Idul Fitri'},
        {'date': '2026-04-03', 'name': 'Wafat Isa Almasih'},
        {'date': '2026-05-14', 'name': 'Kenaikan Isa Al Masih'},
        {'date': '2026-05-15', 'name': 'Cuti Bersama Kenaikan Isa Al Masih'},
        {'date': '2026-05-27', 'name': 'Hari Raya Idul Adha'},
        {'date': '2026-05-31', 'name': 'Hari Raya Waisak'},
        {'date': '2026-06-17', 'name': 'Tahun Baru Islam (1 Muharam)'},
        {'date': '2026-08-25', 'name': 'Maulid Nabi Muhammad'},
        {'date': '2026-12-24', 'name': 'Cuti Bersama Hari Raya Natal'},
    ]
    if year == 2026:
        all_h = base_holidays + known_2026
        all_h.sort(key=lambda x: x['date'])
        return all_h
    return base_holidays


def call_n8n_routing(kunjungan_id, purpose, department=None, arrival_time=None, *args, **kwargs):
    """
    Memanggil Webhook N8N untuk Auto-Routing / Auto-Approval kunjungan.
    Dijalankan secara asynchronous (threading) agar tidak memperlambat respon user.

    Parameter:
        kunjungan_id (str): UUID kunjungan
        purpose (str): Keperluan kunjungan
        department (str, optional): Nama departemen tujuan
        arrival_time (datetime, optional): Waktu kedatangan
        *args, **kwargs: Menerima argumen tambahan (seperti pegawai_queryset) dengan aman.

    Returns:
        dict | None: Response dari n8n webhook jika berhasil, None jika gagal / dinonaktifkan
    """
    webhook_url = os.getenv('N8N_WEBHOOK_URL')
    if not webhook_url:
        logger.debug("N8N_WEBHOOK_URL tidak dikonfigurasi. Auto-routing dilewati.")
        return None

    timeout_seconds = int(os.getenv('N8N_WEBHOOK_TIMEOUT', '5'))

    arrival_str = (
        arrival_time.isoformat()
        if hasattr(arrival_time, 'isoformat')
        else (str(arrival_time) if arrival_time else timezone.now().isoformat())
    )

    payload = {
        'kunjungan_id': str(kunjungan_id or ''),
        'purpose': str(purpose or ''),
        'department': str(department or ''),
        'arrival_time': arrival_str,
        'timestamp': timezone.now().isoformat(),
        'source': 'bukudigital_django'
    }

    try:
        import urllib.request
        import urllib.error

        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={
                'Content-Type': 'application/json',
                'User-Agent': 'BukuDigital-AutoRouting/1.0',
            },
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
            resp_body = resp.read().decode('utf-8')
            logger.info("N8N Webhook responded HTTP %s for kunjungan %s", resp.status, kunjungan_id)
            try:
                return json.loads(resp_body)
            except json.JSONDecodeError:
                return {'raw': resp_body}

    except urllib.error.HTTPError as e:
        logger.warning("N8N Webhook HTTP %s untuk kunjungan %s: %s", e.code, kunjungan_id, e.reason)
        return None
    except urllib.error.URLError as e:
        logger.warning("N8N Webhook connection error untuk kunjungan %s: %s", kunjungan_id, e.reason)
        return None
    except Exception as e:
        logger.exception("N8N Webhook unhandled exception untuk kunjungan %s: %s", kunjungan_id, str(e))
        return None


def trigger_n8n_routing_async(kunjungan_id, purpose, department, arrival_time):
    """
    Menjalankan call_n8n_routing di latar belakang (background daemon thread)
    sehingga waktu pembuatan kunjungan tetap instan (< 100 ms).
    """
    import threading
    t = threading.Thread(
        target=call_n8n_routing,
        args=(kunjungan_id, purpose, department, arrival_time),
        daemon=True,
        name=f"n8n-routing-{kunjungan_id}"
    )
    t.start()


# ── Integrasi N8N AI Chat Assistant (Opsi A: Chat Admin) ─────────────────────

AI_MAX_STRIKES = 3  # Ambang batas otomatis handoff ke Admin manusia


def _get_clean_session_key(session_id):
    """Menghilangkan karakter berbahaya untuk key cache session."""
    return str(session_id or '').strip().replace(':', '_').replace(' ', '_')


def safe_cache_get(key, default=None):
    """Ambil data dari cache secara aman tanpa pernah melempar exception."""
    try:
        return cache.get(key, default)
    except Exception as e:
        logger.warning(f"safe_cache_get error for {key}: {e}")
        return default


def safe_cache_set(key, value, timeout=None):
    """Simpan data ke cache secara aman tanpa pernah melempar exception."""
    try:
        cache.set(key, value, timeout)
    except Exception as e:
        logger.warning(f"safe_cache_set error for {key}: {e}")


def safe_cache_delete(key):
    """Hapus data dari cache secara aman tanpa pernah melempar exception."""
    try:
        cache.delete(key)
    except Exception as e:
        logger.warning(f"safe_cache_delete error for {key}: {e}")


def is_session_handed_off_to_admin(session_id):
    """Cek apakah sesi chat tamu saat ini sudah dialihkan penuh ke Admin manusia."""
    if not session_id:
        return False
    sess_key = _get_clean_session_key(session_id)
    return bool(safe_cache_get(f"ai_handoff_active_{sess_key}"))


def get_session_strike_count(session_id):
    """Ambil jumlah strike kesalahan AI saat ini untuk sesi tertentu."""
    if not session_id:
        return 0
    sess_key = _get_clean_session_key(session_id)
    return int(safe_cache_get(f"ai_strike_count_{sess_key}", 0) or 0)


def set_session_handoff_to_admin(session_id, active=True):
    """Aktifkan atau nonaktifkan handoff ke admin manusia."""
    if not session_id:
        return
    sess_key = _get_clean_session_key(session_id)
    key = f"ai_handoff_active_{sess_key}"
    strike_key = f"ai_strike_count_{sess_key}"
    if active:
        safe_cache_set(key, True, timeout=86400)
    else:
        safe_cache_delete(key)
        safe_cache_delete(strike_key)


def reset_session_ai_mode(session_id):
    """Reset status handoff agar tamu bisa berbicara kembali dengan Asisten AI."""
    set_session_handoff_to_admin(session_id, active=False)


# ── Memori Konteks Percakapan Multi-Turn (Context Window Engine) ──────────────

def _infer_topic_from_text(text):
    """
    Mendeteksi topik layanan kedinasan dari teks percakapan.
    Mengembalikan: 'tte', 'subdomain', 'magang', 'csirt', 'wifi', 'lapor', 'statistik', 'pers', atau None.
    """
    if not text:
        return None
    txt = _normalize_slang_and_typos(str(text).lower())

    if any(k in txt for k in ('tte', 'bsre', 'tanda tangan elektronik', 'tanda tangan digital', 'sertifikat elektronik', 'passphrase')):
        return 'tte'
    if any(k in txt for k in ('subdomain', 'hosting', 'server opd', 'vps opd', 'data center opd', 'dns bekasikab')):
        return 'subdomain'
    if any(k in txt for k in ('magang', 'pkl', 'prakerin', 'praktik kerja', 'kerja praktek', 'riset kampus', 'penelitian skripsi')):
        return 'magang'
    if any(k in txt for k in ('csirt', 'insiden siber', 'hack', 'dihack', 'judi online', 'judol', 'deface', 'defacement', 'pentest', 'kerentanan', 'kebocoran data')):
        return 'csirt'
    if any(k in txt for k in ('wifi', 'wi-fi', 'intranet', 'fiber optik', 'kabel fo', 'bandwidth', 'jaringan putus', 'wifi mati')):
        return 'wifi'
    if any(k in txt for k in ('lapor', 'span lapor', 'sp4n lapor', 'pengaduan masyarakat', 'jalan rusak', 'keluhan warga', 'aspirasi warga')):
        return 'lapor'
    if any(k in txt for k in ('statistik', 'satu data', 'data sektoral', 'data kemiskinan', 'data kependudukan', 'walidata')):
        return 'statistik'
    if any(k in txt for k in ('liputan', 'pers', 'wartawan', 'media', 'konferensi pers', 'rilis berita')):
        return 'pers'
    return None


def get_conversation_context(session_id):
    """
    Mengambil data memori konteks sesi percakapan multi-turn:
    - active_topic: topik layanan kedinasan yang sedang dibahas
    - active_intent: intent percakapan terakhir
    - history: list giliran percakapan terakhir (sliding window)
    """
    if not session_id:
        return {}
    sess_key = _get_clean_session_key(session_id)
    cache_key = f"chat_conv_context_{sess_key}"
    ctx = safe_cache_get(cache_key)
    if isinstance(ctx, dict) and ctx:
        return ctx

    # Fallback jika cache kosong (misal setelah restart server):
    # Rekonstruksi dari riwayat ChatMessage di database
    try:
        from .models import ChatMessage
        recent_msgs = list(
            ChatMessage.objects.filter(session_id=str(session_id))
            .order_by('-created_at')[:4]
        )
        if recent_msgs:
            last_tamu_txt = ''
            for m in recent_msgs:
                if m.sender_type == 'tamu' and m.content:
                    last_tamu_txt = m.content.lower()
                    break
            topic = _infer_topic_from_text(last_tamu_txt)
            if topic:
                ctx = {
                    'active_topic': topic,
                    'active_intent': 'sop_dan_layanan_teknis',
                    'history': [],
                    'updated_at': timezone.now().isoformat(),
                }
                safe_cache_set(cache_key, ctx, timeout=3600)
                return ctx
    except Exception as e:
        logger.debug("Fallback context retrieval error: %s", e)

    return {}


def save_conversation_context(session_id, user_text, bot_reply_dict_or_str, intent=None, topic=None):
    """
    Menyimpan atau memperbarui memori konteks percakapan multi-turn.
    Menjaga sliding window percakapan (maksimal 5 giliran terakhir).
    """
    if not session_id:
        return
    sess_key = _get_clean_session_key(session_id)
    cache_key = f"chat_conv_context_{sess_key}"
    ctx = safe_cache_get(cache_key) or {}
    if not isinstance(ctx, dict):
        ctx = {}

    reply_text = ''
    if isinstance(bot_reply_dict_or_str, dict):
        reply_text = bot_reply_dict_or_str.get('reply_text') or bot_reply_dict_or_str.get('reply') or ''
        intent = intent or bot_reply_dict_or_str.get('intent')
    elif isinstance(bot_reply_dict_or_str, str):
        reply_text = bot_reply_dict_or_str

    detected_topic = topic or _infer_topic_from_text(user_text) or _infer_topic_from_text(reply_text)
    if detected_topic:
        ctx['active_topic'] = detected_topic
    elif not ctx.get('active_topic'):
        if intent == 'buat_kunjungan':
            ctx['active_topic'] = 'buat_kunjungan'

    if intent:
        ctx['active_intent'] = intent

    history = ctx.get('history') or []
    if not isinstance(history, list):
        history = []

    history.append({
        'user': (user_text or '').strip()[:200],
        'bot': (reply_text or '').strip()[:200],
        'topic': ctx.get('active_topic'),
        'timestamp': timezone.now().isoformat(),
    })
    ctx['history'] = history[-5:]
    ctx['updated_at'] = timezone.now().isoformat()

    safe_cache_set(cache_key, ctx, timeout=3600)


def clear_conversation_context(session_id):
    """Mereset memori konteks percakapan saat tamu ingin berganti topik secara eksplisit."""
    if not session_id:
        return
    sess_key = _get_clean_session_key(session_id)
    cache_key = f"chat_conv_context_{sess_key}"
    safe_cache_delete(cache_key)


SLANG_TYPO_MAP = {
    'daftr': 'daftar', 'daftarin': 'daftarkan', 'daftarn': 'daftar', 'dftr': 'daftar', 'dftarin': 'daftarkan',
    'kunjungn': 'kunjungan', 'knjungan': 'kunjungan', 'kunjunagn': 'kunjungan', 'kunjugan': 'kunjungan', 'knjgn': 'kunjungan',
    'bsk': 'besok', 'esok': 'besok', 'bso': 'besok', 'beso': 'besok',
    'lusa': 'lusa', 'hariini': 'hari ini', 'hr ini': 'hari ini', 'hari ni': 'hari ini', 'harii ini': 'hari ini',
    'skrg': 'sekarang', 'skarang': 'sekarang', 'sekarg': 'sekarang',
    'jadwaln': 'jadwalkan', 'jdwl': 'jadwal', 'jdwalkan': 'jadwalkan', 'jdwlin': 'jadwalkan',
    'kuotany': 'kuota', 'kuotanya': 'kuota', 'kouta': 'kuota', 'slotny': 'slot', 'sisa kuotany': 'sisa kuota',
    'msih': 'masih', 'msh': 'masih', 'msi': 'masih',
    'admn': 'admin', 'admnin': 'admin', 'ptugas': 'petugas', 'oprtr': 'operator',
    'komplainn': 'komplain', 'komplen': 'komplain', 'kluhan': 'keluhan', 'kndala': 'kendala',
    'batalin': 'batalkan', 'btal': 'batal', 'btl': 'batal', 'cancle': 'cancel', 'gk jadi': 'tidak jadi', 'ga jd': 'tidak jadi', 'gak jd': 'tidak jadi', 'nggak jadi': 'tidak jadi',
    'reschedul': 'ubah jadwal', 'reschedule': 'ubah jadwal', 'undur': 'ubah jadwal', 'geser': 'ubah jadwal',
    'ganti jam': 'ubah jadwal', 'ubah jam': 'ubah jadwal', 'ganti jadwal': 'ubah jadwal', 'rubah jadwal': 'ubah jadwal',
    'pndah': 'pindah', 'rubah': 'ubah', 'gnti': 'ganti', 'jm': 'jam', 'pkl': 'pukul',
    'infomasi': 'informasi', 'inpo': 'informasi', 'pegwe': 'pegawai', 'pgwai': 'pegawai', 'pegawaiy': 'pegawai',
    'mksih': 'terima kasih', 'makasih': 'terima kasih', 'tengkyu': 'terima kasih', 'makasi': 'terima kasih',
    'tte': 'tte', 'bsre': 'bsre', 'magang': 'magang', 'pkl': 'pkl',
    'heck': 'hack', 'dihack': 'hack', 'kehack': 'hack', 'kehacked': 'hack', 'hacked': 'hack',
    'judol': 'judi online', 'judi onlen': 'judi online',
    'wifii': 'wifi', 'waifi': 'wifi', 'jaringn': 'jaringan', 'konek': 'koneksi',
    'lpor': 'lapor', 'pelaporan': 'lapor', 'laporkan': 'lapor',
    'stastik': 'statistik', 'statistk': 'statistik', 'statisik': 'statistik', 'statistika': 'statistik',
    'syaratny': 'syarat', 'srat': 'syarat', 'persyaratn': 'persyaratan',
    'almt': 'alamat', 'dmana': 'di mana', 'dmna': 'di mana', 'dimn': 'di mana',
    'mhon': 'mohon', 'tlng': 'tolong', 'tlg': 'tolong',
    'keperluanny': 'keperluan', 'kperluan': 'keperluan',
    'stts': 'status', 'tket': 'tiket',
    'fc': 'fotokopi', 'fotocopy': 'fotokopi', 'photocopy': 'fotokopi',
    'kalo': 'kalau', 'klo': 'kalau', 'klu': 'kalau',
    'ga': 'tidak', 'gak': 'tidak', 'gk': 'tidak', 'ngga': 'tidak', 'nggak': 'tidak',
    'blh': 'boleh', 'bleh': 'boleh',
    'bs': 'bisa', 'bsa': 'bisa',
    'gmn': 'bagaimana', 'gmna': 'bagaimana', 'bgmn': 'bagaimana',
    'bwt': 'buat', 'byr': 'bayar', 'grts': 'gratis',
    'lntai': 'lantai', 'lt': 'lantai',
}


def _normalize_slang_and_typos(text):
    """Normalisasi kata-kata slang, singkatan ponsel, dan saltik umum."""
    import re
    if not text:
        return ""
    t = text.lower()
    for slang, normal in SLANG_TYPO_MAP.items():
        t = re.sub(rf'\b{re.escape(slang)}\b', normal, t)
    return t


def _fuzzy_keyword_match(text, keywords, threshold=0.82):
    """
    Pencocokan kata kunci dengan toleransi typo/saltik menggunakan difflib.
    Mendukung kecocokan exact substring atau perbandingan kemiripan fuzzy.
    """
    import difflib
    txt_clean = (text or '').lower()
    if any(k in txt_clean for k in keywords):
        return True

    words = txt_clean.split()
    if not words:
        return False

    for kw in keywords:
        kw_words = kw.split()
        kw_len = len(kw_words)
        if kw_len == 1:
            for w in words:
                if len(w) >= 3 and len(kw) >= 3 and abs(len(w) - len(kw)) <= 3:
                    if difflib.SequenceMatcher(None, w, kw).ratio() >= threshold:
                        return True
        else:
            for i in range(len(words) - kw_len + 1):
                ngram = " ".join(words[i:i + kw_len])
                if difflib.SequenceMatcher(None, ngram, kw).ratio() >= threshold:
                    return True
    return False


def _detect_user_intent_locally(message_text, session_id=None):
    """
    Deteksi intent lokal fallback jika N8N offline atau tidak merespon.
    Mengembalikan salah satu cabang intent N8N dengan respon ramah, luwes, dan kontekstual.
    Mendukung variasi bahasa sehari-hari, slang lokal (Bekasi/Jakarta), dan urutan kata fleksibel.
    Dilengkapi normalisasi typo, fuzzy keyword matching, dan Memori Konteks Percakapan Multi-Turn.
    """
    import re
    raw_txt = (message_text or '').strip().lower()
    txt = _normalize_slang_and_typos(raw_txt)
    if not txt:
        return {
            'intent': 'sapaan',
            'reply': "Halo! 👋 Ada yang bisa saya bantu terkait kunjungan ke Diskominfosantik Kab. Bekasi?",
            'handoff': False,
        }

    # 00. Reset / Ganti Topik Percakapan
    reset_words = ('reset chat', 'mulai ulang', 'mulai dari awal', 'hapus memori', 'ganti topik', 'topik baru')
    if _fuzzy_keyword_match(txt, reset_words):
        if session_id:
            clear_conversation_context(session_id)
        return {
            'intent': 'sapaan',
            'reply': "Baik, memori percakapan telah diatur ulang. 👋 Silakan tanyakan hal baru seputar layanan Diskominfosantik Kab. Bekasi!",
            'handoff': False,
        }

    # 0. Pengubahan Jadwal (Reschedule) & Pembatalan Kunjungan (Prioritas Sangat Tinggi)
    reschedule_cancel_words = (
        'ubah jadwal', 'ganti jam', 'ganti jadwal', 'ganti hari', 'reschedule',
        'undur jadwal', 'geser jadwal', 'pindah jam', 'pindah hari', 'ubah jam',
        'rubah jadwal', 'rubah jam', 'ganti waktu', 'pindah waktu',
        'batalkan kunjungan', 'batalkan janji temu', 'batal janji', 'batalkan tiket',
        'cancel kunjungan', 'batal kunjungan', 'batalin kunjungan', 'batalin tiket',
        'gak jadi datang', 'tidak jadi datang', 'batal datang', 'cancel tiket',
        'batalkan jadwal', 'batal jadwal', 'batalin jadwal'
    )
    if _fuzzy_keyword_match(txt, reschedule_cancel_words):
        return {
            'intent': 'ubah_jadwal_dan_batal',
            'reply': "Permintaan pengubahan jadwal atau pembatalan kunjungan Anda sedang diproses:",
            'handoff': False,
        }

    # 0a. Direktori Profil Pejabat Struktural & Struktur Organisasi Dinas
    is_pejabat_direct = any(k in txt for k in (
        'kepala dinas', 'kadis', 'pimpinan dinas', 'pimpinan kominfo', 'pimpinan diskominfosantik',
        'nama kepala dinas', 'siapa kadis', 'siapa kepala dinas', 'siapa pimpinan', 'kepala diskominfosantik',
        'kabid', 'kepala bidang', 'siapa kabid', 'sekretaris dinas', 'sekdis', 'siapa sekdis',
        'struktur organisasi', 'bagan organisasi', 'susunan organisasi', 'susunan pejabat',
        'profil pejabat', 'daftar pejabat', 'hierarki dinas', 'pejabat dinas', 'pejabat diskominfosantik',
        'siapa saja pejabat', 'siapa saja pimpinan'
    ))
    is_staf_query = (
        any(k in txt for k in (
            'staf yang menangani', 'petugas yang menangani', 'yang menangani jaringan',
            'yang ngurus jaringan', 'siapa staf', 'siapa teknisi', 'siapa admin jaringan',
            'staf jaringan', 'petugas jaringan', 'teknisi jaringan', 'teknisi wifi',
            'staf siber', 'staf csirt', 'staf ikp', 'staf magang'
        ))
        or ('siapa' in txt and any(k in txt for k in ('staf', 'petugas', 'teknisi', 'pejabat')))
    )
    if is_pejabat_direct or is_staf_query:
        detected_top = None
        if any(w in txt for w in ('jaringan', 'tik', 'wifi', 'internet', 'infrastruktur')):
            detected_top = 'wifi'
        elif any(w in txt for w in ('persandian', 'csirt', 'siber', 'tte')):
            detected_top = 'csirt'
        elif any(w in txt for w in ('statistik', 'data')):
            detected_top = 'statistik'
        elif any(w in txt for w in ('ikp', 'humas', 'lapor', 'liputan', 'media')):
            detected_top = 'lapor'
        elif any(w in txt for w in ('e-gov', 'egov', 'aplikasi', 'subdomain')):
            detected_top = 'subdomain'
        elif any(w in txt for w in ('magang', 'pkl', 'sekretariat', 'umum')):
            detected_top = 'magang'
        elif any(w in txt for w in ('kepala dinas', 'kadis')):
            detected_top = 'pejabat'

        return {
            'intent': 'pejabat_dan_struktur',
            'reply': _handle_pejabat_dan_struktur(txt, pegawai_qs=None),
            'handoff': False,
            'active_topic': detected_top,
        }

    # 0b. SOP & Layanan Teknis Kedinasan (6 Bidang Diskominfosantik) + Standar Waktu Layanan (SLA)
    sop_words = (
        'tte', 'bsre', 'tanda tangan elektronik', 'tanda tangan digital', 'sertifikat elektronik',
        'passphrase tte', 'daftar tte', 'buat tte', 'syarat tte', 'permohonan tte',
        'subdomain', 'hosting', 'server opd', 'domain bekasikab', 'pengajuan subdomain',
        'hosting aplikasi', 'vps opd', 'data center opd', 'sewa server',
        'csirt', 'keamanan siber', 'keamanan informasi', 'insiden siber', 'kena hack', 'dihack', 'judi online', 'judol', 'deface', 'defacement', 'pentest', 'kerentanan', 'kebocoran data',
        'wifi', 'wi-fi', 'intranet', 'fiber optic', 'kabel fo', 'bandwidth', 'jaringan putus', 'wifi mati', 'koneksi lambat', 'internet kecamatan', 'wifi publik', 'akses internet',
        'lapor', 'span lapor', 'sp4n lapor', 'pengaduan masyarakat', 'lapor jalan rusak', 'keluhan warga', 'aspirasi warga',
        'statistik', 'data statistik', 'satu data', 'statistik sektoral', 'data kemiskinan', 'data kependudukan', 'minta data', 'permohonan data', 'data bekasi', 'data sektoral',
        'magang', 'pkl', 'praktik kerja', 'prakerin', 'kerja praktek', 'riset kampus', 'penelitian skripsi',
        'liputan', 'kartu pers', 'wartawan', 'media massa', 'konferensi pers', 'rilis berita', 'ppid',
        'informasi publik', 'sengketa informasi', 'layanan dinas', 'sop dinas',
        # Standar Waktu Layanan (SLA / Durasi Penyelesaian)
        'berapa lama', 'berapa hari', 'durasi pelayanan', 'durasi pengurusan', 'estimasi waktu',
        'standar waktu', 'sla', 'service level agreement', 'lama proses', 'waktu proses',
        'lama penyelesaian', 'waktu penyelesaian', 'lama pengerjaan', 'kapan selesai', 'kapan jadi',
        'kapan beres', 'kapan kelar', 'target waktu', 'lama verifikasi', 'berapa hari kerja'
    )
    if _fuzzy_keyword_match(txt, sop_words):
        detected_top = _infer_topic_from_text(txt)
        return {
            'intent': 'sop_dan_layanan_teknis',
            'reply': "Berikut informasi SOP dan ketentuan layanan kedinasan Diskominfosantik Kab. Bekasi:",
            'handoff': False,
            'active_topic': detected_top,
        }

    # 1. Pendaftaran / Reservasi Kunjungan Baru (Prioritas sebelum sapaan agar kata seperti 'jam 10 pagi' tidak dianggap sapaan)
    booking_actions = (
        'buatkan', 'daftarkan', 'daftarin', 'daftar kunjungan', 'buat kunjungan',
        'bikin jadwal', 'bikin janji', 'buat janji temu', 'bikin janji temu', 'daftar janji temu',
        'bikinkan', 'bikinin',
        'pesan jadwal', 'pesankan', 'pesenin', 'jadwalkan', 'jadwalin',
        'mau daftar', 'mau berkunjung', 'rencana berkunjung', 'mau datang',
        'mau ketemu', 'pengen ketemu', 'ingin ketemu', 'mau sowan', 'mau audiensi',
        'reservasi', 'booking', 'bisa tolong daftarin', 'bisa daftarin',
        'bisa tidak membuatkan', 'bisa membuatkan', 'bisa buatkan', 'tolong buat',
        'tolong daftar', 'tolong daftarin', 'bikin kunjungan', 'atur jadwal',
        'jadwal kunjungan'
    )
    if _fuzzy_keyword_match(txt, booking_actions):
        return {
            'intent': 'buat_kunjungan',
            'reply': (
                "Untuk mengajukan jadwal kunjungan baru, silakan ikuti panduan berikut:\n\n"
                "📝 **Langkah Pengajuan Kunjungan:**\n"
                "1. Buka menu **Buku Tamu** pada menu navigasi samping.\n"
                "2. Pilih **Tanggal dan Waktu** kedatangan yang diinginkan.\n"
                "3. Pilih **Pegawai / Bidang Tujuan** serta isi keperluan kunjungan Anda.\n"
                "4. Klik tombol **Kirim Pengajuan**.\n\n"
                "💡 *Tips: Anda juga bisa langsung menyebutkan hari, jam, dan keperluan di chat ini "
                "(contoh: \"Daftarin hari Senin jam 09:00 urusan konsultasi jaringan WiFi\") agar langsung saya buatkan!*"
            ),
            'handoff': False,
        }

    # 2. Jadwal, Kuota & Hari Operasional (Mendukung susunan fleksibel & bahasa sehari-hari)
    schedule_keywords = (
        'jadwal', 'kuota', 'slot', 'jam operasional', 'hari operasional',
        'hari kerja', 'libur', 'sabtu', 'minggu', 'weekend', 'akhir pekan',
        'tanggal merah', 'buka jam', 'tutup jam', 'jam buka', 'jam tutup',
        'buka gak', 'buka ga', 'buka gk', 'buka tidak', 'buka kah',
        'tutup gak', 'tutup ga', 'tutup gk', 'hari ini buka', 'sekarang buka',
        'besok buka', 'bisa datang hari ini', 'bisa datang gak', 'bisa datang ga',
        'ada pelayanan', 'ada orang gak', 'ada orang ga'
    )
    has_open_close = any(k in txt for k in ('buka', 'tutup', 'operasi', 'operasional'))
    has_time_context = any(k in txt for k in ('hari ini', 'sekarang', 'besok', 'lusa', 'kantor', 'layanan', 'dinas', 'sabtu', 'minggu', 'senin', 'jumat', 'pagi', 'siang', 'sore'))
    if _fuzzy_keyword_match(txt, schedule_keywords) or (has_open_close and has_time_context):
        return {
            'intent': 'jadwal_kuota',
            'reply': "Berikut informasi jadwal operasional dan kuota kunjungan Diskominfosantik Kab. Bekasi:",
            'handoff': False,
        }

    # 2b. BANTUAN MEMORI KONTEKS MULTI-TURN (Contextual Conversation Memory)
    # Jika percakapan memiliki active_topic sebelumnya dan pesan saat ini adalah pertanyaan lanjutan (follow-up)
    if session_id:
        ctx = get_conversation_context(session_id)
        active_topic = ctx.get('active_topic')
        if active_topic in ('tte', 'subdomain', 'magang', 'csirt', 'wifi', 'lapor', 'statistik', 'pers'):
            followup_signals = (
                'boleh tidak', 'boleh gak', 'boleh ga', 'bisa tidak', 'bisa gak', 'bisa ga',
                'apakah boleh', 'apakah bisa', 'bolehkah', 'bisakah', 'kalo', 'kalau',
                'harus', 'wajib', 'perlu', 'butuh', 'bagaimana', 'gimana', 'caranya',
                'kenapa', 'mengapa', 'apakah', 'maksudnya', 'maksud',
                'ktp', 'fotokopi', 'fotocopy', 'fc', 'asli', 'scan', 'dokumen', 'berkas',
                'surat', 'format', 'rekomendasi', 'sk', 'email', 'dinas', 'biaya',
                'bayar', 'gratis', 'tarif', 'ongkos', 'uang', 'diwakilkan', 'sendiri',
                'kuota', 'lama', 'kapan', 'durasi', 'waktu', 'lantai', 'ruangan', 'lokasi',
                'smk', 'mahasiswa', 'jurusan', 'anonim', 'rahasia', 'excel', 'data',
                'itu', 'tadi', 'tersebut', 'lanjutannya', 'terus', 'lalu', 'selanjutnya'
            )
            if any(sig in txt for sig in followup_signals):
                return {
                    'intent': 'sop_dan_layanan_teknis',
                    'reply': f"Berikut penjelasan lanjutan terkait layanan {active_topic}:",
                    'handoff': False,
                    'active_topic': active_topic,
                    'is_followup': True,
                }

    # 3. Status Kunjungan
    status_words = (
        'status', 'cek status', 'cek kunjungan', 'tiket', 'antrian',
        'kunjungan saya', 'sudah diacc', 'sudah acc', 'acc belum', 'disetujui belum',
        'proses sampai mana', 'status tiket', 'gimana kunjungan saya'
    )
    if _fuzzy_keyword_match(txt, status_words):
        return {
            'intent': 'cek_status_kunjungan',
            'reply': "Berikut adalah informasi status kunjungan terbaru Anda dari sistem:",
            'handoff': False,
        }

    # 4. Pengaduan, Keluhan & Bantuan Admin Manusia (Prioritas Tinggi)
    complaint_words = (
        'keluhan', 'komplain', 'kendala', 'masukan', 'saran', 'masalah',
        'tidak bisa', 'gak bisa', 'ga bisa', 'nggak bisa', 'error', 'eror',
        'bantuan admin', 'bicara admin', 'bicara dengan admin', 'hubungkan admin',
        'hubungi admin', 'operator', 'petugas manusia', 'antrean', 'antri',
        'lama banget', 'loket', 'lemot', 'lelet', 'lambat', 'pending',
        'stuck', 'hang', 'down', 'susah', 'gangguan', 'jelek', 'parah',
        'kecewa', 'kesal'
    )
    if _fuzzy_keyword_match(txt, complaint_words):
        return {
            'intent': 'keluhan_dan_masukan',
            'reply': (
                "Terima kasih atas masukan/kendala yang Anda sampaikan. Pesan Anda telah kami catat "
                "dan diteruskan ke petugas Admin Diskominfosantik kami."
            ),
            'handoff': True,
        }

    # 5. Basa-basi & Ucapan Terima Kasih (respon hangat, hindari strike)
    thanks_words = (
        'terima kasih', 'thanks', 'thx', 'nuhun',
        'matur nuwun', 'tengkyu', 'tengs', 'arigatou', 'syukron'
    )
    if _fuzzy_keyword_match(txt, thanks_words):
        return {
            'intent': 'sapaan',
            'reply': (
                "Sama-sama! Senang sekali bisa membantu Anda. 😊\n"
                "Jika ada hal lain yang ingin Anda tanyakan seputar layanan, jadwal kunjungan, "
                "atau status antrean di Diskominfosantik Kab. Bekasi, jangan ragu untuk menyapa saya kembali ya. "
                "Semoga urusan Anda berjalan lancar!"
            ),
            'handoff': False,
        }

    # 6. Persetujuan / Konfirmasi santai pengguna
    confirm_words = (
        'oke', 'ok', 'siap', 'baik', 'baiklah', 'sip', 'noted',
        'siap min', 'siap kak', 'oke min', 'oke kak', 'ok min', 'ok kak',
        'oke siap', 'siap makasih', 'oke makasih', 'yoi', 'mantap', 'oke deh',
        'siap makasi', 'oke terima kasih'
    )
    if txt in confirm_words or any(txt.startswith(c) for c in ('siap kak', 'siap min', 'oke min', 'oke kak', 'baik min')):
        return {
            'intent': 'sapaan',
            'reply': (
                "Baik, terima kasih! 👍\n"
                "Silakan beri tahu saya jika ada hal lain yang ingin Anda konsultasikan atau tanyakan seputar kunjungan."
            ),
            'handoff': False,
        }

    # 7. Alamat / Lokasi Kantor (Mendukung ragam pertanyaan tempat & rute)
    address_words = (
        'alamat', 'lokasi', 'dimana kantor', 'di mana kantor', 'gedung mana', 'daerah mana',
        'rute', 'maps', 'peta', 'google maps', 'kantornya dimana', 'kantornya di mana',
        'dimana lokasinya', 'di mana lokasinya', 'lokasinya dimana', 'lokasinya di mana',
        'lokasi kantor', 'tempatnya dimana', 'tempatnya di mana', 'arah ke kantor',
        'posisi kantor', 'patokan kantor', 'cara ke kantor'
    )
    if any(k in txt for k in address_words):
        return {
            'intent': 'info_layanan_dan_pegawai',
            'reply': (
                "📍 **Alamat & Lokasi Kantor Diskominfosantik Kabupaten Bekasi:**\n\n"
                "Kompleks Perkantoran Pemerintah Kabupaten Bekasi, Gedung Diskominfosantik, Blok B\n"
                "Desa Sukamahi, Kecamatan Cikarang Pusat, Kabupaten Bekasi, Jawa Barat 17530.\n\n"
                "🗺️ **Petunjuk Arah Google Maps:**\n"
                "[Buka Rute di Google Maps](https://www.google.com/maps/search/?api=1&query=Diskominfosantik+Kabupaten+Bekasi)\n\n"
                "🕒 **Waktu Layanan Tatap Muka:**\n"
                "Senin – Jumat, pukul 08:00 – 16:00 WIB (Hari Sabtu, Minggu & Hari Libur Nasional Tutup).\n\n"
                "💡 *Patokan: Berada di kawasan pusat pemerintahan Pemkab Bekasi (Delta Mas / Cikarang Pusat).*"
            ),
            'handoff': False,
        }

    # 8. Persyaratan Kunjungan / Berkas
    requirement_words = (
        'syarat', 'persyaratan', 'bawa apa', 'berkas apa', 'dokumen apa',
        'dokumen yang harus', 'perlu bawa apa', 'harus bawa apa', 'bawa berkas apa',
        'ketentuan berkunjung'
    )
    if any(k in txt for k in requirement_words):
        return {
            'intent': 'info_layanan_dan_pegawai',
            'reply': (
                "📋 **Persyaratan Kunjungan ke Diskominfosantik Kab. Bekasi:**\n\n"
                "1. 🆔 **Identitas Diri**: Membawa KTP / SIM / Kartu Identitas resmi yang masih berlaku.\n"
                "2. 📄 **Surat Tugas / Pengantar**: Wajib untuk kunjungan kedinasan atau perwakilan lembaga/instansi.\n"
                "3. 🎫 **Kode Tiket**: Menunjukkan bukti/kode tiket kunjungan yang didaftarkan melalui Buku Tamu Digital ini.\n"
                "4. 👔 **Tata Tertib**: Berpakaian rapi, sopan (berkerah), dan bersepatu.\n\n"
                "Pelayanan tatap muka dibuka setiap hari kerja (Senin – Jumat, pukul 08:00 – 16:00 WIB)."
            ),
            'handoff': False,
        }

    # 9. Informasi Pegawai & Bidang Layanan
    info_words = (
        'pegawai', 'bidang', 'layanan', 'dinas', 'siapa saja', 'kontak',
        'tik', 'persandian', 'statistik', 'ikp', 'e-gov', 'egov', 'sekretariat',
        'bagian apa', 'divisi'
    )
    if any(k in txt for k in info_words):
        return {
            'intent': 'info_layanan_dan_pegawai',
            'reply': "Berikut daftar bidang dan pegawai layanan aktif di Diskominfosantik Kab. Bekasi:",
            'handoff': False,
        }

    # 10. Sapaan Murni (Greetings)
    pure_greetings = (
        'halo', 'hai', 'hi', 'assalamu', 'sampurasun', 'kulonuwun',
        'permisi', 'punteun', 'punten', 'selamat pagi', 'selamat siang',
        'selamat sore', 'selamat malam',
    )
    is_greeting = any(k in txt for k in pure_greetings)
    tokens = txt.split()
    if not is_greeting and len(tokens) <= 3 and any(t in tokens for t in ('pagi', 'siang', 'sore', 'malam')):
        # Pastikan bukan bagian dari jam (misal "jam 10 pagi")
        if not any(re.search(r'\b\d{1,2}\b', t) for t in tokens) and 'jam' not in txt and 'pukul' not in txt:
            is_greeting = True

    if is_greeting:
        return {
            'intent': 'sapaan',
            'reply': (
                "Halo! 👋 Selamat datang di Layanan Buku Tamu Digital Diskominfosantik Kab. Bekasi.\n"
                "Saya Asisten AI yang siap membantu Anda mengecek status kunjungan, informasi jadwal & kuota, "
                "layanan dinas, atau membuat jadwal kunjungan baru. Ada yang bisa saya bantu?"
            ),
            'handoff': False,
        }

    # 11. Di Luar Konteks (Fallback Ramah & Solutif)
    return {
        'intent': 'di_luar_konteks',
        'reply': (
            "Mohon maaf, saya belum memahami pertanyaan Anda. Saya adalah Asisten AI untuk layanan "
            "Buku Tamu Digital Diskominfosantik Kab. Bekasi.\n\n"
            "Anda dapat menanyakan hal seputar:\n"
            "• *Cek Status Kunjungan*\n"
            "• *Jadwal Operasional & Kuota Kunjungan*\n"
            "• *Informasi Bidang & Pegawai Tujuan*\n"
            "• *Pendaftaran Jadwal Kunjungan Baru*\n"
            "• *Alamat Kantor & Persyaratan Berkunjung*\n\n"
            "Jika Anda membutuhkan bantuan langsung dari petugas manusia, silakan beritahu saya."
        ),
        'handoff': False,
    }


def recommend_pegawai_by_purpose(text, pegawai_qs=None):
    """
    Menganalisis topik / keperluan kunjungan tamu secara otomatis dan
    merekomendasikan Pegawai & Bidang yang paling sesuai di Diskominfosantik.
    """
    if not text:
        return None

    txt = text.lower()

    if not pegawai_qs:
        from .models import Pegawai
        pegawai_qs = list(
            Pegawai.objects.filter(account_status='active')
            .select_related('department_rel')
            .order_by('name')
        )

    # 1. Cek kecocokan nama pegawai langsung jika tamu menyebutkan nama
    for p in pegawai_qs:
        name_tokens = [
            tok.lower().strip('.,')
            for tok in p.name.split()
            if len(tok.strip('.,')) >= 4 and tok.lower().strip('.,') not in ('drs', 'dra', 'mkom', 'skom', 'st', 'mt', 'sh', 'mh', 'msi')
        ]
        if any(tok in txt for tok in name_tokens):
            return p

    # 2. Pemetaan topik ke bidang & role spesifik di Diskominfosantik
    topic_rules = [
        # BIDANG TIK: Jaringan, Internet, WiFi, Server, Infrastruktur
        {
            'keywords': [
                'jaringan', 'internet', 'wifi', 'wi-fi', 'fiber optik', 'fo',
                'server', 'data center', 'router', 'switch', 'cctv', 'bandwidth',
                'kabel lan', 'koneksi internet', 'infrastruktur tik', 'ip address',
                'komputer rusak', 'perangkat jaringan', 'perbaikan lan',
            ],
            'dept_code': 'TIK',
            'preferred_roles': ['Administrator Jaringan', 'Teknisi Infrastruktur TIK', 'Kepala Bidang'],
        },
        # BIDANG E-GOVERNMENT: Aplikasi, Web, SPBE, Sistem Informasi, Database
        {
            'keywords': [
                'aplikasi', 'website', 'web', 'spbe', 'sistem informasi', 'software',
                'database', 'hosting', 'domain', 'programmer', 'coding', 'api',
                'integrasi sistem', 'sistem pemerintahan berbasis elektronik',
                'sistem layanan', 'portal', 'sippn', 'superapp', 'tte terintegrasi',
            ],
            'dept_code': 'E-GOV',
            'preferred_roles': ['Kepala Bidang E-Government', 'Analis Sistem Informasi', 'Pengembang Perangkat Lunak'],
        },
        # BIDANG PERSANDIAN: Keamanan Siber, Sandi, CSIRT, Enkripsi, TTE
        {
            'keywords': [
                'persandian', 'sandi', 'keamanan siber', 'keamanan informasi', 'cyber',
                'cybersecurity', 'hacker', 'hacking', 'enkripsi', 'tte', 'tanda tangan elektronik',
                'sertifikat elektronik', 'bsre', 'csirt', 'pentest', 'kerentanan', 'kebocoran data',
            ],
            'dept_code': 'SANDI',
            'preferred_roles': ['Analis Keamanan Siber', 'Kepala Bidang Persandian'],
        },
        # BIDANG IKP: Berita, Humas, Media, Publikasi, PPID, Liputan
        {
            'keywords': [
                'berita', 'liputan', 'media', 'pers', 'wartawan', 'humas', 'publikasi',
                'ppid', 'informasi publik', 'konten', 'sosial media', 'sosmed',
                'rilis', 'konferensi pers', 'videografer', 'fotografer', 'dokumentasi',
            ],
            'dept_code': 'IKP',
            'preferred_roles': ['Pengelola Informasi Publik', 'Penyusun Konten Media', 'Kepala Bidang'],
        },
        # BIDANG STATISTIK: Data Sektoral, Survei, Satu Data, Analisis
        {
            'keywords': [
                'statistik', 'data', 'survei', 'sensus', 'satu data', 'sdi',
                'metadata', 'data sektoral', 'analisis data', 'portal data', 'infografis data',
            ],
            'dept_code': 'STATISTIK',
            'preferred_roles': ['Statistisi Ahli Pertama', 'Pengolah Data Statistik', 'Kepala Bidang Statistik'],
        },
        # SEKRETARIAT: Magang, PKL, Surat Menyurat, Kepegawaian, Administrasi Umum
        {
            'keywords': [
                'magang', 'pkl', 'praktik kerja', 'penelitian', 'skripsi', 'surat',
                'disposisi', 'kepegawaian', 'administrasi', 'berkas', 'arsip',
                'keuangan', 'gaji', 'umum',
            ],
            'dept_code': 'SEKRE',
            'preferred_roles': ['Pengadministrasi Umum', 'Pengelola Kepegawaian', 'Sekretaris'],
        },
    ]

    matched_dept_code = None
    matched_preferred_roles = []

    for rule in topic_rules:
        if any(kw in txt for kw in rule['keywords']):
            matched_dept_code = rule['dept_code']
            matched_preferred_roles = rule['preferred_roles']
            break

    if not matched_dept_code:
        # Fallback: cek kecocokan nama departemen secara parsial
        for p in pegawai_qs:
            dept_name = (p.department_rel.nama if p.department_rel else (p.department or '')).lower()
            if dept_name and len(dept_name) >= 4 and dept_name in txt:
                return p
        return None

    # Cari pegawai di departemen yang cocok
    candidates = [
        p for p in pegawai_qs
        if (p.department_rel and p.department_rel.kode == matched_dept_code)
        or (p.department and matched_dept_code in p.department.upper())
    ]

    if not candidates:
        return None

    # Utamakan pegawai yang jabatannya paling cocok dengan topik
    for role_pref in matched_preferred_roles:
        for cand in candidates:
            if cand.jabatan and role_pref.lower() in cand.jabatan.lower():
                return cand

    return candidates[0]


def _try_create_kunjungan_from_chat(tamu, message_text, n8n_res, pegawai_qs):
    """
    Mendeteksi apakah pesan Tamu adalah perintah langsung untuk membuat/mendaftarkan
    jadwal kunjungan lewat Chat secara interaktif:
    1. Jika baru menyebutkan hari/tanggal (tanpa jam / keperluan):
       AI mengecek ketersediaan kuota hari tersebut, lalu menanyakan jam berapa & keperluannya.
       Data disimpan sementara di cache (draft).
    2. Jika Tamu membalas dengan jam & keperluan (atau langsung lengkap sejak awal):
       AI langsung membuatkan Kunjungan di database dan memberikan Kode Tiket.
    3. Jika Tamu mengatakan "batal", draft dibatalkan.
    """
    import re
    from datetime import datetime, time as dt_time, timedelta
    import zoneinfo
    from django.db import transaction
    from .models import Kunjungan, KunjunganStatusHistory
    from .validators import get_daily_quota_info

    if not tamu:
        return None

    raw = (message_text or '').strip()
    txt = _normalize_slang_and_typos(raw.lower())

    draft_key = f"chat_booking_draft_{tamu.id}"
    draft = safe_cache_get(draft_key)

    # 1. Cek jika Tamu membatalkan proses pendaftaran
    if draft and any(w in txt for w in ('batal', 'cancel', 'tidak jadi', 'gak jadi', 'ga jadi')):
        safe_cache_delete(draft_key)
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Baik, proses pengajuan kunjungan telah dibatalkan. Jika ada hal lain yang ingin Anda tanyakan, silakan beri tahu saya!"
        )

    # Map nama hari Indonesia
    day_patterns = [
        (0, 'Senin', r'\bsenin\w*\b'),
        (1, 'Selasa', r'\bselasa\w*|\bslasa\w*\b'),
        (2, 'Rabu', r'\brabu\w*|\brebo\w*\b'),
        (3, 'Kamis', r'\bkamis\w*|\bkemis\w*\b'),
        (4, 'Jumat', r'\bjum\'?at\w*\b'),
        (5, 'Sabtu', r'\bsabtu\w*\b'),
        (6, 'Minggu', r'\bminggu\w*|\bahad\w*\b'),
    ]

    jakarta_tz = zoneinfo.ZoneInfo('Asia/Jakarta')
    now_local = timezone.localtime(timezone.now(), jakarta_tz)
    today = now_local.date()

    target_date = None
    matched_day_label = None

    # Ekstraksi Tanggal Eksplisit dari pesan saat ini
    m_iso = re.search(r'\b(20\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])\b', txt)
    m_dmy = re.search(r'\b(0?[1-9]|[12]\d|3[01])[-/](0?[1-9]|1[0-2])(?:[-/](20\d{2}))?\b', txt)
    if m_iso:
        try:
            target_date = datetime(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))).date()
        except ValueError:
            target_date = None
    elif m_dmy:
        try:
            yr = int(m_dmy.group(3)) if m_dmy.group(3) else today.year
            target_date = datetime(yr, int(m_dmy.group(2)), int(m_dmy.group(1))).date()
        except ValueError:
            target_date = None

    if not target_date:
        month_map = {
            'januari': 1, 'jan': 1, 'februari': 2, 'feb': 2, 'maret': 3, 'mar': 3,
            'april': 4, 'apr': 4, 'mei': 5, 'juni': 6, 'jun': 6, 'juli': 7, 'jul': 7,
            'agustus': 8, 'agu': 8, 'ags': 8, 'september': 9, 'sep': 9, 'sept': 9,
            'oktober': 10, 'okt': 10, 'november': 11, 'nov': 11, 'desember': 12, 'des': 12,
        }
        m_named = re.search(
            r'\b(\d{1,2})\s+(januari|jan|februari|feb|maret|mar|april|apr|mei|juni|jun|juli|jul|agustus|agu|ags|september|sept|sep|oktober|okt|november|nov|desember|des)(?:\s+(20\d{2}))?\b',
            txt
        )
        if m_named:
            try:
                yr = int(m_named.group(3)) if m_named.group(3) else today.year
                target_date = datetime(yr, month_map[m_named.group(2)], int(m_named.group(1))).date()
            except ValueError:
                target_date = None

    if not target_date:
        if re.search(r'\blusa\b', txt):
            target_date = today + timedelta(days=2)
        elif re.search(r'\b(besok|esok)\b', txt):
            target_date = today + timedelta(days=1)
        elif re.search(r'\bhari\s+ini\b', txt):
            target_date = today
        else:
            for wd_idx, wd_name, pattern in day_patterns:
                if re.search(pattern, txt):
                    days_ahead = (wd_idx - today.weekday()) % 7
                    if days_ahead == 0 and ('depan' in txt or now_local.hour >= 15):
                        days_ahead = 7
                    target_date = today + timedelta(days=days_ahead)
                    matched_day_label = wd_name
                    break

    if not target_date and (n8n_res.get('tanggal') or n8n_res.get('date')):
        raw_n8n_date = str(n8n_res.get('tanggal') or n8n_res.get('date')).strip()
        try:
            target_date = datetime.strptime(raw_n8n_date[:10], '%Y-%m-%d').date()
        except Exception:
            target_date = None

    # Jika tanggal tidak ada di pesan sekarang tapi ada di draft sebelumnya
    if not target_date and draft and draft.get('target_date'):
        try:
            target_date = datetime.fromisoformat(draft['target_date']).date()
            matched_day_label = draft.get('hari_str')
        except Exception:
            target_date = None

    has_direct_verb = any(k in txt for k in (
        'buatkan', 'daftarkan', 'daftarin', 'bikin jadwal', 'bikin janji', 'janji temu',
        'bikinkan', 'bikinin', 'pesan jadwal', 'pesankan', 'pesenin',
        'jadwalkan', 'jadwalin', 'tolong buat', 'tolong daftar', 'tolong daftarin',
        'mau daftar', 'mau berkunjung', 'rencana berkunjung', 'mau datang',
        'mau ketemu', 'pengen ketemu', 'ingin ketemu', 'mau sowan', 'mau audiensi',
        'reservasi', 'booking', 'buat jadwal', 'mau buat kunjungan',
        'bisa tolong daftarin', 'bisa daftarin', 'bisa tolong daftarkan',
        'bisa tidak membuatkan', 'bisa membuatkan', 'bisa buatkan',
        'bikin kunjungan', 'atur jadwal', 'jadwal kunjungan',
    ))

    if not target_date:
        if has_direct_verb:
            return (
                "🤖 Asisten AI Diskominfosantik:\n"
                "Tentu bisa! Saya dapat langsung mendaftarkan jadwal kunjungan Anda ke sistem.\n\n"
                "📝 **Untuk hari atau tanggal berapa rencana kunjungan Anda?**\n"
                "Contoh: *\"Hari Senin jam 10:00 keperluan rapat koordinasi\"* atau *\"Besok pagi\"*."
            )
        return None

    hari_names = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']
    hari_str = matched_day_label or hari_names[target_date.weekday()]

    # Validasi Hari Sabtu / Minggu (Jam Operasional Senin - Jumat)
    if target_date.weekday() in (5, 6):
        next_monday = target_date + timedelta(days=(7 - target_date.weekday()))
        if draft:
            safe_cache_delete(draft_key)
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            f"⚠️ Mohon maaf, hari **{hari_str} ({target_date.strftime('%d/%m/%Y')})** adalah hari libur akhir pekan "
            "(Layanan Diskominfosantik beroperasi hari **Senin – Jumat, 08:00 – 16:00 WIB**).\n\n"
            f"💡 Silakan sebutkan hari kerja berikutnya, contoh:\n"
            f"*\"Hari Senin ({next_monday.strftime('%d/%m/%Y')}) jam 09:00\"* agar dapat saya daftarkan."
        )

    # Validasi Kuota & Hari Libur Kalender
    try:
        quota_info = get_daily_quota_info(target_date)
    except Exception:
        quota_info = None

    if quota_info and quota_info.get('is_holiday'):
        if draft:
            safe_cache_delete(draft_key)
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            f"🔴 Mohon maaf, tanggal **{target_date.strftime('%d/%m/%Y')} ({hari_str})** ditetapkan sebagai hari libur "
            f"({quota_info.get('holiday_name') or 'Libur Operasional'}).\n\n"
            "Silakan sebutkan hari kerja lainnya (Senin – Jumat) untuk saya daftarkan."
        )
    if quota_info and quota_info.get('is_full'):
        if draft:
            safe_cache_delete(draft_key)
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            f"🔴 Mohon maaf, kuota kunjungan untuk hari **{hari_str}, {target_date.strftime('%d/%m/%Y')}** sudah penuh "
            f"({quota_info['booked']}/{quota_info['quota']} kuota terisi).\n\n"
            "Silakan sebutkan hari kerja berikutnya agar saya daftarkan."
        )

    # Parse Jam Kedatangan
    visit_hour, visit_minute = None, None
    m_time = re.search(r'(?:jam|pukul|pkl)\s*(\d{1,2})(?:[:.](\d{2}))?', txt)
    if not m_time:
        m_time = re.search(r'\b([01]?\d|2[0-3])[:.]([0-5]\d)\s*(?:wib)?\b', txt)
    if m_time:
        h_val = int(m_time.group(1))
        m_val = int(m_time.group(2)) if m_time.group(2) else 0
        if 1 <= h_val <= 4 and ('siang' in txt or 'sore' in txt):
            h_val += 12
        visit_hour = max(8, min(15, h_val))
        visit_minute = max(0, min(59, m_val))
    elif 'siang' in txt:
        visit_hour, visit_minute = 13, 0
    elif 'sore' in txt:
        visit_hour, visit_minute = 14, 30
    elif 'pagi' in txt:
        visit_hour, visit_minute = 9, 0
    elif draft and draft.get('visit_hour') is not None:
        visit_hour = draft['visit_hour']
        visit_minute = draft.get('visit_minute', 0)

    # 1. Ekstrak Keperluan Kunjungan
    purpose_str = None
    m_purp = re.search(
        r'(?:keperluan|tujuan|agenda|dalam rangka|untuk bahas|mengenai|tentang|konsultasi|rapat|koordinasi|audiensi|studi banding|peliputan|wawancara|pengadaan|urusan|soal|perihal|masalah|terkait|bahas|urus)\s*[:\-]?\s*(.+)$',
        raw,
        flags=re.IGNORECASE,
    )
    if m_purp:
        extracted = m_purp.group(1).strip().rstrip('?.!')
        if len(extracted) >= 3:
            purpose_str = f"[Dinas] {extracted}"
    elif draft:
        cleaned = re.sub(r'(?:jam|pukul|pkl)\s*\d{1,2}(?:[:.]\d{2})?', '', raw, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b([01]?\d|2[0-3])[:.]([0-5]\d)\s*(?:wib)?\b', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\b(senin|selasa|rabu|kamis|jumat|sabtu|minggu|besok|lusa|pagi|siang|sore|wib)\b', '', cleaned, flags=re.IGNORECASE).strip(' ,.-')
        if len(cleaned) >= 3:
            purpose_str = f"[Dinas] {cleaned}"
    elif draft and draft.get('purpose'):
        purpose_str = draft['purpose']

    if not purpose_str and tamu:
        ctx_booking = get_conversation_context(str(tamu.id))
        act_top = ctx_booking.get('active_topic')
        topic_purpose_map = {
            'tte': '[Dinas] Konsultasi & Pengurusan Tanda Tangan Elektronik (TTE / BSrE)',
            'subdomain': '[Dinas] Pengajuan Subdomain & Hosting Server OPD',
            'magang': '[Pendidikan] Koordinasi & Pendaftaran Magang / PKL',
            'csirt': '[Keamanan Siber] Konsultasi Penanganan Insiden Keamanan Siber CSIRT',
            'wifi': '[TIK] Koordinasi & Penanganan Gangguan Jaringan WiFi / Intranet',
            'lapor': '[Pelayanan Publik] Konsultasi Kanal Pengaduan SP4N-LAPOR!',
            'statistik': '[Riset] Permohonan Data Statistik Sektoral',
            'pers': '[Kemitraan] Koordinasi Peliputan Media & Publikasi',
        }
        if act_top in topic_purpose_map:
            purpose_str = topic_purpose_map[act_top]

    # 2. Ekstrak / Rekomendasikan Pegawai Tujuan
    rec_peg = None
    is_ai_recommended = False
    if n8n_res.get('pegawai_id'):
        rec_peg = next((p for p in pegawai_qs if str(p.id) == str(n8n_res['pegawai_id'])), None)

    if not rec_peg and draft and draft.get('pegawai_id'):
        rec_peg = next((p for p in pegawai_qs if str(p.id) == str(draft['pegawai_id'])), None)

    # 2b. Cek jika tamu memilih nomor pegawai dari daftar database yang ditampilkan sebelumnya
    if not rec_peg and draft and draft.get('peg_map'):
        peg_map = draft['peg_map']
        m_pick = re.search(r'\b(?:pilih\s+)?(?:nomor|no\.?|angka)\s*(\d{1,2})\b', txt)
        if not m_pick:
            m_pick = re.search(r'\b(?:pilih\s+)?([1-9]\d?)\b', txt)
        if m_pick:
            picked_num = str(m_pick.group(1))
            is_hour_mention = bool(re.search(rf'(?:jam|pukul|pkl)\s*{picked_num}\b', txt))
            if picked_num in peg_map and (not is_hour_mention or 'pilih' in txt or 'nomor' in txt or 'no' in txt):
                matched_id = peg_map[picked_num]
                rec_peg = next((p for p in pegawai_qs if str(p.id) == str(matched_id)), None)

    if not rec_peg:
        # Cek dari nama langsung atau deteksi topik keperluan via AI Auto-Router
        combined_text = f"{raw} {purpose_str or ''}"
        rec_peg = recommend_pegawai_by_purpose(combined_text, pegawai_qs=pegawai_qs)
        if rec_peg:
            is_ai_recommended = True

    # 3. Ambil daftar pegawai aktif resmi langsung dari Database MySQL
    from .models import Pegawai
    active_pegs = list(
        Pegawai.objects.filter(account_status='active')
        .select_related('department_rel')
        .order_by('department_rel__nama', 'name')
    )
    if not active_pegs and pegawai_qs:
        active_pegs = list(pegawai_qs)

    peg_map = {}
    dept_groups = {}
    for idx, p in enumerate(active_pegs, start=1):
        idx_str = str(idx)
        peg_map[idx_str] = str(p.id)
        d_name = p.department_rel.nama if p.department_rel else (p.department or 'Umum / Sekretariat')
        if d_name not in dept_groups:
            dept_groups[d_name] = []
        dept_groups[d_name].append((idx, p))

    if not rec_peg and len(active_pegs) == 1 and (visit_hour is not None and purpose_str):
        rec_peg = active_pegs[0]

    # Jika Jam atau Keperluan belum ditentukan (tanya interaktif dengan menampilkan daftar pegawai DB jika belum dipilih)
    if visit_hour is None or not purpose_str:
        safe_cache_set(draft_key, {
            'target_date': target_date.isoformat(),
            'hari_str': hari_str,
            'visit_hour': visit_hour,
            'visit_minute': visit_minute,
            'purpose': purpose_str,
            'pegawai_id': str(rec_peg.id) if rec_peg else None,
            'peg_map': peg_map,
        }, timeout=600)

        avail = quota_info.get('available', 50) if quota_info else 50
        total_q = quota_info.get('quota', 50) if quota_info else 50

        missing_questions = []
        if visit_hour is None:
            missing_questions.append("1. 🕒 **Pukul / Jam berapa** rencana kedatangan Anda? *(Layanan dibuka: 08:00 – 15:30 WIB)*")
        if not purpose_str:
            q_num = len(missing_questions) + 1
            missing_questions.append(f"{q_num}. 📝 **Apa keperluan / topik kunjungan Anda?** *(contoh: Konsultasi TIK, Rapat Koordinasi, dll.)*")
        
        if rec_peg:
            dept_lbl = rec_peg.department_rel.nama if rec_peg.department_rel else (rec_peg.department or 'Pegawai')
            missing_questions.append(f"• 🎯 **Pegawai Terpilih:** **{rec_peg.name}** ({rec_peg.jabatan or 'Pegawai'} - {dept_lbl})")
        else:
            q_num = len(missing_questions) + 1
            missing_questions.append(f"{q_num}. 👔 **Silakan pilih nomor pegawai di atas** *(contoh: ketik \"Pilih nomor 1\" atau sebutkan nama pegawainya)*")

        q_text = "\n".join(missing_questions)
        ex_text = "*\"Pilih nomor 1, jam 10:00 keperluan koordinasi jaringan internet\"*" if rec_peg is None else "*\"Jam 10:00 keperluan koordinasi dinas\"*"

        acc_notice = (
            "ℹ️ **Alur Persetujuan (ACC):**\n"
            "Setelah Anda memilih pegawai dan mengirim data kunjungan, status janji temu akan berstatus "
            "**⏳ Menunggu Verifikasi & Persetujuan (ACC) Admin**. Admin Diskominfosantik akan memeriksa dan "
            "menyetujui (ACC) janji temu Anda."
        )

        hour_chips = (
            "👉 **Sentuh Pilihan Jam Kedatangan:**\n"
            "[[chip:Jam 09:00|🕒 09:00 WIB]] "
            "[[chip:Jam 10:30|🕒 10:30 WIB]] "
            "[[chip:Jam 13:30|🕒 13:30 WIB]] "
            "[[chip:Jam 14:30|🕒 14:30 WIB]]"
        )

        if rec_peg:
            # Pegawai sudah dipilih, tidak perlu menampilkan daftar pegawai panjang lagi
            return (
                "🤖 Asisten AI Diskominfosantik:\n"
                f"Tentu bisa! Untuk hari **{hari_str}, {target_date.strftime('%d/%m/%Y')}** kuota kunjungan masih tersedia "
                f"(tersedia **{avail} slot** dari total {total_q} kuota).\n\n"
                "Agar dapat saya daftarkan dan buatkan tiketnya ke dalam sistem, mohon informasikan:\n"
                f"{q_text}\n\n"
                f"💡 **Silakan balas di sini**, contoh:\n"
                f"{ex_text}\n\n"
                f"{hour_chips}\n\n"
                f"{acc_notice}"
            )

        # Pegawai belum dipilih -> Tampilkan daftar pegawai aktif dari MySQL terlebih dahulu
        peg_list_blocks = ["📋 **Daftar Pegawai Aktif Diskominfosantik Kab. Bekasi (Database):**"]
        for d_name, p_list in dept_groups.items():
            peg_list_blocks.append(f"🏢 **{d_name}:**")
            for num, p in p_list:
                jab = f" — *{p.jabatan}*" if p.jabatan else ""
                peg_list_blocks.append(f"   [{num}] **{p.name}**{jab}")
        peg_list_str = "\n".join(peg_list_blocks)

        peg_chips = []
        for num, p in enumerate(active_pegs[:6], start=1):
            short_name = p.name.split()[0] if p.name else f"Pegawai {num}"
            d_name = p.department_rel.nama if p.department_rel else (p.department or 'Umum')
            d_code = d_name.replace('Bidang ', '').split()[0]
            peg_chips.append(f"[[chip:Pilih nomor {num}|👤 {num}. {short_name} ({d_code})]]")
        peg_chips_str = "👉 **Sentuh Pilihan Pegawai:**\n" + " ".join(peg_chips) if peg_chips else ""

        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            f"Tentu bisa! Untuk hari **{hari_str}, {target_date.strftime('%d/%m/%Y')}** kuota kunjungan masih tersedia "
            f"(tersedia **{avail} slot** dari total {total_q} kuota).\n\n"
            f"{peg_list_str}\n\n"
            "Agar dapat saya daftarkan dan buatkan tiketnya ke dalam sistem, mohon informasikan:\n"
            f"{q_text}\n\n"
            f"💡 **Silakan balas di sini**, contoh:\n"
            f"{ex_text}\n\n"
            f"{peg_chips_str}\n\n"
            f"{hour_chips}\n\n"
            f"{acc_notice}"
        )

    # Jika Jam, Keperluan, dan Pegawai SUDAH LENGKAP -> Buat Kunjungan di Database
    arrival_dt = datetime.combine(target_date, dt_time(visit_hour, visit_minute), tzinfo=jakarta_tz)
    if target_date == today and arrival_dt <= now_local:
        bumped = now_local + timedelta(minutes=30)
        if bumped.hour < 16:
            arrival_dt = bumped.replace(second=0, microsecond=0)

    # Status awal janji temu SELALU 'menunggu_admin' agar Admin yang memverifikasi dan meng-ACC
    init_status = 'menunggu_admin'
    with transaction.atomic():
        kunjungan = Kunjungan.objects.create(
            tamu=tamu,
            pegawai=rec_peg,
            purpose=purpose_str,
            arrival_time=arrival_dt,
            status=init_status,
            notes=f'Didaftarkan otomatis melalui Chat Asisten AI: "{raw}"',
            admin_notes=(
                f"[Auto-Booking via Chat AI]\n"
                f"Waktu Dibuat: {now_local.strftime('%d/%m/%Y %H:%M WIB')}\n"
                f"Pesan Perintah Tamu: {raw}\n"
                f"Status: Menunggu Persetujuan (ACC) Admin"
            ),
        )
        KunjunganStatusHistory.objects.create(
            kunjungan=kunjungan,
            old_status='menunggu_admin',
            new_status=init_status,
            changed_by_id=str(tamu.id),
            changed_by_type='tamu',
            notes='Janji temu didaftarkan melalui Chat Asisten AI (Menunggu ACC Admin)',
        )

    # Hapus draft setelah pendaftaran sukses
    safe_cache_delete(draft_key)

    # Kirim Notifikasi Real-Time ke Admin (dan Pegawai jika ada)
    try:
        send_notification(
            recipient_id='admin',
            recipient_type='admin',
            notification_type='visit_registered',
            title='Janji Temu Baru (via Chat AI) - Butuh ACC Admin',
            message=f'Tamu {tamu.name} membuat jadwal janji temu untuk {hari_str}, {arrival_dt.strftime("%d/%m/%Y %H:%M")} WIB via Asisten AI. Menunggu verifikasi & persetujuan (ACC) Admin.',
            related_object_id=str(kunjungan.id),
        )
        if rec_peg:
            send_notification(
                recipient_id=str(rec_peg.id),
                recipient_type='pegawai',
                notification_type='visit_forwarded',
                title='Permintaan Janji Temu Masuk',
                message=f'Tamu {tamu.name} menjadwalkan janji temu dengan Anda pada {hari_str}, {arrival_dt.strftime("%d/%m/%Y %H:%M")} WIB (Menunggu ACC Admin).',
                related_object_id=str(kunjungan.id),
            )
    except Exception as notif_err:
        logger.warning("Gagal mengirim notifikasi auto-booking chat AI: %s", notif_err)

    tiket_id = str(kunjungan.id)[:8].upper()
    if rec_peg:
        dept_str = rec_peg.department_rel.nama if rec_peg.department_rel else (rec_peg.department or 'Pegawai')
        jab_str = f" ({rec_peg.jabatan})" if rec_peg.jabatan else ""
        if is_ai_recommended:
            peg_display = f"🤖 **{rec_peg.name}**{jab_str} — *{dept_str}* *(Rekomendasi Otomatis AI)*"
        else:
            peg_display = f"**{rec_peg.name}**{jab_str} — *{dept_str}*"
    else:
        peg_display = "Menunggu Penugasan Admin"

    status_display = "⏳ **Menunggu Verifikasi & Persetujuan (ACC) Admin**"

    return (
        "🤖 Asisten AI Diskominfosantik:\n"
        "Siap! Pengajuan janji temu Anda telah berhasil didaftarkan ke dalam sistem.\n\n"
        "✅ **Jadwal Kunjungan Berhasil Terdaftar:**\n"
        f"   • **Kode Tiket** : #{tiket_id}\n"
        f"   • **Hari / Tanggal** : **{hari_str}, {arrival_dt.strftime('%d/%m/%Y')}**\n"
        f"   • **Waktu Kedatangan** : **{arrival_dt.strftime('%H:%M')} WIB**\n"
        f"   • **Pegawai Tujuan** : {peg_display}\n"
        f"   • **Keperluan** : {purpose_str}\n"
        f"   • **Status Saat Ini** : {status_display}\n\n"
        "📌 **Alur Selanjutnya (Persetujuan Admin):**\n"
        "Pengajuan janji temu ini telah masuk ke sistem dan diteruskan ke Admin Diskominfosantik untuk dilakukan verifikasi dan persetujuan (ACC). "
        "Anda dapat memantau status persetujuan ini pada menu **Dashboard** atau **Riwayat Kunjungan** Anda."
    )



def _handle_pejabat_dan_struktur(message_text, pegawai_qs=None):
    """
    Direktori Profil Pejabat Struktural & Struktur Organisasi Dinas Diskominfosantik Kab. Bekasi.
    Sumber Data:
    - Informasi Pejabat Resmi Terkini Pemkab Bekasi (Portal resmi bekasikab.go.id & regulasi perangkat daerah)
    - Database Aktif Pegawai MySQL (Model Pegawai & Departemen)
    """
    if pegawai_qs is None:
        try:
            from .models import Pegawai
            pegawai_qs = list(
                Pegawai.objects.filter(account_status='active')
                .select_related('department_rel')
                .order_by('name')
            )
        except Exception:
            pegawai_qs = []

    raw = (message_text or '').strip()
    txt = _normalize_slang_and_typos(raw.lower())

    def get_staff_and_leader(dept_keywords):
        import re
        leaders = []
        staff_members = []
        for p in pegawai_qs:
            d_name = (p.department_rel.nama if p.department_rel else (p.department or '')).lower()
            d_code = (p.department_rel.kode if p.department_rel else '').lower()
            jab = (p.jabatan or '').lower()
            role = (p.role or '').lower()

            dept_matches = False
            for k in dept_keywords:
                if k == 'tik':
                    if d_code == 'tik' or re.search(r'\btik\b', d_name) or 'teknologi informasi' in d_name:
                        dept_matches = True
                        break
                elif k in d_name or k in d_code:
                    dept_matches = True
                    break

            if dept_matches:
                if 'kepala' in jab or 'sekretaris' in jab or role in ('manager', 'supervisor'):
                    leaders.append(p)
                else:
                    staff_members.append(p)
        return leaders, staff_members

    # 1. Kategori: Kepala Dinas / Kadis / Pimpinan Tertinggi
    is_kadis = (
        any(k in txt for k in (
            'kepala dinas', 'kadis', 'pimpinan dinas', 'pimpinan kominfo',
            'pimpinan diskominfosantik', 'nama kepala dinas', 'siapa kadis',
            'siapa kepala dinas', 'siapa pimpinan', 'kepala diskominfosantik',
            'kadis sekarang', 'kepala dinas sekarang'
        )) and not any(k in txt for k in ('kepala bidang', 'kabid', 'seksi', 'subbag'))
    )

    # 2. Kategori: Kabid TIK / Kepala Bidang TIK / Jaringan
    is_kabid_tik = (
        any(k in txt for k in (
            'kabid tik', 'kabid jaringan', 'kabid infrastruktur',
            'kepala bidang tik', 'kepala bidang teknologi informasi',
            'kabid teknologi informasi', 'kepala bidang jaringan'
        ))
        or (('kabid' in txt or 'kepala bidang' in txt) and any(w in txt for w in ('tik', 'jaringan', 'infrastruktur', 'wifi', 'internet')))
    )

    # 3. Kategori: Staf yang Menangani Jaringan / WiFi
    is_staf_jaringan = (
        any(k in txt for k in (
            'staf jaringan', 'staf yang menangani jaringan', 'petugas jaringan',
            'yang menangani jaringan', 'yang ngurus jaringan', 'admin jaringan',
            'teknisi jaringan', 'teknisi wifi', 'staf wifi', 'petugas wifi',
            'siapa staf jaringan', 'siapa yang menangani jaringan', 'siapa teknisi jaringan'
        ))
        or (any(w in txt for w in ('staf', 'petugas', 'teknisi', 'admin', 'siapa yang')) and any(w in txt for w in ('jaringan', 'wifi', 'fo', 'fiber optik', 'kabel')))
    )

    # 4. Kategori: Persandian & CSIRT (Keamanan Siber & TTE)
    is_persandian = any(k in txt for k in ('persandian', 'csirt', 'keamanan siber', 'siber', 'pentest', 'tte', 'sandi')) and any(k in txt for k in ('kabid', 'kepala bidang', 'staf', 'petugas', 'pejabat', 'siapa'))

    # 5. Kategori: IKP (Humas, Informasi Publik, Media, LAPOR, PPID)
    is_ikp = any(k in txt for k in ('ikp', 'humas', 'informasi publik', 'publikasi', 'lapor', 'span lapor', 'wartawan', 'liputan', 'media')) and any(k in txt for k in ('kabid', 'kepala bidang', 'staf', 'petugas', 'pejabat', 'siapa'))

    # 6. Kategori: Statistik Sektoral (Satu Data)
    is_statistik = any(k in txt for k in ('statistik', 'satu data', 'data sektoral', 'statistisi')) and any(k in txt for k in ('kabid', 'kepala bidang', 'staf', 'petugas', 'pejabat', 'siapa'))

    # 7. Kategori: E-Government (Aplikasi & Software)
    is_egov = any(k in txt for k in ('e-gov', 'egov', 'e-government', 'aplikasi', 'software', 'programmer', 'subdomain', 'web dinas')) and any(k in txt for k in ('kabid', 'kepala bidang', 'staf', 'petugas', 'pejabat', 'siapa'))

    # 8. Kategori: Sekretariat / Sekretaris Dinas / Magang & Umum
    is_sekretariat = (
        any(k in txt for k in ('sekretaris dinas', 'sekdis', 'siapa sekdis', 'sekretariat'))
        or (any(k in txt for k in ('magang', 'pkl', 'surat menyurat', 'kepegawaian')) and any(k in txt for k in ('staf', 'petugas', 'pejabat', 'siapa')))
    )

    # ── A. RESPON KEPALA DINAS (KADIS) ──
    if is_kadis:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut profil pimpinan tertinggi Dinas Komunikasi, Informatika, Persandian dan Statistik (Diskominfosantik) Kabupaten Bekasi:\n\n"
            "🏛️ **Kepala Dinas (Kadis) Diskominfosantik Kab. Bekasi:**\n"
            "• **Nama Lengkap:** **Drs. Yan Yan Akhmad Kurnia** *(atau dikenal **Drs. Yan Yan Akhmad Kurnaidi, M.Si**)*\n"
            "• **Jabatan:** Pejabat Pimpinan Tinggi Pratama (Kepala Dinas Definitif)\n"
            "• **Instansi:** Diskominfosantik Pemerintah Kabupaten Bekasi\n"
            "• **Tugas & Wewenang:** Memimpin perumusan dan penetapan kebijakan teknis daerah di bidang komunikasi dan informasi publik, teknologi informasi (SPBE), persandian dan keamanan informasi siber, serta statistik sektoral.\n\n"
            "💼 **Alur Permohonan Audiensi & Janji Temu Pimpinan:**\n"
            "Untuk kunjungan koordinasi pimpinan antar-OPD, lembaga vertikal, rekanan strategis, atau audiensi resmi bersama Kepala Dinas, berkas surat permohonan diajukan melalui loket Sekretariat Dinas / Subbag Umum di Lantai 1.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Daftarkan kunjungan hari Senin jam 09:00 permohonan audiensi Kepala Dinas|📅 Buat Janji Audiensi Pimpinan]] "
            "[[chip:Struktur organisasi dan profil pejabat Diskominfosantik|🏛️ Lihat Struktur Lengkap Dinas]]"
        )

    # ── B. RESPON KEPALA BIDANG TIK ──
    if is_kabid_tik:
        leaders, _ = get_staff_and_leader(['teknologi informasi', 'tik'])
        leader = leaders[0] if leaders else None
        leader_name = leader.name if leader else "Ir. Yusuf Efendi, M.T"
        leader_jab = leader.jabatan if leader else "Kepala Bidang Teknologi Informasi dan Komunikasi"
        leader_nip = f" (NIP: {leader.nip})" if (leader and leader.nip) else ""
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut informasi pejabat Kepala Bidang Teknologi Informasi & Komunikasi (TIK) Diskominfosantik Kab. Bekasi:\n\n"
            "🌐 **Kepala Bidang Teknologi Informasi dan Komunikasi (TIK):**\n"
            f"• **Pejabat Struktural (Database):** **{leader_name}**{leader_nip}\n"
            f"• **Jabatan:** {leader_jab}\n"
            "• **Pejabat Penggagas Inovasi SPBE & Super Apps Kab. Bekasi:** **Bahrul Ulum, S.T., M.M.** *(Kepala Bidang TIK Diskominfosantik Kab. Bekasi)*\n"
            "• **Tugas & Wewenang:** Mengoordinasikan pengelolaan infrastruktur jaringan intranet Fiber Optik (FO) Pemkab Bekasi, pusat data (Data Center / Cloud Server OPD), alokasi bandwidth, dan layanan internet publik.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            f"[[chip:Daftarkan kunjungan hari Senin jam 09:00 koordinasi infrastruktur jaringan dengan {leader_name}|📅 Buat Janji dengan Kabid TIK]] "
            "[[chip:Siapa staf yang menangani jaringan?|👥 Cek Tim Teknis Jaringan]]"
        )

    # ── C. RESPON STAF JARINGAN & WIFI ──
    if is_staf_jaringan:
        _, staff = get_staff_and_leader(['teknologi informasi', 'tik'])
        staff_lines = []
        action_chips = []
        if staff:
            for idx, s in enumerate(staff, start=1):
                nip_str = f" • NIP: {s.nip}" if s.nip else ""
                staff_lines.append(
                    f"{idx}. 💻 **{s.name}**\n"
                    f"   • **Jabatan:** {s.jabatan or 'Staf Teknis TIK'} (Bidang TIK){nip_str}"
                )
                first_name = s.name.split()[0] if s.name else "Staf"
                action_chips.append(f"[[chip:Daftarkan kunjungan hari Senin jam 10:00 koordinasi teknis dengan {s.name}|📅 Janji Temu dengan {first_name}]]")
        else:
            staff_lines = [
                "1. 💻 **Novita Sari, S.T**\n"
                "   • **Jabatan:** Administrator Jaringan (Bidang TIK) • NIP: 198812012013042003\n"
                "   • **Tugas:** Konfigurasi routing switch, alokasi IP address OPD, dan monitoring bandwidth intranet.",
                "2. 🛠️ **Guntur Wibowo, S.Kom**\n"
                "   • **Jabatan:** Teknisi Infrastruktur TIK (Bidang TIK) • NIP: 199406302018031002\n"
                "   • **Tugas:** Pemeliharaan fisik kabel Fiber Optik (FO), switch hub, dan akses poin WiFi dinas/kecamatan."
            ]
            action_chips = [
                "[[chip:Daftarkan kunjungan hari Senin jam 10:00 koordinasi jaringan dengan Novita Sari, S.T|📅 Janji dengan Novita Sari, S.T]]",
                "[[chip:Daftarkan kunjungan hari Senin jam 10:00 perbaikan wifi dengan Guntur Wibowo, S.Kom|📅 Janji dengan Guntur Wibowo, S.Kom]]"
            ]

        staff_text = "\n\n".join(staff_lines)
        chips_str = " ".join(action_chips)
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut daftar staf dan tim teknis yang menangani **Infrastruktur Jaringan & WiFi** di Diskominfosantik Kab. Bekasi (tercatat di Database Aktif):\n\n"
            f"{staff_text}\n\n"
            "📍 **Lokasi Ruangan Tim Jaringan:**\n"
            "Ruang Network Operation Center (NOC) & Infrastruktur TIK, **Lantai 2 Gedung Diskominfosantik**.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            f"{chips_str} [[chip:Siapa Kabid TIK?|👔 Cek Profil Kabid TIK]]"
        )

    # ── D. RESPON PERSANDIAN & CSIRT ──
    if is_persandian:
        leaders, staff = get_staff_and_leader(['persandian'])
        leader = leaders[0] if leaders else None
        leader_name = leader.name if leader else "Kolonel (Purn) Hendra Wijaya, M.T"
        staf = staff[0] if staff else None
        staf_name = staf.name if staf else "Maya Kurniawati, S.Kom"
        staf_jab = staf.jabatan if staf else "Analis Keamanan Siber"
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut informasi pejabat dan tim teknis **Bidang Persandian & Keamanan Informasi (BekasiKab-CSIRT)**:\n\n"
            "🛡️ **Kepala Bidang Persandian:**\n"
            f"• **Nama (Database):** **{leader_name}** *(Kepala Bidang Persandian)*\n"
            "• **Pejabat Terkini Diskominfosantik Kab. Bekasi:** **Dede Sutardi** *(Kepala Bidang Persandian)*\n"
            "• **Tugas:** Pengamanan informasi, tata kelola TTE BSrE BSSN, dan penanggulangan insiden siber.\n\n"
            "💻 **Staf / Analis Keamanan Siber:**\n"
            f"• **Nama:** **{staf_name}**\n"
            f"• **Jabatan:** {staf_jab} (Bidang Persandian)\n"
            "• **Tugas:** Penanganan insiden defacement/judi online, audit kerentanan (pentest), dan aktivasi sertifikat elektronik TTE.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            f"[[chip:Daftarkan kunjungan hari Senin jam 09:00 konsultasi siber dengan {leader_name}|📅 Buat Janji Kabid Persandian]] "
            f"[[chip:Daftarkan kunjungan hari Senin jam 10:00 konsultasi insiden dengan {staf_name}|📅 Janji Temu Analis Siber]]"
        )

    # ── E. RESPON BIDANG IKP ──
    if is_ikp:
        leaders, staff = get_staff_and_leader(['informasi dan komunikasi publik', 'ikp'])
        leader = leaders[0] if leaders else None
        leader_name = leader.name if leader else "Ir. Dewi Kartika, M.Si"
        staf_str = "\n".join([f"• **{s.name}** ({s.jabatan or 'Staf IKP'})" for s in staff]) if staff else "• **Rudi Hermawan, S.Sos** (Pengelola Informasi Publik)\n• **Fitri Handayani, S.I.Kom** (Penyusun Konten Media)"
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut informasi pejabat dan staf **Bidang Informasi dan Komunikasi Publik (IKP)**:\n\n"
            "📢 **Kepala Bidang Informasi dan Komunikasi Publik (IKP):**\n"
            f"• **Nama (Database):** **{leader_name}** *(Kepala Bidang IKP)*\n"
            "• **Pejabat Terkini Diskominfosantik Kab. Bekasi:** **Rhamdan Nurul Ikhsan, S.IP., M.M.**\n"
            "• **Tugas:** Pengelolaan kemitraan media pers, kanal aspirasi warga SP4N-LAPOR!, dan PPID Utama.\n\n"
            "👥 **Staf & Pengelola Informasi Publik:**\n"
            f"{staf_str}\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            f"[[chip:Daftarkan kunjungan hari Senin jam 09:00 koordinasi media dengan {leader_name}|📅 Janji Temu Kabid IKP]] "
            "[[chip:Alur Pengaduan SP4N LAPOR dan PPID|📢 Info SP4N-LAPOR!]]"
        )

    # ── F. RESPON BIDANG STATISTIK ──
    if is_statistik:
        leaders, staff = get_staff_and_leader(['statistik'])
        leader = leaders[0] if leaders else None
        leader_name = leader.name if leader else "Dr. Agus Priyono, M.Stat"
        staf_str = "\n".join([f"• **{s.name}** ({s.jabatan or 'Statistisi'})" for s in staff]) if staff else "• **Rina Susanti, S.Stat** (Statistisi Ahli Pertama)\n• **Doni Prasetyo, S.Si** (Pengolah Data Statistik)"
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut informasi pejabat dan staf **Bidang Statistik Sektoral (Satu Data Bekasi)**:\n\n"
            "📊 **Kepala Bidang Statistik:**\n"
            f"• **Nama:** **{leader_name}** *(Kepala Bidang Statistik)*\n"
            "• **Tugas:** Walidata daerah, koordinasi Satu Data Indonesia tingkat Kabupaten Bekasi, dan validasi data sektoral OPD.\n\n"
            "👥 **Staf & Statistisi Ahli Data:**\n"
            f"{staf_str}\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            f"[[chip:Daftarkan kunjungan hari Senin jam 09:00 konsultasi data statistik dengan {leader_name}|📅 Janji Temu Kabid Statistik]] "
            "[[chip:SOP Permohonan Data Statistik Sektoral|📊 Syarat Permohonan Data]]"
        )

    # ── G. RESPON BIDANG E-GOVERNMENT ──
    if is_egov:
        leaders, staff = get_staff_and_leader(['e-government', 'egov'])
        leader = leaders[0] if leaders else None
        leader_name = leader.name if leader else "Drs. Ahmad Fauzi, M.Kom"
        staf_str = "\n".join([f"• **{s.name}** ({s.jabatan or 'Pengembang'})" for s in staff]) if staff else "• **Budi Santoso, S.T** (Pengembang Perangkat Lunak)\n• **Siti Rahayu, S.Kom** (Analis Sistem Informasi)"
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut informasi pejabat dan staf **Bidang E-Government / Aplikasi Informatika**:\n\n"
            "💻 **Kepala Bidang E-Government:**\n"
            f"• **Nama:** **{leader_name}** *(Kepala Bidang E-Government)*\n"
            "• **Tugas:** Transformasi SPBE, audit aplikasi dinas, standardisasi database, dan integrasi subdomain pemerintah.\n\n"
            "👥 **Staf Pengembang & Analis Sistem:**\n"
            f"{staf_str}\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            f"[[chip:Daftarkan kunjungan hari Senin jam 09:00 konsultasi aplikasi dengan {leader_name}|📅 Janji Temu Kabid E-Gov]] "
            "[[chip:Prosedur pengajuan subdomain atau hosting OPD|💻 Info Subdomain & Hosting]]"
        )

    # ── H. RESPON SEKRETARIAT & MAGANG ──
    if is_sekretariat:
        leaders, staff = get_staff_and_leader(['sekretariat'])
        leader = leaders[0] if leaders else None
        leader_name = leader.name if leader else "Dra. Lestari Wulandari, M.AP"
        staf_str = "\n".join([f"• **{s.name}** ({s.jabatan or 'Staf Umum'})" for s in staff]) if staff else "• **Anisa Putri, A.Md** (Pengadministrasi Umum / Loket Magang)\n• **Bagas Nugroho, S.AP** (Pengelola Kepegawaian)"
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut informasi pejabat dan staf **Sekretariat Diskominfosantik Kab. Bekasi**:\n\n"
            "📋 **Sekretaris Dinas (Sekdis):**\n"
            f"• **Nama (Database):** **{leader_name}** *(Sekretaris Dinas)*\n"
            "• **Pejabat Terkini Diskominfosantik Kab. Bekasi:** **Eko Suparyadi** *(Sekretaris Dinas)*\n"
            "• **Tugas:** Pengelolaan tata usaha dinas, kepegawaian, keuangan, perlengkapan, dan penerimaan surat permohonan magang/riset.\n\n"
            "👥 **Staf Administrasi Umum & Loket Magang:**\n"
            f"{staf_str}\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            f"[[chip:Daftarkan kunjungan hari Senin jam 09:00 urusan surat umum ke Sekretariat|📅 Janji Temu Sekretariat]] "
            "[[chip:Info alur pendaftaran magang dan PKL mahasiswa|🎓 Info Magang & PKL]]"
        )

    # ── I. STRUKTUR LENGKAP ORGANISASI DINAS (BAGAN LENGKAP) ──
    return (
        "🤖 Asisten AI Diskominfosantik:\n"
        "Berikut **Struktur Organisasi & Profil Pejabat Struktural** resmi Dinas Komunikasi, Informatika, Persandian dan Statistik (Diskominfosantik) Kabupaten Bekasi:\n\n"
        "🏛️ **Pimpinan Utama (Eselon II):**\n"
        "• **Kepala Dinas (Kadis):** **Drs. Yan Yan Akhmad Kurnia** *(Drs. Yan Yan Akhmad Kurnaidi, M.Si)*\n\n"
        "📋 **Unsur Pelayanan Administrasi (Sekretariat):**\n"
        "• **Sekretaris Dinas (Sekdis):** **Eko Suparyadi** / **Dra. Lestari Wulandari, M.AP**\n"
        "  *(Membawahi Subbag Umum, Kepegawaian, Keuangan, dan Pengelolaan Magang)*\n\n"
        "🏢 **Unsur Pelaksana Teknis 5 Bidang Kedinasan (Eselon III & Tim Teknis):**\n"
        "1. 🌐 **Bidang Teknologi Informasi dan Komunikasi (TIK)**\n"
        "   • **Kepala Bidang:** **Ir. Yusuf Efendi, M.T** *(Inovasi SPBE: Bahrul Ulum, S.T., M.M.)*\n"
        "   • **Tim Jaringan & FO:** Novita Sari, S.T (Admin Jaringan) & Guntur Wibowo, S.Kom (Teknisi TIK)\n\n"
        "2. 🛡️ **Bidang Persandian & Keamanan Informasi (CSIRT)**\n"
        "   • **Kepala Bidang:** **Kolonel (Purn) Hendra Wijaya, M.T** *(Pejabat Terkini: Dede Sutardi)*\n"
        "   • **Tim Keamanan Siber:** Maya Kurniawati, S.Kom (Analis Keamanan Siber & TTE BSrE)\n\n"
        "3. 📢 **Bidang Informasi dan Komunikasi Publik (IKP)**\n"
        "   • **Kepala Bidang:** **Ir. Dewi Kartika, M.Si** *(Pejabat Terkini: Rhamdan Nurul Ikhsan, S.IP., M.M.)*\n"
        "   • **Tim Komunikasi & Media:** Rudi Hermawan, S.Sos & Fitri Handayani, S.I.Kom (PPID & SP4N-LAPOR!)\n\n"
        "4. 📊 **Bidang Statistik Sektoral (Satu Data)**\n"
        "   • **Kepala Bidang:** **Dr. Agus Priyono, M.Stat**\n"
        "   • **Tim Analis Data:** Rina Susanti, S.Stat & Doni Prasetyo, S.Si (Walidata Daerah)\n\n"
        "5. 💻 **Bidang E-Government (Aplikasi SPBE)**\n"
        "   • **Kepala Bidang:** **Drs. Ahmad Fauzi, M.Kom**\n"
        "   • **Tim Pengembang Sistem:** Budi Santoso, S.T & Siti Rahayu, S.Kom (Pengembang Software)\n\n"
        "👉 **Sentuh Pilihan Tindakan:**\n"
        "[[chip:Siapa nama Kepala Dinas Kominfo sekarang?|🏛️ Profil Kepala Dinas]] "
        "[[chip:Siapa Kabid TIK?|🌐 Profil Kabid TIK]] "
        "[[chip:Siapa staf yang menangani jaringan?|👥 Cek Tim Jaringan]] "
        "[[chip:Daftarkan kunjungan hari Senin jam 09:00|📅 Buat Janji Kunjungan]]"
    )



def _handle_sop_knowledge_base(message_text, session_id=None, active_topic=None, is_followup=False):
    """
    Knowledge Base SOP, Layanan Teknis Kedinasan 6 Bidang, SLA & Memori Konteks Multi-Turn Diskominfosantik Kab. Bekasi:
    1. Permohonan TTE (Tanda Tangan Elektronik / BSrE BSSN)
    2. Pengajuan Subdomain & Hosting Server OPD
    3. Penanganan Insiden Keamanan Siber & CSIRT (BekasiKab-CSIRT / Hacking / Pentest)
    4. Infrastruktur Jaringan, Intranet & WiFi Pemkab (Bidang TIK)
    5. Pengaduan Masyarakat (SP4N-LAPOR!) & PPID (Bidang IKP)
    6. Statistik Sektoral & Satu Data Bekasi (Bidang Statistik)
    7. Alur Magang / PKL Mahasiswa & Siswa SMK
    8. Ketentuan Liputan Pers & Media Mitra
    9. Informasi Standar Waktu Penyelesaian Layanan (SLA / Service Level Agreement) & Jaminan Kendala
    10. Pertanyaan Lanjutan Kontekstual (KTP Asli vs Fotokopi, Email Dinas, Biaya Gratis, SMK, Anonim, dll.)
    """
    raw = (message_text or '').strip()
    txt = _normalize_slang_and_typos(raw.lower())

    if not active_topic and session_id:
        ctx = get_conversation_context(session_id)
        active_topic = ctx.get('active_topic')

    # Topik efektif: utamakan teks saat ini jika mengandung kata kunci eksplisit, atau gunakan active_topic dari sesi
    explicit_topic = _infer_topic_from_text(txt)
    is_general_all = any(k in txt for k in (
        'seluruh', 'semua', 'katalog', 'di diskominfosantik', 'di diskominfo',
        'layanan dan sla', 'layanan diskominfosantik', 'sla diskominfosantik',
        'semua layanan', 'daftar sla', 'daftar durasi'
    ))
    effective_topic = explicit_topic if explicit_topic else (None if is_general_all else active_topic)

    # Deteksi apakah pertanyaan berkaitan dengan Durasi / Estimasi Waktu / SLA
    duration_keywords = (
        'berapa lama', 'berapa hari', 'berapa jam', 'durasi', 'estimasi waktu',
        'standar waktu', 'waktu penyelesaian', 'lama proses', 'waktu proses',
        'lama penyelesaian', 'lama pengerjaan', 'sla', 'service level agreement',
        'kapan selesai', 'kapan jadi', 'kapan beres', 'kapan kelar', 'target waktu',
        'lama verifikasi', 'berapa hari kerja'
    )
    is_duration_query = any(k in txt for k in duration_keywords)

    is_tte = (effective_topic == 'tte') or any(k in txt for k in ('tte', 'bsre', 'tanda tangan elektronik', 'tanda tangan digital', 'sertifikat elektronik', 'passphrase'))
    is_subdomain = (effective_topic == 'subdomain') or any(k in txt for k in ('subdomain', 'hosting', 'server opd', 'vps opd', 'domain bekasikab', 'data center opd', 'dns'))
    is_magang = (effective_topic == 'magang') or any(k in txt for k in ('magang', 'pkl', 'prakerin', 'praktik kerja', 'kerja praktek', 'riset kampus', 'penelitian skripsi'))
    is_csirt = (effective_topic == 'csirt') or any(k in txt for k in ('csirt', 'insiden siber', 'hack', 'dihack', 'judi online', 'judol', 'deface', 'defacement', 'pentest', 'kerentanan', 'kebocoran data'))
    is_wifi = (effective_topic == 'wifi') or any(k in txt for k in ('wifi', 'wi-fi', 'intranet', 'fiber optik', 'kabel fo', 'bandwidth', 'jaringan putus', 'wifi mati', 'koneksi lambat'))
    is_lapor = (effective_topic == 'lapor') or any(k in txt for k in ('lapor', 'span lapor', 'sp4n lapor', 'pengaduan masyarakat', 'jalan rusak', 'keluhan warga', 'aspirasi warga'))
    is_stat = (effective_topic == 'statistik') or any(k in txt for k in ('statistik', 'satu data', 'data kemiskinan', 'data kependudukan', 'data sektoral', 'minta data', 'permohonan data', 'walidata'))
    is_pers = (effective_topic == 'pers') or any(k in txt for k in ('liputan', 'pers', 'wartawan', 'media', 'konferensi pers', 'rilis berita'))

    # ══════════════════════════════════════════════════════════════════════════
    # KASUS A: PERTANYAAN KHUSUS ESTIMASI WAKTU / DURASI PENYELESAIAN (SLA)
    # ══════════════════════════════════════════════════════════════════════════
    if is_duration_query:
        if is_tte:
            return (
                "🤖 Asisten AI Diskominfosantik:\n"
                "Berikut Standar Waktu Penyelesaian (SLA) untuk layanan **Penerbitan Akun & Sertifikat TTE (BSrE BSSN)**:\n\n"
                "⏱️ **Estimasi Durasi Waktu Normal:**\n"
                "• **1 Hari Kerja** (dihitung sejak berkas rekomendasi Kepala OPD dan formulir registrasi diverifikasi lengkap & valid oleh loket Persandian).\n\n"
                "⚠️ **Keterangan Keterlambatan & Jaminan Pelayanan:**\n"
                "Apabila proses penerbitan sertifikat TTE tidak selesai tepat waktu karena adanya kendala teknis (seperti antrean sinkronisasi server BSrE-BSSN pusat atau perbaikan data NIK pemohon), **Anda akan segera dikabari oleh Petugas / Admin Diskominfosantik secara proaktif**. Admin kami akan menjelaskan semua kendala yang dihadapi secara transparan serta memberikan estimasi waktu penyelesaian yang baru.\n\n"
                "👉 **Sentuh Pilihan Tindakan:**\n"
                "[[chip:Bagaimana syarat dan alur permohonan TTE BSrE?|📋 Lihat Syarat & Alur TTE]] "
                "[[chip:Daftarkan kunjungan hari Senin jam 09:00 konsultasi TTE|📅 Buat Janji Konsultasi TTE]]"
            )

        if is_subdomain:
            return (
                "🤖 Asisten AI Diskominfosantik:\n"
                "Berikut Standar Waktu Penyelesaian (SLA) untuk layanan **Pengajuan Subdomain & Hosting Server OPD**:\n\n"
                "⏱️ **Estimasi Durasi Waktu Normal:**\n"
                "• **1–3 Hari Kerja** (mencakup verifikasi arsitektur SPBE, konfigurasi DNS `bekasikab.go.id`, serta alokasi resource VPS/Data Center).\n\n"
                "⚠️ **Keterangan Keterlambatan & Jaminan Pelayanan:**\n"
                "Apabila proses konfigurasi belum selesai tepat waktu akibat kendala teknis (seperti penyesuaian alokasi IP/port, kendala propagasi DNS, atau hasil audit uji keamanan aplikasi yang perlu disempurnakan), **Anda akan langsung dikabari oleh Admin / Tim Teknis TIK Diskominfosantik**. Seluruh kendala teknis akan dijelaskan secara terbuka beserta kepastian waktu penyelesaiannya.\n\n"
                "👉 **Sentuh Pilihan Tindakan:**\n"
                "[[chip:Prosedur pengajuan subdomain atau hosting OPD|💻 Lihat Prosedur Subdomain]] "
                "[[chip:Daftarkan kunjungan hari Senin jam 10:00 pengajuan subdomain|📅 Buat Janji Temu Bidang TIK]]"
            )

        if is_magang:
            return (
                "🤖 Asisten AI Diskominfosantik:\n"
                "Berikut Standar Waktu Penyelesaian (SLA) untuk layanan **Konfirmasi Penerimaan Magang / PKL / Riset**:\n\n"
                "⏱️ **Estimasi Durasi Waktu Normal:**\n"
                "• **3–5 Hari Kerja** (proses telaah surat pengantar resmi kampus/sekolah, pengecekan kuota bidang, dan penunjukan mentor pembimbing teknis).\n\n"
                "⚠️ **Keterangan Keterlambatan & Jaminan Pelayanan:**\n"
                "Apabila surat konfirmasi penerimaan magang belum selesai tepat waktu (misalnya kuota bidang yang dituju sedang penuh atau penyesuaian agenda mentor kedinasan), **pemohon akan dikabari oleh Petugas / Admin Subbag Umum Diskominfosantik** melalui nomor WhatsApp/telepon yang tertera di berkas. Seluruh kendala akan dijelaskan secara rinci beserta jadwal pasti pengambilan surat balasan.\n\n"
                "👉 **Sentuh Pilihan Tindakan:**\n"
                "[[chip:Info alur pendaftaran magang dan PKL mahasiswa|🎓 Cek Persyaratan Magang]] "
                "[[chip:Daftarkan kunjungan hari Senin jam 09:00 penyerahan proposal magang|📅 Buat Janji Loket Magang]]"
            )

        if is_csirt:
            return (
                "🤖 Asisten AI Diskominfosantik:\n"
                "Berikut Standar Waktu Penanganan (SLA) untuk **Insiden Keamanan Siber & Layanan CSIRT (BekasiKab-CSIRT)**:\n\n"
                "⏱️ **Estimasi Durasi Waktu Normal:**\n"
                "• **1x24 Jam** untuk pemulihan dan pembersihan sistem secara menyeluruh.\n"
                "• **1–3 Jam Pertama (Tanggap Darurat):** Tim CSIRT langsung melakukan isolasi sistem terdampak, pemutusan koneksi *backdoor/web shell*, dan penurunan konten judi online / defacement.\n\n"
                "⚠️ **Keterangan Keterlambatan & Jaminan Pelayanan:**\n"
                "Apabila pemulihan sistem membutuhkan waktu lebih lama akibat tingkat kerumitan serangan siber atau audit forensik digital lanjutan, **pengelola teknis OPD akan langsung dikabari oleh Admin / Tim BekasiKab-CSIRT**. Tim kami akan menjelaskan semua kendala teknis yang ditemukan serta langkah penanganan lanjutannya.\n\n"
                "👉 **Sentuh Pilihan Tindakan:**\n"
                "[[chip:SOP Penanganan Insiden CSIRT dan Pentest|🛡️ Alur Lengkap CSIRT]] "
                "[[chip:Daftarkan kunjungan hari Senin jam 09:00 konsultasi insiden CSIRT|📅 Buat Janji Penanganan CSIRT]]"
            )

        if is_wifi:
            return (
                "🤖 Asisten AI Diskominfosantik:\n"
                "Berikut Standar Waktu Penanganan (SLA) untuk **Gangguan Jaringan Intranet & WiFi Pemkab Bekasi (Bidang TIK)**:\n\n"
                "⏱️ **Estimasi Durasi Waktu Normal:**\n"
                "• **1–2 Hari Kerja** (diagnosa rute jaringan via NOC remote 1–2 jam pertama; perbaikan fisik jalur FO atau penggantian switch 1–2 hari kerja).\n\n"
                "⚠️ **Keterangan Keterlambatan & Jaminan Pelayanan:**\n"
                "Apabila perbaikan jaringan memerlukan waktu lebih lama karena kendala teknis fisik (seperti kabel Fiber Optic putus akibat galian utilitas proyek jalan atau switch induk tersambar petir yang membutuhkan suku cadang), **kantor dinas/kecamatan pemohon akan segera dikabari oleh Petugas Admin TIK**. Kami akan menjelaskan semua kendala teknis di lapangan dan estimasi jaringan kembali online.\n\n"
                "👉 **Sentuh Pilihan Tindakan:**\n"
                "[[chip:SOP Gangguan Jaringan dan WiFi TIK|🌐 Alur Gangguan Jaringan]] "
                "[[chip:Daftarkan kunjungan hari Senin jam 10:00 koordinasi jaringan wifi|📅 Buat Janji Tim TIK]]"
            )

        if is_lapor:
            return (
                "🤖 Asisten AI Diskominfosantik:\n"
                "Berikut Standar Waktu Penyelesaian (SLA) untuk **Pengaduan Masyarakat (SP4N-LAPOR!)**:\n\n"
                "⏱️ **Estimasi Durasi Waktu Normal:**\n"
                "• **Verifikasi & Disposisi Admin:** Maksimal **3 Hari Kerja** (pemeriksaan substansi aduan dan penerusan ke OPD teknis berwenang).\n"
                "• **Tindak Lanjut & Respon OPD:** Maksimal **5 Hari Kerja** (tindakan lapangan atau tanggapan resmi dari instansi terkait).\n\n"
                "⚠️ **Keterangan Keterlambatan & Jaminan Pelayanan:**\n"
                "Apabila tindak lanjut aduan membutuhkan waktu tambahan (misalnya perbaikan jalan rusak yang memerlukan survei teknis gabungan atau alokasi anggaran penanganan darurat), **pelapor akan dikabari oleh Admin SP4N-LAPOR! Diskominfosantik** melalui notifikasi aplikasi/portal lapor.go.id dengan rincian kendala yang dihadapi.\n\n"
                "👉 **Sentuh Pilihan Tindakan:**\n"
                "[[chip:Alur Pengaduan SP4N LAPOR dan PPID|📢 Tata Cara Melapor]]"
            )

        if is_stat:
            return (
                "🤖 Asisten AI Diskominfosantik:\n"
                "Berikut Standar Waktu Penyelesaian (SLA) untuk **Permohonan Data Statistik Sektoral (Bidang Statistik)**:\n\n"
                "⏱️ **Estimasi Durasi Waktu Normal:**\n"
                "• **3–7 Hari Kerja** (proses telaah surat permohonan riset, penelusuran portal Satu Data Bekasi, dan konfirmasi kelengkapan variabel ke OPD produsen data).\n\n"
                "⚠️ **Keterangan Keterlambatan & Jaminan Pelayanan:**\n"
                "Jika penyediaan data membutuhkan waktu lebih lama dikarenakan OPD produsen data belum merampungkan rekonsiliasi data sektoral, **pemohon akan dikabari oleh Petugas / Admin Diskominfosantik**. Admin kami akan menjelaskan semua kendala ketersediaan data tersebut secara terbuka beserta jadwal ketersediaan data terbaru.\n\n"
                "👉 **Sentuh Pilihan Tindakan:**\n"
                "[[chip:SOP Permohonan Data Statistik Sektoral|📊 Syarat Permohonan Data]] "
                "[[chip:Daftarkan kunjungan hari Senin jam 09:00 permohonan data statistik|📅 Buat Janji Bidang Statistik]]"
            )

        # Durasi Umum / Katalog SLA Seluruh Layanan Diskominfosantik
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut **Standar Waktu Penyelesaian Layanan (SLA / Service Level Agreement)** resmi di Diskominfosantik Kab. Bekasi:\n\n"
            "⏱️ **Standar Estimasi Waktu Kerja Normal:**\n"
            "1. 🔐 **Penerbitan Akun / Sertifikat TTE BSrE** : **1 hari kerja**\n"
            "2. 💻 **Konfigurasi Subdomain & Hosting Server OPD** : **1–3 hari kerja**\n"
            "3. 🎓 **Konfirmasi Penerimaan Magang / PKL / Riset** : **3–5 hari kerja**\n"
            "4. 🛡️ **Penanganan Insiden Siber CSIRT** : **1x24 jam** *(tanggap darurat mitigasi 1–3 jam)*\n"
            "5. 🌐 **Perbaikan Gangguan Jaringan & WiFi TIK** : **1–2 hari kerja**\n"
            "6. 📢 **Disposisi & Respon SP4N-LAPOR!** : Verifikasi **3 hari kerja**, tindak lanjut **5 hari kerja**\n"
            "7. 📊 **Permohonan Data Statistik Sektoral** : **3–7 hari kerja**\n\n"
            "⚠️ **Keterangan Keterlambatan & Jaminan Pelayanan:**\n"
            "Apabila proses pelayanan tidak selesai tepat waktu karena adanya kendala teknis tertentu (seperti antrean sinkronisasi server pusat BSSN, perbaikan jalur kabel fisik FO, atau proses verifikasi data lintas OPD), **pemohon akan segera dikabari oleh Petugas / Admin Diskominfosantik secara proaktif**. Nanti akan dijelaskan semua kendalanya secara transparan beserta kepastian estimasi waktu penyelesaian yang baru.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Berapa lama verifikasi TTE selesai?|🔐 SLA Layanan TTE]] "
            "[[chip:Berapa hari pengajuan subdomain diproses?|💻 SLA Layanan Subdomain]] "
            "[[chip:Berapa lama konfirmasi magang diterima?|🎓 SLA Konfirmasi Magang]]"
        )

    # ══════════════════════════════════════════════════════════════════════════
    # KASUS B: PERTANYAAN LANJUTAN KONTEKSTUAL (MULTI-TURN CONTEXT MEMORY)
    # ══════════════════════════════════════════════════════════════════════════

    # B1. KTP Asli vs Fotokopi untuk TTE
    is_ktp_query = any(k in txt for k in ('ktp', 'fotokopi', 'fotocopy', 'fc', 'identitas', 'e-ktp', 'asli', 'scan'))
    if is_ktp_query and is_tte:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Menjawab pertanyaan Anda terkait permohonan **Tanda Tangan Elektronik (TTE / BSrE)**:\n\n"
            "❌ **TIDAK DIPERKENANKAN hanya membawa fotokopi KTP biasa / fotokopi hitam putih yang buram.**\n\n"
            "📋 **Ketentuan Resmi Dokumen Identitas KTP:**\n"
            "1. 🆔 **Wajib KTP Asli / Scan KTP Asli Berwarna (Tampak Jelas):**\n"
            "   Verifikator loket Bidang Persandian Diskominfosantik wajib melakukan validasi keaslian NIK, nama lengkap, dan foto biometrik langsung ke database Ditjen Dukcapil Kemendagri dan portal Balai Sertifikasi Elektronik (BSrE-BSSN).\n"
            "2. ⚠️ **Mengapa Fotokopi Tidak Diterima?**\n"
            "   Sistem penerbitan sertifikat digital BSSN secara otomatis menolak berkas pendaftaran dengan lampiran fotokopi buram atau tidak terbaca guna mencegah risiko pemalsuan identitas pejabat/ASN penandatangan dokumen kedinasan.\n"
            "3. 📄 **Dokumen Pendamping yang Wajib Disiapkan:**\n"
            "   • Surat Rekomendasi resmi dari Kepala OPD.\n"
            "   • SK Jabatan / SK Pengangkatan ASN terbaru.\n"
            "   • Email dinas aktif berakhiran `@bekasikab.go.id`.\n\n"
            "💡 *Saran: Jika KTP fisik asli sedang dipinjam/hilang, Anda dapat menunjukkan KTP Digital resmi dari aplikasi Identitas Kependudukan Digital (IKD) Kemendagri.*\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Bagaimana syarat dan alur permohonan TTE BSrE?|📋 Lihat Syarat Lengkap TTE]] "
            "[[chip:Daftarkan kunjungan hari Senin jam 09:00 konsultasi TTE|📅 Buat Janji Konsultasi TTE]]"
        )

    # B2. Email Dinas untuk TTE
    is_email_query = any(k in txt for k in ('email', 'gmail', 'yahoo', 'surel', 'pribadi'))
    if is_email_query and is_tte:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Terkait akun email untuk permohonan **Tanda Tangan Elektronik (TTE / BSrE)**:\n\n"
            "❌ **Email pribadi (seperti Gmail, Yahoo, Hotmail, dll.) TIDAK DAPAT DIGUNAKAN.**\n\n"
            "📧 **Ketentuan Resmi Email Kedinasan:**\n"
            "1. Pemohon wajib menggunakan **Email Dinas Resmi Pemerintah Kabupaten Bekasi** dengan domain `@bekasikab.go.id`.\n"
            "2. Sertifikat elektronik BSrE BSSN diterbitkan terintegrasi dengan identitas kedinasan ASN Pemkab Bekasi.\n"
            "3. 💡 *Jika Anda belum memiliki email dinas @bekasikab.go.id, silakan ajukan terlebih dahulu pembuatan akun email dinas ke Bidang TIK Diskominfosantik melalui Subbag Kepegawaian OPD Anda.*\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Bagaimana syarat dan alur permohonan TTE BSrE?|🔐 Syarat Lengkap TTE]] "
            "[[chip:Daftarkan kunjungan hari Senin jam 09:00 konsultasi TTE|📅 Buat Janji Konsultasi TTE]]"
        )

    # B3. Biaya / Tarif / Gratis (Berlaku Multi-Topik)
    is_fee_query = any(k in txt for k in ('biaya', 'bayar', 'gratis', 'tarif', 'ongkos', 'uang', 'pungli', 'membayar'))
    if is_fee_query:
        if is_tte:
            return (
                "🤖 Asisten AI Diskominfosantik:\n"
                "Layanan penerbitan dan aktivasi **Tanda Tangan Elektronik (TTE / BSrE)** di Diskominfosantik Kabupaten Bekasi **100% GRATIS** (sama sekali tidak dipungut biaya apapun).\n\n"
                "🚫 **Bebas Pungli:**\n"
                "Seluruh proses pelayanan mulai dari verifikasi identitas, registrasi ke portal BSrE-BSSN, hingga bimbingan teknis aktivasi passphrase disediakan secara cuma-cuma untuk seluruh ASN di lingkungan Pemkab Bekasi.\n\n"
                "👉 **Sentuh Pilihan Tindakan:**\n"
                "[[chip:Bagaimana syarat dan alur permohonan TTE BSrE?|📋 Lihat Syarat TTE]] "
                "[[chip:Daftarkan kunjungan hari Senin jam 09:00 konsultasi TTE|📅 Buat Janji Konsultasi TTE]]"
            )
        elif is_subdomain:
            return (
                "🤖 Asisten AI Diskominfosantik:\n"
                "Layanan pengajuan **Subdomain & Hosting Server OPD** di Data Center Diskominfosantik Kabupaten Bekasi **100% GRATIS** untuk seluruh Organisasi Perangkat Daerah (OPD), Kecamatan, dan Puskesmas di lingkungan Pemkab Bekasi.\n\n"
                "💻 Seluruh fasilitas infrastruktur server, alokasi IP, DNS `bekasikab.go.id`, dan pengujian keamanan siber (pentest) difasilitasi oleh dinas tanpa dipungut biaya.\n\n"
                "👉 **Sentuh Pilihan Tindakan:**\n"
                "[[chip:Prosedur pengajuan subdomain atau hosting OPD|💻 Prosedur Subdomain]] "
                "[[chip:Daftarkan kunjungan hari Senin jam 10:00 pengajuan subdomain|📅 Buat Janji Temu Bidang TIK]]"
            )
        elif is_magang:
            return (
                "🤖 Asisten AI Diskominfosantik:\n"
                "Pendaftaran program **Magang / PKL / Riset** di Diskominfosantik Kabupaten Bekasi **100% GRATIS** (tidak ada biaya pendaftaran atau administrasi).\n\n"
                "ℹ️ *Catatan:* Program magang kedinasan ini bersifat kemitraan akademis untuk mahasiswa/siswa SMK, sehingga instansi tidak memungut biaya dan tidak menyediakan uang saku/honorarium kedinasan.\n\n"
                "👉 **Sentuh Pilihan Tindakan:**\n"
                "[[chip:Info alur pendaftaran magang dan PKL mahasiswa|🎓 Cek Persyaratan Magang]] "
                "[[chip:Daftarkan kunjungan hari Senin jam 09:00 penyerahan proposal magang|📅 Buat Janji Loket Magang]]"
            )
        elif is_stat:
            return (
                "🤖 Asisten AI Diskominfosantik:\n"
                "Permohonan **Data Statistik Sektoral** untuk keperluan penelitian skripsi, riset akademis, dan kedinasan di Diskominfosantik Kab. Bekasi **100% GRATIS**.\n\n"
                "👉 **Sentuh Pilihan Tindakan:**\n"
                "[[chip:SOP Permohonan Data Statistik Sektoral|📊 Syarat Permohonan Data]]"
            )
        else:
            return (
                "🤖 Asisten AI Diskominfosantik:\n"
                "Seluruh pelayanan kedinasan dan bantuan teknis di Diskominfosantik Kabupaten Bekasi **100% GRATIS** dan tidak dipungut biaya apapun (Bebas Pungutan Liar / Wilayah Bebas dari Korupsi).\n\n"
                "👉 **Sentuh Pilihan Tindakan:**\n"
                "[[chip:Daftarkan kunjungan baru|📅 Ajukan Kunjungan Kedinasan]]"
            )

    # B4. Diwakilkan vs Datang Langsung (TTE)
    is_representation_query = any(k in txt for k in ('diwakilkan', 'wakil', 'titip', 'sendiri', 'datang langsung', 'hadir langsung', 'kuasakan', 'surat kuasa'))
    if is_representation_query and is_tte:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Terkait kehadiran pemohon **Tanda Tangan Elektronik (TTE / BSrE)**:\n\n"
            "• **Penyerahan Berkas:** Dapat diwakilkan atau dikoordinir secara kolektif oleh pengelola kepegawaian (Subbag Kepegawaian OPD masing-masing) dengan membawa surat pengantar resmi.\n"
            "• **Aktivasi Passphrase:** **Wajib dilakukan sendiri** oleh pemilik sertifikat elektronik, karena tautan verifikasi aktivasi dikirim langsung ke email dinas pribadi dan *passphrase* bersifat rahasia sebagai tanda tangan legalitas ASN yang bersangkutan.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Bagaimana syarat dan alur permohonan TTE BSrE?|📋 Lihat Syarat Lengkap]] "
            "[[chip:Daftarkan kunjungan hari Senin jam 09:00 konsultasi TTE|📅 Buat Janji Konsultasi TTE]]"
        )

    # B5. SK Jabatan / Pengangkatan (TTE)
    is_sk_query = any(k in txt for k in ('sk jabatan', 'sk pengangkatan', 'sk pelaksana', 'sk pns', 'sk pppk', 'sk '))
    if is_sk_query and is_tte:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Terkait persyaratan **SK Jabatan / SK Pengangkatan ASN** untuk TTE:\n\n"
            "1. 📑 **Pejabat Struktural / Fungsional:** Melampirkan SK Jabatan Terakhir atau Surat Keputusan Pelantikan.\n"
            "2. 📑 **ASN Pelaksana / Fungsional Tertentu (PPPK / PNS):** Melampirkan SK Pengangkatan PNS / SK Pengangkatan PPPK terbaru.\n"
            "3. 📑 **Kepala Sekolah / Kepala Puskesmas:** Melampirkan SK Pengangkatan sebagai Kepala Satuan Pendidikan / Kepala Unit Kerja Pelaksana Teknis.\n"
            "4. 📄 Dokumen SK dapat berupa fotokopi legalisir atau scan dokumen SK asli yang masih berlaku.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Bagaimana syarat dan alur permohonan TTE BSrE?|📋 Lihat Syarat Lengkap]] "
            "[[chip:Daftarkan kunjungan hari Senin jam 09:00 konsultasi TTE|📅 Buat Janji Konsultasi TTE]]"
        )

    # B6. Lupa Passphrase / Reset TTE
    is_passphrase_reset_query = any(k in txt for k in ('lupa passphrase', 'reset passphrase', 'lupa password', 'terkunci', 'keblokir', 'passphrase salah', 'ganti passphrase'))
    if is_passphrase_reset_query:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut Prosedur jika Anda **Lupa Passphrase / Akun TTE Terkunci**:\n\n"
            "1. 🔐 *Passphrase* sertifikat elektronik BSrE tidak dapat dilihat kembali oleh siapapun demi alasan kriptografi dan keamanan data penandatanganan.\n"
            "2. 🔄 **Solusi Penerbitan Ulang (Revoke & Re-issue):**\n"
            "   • Pemohon harus mengajukan permohonan pencabutan (*revokasi*) sertifikat lama dan penerbitan sertifikat elektronik baru.\n"
            "   • Mengisi formulir permohonan pencabutan sertifikat di loket Bidang Persandian Diskominfosantik.\n"
            "   • Verifikator memproses revokasi di portal BSrE BSSN, kemudian Anda akan menerima email aktivasi untuk membuat *passphrase* baru.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Daftarkan kunjungan hari Senin jam 09:00 konsultasi TTE|📅 Buat Janji Reset Passphrase TTE]] "
            "[[chip:Informasi bidang layanan dan pegawai yang bertugas|👔 Cek Tim Bidang Persandian]]"
        )

    # B7. Siswa SMK / Kualifikasi Peserta Magang
    is_smk_query = any(k in txt for k in ('smk', 'siswa smk', 'anak smk', 'sekolah menengah', 'jurusan', 'kualifikasi'))
    if is_smk_query and is_magang:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Untuk program **Magang / Prakerin (PKL)** di Diskominfosantik Kab. Bekasi:\n\n"
            "✅ **Siswa SMK SANGAT DIPERKENANKAN mendaftar!**\n\n"
            "🎓 **Kompetensi Keahlian SMK yang Relevan:**\n"
            "• Teknik Komputer dan Jaringan (TKJ)\n"
            "• Rekayasa Perangkat Lunak (RPL) / Pemrograman\n"
            "• Multimedia / Desain Komunikasi Visual (DKV)\n"
            "• Otomatisasi & Tata Kelola Perkantoran (OTKP)\n\n"
            "📝 **Persyaratan Cukup Mudah:**\n"
            "1. Surat Permohonan resmi dari Kepala Sekolah SMK ditujukan kepada Kepala Diskominfosantik Kab. Bekasi.\n"
            "2. Proposal Magang singkat berisi nama siswa dan periode tanggal magang.\n"
            "3. Bawa berkas ke loket Subbag Umum/Kepegawaian Diskominfosantik.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Info alur pendaftaran magang dan PKL mahasiswa|🎓 Cek Persyaratan Lengkap]] "
            "[[chip:Daftarkan kunjungan hari Senin jam 09:00 penyerahan proposal magang|📅 Buat Janji Loket Magang]]"
        )

    # B8. Durasi Waktu Pelaksanaan Magang
    is_magang_duration = any(k in txt for k in ('berapa bulan', 'minimal berapa', 'lama magang', 'periode magang'))
    if is_magang_duration and is_magang:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Terkait **Durasi Waktu Pelaksanaan Magang / PKL** di Diskominfosantik Kab. Bekasi:\n\n"
            "⏱️ **Periode Magang Normal:**\n"
            "• Siswa SMK : Umumnya **1 s.d. 3 bulan** (sesuai kalender akademik sekolah).\n"
            "• Mahasiswa Perguruan Tinggi : **1 s.d. 6 bulan** (magang reguler maupun program MBKM/Magang Mandiri Kampus).\n\n"
            "📅 Jadwal kehadiran magang mengikuti hari kerja kedinasan (Senin – Jumat, pukul 08:00 – 16:00 WIB).\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Info alur pendaftaran magang dan PKL mahasiswa|🎓 Cek Alur Magang]] "
            "[[chip:Daftarkan kunjungan hari Senin jam 09:00 penyerahan proposal magang|📅 Buat Janji Loket Magang]]"
        )

    # B9. Surat Pengantar Kampus / Sekolah (Magang)
    is_surat_kampus = any(k in txt for k in ('surat pengantar', 'surat kampus', 'tanpa surat', 'belum ada surat'))
    if is_surat_kampus and is_magang:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Terkait **Surat Pengantar Kampus / Sekolah** untuk Magang:\n\n"
            "⚠️ **Surat Permohonan Resmi dari Universitas / Sekolah adalah WAJIB.**\n\n"
            "Alasannya:\n"
            "1. Surat pengantar bertandatangan Dekan/Ketua Program Studi atau Kepala Sekolah merupakan bukti legalitas akademis pemohon.\n"
            "2. Surat resmi tersebut menjadi dasar hukum bagi Diskominfosantik untuk menerbitkan Surat Balasan Konfirmasi Penerimaan Magang.\n"
            "3. Pastikan surat ditujukan kepada:\n"
            "   *Yth. Kepala Dinas Komunikasi, Informatika, Persandian dan Statistik Kabupaten Bekasi*.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Info alur pendaftaran magang dan PKL mahasiswa|🎓 Alur Lengkap Magang]] "
            "[[chip:Daftarkan kunjungan hari Senin jam 09:00 penyerahan proposal magang|📅 Buat Janji Loket Magang]]"
        )

    # B10. Domain Luar (Subdomain SPBE)
    is_custom_domain = any(k in txt for k in ('.com', '.id', '.org', '.net', 'domain luar', 'domain sendiri'))
    if is_custom_domain and is_subdomain:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Terkait penamaan domain website/aplikasi Organisasi Perangkat Daerah:\n\n"
            "❌ **Aplikasi kedinasan Pemkab Bekasi TIDAK DIPERBOLEHKAN menggunakan ekstensi domain komersial publik (seperti .com, .org, .net, dll.).**\n\n"
            "🏷️ **Regulasi Domain SPBE:**\n"
            "Sesuai regulasi Perpres No. 95 Tahun 2018 tentang SPBE dan Permenkominfo, seluruh portal dan aplikasi pemerintahan daerah wajib menggunakan subdomain resmi:\n"
            "👉 `[nama-layanan-opd].bekasikab.go.id`\n\n"
            "Hal ini bertujuan menjaga kredibilitas, keamanan siber, dan keaslian informasi resmi milik Pemerintah Kabupaten Bekasi.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Prosedur pengajuan subdomain atau hosting OPD|💻 Prosedur Subdomain]] "
            "[[chip:Daftarkan kunjungan hari Senin jam 10:00 pengajuan subdomain|📅 Buat Janji Temu Bidang TIK]]"
        )

    # B11. Anonim & Rahasia (SP4N-LAPOR)
    is_anon_query = any(k in txt for k in ('anonim', 'rahasia', 'nama samaran', 'identitas aman', 'sembunyi', 'ketahuan'))
    if is_anon_query and is_lapor:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Terkait kerahasiaan identitas pelapor di **SP4N-LAPOR!**:\n\n"
            "🛡️ **Sangat Aman! Anda dapat melapor secara ANONIM atau RAHASIA.**\n\n"
            "🔒 **Fitur Perlindungan Pelapor di portal lapor.go.id:**\n"
            "1. **Fitur Anonim:** Nama dan identitas Anda tidak akan ditampilkan kepada publik maupun instansi terlapor.\n"
            "2. **Fitur Rahasia:** Isi laporan hanya dapat dibaca oleh Admin Utama dan OPD yang berwenang menindaklanjuti, tidak dapat diakses oleh publik.\n"
            "3. Perlindungan identitas pelapor dijamin oleh undang-undang pelayanan publik dan sistem pengaduan nasional.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Alur Pengaduan SP4N LAPOR dan PPID|📢 Cara Melapor di SP4N-LAPOR!]]"
        )

    # B12. Format Data Statistik Sektoral
    is_format_data = any(k in txt for k in ('format data', 'file apa', 'excel', 'csv', 'pdf', 'bentuk data'))
    if is_format_data and is_stat:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Terkait **Format File Data Statistik Sektoral & Satu Data Bekasi**:\n\n"
            "📊 **Format Data yang Disediakan:**\n"
            "1. **Portal Satu Data (data.bekasikab.go.id):** Dapat diunduh langsung dalam format terbuka standar mesin: **CSV, XLSX (Excel), JSON, dan PDF**.\n"
            "2. **Permohonan Data Khusus / Riset di Loket:** Data rekapitulasi tabular diberikan dalam format **Excel / CSV** disertai metadata resmi dan Berita Acara Serah Terima (BAST) pemanfaatan data statistik.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:SOP Permohonan Data Statistik Sektoral|📊 Syarat Permohonan Data]] "
            "[[chip:Daftarkan kunjungan hari Senin jam 09:00 permohonan data statistik|📅 Buat Janji Bidang Statistik]]"
        )

    # B13. Lokasi Loket / Lantai Berapa
    is_location_query = any(k in txt for k in ('lantai berapa', 'ruangan mana', 'ruangan apa', 'loket mana', 'ke lantai', 'lantai', 'ruangannya'))
    if is_location_query and effective_topic:
        if is_tte or is_csirt:
            lokasi = "Lantai 2 Gedung Diskominfosantik Kab. Bekasi — Bidang Persandian & Keamanan Informasi"
            chips = "[[chip:Bagaimana syarat dan alur permohonan TTE BSrE?|🔐 Info Layanan TTE]] [[chip:Daftarkan kunjungan hari Senin jam 09:00 konsultasi TTE|📅 Buat Janji Temu]]"
        elif is_subdomain or is_wifi:
            lokasi = "Lantai 2 Gedung Diskominfosantik Kab. Bekasi — Bidang Teknologi Informasi dan Komunikasi (TIK)"
            chips = "[[chip:Prosedur pengajuan subdomain atau hosting OPD|💻 Info Subdomain]] [[chip:Daftarkan kunjungan hari Senin jam 10:00 pengajuan subdomain|📅 Buat Janji Temu]]"
        elif is_magang:
            lokasi = "Lantai 1 Gedung Diskominfosantik Kab. Bekasi — Subbagian Umum & Kepegawaian (Sekretariat)"
            chips = "[[chip:Info alur pendaftaran magang dan PKL mahasiswa|🎓 Info Magang]] [[chip:Daftarkan kunjungan hari Senin jam 09:00 penyerahan proposal magang|📅 Buat Janji Temu]]"
        elif is_lapor or is_pers:
            lokasi = "Lantai 1 Gedung Diskominfosantik Kab. Bekasi — Bidang Informasi & Komunikasi Publik (IKP) / Desk PPID"
            chips = "[[chip:Alur Pengaduan SP4N LAPOR dan PPID|📢 Info IKP]] [[chip:Daftarkan kunjungan hari Senin jam 10:00 konsultasi SP4N LAPOR|📅 Buat Janji Temu]]"
        elif is_stat:
            lokasi = "Lantai 2 Gedung Diskominfosantik Kab. Bekasi — Bidang Statistik Sektoral (Walidata)"
            chips = "[[chip:SOP Permohonan Data Statistik Sektoral|📊 Info Statistik]] [[chip:Daftarkan kunjungan hari Senin jam 09:00 permohonan data statistik|📅 Buat Janji Temu]]"
        else:
            lokasi = "Gedung Diskominfosantik Kabupaten Bekasi, Blok B, Kompleks Perkantoran Pemkab Bekasi, Sukamahi, Cikarang Pusat"
            chips = "[[chip:Daftarkan kunjungan baru|📅 Buat Janji Kunjungan]]"

        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            f"📍 **Lokasi Loket & Ruangan Pelayanan:**\n"
            f"**{lokasi}**\n\n"
            "🕒 **Waktu Layanan Tatap Muka:**\n"
            "Senin – Jumat, pukul 08:00 – 15:30 WIB.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            f"{chips}"
        )

    # ══════════════════════════════════════════════════════════════════════════
    # KASUS B: INFORMASI SOP & ALUR KEDINASAN LENGKAP (DISERTAI SLA & JAMINAN)
    # ══════════════════════════════════════════════════════════════════════════

    # 1. TTE (Tanda Tangan Elektronik / BSrE BSSN)
    if is_tte:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut Prosedur & Persyaratan Penerbitan **Tanda Tangan Elektronik (TTE / BSrE)** di Diskominfosantik Kab. Bekasi:\n\n"
            "📋 **Sasaran Pemohon:**\n"
            "Pejabat Struktural, Kepala Sekolah/Puskesmas, Pejabat Pengadaan, dan ASN di lingkungan Pemerintah Kabupaten Bekasi.\n\n"
            "📝 **Persyaratan Berkas:**\n"
            "1. 📄 Surat Rekomendasi/Pengantar resmi dari Kepala Perangkat Daerah / OPD pemohon.\n"
            "2. 🆔 Scan KTP asli dan SK Jabatan / SK Pengangkatan ASN terbaru.\n"
            "3. 📧 Memiliki email dinas resmi dengan domain `@bekasikab.go.id`.\n"
            "4. 📝 Mengisi Formulir Pendaftaran Sertifikat Elektronik Balai Sertifikasi Elektronik (BSrE-BSSN).\n\n"
            "🔄 **Alur Penerbitan:**\n"
            "1. Pemohon membawa berkas ke loket Bidang Persandian & Keamanan Informasi Diskominfosantik.\n"
            "2. Verifikator memeriksa kesesuaian identitas dan meregistrasikan NIK ke portal BSrE BSSN.\n"
            "3. Pemohon menerima email verifikasi BSrE lalu melakukan aktivasi dan pembuatan *Passphrase* mandiri.\n\n"
            "⏱️ **Standar Waktu Penyelesaian (SLA):**\n"
            "• **1 hari kerja** (setelah berkas pendaftaran dinyatakan lengkap & valid).\n"
            "• *Keterangan Keterlambatan:* Jika tidak selesai tepat waktu karena kendala teknis (sinkronisasi BSrE/NIK), pemohon akan dikabari oleh admin dan dijelaskan semua kendalanya.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Daftarkan kunjungan hari Senin jam 09:00 konsultasi TTE|📅 Buat Janji Konsultasi TTE]] "
            "[[chip:Berapa lama verifikasi TTE selesai?|⏱️ Cek SLA Layanan TTE]] "
            "[[chip:Informasi bidang layanan dan pegawai yang bertugas|👔 Cek Tim Bidang Persandian]]"
        )

    # 2. Penanganan Insiden Keamanan Siber & CSIRT (BekasiKab-CSIRT / Hacking / Judi Online / Pentest)
    if is_csirt:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut Prosedur Pelaporan **Insiden Keamanan Siber & Layanan CSIRT (BekasiKab-CSIRT)** di Diskominfosantik Kab. Bekasi:\n\n"
            "🛡️ **1. Pelaporan Insiden Siber (Web Kena Hack / Judi Online / Defacement):**\n"
            "• **Sasaran:** Seluruh Perangkat Daerah (OPD), Kecamatan, Puskesmas, dan Kelurahan/Desa pemilik website kedinasan.\n"
            "• **Alur Tindak Lanjut Darurat:**\n"
            "  1. Laporkan segera tautan (URL) halaman yang terindikasi disusupi atau disisipi konten judi online / deface.\n"
            "  2. Lampirkan tangkapan layar (*screenshot*) bukti tampilan insiden serta catatan estimasi waktu kejadian.\n"
            "  3. Tim Tanggap Insiden Siber (**BekasiKab-CSIRT**) akan langsung mengisolasi akses server, memutus *backdoor/web shell*, dan membersihkan skrip injeksi berbahaya.\n"
            "  4. Pengelola teknis OPD wajib mereset seluruh kredensial database/FTP dan mengaktifkan proteksi WAF.\n\n"
            "🔒 **2. Pengujian Keamanan Aplikasi (Penetration Testing / Pentest):**\n"
            "• Aplikasi baru milik OPD **wajib** lolos uji *Vulnerability Assessment (VA)* sebelum di-hosting atau di-launching.\n"
            "• Kirim surat resmi permohonan asesmen keamanan dari Kepala OPD ke Kepala Diskominfosantik.\n"
            "• Tim Persandian melakukan pengujian kerentanan (OWASP Top 10) dan menerbitkan Surat Keterangan Rekomendasi Keamanan.\n\n"
            "⏱️ **Standar Waktu Penanganan (SLA):**\n"
            "• **1x24 jam** (tanggap darurat mitigasi 1–3 jam pertama).\n"
            "• *Keterangan Keterlambatan:* Jika penanganan membutuhkan waktu tambahan karena kendala forensik mendalam, pengelola OPD akan dikabari oleh admin dan dijelaskan semua kendalanya.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Daftarkan kunjungan hari Senin jam 09:00 konsultasi insiden CSIRT|🛡️ Buat Janji Penanganan Insiden CSIRT]] "
            "[[chip:Informasi bidang layanan dan pegawai yang bertugas|👔 Cek Tim Bidang Persandian]]"
        )

    # 3. Infrastruktur Jaringan, Intranet & WiFi Pemkab (Bidang TIK)
    if is_wifi:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut Prosedur Layanan **Infrastruktur Jaringan, Intranet & WiFi Pemkab Bekasi** (Bidang TIK):\n\n"
            "🌐 **1. Penanganan Gangguan Koneksi Internet & Intranet OPD / Kecamatan:**\n"
            "• Melayani kantor dinas, kecamatan, puskesmas, dan kelurahan yang terhubung ke jaringan Fiber Optic (FO) Pemkab Bekasi.\n"
            "• **Alur Penanganan Gangguan:**\n"
            "  1. Laporkan nama kantor/lokasi, nomor rack/port switch, dan jenis kendala (koneksi putus total / RTO / lambat).\n"
            "  2. Tim *Network Operation Center (NOC)* TIK melakukan verifikasi link status dan diagnosa rute jaringan secara remote.\n"
            "  3. Apabila terjadi kendala fisik (kabel FO putus atau switch rusak tersambar petir), tim teknisi lapangan segera meluncur ke lokasi kerja Anda.\n\n"
            "📶 **2. Permohonan Penambahan Bandwidth & Titik WiFi Publik:**\n"
            "• Kepala Perangkat Daerah mengajukan surat permohonan analisis kebutuhan kapasitas bandwidth dinas.\n"
            "• Tim TIK melakukan survei kelayakan jalur kabel FO dan konfigurasi alokasi bandwidth terkelola (QoS).\n"
            "• Penyediaan titik WiFi Publik di area ruang terbuka hijau (RTH) dan taman publik dikelola terpusat untuk masyarakat Kabupaten Bekasi.\n\n"
            "⏱️ **Standar Waktu Penanganan (SLA):**\n"
            "• **1–2 hari kerja** (diagnosa NOC remote 1–2 jam, perbaikan lapangan 1–2 hari kerja).\n"
            "• *Keterangan Keterlambatan:* Jika perbaikan jaringan terkendala kabel putus atau modul switch rusak, kantor pemohon akan dikabari oleh admin dan dijelaskan semua kendalanya.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Daftarkan kunjungan hari Senin jam 10:00 koordinasi jaringan wifi|🌐 Buat Janji Koordinasi Jaringan TIK]] "
            "[[chip:Informasi bidang layanan dan pegawai yang bertugas|👔 Cek Tim Bidang TIK]]"
        )

    # 4. Pengaduan Masyarakat (SP4N-LAPOR!) & PPID (Bidang IKP)
    if is_lapor:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut Panduan Kanal **Pengaduan Masyarakat (SP4N-LAPOR!)** di Kabupaten Bekasi (Bidang IKP):\n\n"
            "📢 **1. Layanan Aspirasi & Pengaduan Online Rakyat (SP4N-LAPOR!):**\n"
            "• **Fungsi:** Saluran resmi pengaduan masyarakat seputar pelayanan publik, jalan rusak, jembatan, sampah, lampu penerangan jalan mati, bansos, hingga pungli di Kab. Bekasi.\n"
            "• **Cara Melapor:**\n"
            "  1. Akses portal resmi **www.lapor.go.id**, aplikasi ponsel *SP4N LAPOR!*, atau kirim SMS ke **1708**.\n"
            "  2. Tuliskan laporan dengan jelas: judul, kronologi kejadian, alamat/lokasi lengkap titik masalah, dan lampirkan foto bukti.\n"
            "  3. Pilih kategori laporan: Pengaduan, Aspirasi, atau Permintaan Informasi.\n"
            "• **Alur Tindak Lanjut Pemkab:**\n"
            "  Admin Utama Diskominfosantik Kab. Bekasi memverifikasi laporan maksimal 3 hari kerja lalu mendisposisikannya ke OPD teknis terkait (misal: Dinas SDABMBK untuk perbaikan jalan). Instansi teknis wajib menindaklanjuti maksimal 5 hari kerja.\n\n"
            "📑 **2. Layanan Informasi Publik (PPID):**\n"
            "• Permohonan informasi publik berkala dan serta-merta dilayani di Desk PPID Kantor Diskominfosantik atau portal PPID Kab. Bekasi sesuai UU No. 14 Tahun 2008.\n\n"
            "⏱️ **Standar Waktu Penyelesaian (SLA):**\n"
            "• Verifikasi Admin: **maksimal 3 hari kerja**; Tindak Lanjut OPD: **maksimal 5 hari kerja**.\n"
            "• *Keterangan Keterlambatan:* Apabila tindak lanjut aduan butuh waktu tambahan, pelapor akan dikabari oleh admin melalui portal lapor.go.id beserta keterangan kendalanya.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Daftarkan kunjungan hari Senin jam 10:00 konsultasi pengaduan SP4N LAPOR|📢 Buat Janji Konsultasi Bidang IKP]] "
            "[[chip:Informasi bidang layanan dan pegawai yang bertugas|👔 Cek Tim Bidang IKP]]"
        )

    # 5. Statistik Sektoral & Portal Satu Data Bekasi (Bidang Statistik)
    if is_stat:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut Prosedur **Permohonan Data Statistik Sektoral & Satu Data Bekasi** (Bidang Statistik):\n\n"
            "📊 **1. Portal Terbuka Satu Data Kabupaten Bekasi:**\n"
            "• Berbagai dataset terbuka (kependudukan, kemiskinan, kesehatan, pendidikan, geospasial, ekonomi daerah) dapat diakses dan diunduh langsung secara publik melalui portal:\n"
            "  👉 **data.bekasikab.go.id**\n\n"
            "📝 **2. Permohonan Data Statistik untuk Riset, Skripsi & Kajian OPD:**\n"
            "• **Sasaran Pemohon:** Mahasiswa, akademisi, peneliti, lembaga swadaya masyarakat, serta perangkat daerah.\n"
            "• **Persyaratan Berkas:**\n"
            "  1. 📄 Surat Pengantar Permohonan Data resmi dari Universitas/Instansi ditujukan kepada *Kepala Diskominfosantik Kab. Bekasi*.\n"
            "  2. 📑 Lembar rincian variabel data, periode tahun yang dibutuhkan, dan tujuan pemanfaatan data riset.\n"
            "  3. 🆔 Fotokopi identitas pemohon (KTM / KTP).\n"
            "• **Alur Pelayanan:**\n"
            "  1. Pemohon menyerahkan berkas ke loket Bidang Statistik Sektoral Diskominfosantik (selaku Walidata Daerah).\n"
            "  2. Tim Walidata memeriksa ketersediaan data dan berkoordinasi dengan OPD Produsen Data terkait.\n"
            "  3. Penyerahan kompilasi data resmi disertai Berita Acara Pemanfaatan Data Statistik.\n\n"
            "⏱️ **Standar Waktu Penyelesaian (SLA):**\n"
            "• **3–7 hari kerja** (verifikasi proposal riset & koordinasi data bersama OPD produsen data).\n"
            "• *Keterangan Keterlambatan:* Jika pengumpulan data membutuhkan waktu lebih lama, pemohon akan dikabari oleh admin dan dijelaskan semua kendalanya.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Daftarkan kunjungan hari Senin jam 09:00 permohonan data statistik|📊 Buat Janji Permohonan Data Statistik]] "
            "[[chip:Informasi bidang layanan dan pegawai yang bertugas|👔 Cek Tim Bidang Statistik]]"
        )

    # 6. Subdomain & Hosting Server OPD
    if is_subdomain:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut Prosedur Pengajuan **Subdomain & Hosting Server OPD** di Diskominfosantik Kab. Bekasi:\n\n"
            "📋 **Sasaran Pemohon:**\n"
            "Organisasi Perangkat Daerah (OPD) yang membangun aplikasi layanan publik atau administrasi pemerintahan.\n\n"
            "📝 **Persyaratan Teknis & Administrasi:**\n"
            "1. 📄 Surat Permohonan resmi dari Kepala OPD ditujukan kepada Kepala Diskominfosantik Kab. Bekasi.\n"
            "2. 📑 Formulir Kelayakan Teknis Aplikasi & Arsitektur SPBE (Sistem Pemerintahan Berbasis Elektronik).\n"
            "3. 🔒 Hasil pengujian keamanan mandiri (Security Assessment) bebas kerentanan OWASP/SQLi/XSS.\n"
            "4. 🏷️ Nama subdomain yang diajukan (contoh: `layananopd.bekasikab.go.id`).\n\n"
            "🔄 **Alur Layanan:**\n"
            "1. Penyerahan dokumen ke Bidang TIK & E-Government Diskominfosantik.\n"
            "2. Verifikasi kesesuaian penamaan domain dan ketersediaan resource server/VPS Data Center.\n"
            "3. Konfigurasi DNS & alokasi IP server oleh Tim Teknis TIK.\n"
            "4. Serah terima akun dan Berita Acara Serah Terima (BAST) akses hosting kepada PIC teknis OPD.\n\n"
            "⏱️ **Standar Waktu Penyelesaian (SLA):**\n"
            "• **1–3 hari kerja** (konfigurasi DNS & alokasi server Data Center).\n"
            "• *Keterangan Keterlambatan:* Jika proses tidak selesai tepat waktu karena kendala teknis, pemohon akan dikabari oleh admin dan dijelaskan semua kendalanya.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Daftarkan kunjungan hari Senin jam 10:00 pengajuan subdomain|📅 Buat Janji Pengajuan Subdomain]] "
            "[[chip:Berapa hari pengajuan subdomain diproses?|⏱️ Cek SLA Subdomain]] "
            "[[chip:Informasi bidang layanan dan pegawai yang bertugas|👔 Cek Tim Bidang TIK]]"
        )

    # 7. Magang / PKL / Prakerin
    if is_magang:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut Alur Pendaftaran **Magang / Prakerin (PKL) / Penelitian** di Diskominfosantik Kab. Bekasi:\n\n"
            "🎓 **Sasaran Peserta:**\n"
            "Mahasiswa Perguruan Tinggi & Siswa SMK jurusan Teknik Informatika, Ilmu Komputer, Sistem Informasi, TKJ, Multimedia/Desain Grafis, dan Jurnalistik/Komunikasi.\n\n"
            "📝 **Persyaratan Berkas:**\n"
            "1. 📄 Surat Permohonan Resmi dari Universitas/Sekolah ditujukan kepada:\n"
            "   *Kepala Dinas Komunikasi, Informatika, Persandian dan Statistik Kabupaten Bekasi*.\n"
            "2. 📑 Proposal Rencana Magang / Riset (mencakup periode pelaksanaan & bidang yang dituju).\n"
            "3. 🆔 Fotokopi KTM / Kartu Pelajar dan CV singkat pemohon.\n\n"
            "🔄 **Alur Penerimaan:**\n"
            "1. Bawa berkas ke loket Sekretariat / Subbag Umum & Kepegawaian Diskominfosantik.\n"
            "2. Pengecekan kuota magang dan ketersediaan mentor/pembimbing lapangan di bidang terkait.\n"
            "3. Pengambilan Surat Konfirmasi Penerimaan Magang.\n\n"
            "⏱️ **Standar Waktu Penyelesaian (SLA):**\n"
            "• **3–5 hari kerja** (evaluasi kuota bidang & penerbitan surat konfirmasi penerimaan magang).\n"
            "• *Keterangan Keterlambatan:* Jika tidak selesai tepat waktu karena kendala teknis atau penyesuaian mentor, pemohon akan dikabari oleh admin dan dijelaskan semua kendalanya.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Daftarkan kunjungan hari Senin jam 09:00 penyerahan proposal magang|📅 Buat Janji Penyerahan Berkas Magang]] "
            "[[chip:Berapa lama konfirmasi magang diterima?|⏱️ Cek SLA Penerimaan Magang]] "
            "[[chip:Berapa sisa kuota kunjungan dan jam operasional hari ini?|📊 Cek Jam Operasional Loket]]"
        )

    # 8. Liputan Pers / Rekan Media & Wartawan (Bidang IKP)
    if is_pers:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Berikut Ketentuan Layanan **Liputan Pers & Media Rekanan** di Diskominfosantik Kab. Bekasi:\n\n"
            "📰 **1. Layanan Kerjasama & Liputan Media (Bidang IKP):**\n"
            "• Media terdaftar / terverifikasi Dewan Pers atau berbadan hukum pers resmi.\n"
            "• Wartawan wajib menunjukkan Kartu Pers (ID Card) aktif dan surat tugas liputan.\n"
            "• Koordinasi rilis berita atau liputan pimpinan daerah dilakukan melalui Bidang Informasi dan Komunikasi Publik (IKP).\n\n"
            "⏱️ **Standar Waktu Penyelesaian (SLA):**\n"
            "• **1–3 hari kerja** (atau koordinasi langsung mengikuti agenda pimpinan daerah).\n"
            "• *Keterangan Keterlambatan:* Jika ada kendala penyesuaian jadwal peliputan, wartawan/media akan dikabari oleh admin Bidang IKP.\n\n"
            "👉 **Sentuh Pilihan Tindakan:**\n"
            "[[chip:Daftarkan kunjungan hari Senin jam 10:00 koordinasi liputan media|📅 Buat Janji Temu Bidang IKP]] "
            "[[chip:Informasi bidang layanan dan pegawai yang bertugas|👔 Cek Tim Bidang IKP]]"
        )

    # Default / Katalog umum SOP 6 Bidang & SLA
    return (
        "🤖 Asisten AI Diskominfosantik:\n"
        "Berikut katalog informasi **SOP, Layanan Teknis 6 Bidang & Standar Waktu Layanan (SLA)** Diskominfosantik Kab. Bekasi:\n\n"
        "Silakan sentuh salah satu pilihan di bawah untuk melihat rincian persyaratan, alur, dan estimasi durasi penyelesaiannya:\n\n"
        "👉 **Pilihan SOP Layanan:**\n"
        "[[chip:SOP Permohonan TTE BSrE|🔐 1. Tanda Tangan Elektronik (TTE)]] \n"
        "[[chip:SOP Penanganan Insiden CSIRT dan Pentest|🛡️ 2. Insiden Siber CSIRT & Pentest]] \n"
        "[[chip:SOP Gangguan Jaringan dan WiFi TIK|🌐 3. Jaringan, Intranet & WiFi TIK]] \n"
        "[[chip:SOP Pengajuan Subdomain dan Hosting|💻 4. Subdomain & Hosting Server OPD]] \n"
        "[[chip:Alur Pengaduan SP4N LAPOR dan PPID|📢 5. Pengaduan SP4N-LAPOR & PPID]] \n"
        "[[chip:SOP Permohonan Data Statistik Sektoral|📊 6. Statistik & Satu Data Bekasi]] \n"
        "[[chip:Alur Pendaftaran Magang dan PKL|🎓 7. Alur Magang / PKL Mahasiswa]] \n"
        "[[chip:Ketentuan Liputan Pers dan PPID|📰 8. Liputan Pers & Rekan Media]] \n"
        "[[chip:Standar waktu penyelesaian layanan dan SLA Diskominfosantik|⏱️ 9. Standar Waktu Penyelesaian Layanan (SLA)]]"
    )


def _handle_reschedule_or_cancel_from_chat(tamu, message_text):
    """
    Mendukung pengubahan jadwal (Reschedule) dan pembatalan kunjungan
    langsung lewat Chat Asisten AI tanpa harus membuka menu riwayat.
    - Pembatalan: Mengubah status kunjungan aktif menjadi 'cancelled'.
    - Reschedule: Mengubah jam/tanggal kedatangan, status diset 'menunggu_admin'
      agar Admin memverifikasi dan meng-ACC jadwal baru tersebut.
    """
    import re
    from datetime import datetime, time as dt_time, timedelta
    import zoneinfo
    from django.db import transaction
    from .models import Kunjungan, KunjunganStatusHistory
    from .validators import get_daily_quota_info

    if not tamu:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Silakan login terlebih dahulu untuk mengelola tiket kunjungan Anda."
        )

    raw = (message_text or '').strip()
    txt = _normalize_slang_and_typos(raw.lower())

    # Ambil tiket aktif tamu
    active_visits = list(
        Kunjungan.objects.filter(
            tamu=tamu,
            status__in=['menunggu_admin', 'menunggu_pegawai', 'disetujui_pegawai', 'disetujui']
        ).select_related('pegawai', 'pegawai__department_rel').order_by('arrival_time')
    )

    if not active_visits:
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            "Saat ini Anda belum memiliki tiket kunjungan yang aktif untuk diubah jadwalnya atau dibatalkan.\n\n"
            "💡 *Jika Anda ingin mengajukan kunjungan baru, silakan gunakan tombol di bawah:*\n"
            "[[chip:Daftarkan kunjungan baru|📅 Ajukan Kunjungan Baru]]"
        )

    # Deteksi jenis tindakan: Batalkan vs Ubah Jadwal
    is_reschedule = any(k in txt for k in (
        'ubah jadwal', 'ganti jam', 'ganti jadwal', 'ganti hari', 'reschedule',
        'undur', 'geser', 'pindah jam', 'pindah hari', 'ubah jam', 'rubah',
        'ganti waktu', 'pindah waktu'
    ))
    is_cancel = any(k in txt for k in (
        'batalkan', 'batal', 'cancel', 'tidak jadi datang', 'gak jadi datang',
        'ga jadi datang', 'batalin', 'batal datang'
    )) and not is_reschedule

    # Cari tiket yang cocok jika ada beberapa tiket aktif
    target_visit = None
    if len(active_visits) == 1:
        target_visit = active_visits[0]
    else:
        # Cek kecocokan kode tiket
        m_code = re.search(r'#?([a-f0-9]{8})\b', txt)
        if m_code:
            code_prefix = m_code.group(1).lower()
            target_visit = next((v for v in active_visits if str(v.id).lower().startswith(code_prefix)), None)
        
        # Cek kecocokan hari kunjungan
        if not target_visit:
            day_names = ['senin', 'selasa', 'rabu', 'kamis', 'jumat', 'sabtu', 'minggu']
            for v in active_visits:
                v_day = day_names[v.arrival_time.weekday()]
                if v_day in txt:
                    target_visit = v
                    break

        # Jika masih belum spesifik, tampilkan opsi tiket dengan tombol chip
        if not target_visit:
            action_label = "diubah jadwalnya" if is_reschedule else "dibatalkan"
            action_prefix = "Ganti jam tiket #" if is_reschedule else "Batalkan tiket #"
            btn_icon = "🕒" if is_reschedule else "🚫"
            blocks = [
                f"🤖 Asisten AI Diskominfosantik:\n"
                f"Anda memiliki **{len(active_visits)} tiket kunjungan aktif**. Silakan pilih tiket mana yang ingin {action_label}:\n"
            ]
            chips = []
            for idx, v in enumerate(active_visits, start=1):
                tgl_str = timezone.localtime(v.arrival_time).strftime('%d/%m/%Y (%H:%M WIB)')
                c_code = str(v.id)[:8].upper()
                peg_name = v.pegawai.name if v.pegawai else 'Pegawai Belum Ditentukan'
                blocks.append(f"{idx}. Tiket **#{c_code}** — {tgl_str} ({peg_name})")
                chips.append(f"[[chip:{action_prefix}{c_code}|{btn_icon} Tiket #{c_code} ({tgl_str[:10]})]]")
            blocks.append("\n👉 **Pilih Tiket:**\n" + " ".join(chips))
            return "\n".join(blocks)

    # ── KASUS 1: PEMBATALAN KUNJUNGAN ──
    if is_cancel:
        c_code = str(target_visit.id)[:8].upper()
        old_time_str = timezone.localtime(target_visit.arrival_time).strftime('%d/%m/%Y pukul %H:%M WIB')
        peg_name = target_visit.pegawai.name if target_visit.pegawai else 'Dinas'
        old_status = target_visit.status

        with transaction.atomic():
            target_visit.status = 'cancelled'
            target_visit.admin_notes = (target_visit.admin_notes or '') + f"\n[Dibatalkan Tamu via Chat AI pada {timezone.now().strftime('%d/%m/%Y %H:%M')}]: {raw}"
            target_visit.save(update_fields=['status', 'admin_notes', 'updated_at'])

            KunjunganStatusHistory.objects.create(
                kunjungan=target_visit,
                old_status=old_status,
                new_status='cancelled',
                changed_by_id=str(tamu.id),
                changed_by_type='tamu',
                notes=f'Dibatalkan langsung oleh tamu melalui Chat Asisten AI: "{raw}"',
            )

        try:
            send_notification(
                recipient_id='admin',
                recipient_type='admin',
                notification_type='visit_cancelled',
                title='Kunjungan Dibatalkan (via Chat AI)',
                message=f'Tamu {tamu.name} membatalkan tiket #{c_code} (Jadwal: {old_time_str}) melalui Asisten AI.',
                related_object_id=str(target_visit.id),
            )
        except Exception as e:
            logger.warning("Gagal mengirim notif pembatalan: %s", e)

        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            f"✅ **Tiket Kunjungan #{c_code} Berhasil Dibatalkan.**\n\n"
            f"📋 **Rincian Tiket yang Dibatalkan:**\n"
            f"   • Pegawai : {peg_name}\n"
            f"   • Jadwal Lama : {old_time_str}\n"
            f"   • Status Saat Ini : 🚫 **Dibatalkan (Cancelled)**\n\n"
            "Kuota kunjungan telah dikembalikan ke sistem. Jika Anda ingin menjadwalkan ulang di waktu lain, silakan gunakan tombol di bawah:\n"
            "[[chip:Daftarkan kunjungan baru|📅 Ajukan Kunjungan Baru]]"
        )

    # ── KASUS 2: RESCHEDULE (UBAH JADWAL / GANTI JAM) ──
    jakarta_tz = zoneinfo.ZoneInfo('Asia/Jakarta')
    now_local = timezone.localtime(timezone.now(), jakarta_tz)
    cur_local_dt = timezone.localtime(target_visit.arrival_time, jakarta_tz)

    # Ekstrak Jam Baru
    new_hour, new_minute = None, None
    m_time = re.search(r'(?:jam|pukul|pkl)\s*(\d{1,2})(?:[:.](\d{2}))?', txt)
    if not m_time:
        m_time = re.search(r'\b([01]?\d|2[0-3])[:.]([0-5]\d)\s*(?:wib)?\b', txt)
    if m_time:
        h_val = int(m_time.group(1))
        m_val = int(m_time.group(2)) if m_time.group(2) else 0
        if 1 <= h_val <= 4 and ('siang' in txt or 'sore' in txt):
            h_val += 12
        new_hour = max(8, min(15, h_val))
        new_minute = max(0, min(59, m_val))
    elif 'siang' in txt:
        new_hour, new_minute = 13, 0
    elif 'sore' in txt:
        new_hour, new_minute = 14, 30
    elif 'pagi' in txt:
        new_hour, new_minute = 9, 0

    # Ekstrak Hari / Tanggal Baru jika tamu ingin pindah tanggal juga
    new_date = None
    day_patterns = [
        (0, 'Senin', r'\bsenin\w*\b'),
        (1, 'Selasa', r'\bselasa\w*|\bslasa\w*\b'),
        (2, 'Rabu', r'\brabu\w*|\brebo\w*\b'),
        (3, 'Kamis', r'\bkamis\w*|\bkemis\w*\b'),
        (4, 'Jumat', r'\bjum\'?at\w*\b'),
        (5, 'Sabtu', r'\bsabtu\w*\b'),
        (6, 'Minggu', r'\bminggu\w*|\bahad\w*\b'),
    ]
    if re.search(r'\blusa\b', txt):
        new_date = now_local.date() + timedelta(days=2)
    elif re.search(r'\b(besok|esok)\b', txt):
        new_date = now_local.date() + timedelta(days=1)
    elif re.search(r'\bhari\s+ini\b', txt):
        new_date = now_local.date()
    else:
        for wd_idx, wd_name, pattern in day_patterns:
            if re.search(pattern, txt):
                days_ahead = (wd_idx - now_local.date().weekday()) % 7
                if days_ahead == 0 and ('depan' in txt or now_local.hour >= 15):
                    days_ahead = 7
                new_date = now_local.date() + timedelta(days=days_ahead)
                break

    # Jika tanggal tidak diubah dalam pesan, gunakan tanggal kunjungan yang sudah ada
    if not new_date:
        new_date = cur_local_dt.date()

    c_code = str(target_visit.id)[:8].upper()

    # Jika Jam Baru belum disebutkan, minta tamu memilih jam
    if new_hour is None:
        tgl_display = new_date.strftime('%d/%m/%Y')
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            f"Baik, untuk tiket kunjungan **#{c_code}** ({tgl_display}), "
            "pukul / jam berapa jadwal kedatangan baru yang Anda inginkan?\n\n"
            "👉 **Sentuh Pilihan Jam di Bawah:**\n"
            f"[[chip:Ganti tiket #{c_code} jadi jam 09:00|🕒 09:00 WIB]] "
            f"[[chip:Ganti tiket #{c_code} jadi jam 10:30|🕒 10:30 WIB]] "
            f"[[chip:Ganti tiket #{c_code} jadi jam 13:30|🕒 13:30 WIB]] "
            f"[[chip:Ganti tiket #{c_code} jadi jam 14:30|🕒 14:30 WIB]]"
        )

    # Validasi hari libur / akhir pekan
    hari_names = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']
    hari_str = hari_names[new_date.weekday()]
    if new_date.weekday() in (5, 6):
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            f"⚠️ Mohon maaf, hari **{hari_str} ({new_date.strftime('%d/%m/%Y')})** kantor sedang tutup (akhir pekan). "
            "Layanan tatap muka dibuka hari **Senin – Jumat (08:00 – 16:00 WIB)**.\n\n"
            "Silakan pilih hari kerja untuk jadwal perubahan Anda."
        )

    # Validasi kuota hari baru
    try:
        quota_info = get_daily_quota_info(new_date)
    except Exception:
        quota_info = None

    if quota_info and quota_info.get('is_holiday'):
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            f"🔴 Mohon maaf, tanggal **{new_date.strftime('%d/%m/%Y')} ({hari_str})** ditetapkan sebagai hari libur "
            f"({quota_info.get('holiday_name') or 'Libur Operasional'}). Silakan pilih hari kerja lainnya."
        )
    if quota_info and quota_info.get('is_full') and new_date != cur_local_dt.date():
        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            f"🔴 Mohon maaf, kuota kunjungan untuk hari **{hari_str}, {new_date.strftime('%d/%m/%Y')}** sudah penuh. "
            "Silakan pilih tanggal lain untuk jadwal perubahan Anda."
        )

    # Hitung waktu kedatangan baru
    new_arrival_dt = datetime.combine(new_date, dt_time(new_hour, new_minute), tzinfo=jakarta_tz)
    old_time_str = cur_local_dt.strftime('%d/%m/%Y pukul %H:%M WIB')
    new_time_str = f"{hari_str}, {new_arrival_dt.strftime('%d/%m/%Y pukul %H:%M WIB')}"
    peg_name = target_visit.pegawai.name if target_visit.pegawai else 'Pegawai Dinas'
    old_status = target_visit.status

    with transaction.atomic():
        target_visit.arrival_time = new_arrival_dt
        target_visit.status = 'menunggu_admin'  # Menunggu ACC Admin kembali untuk jadwal baru
        target_visit.admin_notes = (
            (target_visit.admin_notes or '') +
            f"\n[Reschedule via Chat AI pada {now_local.strftime('%d/%m/%Y %H:%M')}]: "
            f"Jadwal lama ({old_time_str}) diubah menjadi ({new_time_str}). Menunggu ACC Admin."
        )
        target_visit.save(update_fields=['arrival_time', 'status', 'admin_notes', 'updated_at'])

        KunjunganStatusHistory.objects.create(
            kunjungan=target_visit,
            old_status=old_status,
            new_status='menunggu_admin',
            changed_by_id=str(tamu.id),
            changed_by_type='tamu',
            notes=f'Jadwal diubah via Chat AI dari {old_time_str} ke {new_time_str}. Menunggu persetujuan (ACC) Admin.',
        )

    try:
        send_notification(
            recipient_id='admin',
            recipient_type='admin',
            notification_type='visit_rescheduled',
            title='Permohonan Reschedule (via Chat AI) - Butuh ACC Admin',
            message=f'Tamu {tamu.name} mengubah jadwal tiket #{c_code} ke {new_time_str}. Menunggu verifikasi & persetujuan (ACC) Admin.',
            related_object_id=str(target_visit.id),
        )
        if target_visit.pegawai:
            send_notification(
                recipient_id=str(target_visit.pegawai.id),
                recipient_type='pegawai',
                notification_type='visit_rescheduled',
                title='Jadwal Janji Temu Diubah',
                message=f'Tamu {tamu.name} mengubah jadwal kunjungan dengan Anda ke {new_time_str} (Menunggu ACC Admin).',
                related_object_id=str(target_visit.id),
            )
    except Exception as e:
        logger.warning("Gagal mengirim notif reschedule: %s", e)

    return (
        "🤖 Asisten AI Diskominfosantik:\n"
        f"✅ **Jadwal Kunjungan Tiket #{c_code} Berhasil Diperbarui!**\n\n"
        f"📋 **Rincian Perubahan Jadwal:**\n"
        f"   • **Kode Tiket** : #{c_code}\n"
        f"   • **Pegawai Tujuan** : {peg_name}\n"
        f"   • **Jadwal Sebelumnya** : {old_time_str}\n"
        f"   • **Jadwal Baru** : **{new_time_str}**\n"
        f"   • **Status Saat Ini** : ⏳ **Menunggu Verifikasi & Persetujuan (ACC) Admin**\n\n"
        "📌 **Catatan Alur:**\n"
        "Perubahan jam/tanggal kedatangan Anda telah disimpan dan diteruskan ke Admin Diskominfosantik. "
        "Admin akan memeriksa kembali dan memberikan persetujuan (ACC) untuk jadwal baru Anda."
    )


def build_n8n_chat_response(tamu_id, message_text, session_id=None):
    """
    Memanggil Webhook N8N (6-cabang Text Classifier + Information Extractor)
    dan menggabungkan hasilnya (`intent`, `reply`/`replay`, `handoff`)
    dengan data dinamis database Django (Kunjungan, Kuota, Pegawai, Departemen)
    serta aturan 3-Strike Auto-Handoff.
    """
    sess_key = _get_clean_session_key(session_id or tamu_id)

    # 1. Cek apakah sesi sudah dialihkan penuh ke Petugas Admin manusia
    if is_session_handed_off_to_admin(sess_key):
        return {
            'intent': 'handoff_admin',
            'reply_text': None,  # Tidak ada balasan bot; menunggu respon manual dari admin
            'handoff': True,
            'strike_count': AI_MAX_STRIKES,
        }

    # 2. Panggil N8N Webhook AI Assistant
    n8n_res = None
    try:
        mock_check = call_n8n_routing(None, message_text, None, None)
        if isinstance(mock_check, dict) and ('intent' in mock_check or 'reply' in mock_check or 'replay' in mock_check):
            n8n_res = mock_check
    except Exception:
        pass

    n8n_chat_url = os.getenv('N8N_CHAT_WEBHOOK_URL')
    if not n8n_res and n8n_chat_url:
        try:
            import urllib.request
            payload = json.dumps({
                'tamu_id': str(tamu_id),
                'session_id': str(sess_key),
                'message': message_text,
                'timestamp': timezone.now().isoformat(),
            }).encode('utf-8')
            req = urllib.request.Request(
                n8n_chat_url,
                data=payload,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'BukuDigital-ChatAI/1.0',
                },
                method='POST'
            )
            timeout = int(os.getenv('N8N_WEBHOOK_TIMEOUT', '5'))
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_data = resp.read().decode('utf-8')
                n8n_res = json.loads(resp_data)
        except Exception as e:
            logger.warning("Panggilan N8N Chat Webhook gagal atau timeout: %s", e)
            n8n_res = None

    if not n8n_res or not isinstance(n8n_res, dict):
        n8n_res = _detect_user_intent_locally(message_text, session_id=sess_key)
    elif n8n_res.get('intent') == 'di_luar_konteks':
        # Cek apakah memori konteks sesi lokal mengenali pertanyaan lanjutan ini
        local_res = _detect_user_intent_locally(message_text, session_id=sess_key)
        if local_res and local_res.get('intent') != 'di_luar_konteks':
            n8n_res = local_res

    # 3. Gabungkan respon N8N dengan data sistem & rule 3-Strike Handoff
    enriched_res = _enrich_n8n_chat_assistant_response(tamu_id, message_text, n8n_res, sess_key)

    # 4. Simpan ke Memori Konteks Sesi Multi-Turn
    try:
        reply_txt = enriched_res.get('reply_text')
        if reply_txt:
            save_conversation_context(
                session_id=sess_key,
                user_text=message_text,
                bot_reply_dict_or_str=reply_txt,
                intent=enriched_res.get('intent'),
                topic=n8n_res.get('active_topic') or enriched_res.get('active_topic'),
            )
    except Exception as ctx_err:
        logger.debug("Gagal menyimpan memori konteks chat: %s", ctx_err)

    return enriched_res


def _enrich_n8n_chat_assistant_response(tamu_id, message_text, n8n_res, sess_key):
    """
    Memperkaya balasan AI N8N dengan data nyata dari database:
    - Status Kunjungan nyata dari tabel Kunjungan
    - Kuota kalender riil dari CalendarSettings & validasi hari libur
    - Daftar Pegawai & Bidang nyata
    - Hitungan 3x Strike untuk Auto-Handoff ke Admin
    """
    from .models import Kunjungan, Pegawai, Departemen, Instansi, Tamu
    from .validators import get_daily_quota_info

    intent = str(n8n_res.get('intent') or 'di_luar_konteks').lower()
    ai_reply = n8n_res.get('reply') or n8n_res.get('replay') or ''
    n8n_wants_handoff = bool(n8n_res.get('handoff'))

    tamu = None
    if tamu_id:
        try:
            import uuid
            if isinstance(tamu_id, uuid.UUID):
                tamu = Tamu.objects.filter(id=tamu_id).first()
            elif isinstance(tamu_id, str):
                try:
                    uuid.UUID(tamu_id)
                    tamu = Tamu.objects.filter(id=tamu_id).first()
                except (ValueError, TypeError):
                    tamu = None
        except Exception:
            tamu = None
    try:
        pegawai_qs = list(
            Pegawai.objects.filter(account_status='active')
            .select_related('department_rel')
            .order_by('name')
        )
    except Exception:
        pegawai_qs = []

    txt_lower = (message_text or '').strip().lower()
    txt_norm = _normalize_slang_and_typos(txt_lower)

    # Cek jika tamu sedang berada di alur booking interaktif di cache
    draft_key = f"chat_booking_draft_{tamu_id}"
    has_active_draft = bool(safe_cache_get(draft_key))
    if has_active_draft:
        intent = 'buat_kunjungan'
        n8n_wants_handoff = False

    # Deteksi umpan balik ketidakpuasan tamu ("jawaban salah", "kurang suka", "ai tidak jelas")
    dissatisfaction_keywords = (
        'tidak membantu', 'jawaban salah', 'kurang sesuai', 'kurang suka',
        'tidak jelas', 'salah jawab', 'bukan itu maksud', 'ngawur',
        'kurang puas', 'gak jelas', 'masih belum',
    )
    is_unsatisfied = any(k in txt_lower for k in dissatisfaction_keywords)

    is_reschedule_cancel_word = any(k in txt_norm for k in (
        'batal', 'batalkan', 'cancel', 'tidak jadi', 'gak jadi', 'ga jadi',
        'ubah jadwal', 'ganti jam', 'ganti jadwal', 'ganti hari', 'reschedule',
        'undur', 'geser', 'pindah jam', 'pindah hari', 'ubah jam', 'rubah'
    ))

    booking_override_keywords = (
        'buatkan', 'daftarkan', 'daftarin', 'daftar kunjungan', 'buat kunjungan',
        'bikin jadwal', 'bikin janji', 'buat janji temu', 'bikin janji temu', 'daftar janji temu',
        'bikinkan', 'bikinin',
        'pesan jadwal', 'pesankan', 'pesenin', 'jadwalkan', 'jadwalin',
        'mau daftar', 'mau berkunjung', 'rencana berkunjung', 'mau datang',
        'mau ketemu', 'pengen ketemu', 'ingin ketemu', 'mau sowan', 'mau audiensi',
        'reservasi', 'booking', 'bisa tolong daftarin', 'bisa daftarin',
        'bisa tidak membuatkan', 'bisa membuatkan', 'bisa buatkan',
        'tolong buat', 'tolong daftar', 'tolong daftarin', 'bikin kunjungan',
    )
    if not is_unsatisfied and not is_reschedule_cancel_word and (has_active_draft or any(k in txt_norm for k in booking_override_keywords)):
        intent = 'buat_kunjungan'
        n8n_wants_handoff = False

    # Hitung strike jika AI tidak bisa menjawab (di_luar_konteks) atau Tamu kurang suka jawaban AI
    strike_key = f"ai_strike_count_{sess_key}"
    strike_count = int(safe_cache_get(strike_key, 0) or 0)
    is_strike = is_unsatisfied or ('luar_konteks' in intent) or bool(n8n_res.get('cannot_answer')) or (n8n_wants_handoff and 'keluhan' not in intent and 'masukan' not in intent)
    handoff = False

    if is_strike:
        strike_count += 1
        safe_cache_set(strike_key, strike_count, timeout=3600)
        if strike_count >= AI_MAX_STRIKES:
            handoff = True
            set_session_handoff_to_admin(sess_key, active=True)
            auto_handoff_text = (
                "🤖 Asisten AI Diskominfosantik:\n"
                "🔄 [Dialihkan Otomatis ke Petugas Admin]\n"
                "Mohon maaf karena Asisten AI belum dapat memberikan jawaban yang sesuai "
                f"setelah {AI_MAX_STRIKES} kali percobaan ({AI_MAX_STRIKES}/{AI_MAX_STRIKES}).\n\n"
                "Saat ini percakapan Anda telah dialihkan langsung ke Petugas Admin Diskominfosantik. "
                "Silakan tulis pesan Anda, Admin kami akan segera membalas langsung di ruang chat ini."
            )
            return {
                'intent': intent,
                'reply_text': auto_handoff_text,
                'handoff': True,
                'strike_count': strike_count,
            }

    status_labels = {
        'menunggu_admin': '⏳ Menunggu Verifikasi Admin',
        'menunggu_pegawai': '⏳ Menunggu Persetujuan Pegawai',
        'disetujui_pegawai': '⏳ Disetujui Pegawai (Menunggu ACC Admin)',
        'ditolak_pegawai': '❌ Ditolak oleh Pegawai',
        'ditolak_admin': '❌ Ditolak oleh Admin',
        'disetujui': '✅ Disetujui (Tiket Kunjungan Aktif)',
        'in_progress': '🔵 Sedang Berlangsung',
        'completed': '✅ Selesai',
        'cancelled': '🚫 Dibatalkan',
    }

    sections = []

    reschedule_or_cancel_words = (
        'ubah jadwal', 'ganti jam', 'ganti jadwal', 'ganti hari', 'reschedule',
        'undur', 'geser', 'pindah jam', 'pindah hari', 'ubah jam', 'rubah',
        'batalkan kunjungan', 'batalkan janji temu', 'batal janji', 'batalkan tiket',
        'cancel kunjungan', 'batal kunjungan', 'batalin kunjungan', 'batalin tiket',
        'gak jadi datang', 'tidak jadi datang', 'batal datang', 'cancel tiket',
        'batalkan jadwal', 'batal jadwal', 'batalin jadwal', 'batalkan', 'batalin'
    )
    is_reschedule_cancel_query = (
        'ubah_jadwal' in intent or 'batal' in intent
        or (not has_active_draft and _fuzzy_keyword_match(txt_norm, reschedule_or_cancel_words))
    )

    is_pejabat_direct = any(k in txt_norm for k in (
        'kepala dinas', 'kadis', 'pimpinan dinas', 'pimpinan kominfo', 'pimpinan diskominfosantik',
        'nama kepala dinas', 'siapa kadis', 'siapa kepala dinas', 'siapa pimpinan', 'kepala diskominfosantik',
        'kabid', 'kepala bidang', 'siapa kabid', 'sekretaris dinas', 'sekdis', 'siapa sekdis',
        'struktur organisasi', 'bagan organisasi', 'susunan organisasi', 'susunan pejabat',
        'profil pejabat', 'daftar pejabat', 'hierarki dinas', 'pejabat dinas', 'pejabat diskominfosantik',
        'siapa saja pejabat', 'siapa saja pimpinan'
    ))
    is_staf_check = (
        any(k in txt_norm for k in (
            'staf yang menangani', 'petugas yang menangani', 'yang menangani jaringan',
            'yang ngurus jaringan', 'siapa staf', 'siapa teknisi', 'siapa admin jaringan',
            'staf jaringan', 'petugas jaringan', 'teknisi jaringan', 'teknisi wifi',
            'staf siber', 'staf csirt', 'staf ikp', 'staf magang'
        ))
        or ('siapa' in txt_norm and any(k in txt_norm for k in ('staf', 'petugas', 'teknisi', 'pejabat')))
    )
    is_pejabat_query = (
        'pejabat' in intent or 'struktur' in intent
        or (not has_active_draft and not any(k in txt_norm for k in booking_override_keywords) and (is_pejabat_direct or is_staf_check))
    )

    sop_check_words = (
        'tte', 'bsre', 'tanda tangan elektronik', 'tanda tangan digital', 'sertifikat elektronik',
        'subdomain', 'hosting', 'server opd', 'vps opd', 'data center opd',
        'magang', 'pkl', 'prakerin', 'praktik kerja', 'kerja praktek',
        'liputan', 'wartawan', 'kartu pers', 'ppid', 'informasi publik',
        'csirt', 'keamanan siber', 'keamanan informasi', 'insiden siber', 'kena hack', 'dihack', 'judi online', 'judol', 'deface', 'defacement', 'pentest', 'kerentanan', 'kebocoran data',
        'wifi', 'wi-fi', 'intranet', 'fiber optic', 'kabel fo', 'bandwidth', 'jaringan putus', 'wifi mati', 'koneksi lambat', 'internet kecamatan', 'wifi publik', 'akses internet',
        'lapor', 'span lapor', 'sp4n lapor', 'pengaduan masyarakat', 'lapor jalan rusak', 'keluhan warga', 'aspirasi warga',
        'statistik', 'data statistik', 'satu data', 'statistik sektoral', 'data kemiskinan', 'data kependudukan', 'minta data', 'permohonan data', 'data bekasi', 'data sektoral',
        'berapa lama', 'berapa hari', 'durasi pelayanan', 'durasi pengurusan', 'estimasi waktu',
        'standar waktu', 'sla', 'service level agreement', 'lama proses', 'waktu proses',
        'lama penyelesaian', 'waktu penyelesaian', 'lama pengerjaan', 'kapan selesai', 'kapan jadi',
        'kapan beres', 'kapan kelar', 'target waktu', 'lama verifikasi', 'berapa hari kerja'
    )
    is_sop_query = (
        'sop' in intent or 'teknis' in intent
        or (not has_active_draft and not any(k in txt_norm for k in booking_override_keywords) and _fuzzy_keyword_match(txt_norm, sop_check_words))
    )

    # ── 0a. Cabang: buat_kunjungan (Prioritas utama jika tamu melakukan pemesanan jadwal) ──
    if 'buat_kunjungan' in intent:
        direct_booking_reply = _try_create_kunjungan_from_chat(
            tamu=tamu,
            message_text=message_text,
            n8n_res=n8n_res,
            pegawai_qs=pegawai_qs,
        )
        if direct_booking_reply:
            return {
                'intent': 'buat_kunjungan',
                'reply_text': direct_booking_reply,
                'handoff': False,
                'strike_count': strike_count,
            }

        rec_peg = None
        if n8n_res.get('pegawai_id'):
            rec_peg = next((p for p in pegawai_qs if str(p.id) == str(n8n_res['pegawai_id'])), None)
        bidang_rec = n8n_res.get('bidang')
        rec_lines = [
            "🤖 Asisten AI Diskominfosantik:\n"
            "Untuk mengajukan jadwal kunjungan baru, silakan ikuti panduan berikut:"
        ]
        if rec_peg:
            b_name = rec_peg.department_rel.nama if rec_peg.department_rel else (rec_peg.department or '-')
            rec_lines.append(
                f"✨ **Rekomendasi Tujuan:**\n"
                f"   • Pegawai : **{rec_peg.name}**\n"
                f"   • Bidang : {b_name}"
            )
        elif bidang_rec:
            rec_lines.append(f"✨ **Rekomendasi Bidang Tujuan:** {bidang_rec}")
        rec_lines.append(
            "⚡ **Daftar Langsung Lewat Chat Ini:**\n"
            "   Ketik langsung rencana kunjungan Anda, contoh:\n"
            "   *\"Buatkan saya daftar kunjungan untuk hari Senin jam 09:00 keperluan rapat koordinasi\"*\n\n"
            "📝 **Atau Melalui Formulir Buku Tamu:**\n"
            "   1. Klik menu **Buku Tamu** di sidebar kiri.\n"
            "   2. Pilih **Tanggal & Jam** kedatangan serta **Pegawai Tujuan**.\n"
            "   3. Tulis keperluan kunjungan Anda lalu kirim."
        )
        sections.append("\n\n".join(rec_lines))

    # ── 0b. Cabang: ubah_jadwal_dan_batal (Reschedule & Batal langsung via Chat) ──
    elif is_reschedule_cancel_query:
        reschedule_reply = _handle_reschedule_or_cancel_from_chat(tamu=tamu, message_text=message_text)
        return {
            'intent': 'ubah_jadwal_dan_batal',
            'reply_text': reschedule_reply,
            'handoff': False,
            'strike_count': strike_count,
        }

    # ── 0b2. Cabang: pejabat_dan_struktur (Direktori Profil Pejabat & Struktur Organisasi Dinas) ──
    elif is_pejabat_query:
        pejabat_reply = _handle_pejabat_dan_struktur(
            message_text=message_text,
            pegawai_qs=pegawai_qs,
        )
        return {
            'intent': 'pejabat_dan_struktur',
            'reply_text': pejabat_reply,
            'handoff': False,
            'strike_count': strike_count,
        }

    # ── 0c. Cabang: sop_dan_layanan_teknis (Knowledge Base Kedinasan & Action Chips) ──
    elif is_sop_query:
        active_top = n8n_res.get('active_topic') if isinstance(n8n_res, dict) else None
        is_fol = bool(n8n_res.get('is_followup')) if isinstance(n8n_res, dict) else False
        sop_reply = _handle_sop_knowledge_base(
            message_text=message_text,
            session_id=sess_key,
            active_topic=active_top,
            is_followup=is_fol,
        )
        return {
            'intent': 'sop_dan_layanan_teknis',
            'reply_text': sop_reply,
            'handoff': False,
            'strike_count': strike_count,
        }

    # ── 1. Cabang: cek_status_kunjungan ───────────────────────────────────────
    elif 'cek_status' in intent or 'status' in intent:
        sections.append("🤖 Asisten AI Diskominfosantik:\nBerikut adalah informasi status kunjungan terbaru Anda dari sistem:")
        visits = list(
            Kunjungan.objects.filter(tamu_id=tamu_id)
            .select_related('pegawai', 'pegawai__department_rel')
            .order_by('-created_at')[:3]
        )
        if visits:
            visit_blocks = ["📋 **Data Status Kunjungan Anda:**"]
            for idx, v in enumerate(visits, start=1):
                tgl = timezone.localtime(v.arrival_time).strftime('%d/%m/%Y (%H:%M WIB)') if v.arrival_time else '-'
                peg_name = v.pegawai.name if v.pegawai else 'Belum ditentukan'
                keperluan = (v.purpose or '-').strip()
                if len(keperluan) > 45:
                    keperluan = keperluan[:42] + '...'
                st_label = status_labels.get(v.status, v.status)
                visit_blocks.append(
                    f"**{idx}. Kunjungan #{idx}**\n"
                    f"   • Jadwal : {tgl}\n"
                    f"   • Pegawai : {peg_name}\n"
                    f"   • Keperluan : {keperluan}\n"
                    f"   • Status : **{st_label}**"
                )
            sections.append("\n\n".join(visit_blocks))
        else:
            sections.append("📋 Saat ini Anda belum memiliki riwayat pengajuan kunjungan yang terdaftar.")

    # ── 2. Cabang: jadwal_kuota ───────────────────────────────────────────────
    elif 'jadwal' in intent or 'kuota' in intent:
        instansi = Instansi.objects.first()
        jam_buka = instansi.jam_buka.strftime('%H:%M') if instansi and instansi.jam_buka else '08:00'
        jam_tutup = instansi.jam_tutup.strftime('%H:%M') if instansi and instansi.jam_tutup else '16:00'

        target_date = n8n_res.get('tanggal') or n8n_res.get('date')
        try:
            quota_info = get_daily_quota_info(target_date if target_date else timezone.localdate())
        except Exception:
            quota_info = get_daily_quota_info(timezone.localdate())

        tgl_str = quota_info['date'].strftime('%d/%m/%Y')
        if quota_info['is_holiday']:
            kuota_line = f"🔴 Libur ({quota_info['holiday_name'] or 'Hari Libur'})"
        else:
            kuota_line = f"🟢 Tersedia **{quota_info['available']}** dari **{quota_info['quota']}** kuota (Terisi: {quota_info['booked']})"

        is_weekend_question = (
            any(w in txt_lower for w in ('sabtu', 'minggu', 'weekend', 'akhir pekan'))
            or ('libur' in txt_lower and any(w in txt_lower for w in ('kan', 'ya', 'buka', 'tutup', 'apakah', 'berarti', 'gak', 'nggak', 'bisa')))
        )
        is_today_question = any(w in txt_lower for w in ('hari ini', 'sekarang', 'saat ini'))
        is_quota_only_question = any(w in txt_lower for w in ('sisa kuota', 'kuota', 'slot')) and not is_weekend_question

        day_names = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']
        day_name = day_names[quota_info['date'].weekday()]

        if is_weekend_question:
            schedule_reply = (
                "🤖 Asisten AI Diskominfosantik:\n"
                "**Betul sekali!** Kantor Diskominfosantik Kabupaten Bekasi **tutup / libur pada akhir pekan (hari Sabtu dan Minggu)** serta pada hari libur nasional / tanggal merah.\n\n"
                "Pelayanan tatap muka dan penerimaan kunjungan tamu hanya dibuka pada hari kerja:\n\n"
                f"🕒 **Jam Operasional:**\n"
                f"   • Hari : Senin – Jumat\n"
                f"   • Pukul : {jam_buka} – {jam_tutup} WIB\n\n"
                f"📊 **Status Kuota ({tgl_str}):**\n"
                f"   • {kuota_line}\n\n"
                "💡 *Saran: Jika Anda memiliki keperluan koordinasi atau konsultasi kedinasan, silakan jadwalkan kunjungan pada hari kerja berikutnya (hari Senin). "
                "Apakah Anda ingin saya bantu buatkan jadwal kunjungan untuk hari Senin?*"
            )
        elif is_today_question:
            if quota_info['is_holiday']:
                schedule_reply = (
                    "🤖 Asisten AI Diskominfosantik:\n"
                    f"Untuk hari ini (**{day_name}, {tgl_str}**), kantor Diskominfosantik Kabupaten Bekasi **sedang libur** ({quota_info['holiday_name'] or 'Hari Libur'}).\n\n"
                    f"Pelayanan tatap muka kami akan kembali dibuka pada hari kerja berikutnya mulai pukul {jam_buka} WIB.\n\n"
                    f"🕒 **Jam Operasional:**\n"
                    f"   • Hari : Senin – Jumat\n"
                    f"   • Pukul : {jam_buka} – {jam_tutup} WIB\n\n"
                    f"📊 **Status Kuota ({tgl_str}):**\n"
                    f"   • {kuota_line}\n\n"
                    "💡 *Silakan pilih tanggal pada hari kerja berikutnya jika Anda ingin mengajukan kunjungan baru.*"
                )
            else:
                schedule_reply = (
                    "🤖 Asisten AI Diskominfosantik:\n"
                    f"Hari ini (**{day_name}, {tgl_str}**), kantor Diskominfosantik Kabupaten Bekasi **buka dan beroperasi** melayani kunjungan tamu.\n\n"
                    f"🕒 **Jam Operasional:**\n"
                    f"   • Hari : Senin – Jumat\n"
                    f"   • Pukul : {jam_buka} – {jam_tutup} WIB\n\n"
                    f"📊 **Status Kuota ({tgl_str}):**\n"
                    f"   • {kuota_line}\n\n"
                    "💡 *Pastikan Anda telah mengisi formulir kunjungan atau bisa langsung meminta saya untuk mendaftarkan jadwal Anda.*"
                )
        elif is_quota_only_question:
            schedule_reply = (
                "🤖 Asisten AI Diskominfosantik:\n"
                f"Berikut adalah informasi kuota kunjungan Diskominfosantik Kab. Bekasi untuk tanggal **{tgl_str}**:\n\n"
                f"📊 **Status Kuota ({tgl_str}):**\n"
                f"   • {kuota_line}\n\n"
                f"🕒 **Jam Operasional:**\n"
                f"   • Hari : Senin – Jumat\n"
                f"   • Pukul : {jam_buka} – {jam_tutup} WIB\n\n"
                "💡 *Kuota kunjungan diperbarui secara real-time. Anda dapat langsung mengajukan kunjungan melalui menu **Buku Tamu** atau meminta saya membuatkannya.*"
            )
        else:
            schedule_reply = (
                "🤖 Asisten AI Diskominfosantik:\n"
                "Berikut informasi jadwal operasional dan kuota kunjungan Diskominfosantik Kab. Bekasi:\n\n"
                f"🕒 **Jam Operasional:**\n"
                f"   • Hari : Senin – Jumat\n"
                f"   • Pukul : {jam_buka} – {jam_tutup} WIB\n"
                f"   • Hari Sabtu, Minggu & Libur Nasional : **Tutup / Libur**\n\n"
                f"📊 **Status Kuota ({tgl_str}):**\n"
                f"   • {kuota_line}\n\n"
                "💡 *Ada tanggal atau keperluan tertentu yang ingin Anda jadwalkan?*"
            )
        sections.append(schedule_reply)

    # ── 3. Cabang: info_layanan_dan_pegawai ────────────────────────────────────
    elif 'info_layanan' in intent or 'layanan' in intent or 'pegawai' in intent:
        prefix = "🤖 Asisten AI Diskominfosantik:\n"
        is_address_query = any(w in txt_lower for w in ('alamat', 'lokasi', 'di mana', 'dimana', 'gedung', 'daerah', 'rute', 'maps', 'peta', 'google maps'))
        is_req_query = any(w in txt_lower for w in ('syarat', 'persyaratan', 'bawa apa', 'berkas', 'dokumen'))

        if is_address_query:
            sections.append(
                f"{prefix}"
                "📍 **Alamat & Lokasi Kantor Diskominfosantik Kabupaten Bekasi:**\n\n"
                "Kompleks Perkantoran Pemerintah Kabupaten Bekasi, Gedung Diskominfosantik, Blok B\n"
                "Desa Sukamahi, Kecamatan Cikarang Pusat, Kabupaten Bekasi, Jawa Barat 17530.\n\n"
                "🗺️ **Petunjuk Arah Google Maps:**\n"
                "[Buka Rute di Google Maps](https://www.google.com/maps/search/?api=1&query=Diskominfosantik+Kabupaten+Bekasi)\n\n"
                "🕒 **Waktu Layanan Tatap Muka:**\n"
                "Senin – Jumat, pukul 08:00 – 16:00 WIB (Hari Sabtu, Minggu & Hari Libur Nasional Tutup).\n\n"
                "💡 *Patokan: Berada di kawasan pusat pemerintahan Pemkab Bekasi (Delta Mas / Cikarang Pusat).*"
            )
        elif is_req_query:
            sections.append(
                f"{prefix}"
                "📋 **Persyaratan Kunjungan ke Diskominfosantik Kab. Bekasi:**\n\n"
                "1. 🆔 **Identitas Diri**: Membawa KTP / SIM / Kartu Identitas resmi yang masih berlaku.\n"
                "2. 📄 **Surat Tugas / Pengantar**: Wajib untuk kunjungan dinas, koordinasi lembaga, atau studi banding.\n"
                "3. 🎫 **Kode Tiket**: Menunjukkan bukti atau kode tiket kunjungan yang diperoleh setelah mendaftar di sistem ini.\n"
                "4. 👔 **Tata Tertib**: Berpakaian rapi, sopan (berkerah), dan bersepatu.\n\n"
                "Pelayanan tatap muka dibuka setiap hari kerja (Senin – Jumat, pukul 08:00 – 16:00 WIB)."
            )
        else:
            rec_targeted = recommend_pegawai_by_purpose(message_text, pegawai_qs=pegawai_qs)
            sec_parts = []
            if ai_reply and not ai_reply.startswith("Berikut informasi jadwal"):
                sec_parts.append(f"{prefix}{ai_reply}" if not ai_reply.startswith("🤖") else ai_reply)
            else:
                sec_parts.append(f"{prefix}Berikut daftar bidang dan pegawai layanan aktif di Diskominfosantik Kab. Bekasi:")

            if rec_targeted:
                b_name = rec_targeted.department_rel.nama if rec_targeted.department_rel else (rec_targeted.department or '-')
                sec_parts.append(
                    f"🎯 **Rekomendasi Pegawai Tujuan (Otomatis oleh AI):**\n"
                    f"Berdasarkan pertanyaan / topik Anda, pegawai yang paling tepat untuk ditemui adalah:\n"
                    f"• **{rec_targeted.name}**\n"
                    f"  Jabatan : {rec_targeted.jabatan or 'Pegawai'} ({b_name})\n\n"
                    f"💡 *Ingin langsung dibuatkan jadwal kunjungan? Silakan ketik:*\n"
                    f"*\"Buatkan saya kunjungan untuk hari Senin jam 10:00 dengan {rec_targeted.name}\"*"
                )

            bidang_filter = (n8n_res.get('bidang') or '').strip()
            depts = list(Departemen.objects.all().order_by('nama'))
            if bidang_filter:
                matched_peg = [
                    p for p in pegawai_qs
                    if bidang_filter.lower() in (p.department_rel.nama.lower() if p.department_rel else '')
                    or bidang_filter.lower() in (p.name.lower())
                ][:5]
            else:
                matched_peg = list(pegawai_qs[:5])

            dept_names = ", ".join(d.nama for d in depts) if depts else "Umum, TIK, Persandian, Statistik, IKP"
            info_lines = [
                f"🏢 **Bidang Layanan:**\n   {dept_names}"
            ]
            if matched_peg and not rec_targeted:
                peg_lines = ["👔 **Daftar Pegawai Aktif:**"]
                for idx, p in enumerate(matched_peg, start=1):
                    b_name = p.department_rel.nama if p.department_rel else (p.department or '-')
                    peg_lines.append(
                        f"   {idx}. **{p.name}**\n"
                        f"      Jabatan: {p.jabatan or 'Pegawai'} ({b_name})"
                    )
                info_lines.append("\n".join(peg_lines))
            sec_parts.append("\n\n".join(info_lines))
            sections.append("\n\n".join(sec_parts))

    # ── 5. Cabang: keluhan_dan_masukan ────────────────────────────────────────
    elif 'keluhan' in intent or 'masukan' in intent:
        handoff = True
        set_session_handoff_to_admin(sess_key, active=True)
        try:
            from .models import Message
            Message.objects.create(
                sender_id=str(tamu_id),
                sender_type='tamu',
                subject=f"Keluhan/Masukan via Chat AI ({timezone.localdate().strftime('%d/%m/%Y')})",
                content=message_text,
                status='pending',
            )
        except Exception as msg_err:
            logger.warning("Gagal menyimpan pesan keluhan ke Message: %s", msg_err)
        sections.append(
            "🤖 Asisten AI Diskominfosantik:\n"
            "Terima kasih atas masukan/kendala yang Anda sampaikan. Pesan Anda telah kami catat "
            "dan diteruskan ke petugas Admin Diskominfosantik kami.\n\n"
            "💬 **Pusat Bantuan & Layanan Pengaduan:**\n"
            "Admin kami akan segera merespon langsung di ruang chat ini."
        )

    # ── 6. Cabang: sapaan & basa-basi ─────────────────────────────────────────
    elif 'sapaan' in intent or 'terima_kasih' in intent or 'konfirmasi' in intent:
        if ai_reply:
            sections.append(ai_reply if ai_reply.startswith("🤖") else f"🤖 Asisten AI Diskominfosantik:\n{ai_reply}")
        else:
            sections.append(
                "🤖 Asisten AI Diskominfosantik:\n"
                "Halo! 👋 Selamat datang di Layanan Buku Tamu Digital Diskominfosantik Kab. Bekasi. Ada yang bisa saya bantu?"
            )

    # ── 7. Cabang: di_luar_konteks ────────────────────────────────────────────
    else:
        remaining = AI_MAX_STRIKES - strike_count
        msg_out = ai_reply if ai_reply else (
            "Mohon maaf, saya belum memahami pertanyaan Anda. Saya adalah Asisten AI untuk layanan "
            "Buku Tamu Digital Diskominfosantik Kab. Bekasi.\n\n"
            "Anda dapat menanyakan hal seputar:\n"
            "• *Cek Status Kunjungan*\n"
            "• *Jadwal Operasional & Kuota Kunjungan*\n"
            "• *Informasi Bidang & Pegawai Tujuan*\n"
            "• *Pendaftaran Jadwal Kunjungan Baru*\n"
            "• *Alamat Kantor & Persyaratan Berkunjung*"
        )
        if not msg_out.startswith("🤖"):
            msg_out = f"🤖 Asisten AI Diskominfosantik:\n{msg_out}"
        sections.append(msg_out)
        if remaining > 0:
            sections.append(
                f"💡 *Tips: Jika Anda ingin langsung terhubung dengan petugas kami, silakan ketik \"Bicara dengan Admin\" ya. (Bantuan AI: {remaining}x kesempatan sebelum otomatis dialihkan ke admin)*"
            )

    full_reply = "\n\n".join(sections)
    return {
        'intent': intent,
        'reply_text': full_reply,
        'handoff': handoff,
        'strike_count': strike_count,
    }


def process_n8n_chat_assistant(session_id, tamu_id, message_text, room_group_name):
    """
    Worker yang dipanggil di thread latar belakang untuk memproses pesan tamu
    lewat N8N AI Assistant dan menyiarkan jawabannya ke WebSocket.
    """
    from .models import ChatMessage
    from asgiref.sync import async_to_sync
    from channels.layers import get_channel_layer

    try:
        res = build_n8n_chat_response(tamu_id, message_text, session_id=session_id)
        reply_text = res.get('reply_text')
        if not reply_text:
            return

        chat_msg = ChatMessage.objects.create(
            session_id=session_id,
            sender_id='admin',
            sender_type='admin',
            message_type='text',
            content=reply_text,
        )

        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                room_group_name,
                {
                    'type': 'chat_message',
                    'message_id': str(chat_msg.id),
                    'message': reply_text,
                    'sender_id': 'admin',
                    'sender_type': 'admin',
                    'message_type': 'text',
                    'file_url': None,
                    'created_at': timezone.localtime(chat_msg.created_at).strftime('%H:%M'),
                    'handoff_active': bool(res.get('handoff')),
                }
            )
    except Exception as e:
        logger.exception("Error saat memproses N8N Chat Assistant: %s", e)
