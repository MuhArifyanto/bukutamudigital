from django.contrib import admin
from .models import (
    Tamu, Pegawai, Admin as AdminUser,
    Kunjungan, KunjunganStatusHistory, KunjunganNote,
    Message, MessageReply,
    CalendarSettings,
    AuditLog, LoginAttempt, Session,
    Notification,
    Instansi, Departemen
)

# ============================================================================
# USER ADMINS
# ============================================================================

@admin.register(Tamu)
class TamuAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'phone', 'registration_type', 'account_status', 'registration_date')
    list_filter = ('account_status', 'registration_type', 'registration_date')
    search_fields = ('name', 'email', 'phone')
    readonly_fields = ('id', 'registration_date', 'last_login')
    fieldsets = (
        ('Personal Information', {
            'fields': ('id', 'name', 'email', 'phone', 'profile_picture')
        }),
        ('Account', {
            'fields': ('password', 'account_status', 'registration_type')
        }),
        ('SSO Information', {
            'fields': ('google_id',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('registration_date', 'last_login'),
            'classes': ('collapse',)
        }),
    )


@admin.register(Pegawai)
class PegawaiAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'department_rel', 'account_status', 'created_at')
    list_filter = ('account_status', 'department_rel', 'created_at')
    search_fields = ('name', 'email', 'department_rel__nama')
    readonly_fields = ('id', 'created_at', 'last_login')
    fieldsets = (
        ('Personal Information', {
            'fields': ('id', 'name', 'email', 'phone', 'department_rel')
        }),
        ('Account', {
            'fields': ('password', 'account_status')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'last_login'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AdminUser)
class AdminUserAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'account_status', 'two_fa_enabled', 'created_at')
    list_filter = ('account_status', 'two_fa_enabled', 'created_at')
    search_fields = ('name', 'email')
    readonly_fields = ('id', 'created_at', 'last_login')
    fieldsets = (
        ('Personal Information', {
            'fields': ('id', 'name', 'email', 'phone')
        }),
        ('Account', {
            'fields': ('password', 'account_status')
        }),
        ('Security', {
            'fields': ('two_fa_enabled', 'two_fa_secret'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'last_login'),
            'classes': ('collapse',)
        }),
    )


# ============================================================================
# VISIT ADMINS
# ============================================================================

class KunjunganStatusHistoryInline(admin.TabularInline):
    model = KunjunganStatusHistory
    extra = 0
    readonly_fields = ('changed_at',)


class KunjunganNoteInline(admin.TabularInline):
    model = KunjunganNote
    extra = 1
    readonly_fields = ('created_at',)


@admin.register(Kunjungan)
class KunjunganAdmin(admin.ModelAdmin):
    list_display = ('tamu', 'pegawai', 'arrival_time', 'status', 'purpose')
    list_filter = ('status', 'arrival_time', 'pegawai')
    search_fields = ('tamu__name', 'purpose', 'pegawai__name')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [KunjunganStatusHistoryInline, KunjunganNoteInline]
    fieldsets = (
        ('Visit Information', {
            'fields': ('id', 'tamu', 'pegawai', 'purpose')
        }),
        ('Timeline', {
            'fields': ('arrival_time', 'departure_time', 'status')
        }),
        ('Notes', {
            'fields': ('notes',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(KunjunganStatusHistory)
class KunjunganStatusHistoryAdmin(admin.ModelAdmin):
    list_display = ('kunjungan', 'old_status', 'new_status', 'changed_by_type', 'changed_at')
    list_filter = ('changed_by_type', 'changed_at')
    search_fields = ('kunjungan__tamu__name',)
    readonly_fields = ('id', 'changed_at')


@admin.register(KunjunganNote)
class KunjunganNoteAdmin(admin.ModelAdmin):
    list_display = ('kunjungan', 'author_type', 'created_at')
    list_filter = ('author_type', 'created_at')
    search_fields = ('kunjungan__tamu__name', 'content')
    readonly_fields = ('id', 'created_at')


# ============================================================================
# MESSAGING ADMINS
# ============================================================================

class MessageReplyInline(admin.TabularInline):
    model = MessageReply
    extra = 0
    readonly_fields = ('created_at',)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('subject', 'sender_type', 'status', 'created_at')
    list_filter = ('status', 'sender_type', 'created_at')
    search_fields = ('subject', 'content', 'sender_id')
    readonly_fields = ('id', 'created_at', 'updated_at')
    inlines = [MessageReplyInline]
    fieldsets = (
        ('Message Information', {
            'fields': ('id', 'sender_id', 'sender_type', 'subject')
        }),
        ('Content', {
            'fields': ('content', 'attachment_path')
        }),
        ('Status', {
            'fields': ('status',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(MessageReply)
class MessageReplyAdmin(admin.ModelAdmin):
    list_display = ('message', 'admin', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('message__subject', 'reply_content')
    readonly_fields = ('id', 'created_at')


# ============================================================================
# CALENDAR ADMIN
# ============================================================================

@admin.register(CalendarSettings)
class CalendarSettingsAdmin(admin.ModelAdmin):
    list_display = ('date', 'daily_quota', 'is_holiday', 'holiday_name')
    list_filter = ('is_holiday', 'date')
    search_fields = ('holiday_name',)
    readonly_fields = ('id', 'created_at', 'updated_at')
    fieldsets = (
        ('Date', {
            'fields': ('id', 'date')
        }),
        ('Quota', {
            'fields': ('daily_quota',)
        }),
        ('Holiday', {
            'fields': ('is_holiday', 'holiday_name')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


# ============================================================================
# AUDIT & LOGGING ADMINS
# ============================================================================

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('user_type', 'action', 'table_name', 'timestamp')
    list_filter = ('user_type', 'action', 'table_name', 'timestamp')
    search_fields = ('user_id', 'record_id')
    readonly_fields = ('id', 'timestamp')
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LoginAttempt)
class LoginAttemptAdmin(admin.ModelAdmin):
    list_display = ('email', 'user_type', 'success', 'ip_address', 'timestamp')
    list_filter = ('user_type', 'success', 'timestamp')
    search_fields = ('email', 'ip_address')
    readonly_fields = ('id', 'timestamp')
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('user_type', 'user_id', 'created_at', 'expires_at')
    list_filter = ('user_type', 'created_at', 'expires_at')
    search_fields = ('user_id', 'ip_address')
    readonly_fields = ('id', 'created_at')


# ============================================================================
# NOTIFICATION ADMIN
# ============================================================================

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'recipient_type', 'notification_type', 'status', 'created_at')
    list_filter = ('status', 'notification_type', 'recipient_type', 'created_at')
    search_fields = ('title', 'message', 'recipient_id')
    readonly_fields = ('id', 'created_at', 'read_at')
    fieldsets = (
        ('Notification Information', {
            'fields': ('id', 'recipient_id', 'recipient_type', 'notification_type')
        }),
        ('Content', {
            'fields': ('title', 'message')
        }),
        ('Status', {
            'fields': ('status', 'read_at')
        }),
        ('Related Object', {
            'fields': ('related_object_id',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
@admin.register(Instansi)
class InstansiAdmin(admin.ModelAdmin):
    list_display = ('nama', 'status_operasional', 'jam_buka', 'jam_tutup')
    readonly_fields = ('id', 'updated_at')

@admin.register(Departemen)
class DepartemenAdmin(admin.ModelAdmin):
    list_display = ('nama', 'kode', 'created_at')
    search_fields = ('nama', 'kode')
    readonly_fields = ('id', 'created_at')
