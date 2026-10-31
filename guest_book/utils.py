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
            group_name = 'admin_notifications' if recipient_type == 'admin' else f"notifications_{recipient_type}_{recipient_id}"
            async_to_sync(channel_layer.group_send)(
                group_name,
                {
                    'type': 'notification_message',
                    'notification': {
                        'id': str(notif.id),
                        'title': notif.title,
                        'message': notif.message,
                        'created_at': notif.created_at.strftime('%H:%M'),
                        'notification_type': notif.notification_type,
                        'related_object_id': notif.related_object_id
                    }
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


def call_n8n_routing(kunjungan_id, purpose, department, arrival_time):
    """
    Memanggil Webhook N8N untuk Auto-Routing / Auto-Approval kunjungan.
    Dijalankan secara asynchronous (threading) agar tidak memperlambat respon user.

    Parameter:
        kunjungan_id (str): UUID kunjungan
        purpose (str): Keperluan kunjungan
        department (str): Nama departemen tujuan
        arrival_time (datetime): Waktu kedatangan

    Returns:
        dict | None: Response dari n8n webhook jika berhasil, None jika gagal / dinonaktifkan
    """
    webhook_url = os.getenv('N8N_WEBHOOK_URL')
    if not webhook_url:
        logger.debug("N8N_WEBHOOK_URL tidak dikonfigurasi. Auto-routing dilewati.")
        return None

    timeout_seconds = int(os.getenv('N8N_WEBHOOK_TIMEOUT', '5'))

    payload = {
        'kunjungan_id': str(kunjungan_id),
        'purpose': purpose,
        'department': department,
        'arrival_time': arrival_time.isoformat() if hasattr(arrival_time, 'isoformat') else str(arrival_time),
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


def _detect_user_intent_locally(message_text):
    """
    Deteksi intent lokal fallback jika N8N offline atau tidak merespon.
    Mengembalikan salah satu dari 6 cabang intent N8N dengan respon ramah dan kontekstual.
    """
    txt = (message_text or '').strip().lower()

    # 1. Basa-basi & Ucapan Terima Kasih (respon hangat, hindari strike)
    if any(k in txt for k in ('terima kasih', 'makasih', 'terimakasih', 'thanks', 'thx', 'nuhun', 'matur nuwun', 'makasi', 'tengkyu')):
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

    # 2. Persetujuan / Konfirmasi santai pengguna
    if txt in ('oke', 'ok', 'siap', 'baik', 'baiklah', 'sip', 'noted', 'siap min', 'siap kak', 'oke min', 'oke kak', 'ok min', 'ok kak', 'oke siap', 'siap makasih', 'oke makasih'):
        return {
            'intent': 'sapaan',
            'reply': (
                "Baik, terima kasih! 👍\n"
                "Silakan beri tahu saya jika ada hal lain yang ingin Anda konsultasikan atau tanyakan seputar kunjungan."
            ),
            'handoff': False,
        }

    # 3. Sapaan umum
    if any(k in txt for k in ('halo', 'hai', 'hi', 'assalamu', 'selamat pagi', 'selamat siang', 'selamat sore', 'pagi', 'siang', 'sore', 'malam')):
        return {
            'intent': 'sapaan',
            'reply': (
                "Halo! 👋 Selamat datang di Layanan Buku Tamu Digital Diskominfosantik Kab. Bekasi.\n"
                "Saya Asisten AI yang siap membantu Anda mengecek status kunjungan, informasi jadwal & kuota, "
                "layanan dinas, atau membuat jadwal kunjungan baru. Ada yang bisa saya bantu?"
            ),
            'handoff': False,
        }

    # 4. Status Kunjungan
    if any(k in txt for k in ('status', 'cek kunjungan', 'tiket', 'antrian', 'kunjungan saya', 'sudah diacc', 'sudah acc', 'disetujui belum')):
        return {
            'intent': 'cek_status_kunjungan',
            'reply': "Berikut adalah informasi status kunjungan terbaru Anda dari sistem:",
            'handoff': False,
        }

    # 5. Jadwal, Kuota & Hari Operasional (termasuk pertanyaan Sabtu/Minggu/Libur)
    if any(k in txt for k in (
        'jadwal', 'kuota', 'slot', 'buka jam', 'tutup jam', 'jam operasional', 'hari apa',
        'hari kerja', 'libur', 'sabtu', 'minggu', 'weekend', 'akhir pekan', 'tanggal merah',
        'hari ini buka', 'bisa datang hari ini', 'sekarang buka'
    )):
        return {
            'intent': 'jadwal_kuota',
            'reply': "Berikut informasi jadwal operasional dan kuota kunjungan Diskominfosantik Kab. Bekasi:",
            'handoff': False,
        }

    # 6. Alamat / Lokasi Kantor
    if any(k in txt for k in ('alamat', 'lokasi', 'dimana kantor', 'di mana kantor', 'gedung mana', 'daerah mana', 'rute')):
        return {
            'intent': 'info_layanan_dan_pegawai',
            'reply': (
                "📍 **Alamat & Lokasi Kantor Diskominfosantik Kabupaten Bekasi:**\n\n"
                "Kompleks Perkantoran Pemerintah Kabupaten Bekasi, Gedung Diskominfosantik, Blok B\n"
                "Desa Sukamahi, Kecamatan Cikarang Pusat, Kabupaten Bekasi, Jawa Barat 17530.\n\n"
                "🕒 **Waktu Layanan Tatap Muka:**\n"
                "Senin – Jumat, pukul 08:00 – 16:00 WIB (Hari Sabtu, Minggu & Hari Libur Nasional Tutup).\n\n"
                "💡 *Patokan: Berada di kawasan pusat pemerintahan Pemkab Bekasi (Delta Mas / Cikarang Pusat).*"
            ),
            'handoff': False,
        }

    # 7. Persyaratan Kunjungan / Berkas
    if any(k in txt for k in ('syarat', 'persyaratan', 'bawa apa', 'berkas apa', 'dokumen apa', 'dokumen yang harus')):
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

    # 8. Pendaftaran Kunjungan Baru
    if any(k in txt for k in ('buatkan', 'daftarkan', 'daftar kunjungan', 'buat kunjungan', 'bikin jadwal', 'bikin kunjungan', 'jadwalkan', 'pesan jadwal')):
        return {
            'intent': 'buat_kunjungan',
            'reply': (
                "Untuk mengajukan jadwal kunjungan baru, silakan ikuti panduan berikut:\n\n"
                "📝 **Langkah Pengajuan Kunjungan:**\n"
                "1. Buka menu **Buku Tamu** pada menu navigasi samping.\n"
                "2. Pilih **Tanggal dan Waktu** kedatangan yang diinginkan.\n"
                "3. Pilih **Pegawai / Bidang Tujuan** serta isi keperluan kunjungan Anda.\n"
                "4. Klik tombol **Kirim Pengajuan**.\n\n"
                "💡 *Tips: Pengajuan kunjungan minimal 1 hari kerja sebelumnya agar pegawai dapat mengonfirmasi ketersediaan jadwal.*"
            ),
            'handoff': False,
        }

    # 9. Informasi Pegawai & Bidang Layanan
    if any(k in txt for k in ('pegawai', 'bidang', 'layanan', 'dinas', 'siapa saja', 'kontak', 'tik', 'persandian', 'statistik', 'ikp')):
        return {
            'intent': 'info_layanan_dan_pegawai',
            'reply': "Berikut daftar bidang dan pegawai layanan aktif di Diskominfosantik Kab. Bekasi:",
            'handoff': False,
        }

    # 10. Pengaduan & Keluhan
    if any(k in txt for k in ('keluhan', 'komplain', 'kendala', 'masukan', 'saran', 'masalah', 'tidak bisa', 'error', 'bantuan admin', 'bicara admin', 'operator', 'antrean', 'antri', 'lama', 'loket')):
        return {
            'intent': 'keluhan_dan_masukan',
            'reply': (
                "Terima kasih atas masukan/kendala yang Anda sampaikan. Pesan Anda telah kami catat "
                "dan diteruskan ke petugas Admin Diskominfosantik kami."
            ),
            'handoff': True,
        }

    # 11. Di Luar Konteks (Fallback)
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
    txt = raw.lower()

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
        'buatkan', 'daftarkan', 'bikin jadwal', 'bikinkan', 'pesan jadwal',
        'jadwalkan', 'jadwalin', 'tolong buat', 'tolong daftar', 'mau daftar',
        'bisa tidak membuatkan', 'bisa membuatkan', 'bisa buatkan',
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
        r'(?:keperluan|tujuan|agenda|dalam rangka|untuk bahas|mengenai|tentang|konsultasi|rapat|koordinasi|audiensi|studi banding|peliputan|wawancara|pengadaan)\s*[:\-]?\s*(.+)$',
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

    # 2. Ekstrak / Rekomendasikan Pegawai Tujuan
    rec_peg = None
    is_ai_recommended = False
    if n8n_res.get('pegawai_id'):
        rec_peg = next((p for p in pegawai_qs if str(p.id) == str(n8n_res['pegawai_id'])), None)

    if not rec_peg and draft and draft.get('pegawai_id'):
        rec_peg = next((p for p in pegawai_qs if str(p.id) == str(draft['pegawai_id'])), None)

    if not rec_peg:
        # Cek dari nama langsung atau deteksi topik keperluan via AI Auto-Router
        combined_text = f"{raw} {purpose_str or ''}"
        rec_peg = recommend_pegawai_by_purpose(combined_text, pegawai_qs=pegawai_qs)
        if rec_peg:
            is_ai_recommended = True

    # Jika Jam atau Keperluan belum diisi oleh Tamu (tanya interaktif)
    if visit_hour is None or not purpose_str:
        safe_cache_set(draft_key, {
            'target_date': target_date.isoformat(),
            'hari_str': hari_str,
            'visit_hour': visit_hour,
            'visit_minute': visit_minute,
            'purpose': purpose_str,
            'pegawai_id': str(rec_peg.id) if rec_peg else None,
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
            missing_questions.append(f"• 🎯 **Pegawai Rekomendasi AI:** **{rec_peg.name}** ({rec_peg.jabatan or 'Pegawai'} - {dept_lbl})")
        else:
            q_num = len(missing_questions) + 1
            missing_questions.append(f"{q_num}. 👔 *(Opsional)* **Ingin bertemu dengan pegawai siapa atau bidang apa?** *(Bisa dikosongkan jika ingin AI yang merekomendasikan)*")

        q_text = "\n".join(missing_questions)
        ex_text = "*\"Jam 10:00 keperluan koordinasi jaringan internet\"*" if visit_hour is None else "*\"Keperluan konsultasi teknis SPBE\"*"

        return (
            "🤖 Asisten AI Diskominfosantik:\n"
            f"Tentu bisa! Untuk hari **{hari_str}, {target_date.strftime('%d/%m/%Y')}** kuota kunjungan masih tersedia "
            f"(tersedia **{avail} slot** dari total {total_q} kuota).\n\n"
            "Agar dapat saya daftarkan dan buatkan tiketnya ke dalam sistem, mohon informasikan:\n"
            f"{q_text}\n\n"
            f"💡 **Silakan balas di sini**, contoh:\n"
            f"{ex_text}\n\n"
            "Setelah Anda membalas, jadwal kunjungan akan langsung terdaftar di sistem!"
        )

    # Jika Jam dan Keperluan SUDAH LENGKAP -> Buat Kunjungan di Database
    arrival_dt = datetime.combine(target_date, dt_time(visit_hour, visit_minute), tzinfo=jakarta_tz)
    if target_date == today and arrival_dt <= now_local:
        bumped = now_local + timedelta(minutes=30)
        if bumped.hour < 16:
            arrival_dt = bumped.replace(second=0, microsecond=0)

    init_status = 'menunggu_pegawai' if rec_peg else 'menunggu_admin'
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
                f"Pesan Perintah Tamu: {raw}"
            ),
        )
        KunjunganStatusHistory.objects.create(
            kunjungan=kunjungan,
            old_status='menunggu_admin',
            new_status=init_status,
            changed_by_id=str(tamu.id),
            changed_by_type='tamu',
            notes='Kunjungan dibuat otomatis melalui interaksi Chat Asisten AI',
        )

    # Hapus draft setelah pendaftaran sukses
    safe_cache_delete(draft_key)

    # Kirim Notifikasi Real-Time ke Admin (dan Pegawai jika ada)
    try:
        send_notification(
            recipient_id='admin',
            recipient_type='admin',
            notification_type='visit_registered',
            title='Kunjungan Baru (via Chat AI)',
            message=f'Tamu {tamu.name} membuat jadwal kunjungan untuk {hari_str}, {arrival_dt.strftime("%d/%m/%Y %H:%M")} WIB via Asisten AI.',
            related_object_id=str(kunjungan.id),
        )
        if rec_peg:
            send_notification(
                recipient_id=str(rec_peg.id),
                recipient_type='pegawai',
                notification_type='visit_forwarded',
                title='Permintaan Kunjungan Baru',
                message=f'Tamu {tamu.name} menjadwalkan kunjungan dengan Anda pada {hari_str}, {arrival_dt.strftime("%d/%m/%Y %H:%M")} WIB.',
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
        status_display = f"⏳ **Menunggu Persetujuan Pegawai (Diteruskan ke {rec_peg.name})**"
    else:
        peg_display = "Menunggu Penugasan Admin"
        status_display = "⏳ Menunggu Verifikasi Admin"

    return (
        "🤖 Asisten AI Diskominfosantik:\n"
        "Siap! Saya telah mendaftarkan jadwal kunjungan Anda ke dalam sistem.\n\n"
        "✅ **Jadwal Kunjungan Berhasil Terdaftar:**\n"
        f"   • **Kode Tiket** : #{tiket_id}\n"
        f"   • **Hari / Tanggal** : **{hari_str}, {arrival_dt.strftime('%d/%m/%Y')}**\n"
        f"   • **Waktu Kedatangan** : **{arrival_dt.strftime('%H:%M')} WIB**\n"
        f"   • **Pegawai Tujuan** : {peg_display}\n"
        f"   • **Keperluan** : {purpose_str}\n"
        f"   • **Status Saat Ini** : {status_display}\n\n"
        "📌 Data kunjungan ini **sudah langsung masuk** ke menu **Dashboard** dan **Aktifitas** Anda!\n"
        "Admin dan Pegawai tujuan akan segera meninjau dan memverifikasi pengajuan Anda."
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
        n8n_res = _detect_user_intent_locally(message_text)

    # 3. Gabungkan respon N8N dengan data sistem & rule 3-Strike Handoff
    return _enrich_n8n_chat_assistant_response(tamu_id, message_text, n8n_res, sess_key)


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

    tamu = Tamu.objects.filter(id=tamu_id).first()
    pegawai_qs = list(
        Pegawai.objects.filter(account_status='active')
        .select_related('department_rel')
        .order_by('name')
    )

    txt_lower = (message_text or '').strip().lower()

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

    if not is_unsatisfied and any(k in txt_lower for k in (
        'buatkan', 'daftarkan', 'daftar kunjungan', 'buat kunjungan',
        'bikin jadwal', 'bikin kunjungan', 'jadwalkan', 'pesan jadwal',
        'bisa tidak membuatkan', 'bisa membuatkan', 'bisa buatkan',
    )):
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

    # ── 1. Cabang: cek_status_kunjungan ───────────────────────────────────────
    if 'cek_status' in intent or 'status' in intent:
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
        is_address_query = any(w in txt_lower for w in ('alamat', 'lokasi', 'di mana', 'dimana', 'gedung', 'daerah'))
        is_req_query = any(w in txt_lower for w in ('syarat', 'persyaratan', 'bawa apa', 'berkas', 'dokumen'))

        if is_address_query:
            sections.append(
                f"{prefix}"
                "📍 **Alamat & Lokasi Kantor Diskominfosantik Kabupaten Bekasi:**\n\n"
                "Kompleks Perkantoran Pemerintah Kabupaten Bekasi, Gedung Diskominfosantik, Blok B\n"
                "Desa Sukamahi, Kecamatan Cikarang Pusat, Kabupaten Bekasi, Jawa Barat 17530.\n\n"
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

    # ── 4. Cabang: buat_kunjungan ─────────────────────────────────────────────
    elif 'buat_kunjungan' in intent:
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
                f"💡 *(Catatan: Jika 3 kali pertanyaan belum sesuai, Anda akan otomatis terhubung ke Petugas Admin. Sisa kesempatan: {remaining}x)*"
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
