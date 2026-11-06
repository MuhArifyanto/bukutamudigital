from .models import Notification, Tamu, Kunjungan, ChatMessage

def notifications_context(request):
    """
    Context processor untuk badge notifikasi di navbar.

    Urutan pengecekan:
    1. Admin via Django Auth (Staff)       → query notifikasi admin
    2. Tamu admin via session (is_admin)   → query notifikasi admin
    3. Tamu biasa via request._tamu        → pakai objek dari decorator, 0 query DB
    4. Tamu biasa via session (fallback)   → 1 query DB jika _tamu tidak tersedia
    5. Tidak login                         → return {}

    Untuk kasus (3): base_context() di view sudah mengisi
    'unread_notifications_count' sehingga kita cukup return {}.
    Untuk kasus (4): sama, return {} — base_context() sudah handle.
    """

    # ── Admin via Django Auth (Staff) ────────────────────────────────────
    if request.user.is_authenticated and request.user.is_staff:
        unread_count = Notification.objects.filter(
            recipient_type='admin', status='unread'
        ).count()
        return {'unread_notifications_count': unread_count}

    tamu_id = request.session.get('tamu_id')
    if not tamu_id:
        return {}

    # ── Cek apakah decorator sudah menitipkan objek tamu di request ──────
    tamu = getattr(request, '_tamu', None)

    if tamu is None:
        # Fallback: halaman yang tidak pakai @tamu_login_required
        # (misal: landing, tentang kami) — query 1x sebagai pengaman
        tamu = Tamu.objects.filter(pk=tamu_id).first()
        if tamu is None:
            return {}

    # ── Tamu dengan role admin ───────────────────────────────────────────
    if tamu.nik == 'admin' or tamu.is_admin:
        unread_count = Notification.objects.filter(
            recipient_type='admin', status='unread'
        ).count()
        return {'unread_notifications_count': unread_count}

    # ── Tamu biasa ───────────────────────────────────────────────────────
    # base_context() di view sudah mengisi 'unread_notifications_count'.
    # Kembalikan dict kosong — tidak ada query tambahan.
    return {}

def pegawai_notifications_context(request):
    """
    Context processor untuk badge notifikasi & counter sidebar di Portal Pegawai.
    """
    pegawai = getattr(request, '_pegawai', None)
    if not pegawai:
        return {}

    pegawai_id_str = str(pegawai.id)

    unread_count = Notification.objects.filter(
        recipient_id=pegawai_id_str,
        recipient_type='pegawai',
        status='unread'
    ).count()

    pending_kunjungan_count = Kunjungan.objects.filter(
        pegawai=pegawai,
        status='menunggu_pegawai'
    ).count()

    # Hitung pesan chat belum dibaca untuk pegawai ini (dari Admin maupun Tamu)
    kunjungan_ids = list(
        Kunjungan.objects.filter(
            pegawai=pegawai,
            status__in=['disetujui_pegawai', 'disetujui', 'in_progress', 'completed']
        ).values_list('id', flat=True)
    )
    chat_sessions = [f'pegawai_admin_{pegawai_id_str}'] + [f'kunjungan_{kid}' for kid in kunjungan_ids]
    unread_chat_count = ChatMessage.objects.filter(
        session_id__in=chat_sessions,
        is_read=False
    ).exclude(sender_type='pegawai').count()

    return {
        'pegawai_unread_count': unread_count,
        'pegawai_pending_kunjungan_count': pending_kunjungan_count,
        'pegawai_unread_chat_count': unread_chat_count,
    }
