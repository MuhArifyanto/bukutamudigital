from django.db import models
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
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    nik = models.CharField(max_length=16, null=True, blank=True)
    instansi = models.CharField(max_length=255, null=True, blank=True)
    password = models.CharField(max_length=255, null=True, blank=True)  # Null untuk SSO
    registration_date = models.DateTimeField(auto_now_add=True)
    account_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    last_login = models.DateTimeField(null=True, blank=True)
    registration_type = models.CharField(max_length=20, choices=REGISTRATION_TYPE_CHOICES, default='manual')
    google_id = models.CharField(max_length=255, unique=True, null=True, blank=True)
    profile_picture = models.FileField(upload_to='profiles/', null=True, blank=True)
    is_admin = models.BooleanField(default=False)
    nip = models.CharField(max_length=50, null=True, blank=True)
    jabatan = models.CharField(max_length=100, null=True, blank=True)
    
    class Meta:
        db_table = 'tamu'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['google_id']),
            models.Index(fields=['account_status']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.email})"


class Pegawai(models.Model):
    """Model untuk Pegawai/Tuan Rumah"""
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
        ('suspended', 'Suspended'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20)
    department_rel = models.ForeignKey(Departemen, on_delete=models.SET_NULL, null=True, blank=True, related_name='pegawai_list', verbose_name='Bidang')
    department = models.CharField(max_length=255, null=True, blank=True)  # Legacy field, kept for compatibility for now
    password = models.CharField(max_length=255)
    account_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    last_login = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'pegawai'
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['department']),
            models.Index(fields=['account_status']),
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

class Kunjungan(models.Model):
    """Model untuk Catatan Kunjungan"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tamu = models.ForeignKey(Tamu, on_delete=models.CASCADE, related_name='kunjungan')
    pegawai = models.ForeignKey(Pegawai, on_delete=models.SET_NULL, null=True, blank=True, related_name='kunjungan_diterima')
    arrival_time = models.DateTimeField()
    departure_time = models.DateTimeField(null=True, blank=True)
    purpose = models.CharField(max_length=500)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'kunjungan'
        indexes = [
            models.Index(fields=['tamu', 'arrival_time']),
            models.Index(fields=['pegawai', 'arrival_time']),
            models.Index(fields=['status']),
            models.Index(fields=['arrival_time']),
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


class ChatMessage(models.Model):
    """Model untuk Chat Real-time (WhatsApp Style)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # session_id biasanya berupa tamu_id atau pegawai_id
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
        # indexes = [
        #     models.Index(fields=['session_id', 'created_at']),
        # ]



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
            models.Index(fields=['date']),
            models.Index(fields=['is_holiday']),
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
            models.Index(fields=['recipient_id', 'created_at']),
            models.Index(fields=['status']),
        ]
