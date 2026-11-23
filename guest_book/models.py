from django.db import IntegrityError, models, transaction
from django.db.models import Count, Max, Q
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
import uuid

# ============================================================================
# SETTINGS MODELS (Instansi, Departemen)
# ============================================================================

class Instansi(models.Model):
    """Model untuk Pengaturan Instansi Utama"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nama = models.CharField(max_length=255, default='Diskominfosantik Kabupaten Bekasi')
    slogan = models.CharField(max_length=255, null=True, blank=True)
    status_operasional = models.CharField(max_length=50, default='Aktif')
    jumlah_petugas = models.IntegerField(default=8)
    kapasitas_maksimal = models.IntegerField(default=20)
    jam_buka = models.TimeField(default='08:00')
    jam_tutup = models.TimeField(default='16:00')
    alamat = models.TextField(null=True, blank=True)
    logo = models.URLField(null=True, blank=True)
    hari_kerja = models.CharField(max_length=50, default='0,1,2,3,4', null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'instansi'

    def __str__(self):
        return self.nama


class Departemen(models.Model):
    """Model untuk Daftar Departemen/Dinas"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    nama = models.CharField(max_length=255)
    kode = models.CharField(max_length=50, null=True, blank=True)
    deskripsi = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'departemen'
        verbose_name = 'Bidang / Bagian'
        verbose_name_plural = 'Daftar Bidang / Bagian'

    def __str__(self):
        return self.nama


# ============================================================================
# USER MODELS (Tamu, Pegawai, Admin)
# ============================================================================

class EncryptedNIKField(models.CharField):
    """Field CharField yang mengenkripsi NIK secara transparan di database."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('max_length', 255)
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        from .security_utils import decrypt_nik
        return decrypt_nik(value)

    def to_python(self, value):
        if value is None or not isinstance(value, str):
            return value
        from .security_utils import decrypt_nik, is_encrypted_token
        if is_encrypted_token(value):
            return decrypt_nik(value)
        return value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == '':
            return value
        from .security_utils import encrypt_nik
        return encrypt_nik(value)


class TamuQuerySet(models.QuerySet):
    """Jaga blind-index nik_hash tetap sinkron saat batch .update(nik=...)."""

    def update(self, **kwargs):
        if 'nik' in kwargs and 'nik_hash' not in kwargs:
            from .security_utils import hash_nik
            kwargs['nik_hash'] = hash_nik(kwargs['nik'])
        return super().update(**kwargs)


class Tamu(models.Model):
    """Model untuk Pengunjung/Tamu"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    ]
    
    REGISTRATION_TYPE_CHOICES = [
        ('manual', 'Manual Registration'),
        ('google_sso', 'Google SSO'),
    ]
    
    ADMIN_ROLE_CHOICES = [
        ('super_admin', 'Super Admin'),
        ('operator', 'Operator'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    nik = EncryptedNIKField(max_length=255, null=True, blank=True)
    nik_hash = models.CharField(max_length=64, null=True, blank=True)
    instansi = models.CharField(max_length=255, null=True, blank=True)
    password = models.CharField(max_length=255, null=True, blank=True)  # Null untuk SSO
    registration_date = models.DateTimeField(auto_now_add=True)
    account_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    last_login = models.DateTimeField(null=True, blank=True)
    registration_type = models.CharField(max_length=20, choices=REGISTRATION_TYPE_CHOICES, default='manual')
    google_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    profile_picture = models.FileField(upload_to='profiles/', null=True, blank=True)
    is_admin = models.BooleanField(default=False)
    admin_role = models.CharField(max_length=20, choices=ADMIN_ROLE_CHOICES, default='operator')
    nip = models.CharField(max_length=50, null=True, blank=True)
    jabatan = models.CharField(max_length=100, null=True, blank=True)
    
    class Meta:
        db_table = 'tamu'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['google_id']),
            models.Index(fields=['nik_hash'], name='idx_tamu_nik_hash'),
            models.Index(fields=['account_status']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.email})"

    objects = TamuQuerySet.as_manager()

    @classmethod
    def nik_lookup_q(cls, raw_nik):
        """Kembalikan Q object berbasis blind-index nik_hash."""
        from django.db.models import Q
        from .security_utils import hash_nik
        h = hash_nik(raw_nik)
        return Q(nik_hash=h) if h else Q(pk__isnull=True)

    def save(self, *args, **kwargs):
        from .security_utils import hash_nik
        new_hash = hash_nik(self.nik)
        update_fields = kwargs.get('update_fields')
        if self.nik_hash != new_hash:
            self.nik_hash = new_hash
            if update_fields is not None:
                uf = list(update_fields)
                if 'nik_hash' not in uf:
                    uf.append('nik_hash')
                    kwargs['update_fields'] = uf
        elif update_fields is not None and 'nik' in update_fields:
            uf = list(update_fields)
            if 'nik_hash' not in uf:
                uf.append('nik_hash')
                kwargs['update_fields'] = uf
        super().save(*args, **kwargs)


class Pegawai(models.Model):
    """Model untuk Pegawai/Tuan Rumah"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    ]
    
    ROLE_CHOICES = [
        ('staff', 'Staff'),
        ('supervisor', 'Supervisor'),
        ('manager', 'Manager'),
        ('admin', 'Admin'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    username = models.CharField(max_length=50, unique=True, null=True, blank=True, verbose_name='Username')
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    department_rel = models.ForeignKey(Departemen, on_delete=models.SET_NULL, null=True, blank=True, related_name='pegawai_list', verbose_name='Bidang')
    department = models.CharField(max_length=255, null=True, blank=True)  # Legacy field, kept for compatibility for now
    password = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='staff', verbose_name='Role')
    nip = models.CharField(max_length=50, null=True, blank=True, verbose_name='NIP')
    jabatan = models.CharField(max_length=100, null=True, blank=True, verbose_name='Jabatan')
    account_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    must_change_password = models.BooleanField(default=False)
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'pegawai'
        indexes = [
            models.Index(fields=['username']),
            models.Index(fields=['email']),
            models.Index(fields=['department']),
            models.Index(fields=['account_status']),
            models.Index(fields=['role']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.department})"


class Admin(models.Model):
    """Model untuk Administrator"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    password = models.CharField(max_length=255)
    account_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    last_login = models.DateTimeField(null=True, blank=True)
    two_fa_enabled = models.BooleanField(default=False)
    two_fa_secret = models.CharField(max_length=255, null=True, blank=True)
    email_notif_enabled = models.BooleanField(default=True)
    push_notif_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'admin'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['account_status']),
        ]
    
    def __str__(self):
        return f"Admin: {self.name}"


# ============================================================================
# VISIT MODELS (Kunjungan)
# ============================================================================

class KunjunganStatus:
    """Konstanta status resmi Kunjungan untuk mencegah string typo."""
    MENUNGGU_ADMIN = 'menunggu_admin'
    MENUNGGU_PEGAWAI = 'menunggu_pegawai'
    DISETUJUI_PEGAWAI = 'disetujui_pegawai'
    DITOLAK_PEGAWAI = 'ditolak_pegawai'
    DITOLAK_ADMIN = 'ditolak_admin'
    DISETUJUI = 'disetujui'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'

    PENDING_VERIFICATION = [
        MENUNGGU_ADMIN,
        MENUNGGU_PEGAWAI,
        DISETUJUI_PEGAWAI,
    ]

    CANCELABLE = [
        MENUNGGU_ADMIN,
        MENUNGGU_PEGAWAI,
        DISETUJUI_PEGAWAI,
        DISETUJUI,
    ]

    ALL = [
        MENUNGGU_ADMIN,
        MENUNGGU_PEGAWAI,
        DISETUJUI_PEGAWAI,
        DITOLAK_PEGAWAI,
        DITOLAK_ADMIN,
        DISETUJUI,
        IN_PROGRESS,
        COMPLETED,
        CANCELLED,
    ]


class Kunjungan(models.Model):
    """Model untuk Catatan Kunjungan"""
    Status = KunjunganStatus

    STATUS_CHOICES = [
        (KunjunganStatus.MENUNGGU_ADMIN, 'Menunggu Admin'),
        (KunjunganStatus.MENUNGGU_PEGAWAI, 'Menunggu Pegawai'),
        (KunjunganStatus.DISETUJUI_PEGAWAI, 'Disetujui Pegawai'),
        (KunjunganStatus.DITOLAK_PEGAWAI, 'Ditolak Pegawai'),
        (KunjunganStatus.DITOLAK_ADMIN, 'Ditolak Admin'),
        (KunjunganStatus.DISETUJUI, 'Disetujui Admin (ACC)'),
        (KunjunganStatus.IN_PROGRESS, 'Berjalan'),
        (KunjunganStatus.COMPLETED, 'Selesai'),
        (KunjunganStatus.CANCELLED, 'Batal'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tamu = models.ForeignKey(Tamu, on_delete=models.CASCADE, related_name='kunjungan')
    pegawai = models.ForeignKey(Pegawai, on_delete=models.SET_NULL, null=True, blank=True, related_name='kunjungan_diterima')
    arrival_time = models.DateTimeField()
    departure_time = models.DateTimeField(null=True, blank=True)
    purpose = models.CharField(max_length=500)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='menunggu_admin')
    notes = models.TextField(null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True, verbose_name='Alasan Penolakan')
    admin_notes = models.TextField(null=True, blank=True, verbose_name='Catatan Admin Internal')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'kunjungan'
        indexes = [
            # Covering index untuk dashboard tamu: filter tamu + COUNT per status
            models.Index(fields=['tamu', 'status'], name='idx_kunjungan_tamu_status'),
            # Covering index untuk dashboard admin: filter arrival_time + status
            models.Index(fields=['arrival_time', 'status'], name='idx_kunjungan_arrival_status'),
            # Untuk query pegawai timeline
            models.Index(fields=['pegawai', 'arrival_time'], name='idx_kunjungan_pegawai_arrival'),
            # Filter bulan_ini: (tamu, arrival_time) agar YEAR/MONTH bisa manfaatkan range scan
            models.Index(fields=['tamu', 'arrival_time'], name='idx_kunjungan_tamu_arrival'),
        ]
    
    def __str__(self):
        return f"Kunjungan: {self.tamu.name} - {self.arrival_time}"


class KunjunganStatusHistory(models.Model):
    """Model untuk Riwayat Perubahan Status Kunjungan"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kunjungan = models.ForeignKey(Kunjungan, on_delete=models.CASCADE, related_name='status_history')
    old_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    changed_by_id = models.CharField(max_length=255)  # Bisa Pegawai atau Admin
    changed_by_type = models.CharField(max_length=20, choices=[('pegawai', 'Pegawai'), ('admin', 'Admin')])
    notes = models.TextField(null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'kunjungan_status_history'
        indexes = [
            models.Index(fields=['kunjungan', 'changed_at']),
        ]


class KunjunganNote(models.Model):
    """Model untuk Catatan/Komentar pada Kunjungan"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kunjungan = models.ForeignKey(Kunjungan, on_delete=models.CASCADE, related_name='notes_history')
    author_id = models.CharField(max_length=255)  # Bisa Pegawai atau Admin
    author_type = models.CharField(max_length=20, choices=[('pegawai', 'Pegawai'), ('admin', 'Admin')])
    content = models.TextField()
    note_type = models.CharField(max_length=20, default='general')  # general, rejection, approval
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'kunjungan_note'
        indexes = [
            models.Index(fields=['kunjungan', 'created_at']),
        ]


# ============================================================================
# MESSAGING MODELS (Pesan)
# ============================================================================

class Message(models.Model):
    """Model untuk Pesan dari Pegawai/Tamu ke Admin"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('read', 'Read'),
        ('replied', 'Replied'),
        ('resolved', 'Resolved'),
    ]
    
    SENDER_TYPE_CHOICES = [
        ('pegawai', 'Pegawai'),
        ('tamu', 'Tamu'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender_id = models.CharField(max_length=255)
    sender_type = models.CharField(max_length=20, choices=SENDER_TYPE_CHOICES)
    subject = models.CharField(max_length=500)
    content = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    attachment_path = models.FileField(upload_to='message_attachments/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'message'
        indexes = [
            models.Index(fields=['sender_id', 'created_at']),
            models.Index(fields=['status']),
        ]
    
    def __str__(self):
        return f"Message: {self.subject} from {self.sender_type}"


class MessageReply(models.Model):
    """Model untuk Balasan Admin terhadap Pesan (Legacy)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name='replies')
    admin = models.ForeignKey(Admin, on_delete=models.SET_NULL, null=True, blank=True)
    reply_content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'message_reply'
        indexes = [
            models.Index(fields=['message', 'created_at']),
        ]


def parse_chat_session_id(session_id):
    """
    Parse konvensi session_id campuran ('tamu_<id>', '<id>', 'pegawai_admin_<id>',
    'kunjungan_<id>', dst.) menjadi tipe ruang chat & UUID entitas terkait.
    """
    sid = str(session_id or '').strip()
    if sid.startswith('pegawai_admin_'):
        raw_id = sid[len('pegawai_admin_'):]
        room_type = 'pegawai_admin'
    elif sid.startswith('kunjungan_'):
        raw_id = sid[len('kunjungan_'):]
        room_type = 'kunjungan'
    elif sid.startswith('tamu_'):
        raw_id = sid[len('tamu_'):]
        room_type = 'tamu_admin'
    else:
        raw_id = sid
        room_type = 'tamu_admin' if sid else 'custom'

    entity_uuid = None
    if raw_id:
        try:
            entity_uuid = uuid.UUID(str(raw_id))
        except (ValueError, TypeError, AttributeError):
            entity_uuid = None
            if not sid.startswith(('pegawai_admin_', 'kunjungan_', 'tamu_')):
                room_type = 'custom'

    return {
        'session_id': sid,
        'room_type': room_type,
        'entity_uuid': entity_uuid,
    }


class ChatRoom(models.Model):
    """Model terstruktur untuk ruang percakapan chat (Tamu-Admin, Pegawai-Admin, Tamu-Pegawai)."""

    class RoomType(models.TextChoices):
        TAMU_ADMIN = 'tamu_admin', 'Tamu - Admin'
        PEGAWAI_ADMIN = 'pegawai_admin', 'Pegawai - Admin'
        KUNJUNGAN = 'kunjungan', 'Tamu - Pegawai (Kunjungan)'
        CUSTOM = 'custom', 'Lainnya'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_id = models.CharField(max_length=255, unique=True)
    room_type = models.CharField(
        max_length=20,
        choices=RoomType.choices,
        default=RoomType.CUSTOM,
    )
    tamu = models.ForeignKey(
        Tamu, on_delete=models.CASCADE, null=True, blank=True, related_name='chat_rooms'
    )
    pegawai = models.ForeignKey(
        Pegawai, on_delete=models.CASCADE, null=True, blank=True, related_name='chat_rooms'
    )
    kunjungan = models.ForeignKey(
        Kunjungan, on_delete=models.CASCADE, null=True, blank=True, related_name='chat_rooms'
    )
    last_message_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'chat_room'
        ordering = ['-last_message_at', '-created_at']
        indexes = [
            models.Index(fields=['room_type', 'last_message_at'], name='idx_chatroom_type_lastmsg'),
            models.Index(fields=['tamu', 'room_type'], name='idx_chatroom_tamu_type'),
            models.Index(fields=['pegawai', 'room_type'], name='idx_chatroom_pegawai_type'),
        ]

    def __str__(self):
        return f"ChatRoom({self.room_type}: {self.session_id})"

    @staticmethod
    def session_id_for_tamu(tamu_id):
        """Kembalikan session_id kanonis untuk ruang chat Tamu <-> Admin."""
        return str(tamu_id)

    @staticmethod
    def session_id_for_pegawai_admin(pegawai_id):
        """Kembalikan session_id kanonis untuk ruang chat Pegawai <-> Admin."""
        return f"pegawai_admin_{pegawai_id}"

    @staticmethod
    def session_id_for_kunjungan(kunjungan_id):
        """Kembalikan session_id kanonis untuk ruang chat Kunjungan (Tamu <-> Pegawai)."""
        return f"kunjungan_{kunjungan_id}"

    @staticmethod
    def parse_session_id(session_id):
        """Parse string session_id menjadi metadata ruang chat."""
        return parse_chat_session_id(session_id)

    @classmethod
    def resolve_or_create_for_session(cls, session_id, *, last_message_at=None):
        """
        Ambil atau buat ChatRoom terstruktur untuk session_id tertentu,
        menghubungkan relasi Tamu/Pegawai/Kunjungan secara aman bila UUID valid tersedia.
        """
        parsed = parse_chat_session_id(session_id)
        sid = parsed['session_id']
        if not sid:
            return None

        existing = cls.objects.filter(session_id=sid).first()
        if existing is not None:
            if last_message_at and (
                existing.last_message_at is None or last_message_at > existing.last_message_at
            ):
                cls.objects.filter(pk=existing.pk).update(last_message_at=last_message_at)
                existing.last_message_at = last_message_at
            return existing

        room_type = parsed['room_type']
        entity_uuid = parsed['entity_uuid']
        tamu_id = None
        pegawai_id = None
        kunjungan_id = None

        if entity_uuid is not None:
            if room_type == cls.RoomType.TAMU_ADMIN:
                if Tamu.objects.filter(pk=entity_uuid).exists():
                    tamu_id = entity_uuid
            elif room_type == cls.RoomType.PEGAWAI_ADMIN:
                if Pegawai.objects.filter(pk=entity_uuid).exists():
                    pegawai_id = entity_uuid
            elif room_type == cls.RoomType.KUNJUNGAN:
                kunj = Kunjungan.objects.filter(pk=entity_uuid).values('id', 'tamu_id', 'pegawai_id').first()
                if kunj:
                    kunjungan_id = kunj['id']
                    tamu_id = kunj['tamu_id']
                    pegawai_id = kunj['pegawai_id']

        defaults = {
            'room_type': room_type,
            'tamu_id': tamu_id,
            'pegawai_id': pegawai_id,
            'kunjungan_id': kunjungan_id,
            'last_message_at': last_message_at,
        }
        try:
            with transaction.atomic():
                room, _ = cls.objects.get_or_create(session_id=sid, defaults=defaults)
                return room
        except IntegrityError:
            return cls.objects.get(session_id=sid)


class ChatMessage(models.Model):
    """Model untuk Chat Real-time (WhatsApp Style)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(
        ChatRoom, on_delete=models.CASCADE, null=True, blank=True, related_name='messages'
    )
    # session_id mengikuti konvensi ruang chat; terhubung otomatis ke ChatRoom
    session_id = models.CharField(max_length=255, db_index=True)
    sender_id = models.CharField(max_length=255)
    sender_type = models.CharField(max_length=20, choices=[('admin', 'Admin'), ('tamu', 'Tamu'), ('pegawai', 'Pegawai')])
    content = models.TextField()
    attachment = models.FileField(upload_to='chat_attachments/', null=True, blank=True)
    message_type = models.CharField(max_length=20, default='text') # text, file, image, sticker
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'chat_message'
        ordering = ['created_at']
        indexes = [
            # Index aktif untuk query history chat per sesi
            models.Index(fields=['session_id', 'created_at'], name='idx_chat_session_created'),
            # Covering composite index untuk hitung pesan belum dibaca per sesi & pengirim
            models.Index(fields=['session_id', 'is_read', 'sender_type'], name='idx_chat_sess_read_sender'),
            # Index relasional berbasis ChatRoom FK
            models.Index(fields=['room', 'created_at'], name='idx_chat_room_created'),
            models.Index(fields=['room', 'is_read', 'sender_type'], name='idx_chat_room_read_sender'),
        ]

    def save(self, *args, **kwargs):
        if self.room_id and not self.session_id:
            self.session_id = self.room.session_id
        is_new = self._state.adding
        if is_new and self.session_id and not self.room_id:
            self.room = ChatRoom.resolve_or_create_for_session(self.session_id)
        super().save(*args, **kwargs)
        if is_new and self.room_id and self.created_at:
            ChatRoom.objects.filter(pk=self.room_id).filter(
                Q(last_message_at__isnull=True) | Q(last_message_at__lt=self.created_at)
            ).update(last_message_at=self.created_at)
            if self.room is not None and (
                self.room.last_message_at is None or self.room.last_message_at < self.created_at
            ):
                self.room.last_message_at = self.created_at

    @classmethod
    def unread_counts_by_session(cls, session_ids, *, exclude_sender_type=None, sender_type=None):
        """Hitung pesan belum dibaca secara batch per session_id memakai idx_chat_sess_read_sender."""
        if not session_ids:
            return {}
        qs = cls.objects.filter(session_id__in=session_ids, is_read=False)
        if exclude_sender_type:
            qs = qs.exclude(sender_type=exclude_sender_type)
        if sender_type:
            qs = qs.filter(sender_type=sender_type)
        return dict(
            qs.values('session_id')
            .annotate(total=Count('id'))
            .values_list('session_id', 'total')
        )

    @classmethod
    def latest_by_session(cls, session_ids):
        """Ambil pesan terakhir untuk sekumpulan session_id secara batch (kompatibel MySQL & SQLite)."""
        if not session_ids:
            return {}
        latest_timestamps = [
            ts for ts in (
                cls.objects.filter(session_id__in=session_ids)
                .values('session_id')
                .annotate(last_msg=Max('created_at'))
                .values_list('last_msg', flat=True)
            )
            if ts is not None
        ]
        if not latest_timestamps:
            return {}
        latest_map = {}
        recent_qs = cls.objects.filter(
            session_id__in=session_ids,
            created_at__in=latest_timestamps,
        ).order_by('-created_at')
        for msg in recent_qs:
            if msg.session_id not in latest_map:
                latest_map[msg.session_id] = msg
        return latest_map



# ============================================================================
# CALENDAR & QUOTA MODELS
# ============================================================================

class CalendarSettings(models.Model):
    """Model untuk Pengaturan Kalender (Kuota Harian, Hari Libur)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date = models.DateField(unique=True)
    daily_quota = models.IntegerField(default=50)
    is_holiday = models.BooleanField(default=False)
    holiday_name = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'calendar_settings'
        indexes = [
            # (date) tidak perlu — unique=True sudah otomatis buat index
            models.Index(fields=['is_holiday'], name='idx_calendar_is_holiday'),
        ]
    
    def __str__(self):
        return f"Calendar: {self.date} - Quota: {self.daily_quota}"


# ============================================================================
# AUDIT & LOGGING MODELS
# ============================================================================

class AuditLog(models.Model):
    """Model untuk Audit Log (Pencatatan Semua Perubahan Data)"""
    ACTION_CHOICES = [
        ('create', 'Create'),
        ('update', 'Update'),
        ('delete', 'Delete'),
    ]
    
    USER_TYPE_CHOICES = [
        ('tamu', 'Tamu'),
        ('pegawai', 'Pegawai'),
        ('admin', 'Admin'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.CharField(max_length=255)
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    table_name = models.CharField(max_length=255)
    record_id = models.CharField(max_length=255)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        db_table = 'audit_log'
        indexes = [
            models.Index(fields=['user_id', 'timestamp']),
            models.Index(fields=['table_name', 'record_id']),
            models.Index(fields=['timestamp']),
        ]


class LoginAttempt(models.Model):
    """Model untuk Pencatatan Login Attempts (Keamanan)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    user_type = models.CharField(max_length=20, choices=[('tamu', 'Tamu'), ('pegawai', 'Pegawai'), ('admin', 'Admin')])
    success = models.BooleanField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'login_attempt'
        indexes = [
            models.Index(fields=['email', 'timestamp']),
            models.Index(fields=['ip_address', 'timestamp']),
        ]


class Session(models.Model):
    """Model untuk Session Management"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.CharField(max_length=255)
    user_type = models.CharField(max_length=20, choices=[('tamu', 'Tamu'), ('pegawai', 'Pegawai'), ('admin', 'Admin')])
    session_token = models.CharField(max_length=255, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    
    class Meta:
        db_table = 'session'
        indexes = [
            models.Index(fields=['user_id', 'expires_at']),
            models.Index(fields=['session_token']),
        ]


# ============================================================================
# NOTIFICATION MODELS
# ============================================================================

class Notification(models.Model):
    """Model untuk Notifikasi Pengguna"""
    TYPE_CHOICES = [
        ('visit_registered', 'Visit Registered'),
        ('visit_forwarded', 'Visit Forwarded to Pegawai'),
        ('visit_approved', 'Visit Approved by Pegawai'),
        ('visit_rejected', 'Visit Rejected by Pegawai'),
        ('visit_rejected_admin', 'Visit Rejected by Admin'),
        ('visit_acc', 'Visit ACC by Admin'),
        ('visit_in_progress', 'Visit In Progress'),
        ('visit_completed', 'Visit Completed'),
        ('message_received', 'Message Received'),
        ('message_replied', 'Message Replied'),
        ('quota_reached', 'Quota Reached'),
        ('system_alert', 'System Alert'),
    ]
    
    STATUS_CHOICES = [
        ('unread', 'Unread'),
        ('read', 'Read'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient_id = models.CharField(max_length=255)
    recipient_type = models.CharField(max_length=20, choices=[('tamu', 'Tamu'), ('pegawai', 'Pegawai'), ('admin', 'Admin')])
    notification_type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='unread')
    related_object_id = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'notification'
        indexes = [
            # Covering index untuk query badge & dropdown: filter recipient + type + status
            models.Index(fields=['recipient_id', 'recipient_type', 'status'], name='idx_notif_recipient_status'),
            # Untuk sort & pagination notifikasi terbaru
            models.Index(fields=['recipient_id', 'created_at'], name='idx_notif_recipient_created'),
        ]


class IKMSurvey(models.Model):
    """
    Model Survei Indeks Kepuasan Masyarakat (IKM) & Rating Pelayanan
    Mengacu pada standar PermenPAN-RB No. 14 Tahun 2017.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kunjungan = models.OneToOneField(Kunjungan, on_delete=models.CASCADE, related_name='ikm_survey')
    tamu = models.ForeignKey(Tamu, on_delete=models.CASCADE, related_name='ikm_surveys')
    
    # Rating utama 1-5 bintang
    rating = models.PositiveSmallIntegerField(default=5, verbose_name='Rating Keseluruhan')
    
    # Unsur-unsur Pelayanan Standar IKM PermenPAN-RB (Skala 1 - 5)
    kesesuaian_persyaratan = models.PositiveSmallIntegerField(default=5, verbose_name='Kesesuaian Persyaratan')
    kemudahan_prosedur = models.PositiveSmallIntegerField(default=5, verbose_name='Kemudahan Prosedur')
    kecepatan_layanan = models.PositiveSmallIntegerField(default=5, verbose_name='Kecepatan Layanan')
    keramahan_petugas = models.PositiveSmallIntegerField(default=5, verbose_name='Keramahan Petugas')
    kualitas_sarana = models.PositiveSmallIntegerField(default=5, verbose_name='Kualitas Sarana & Prasarana')
    
    ulasan = models.TextField(null=True, blank=True, verbose_name='Kritik, Saran & Ulasan')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ikm_survey'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['rating']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"IKM: {self.tamu.name} ({self.rating}★)"
