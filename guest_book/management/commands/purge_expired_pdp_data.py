"""
Management command retensi & anonimisasi data pribadi otomatis (Kepatuhan UU PDP).

Contoh penggunaan:
    python manage.py purge_expired_pdp_data --dry-run
    python manage.py purge_expired_pdp_data --kunjungan-days 365 --chat-days 180 --log-days 90
"""
from datetime import timedelta
import logging

from django.conf import settings
from django.contrib.sessions.models import Session as DjangoSession
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from guest_book.models import (
    AuditLog,
    ChatMessage,
    Kunjungan,
    KunjunganNote,
    LoginAttempt,
    Message,
    Notification,
    Session as AppSession,
    Tamu,
)

logger = logging.getLogger('guest_book.security')

_REDACTED_MARKER = '[Dihapus sesuai kebijakan retensi UU PDP]'


def _safe_delete_stored_file(file_field):
    """Hapus berkas dari storage tanpa menggagalkan proses batch jika berkas tidak ada."""
    if not file_field or not getattr(file_field, 'name', None):
        return False
    try:
        if default_storage.exists(file_field.name):
            default_storage.delete(file_field.name)
            return True
    except Exception as exc:
        logger.warning("Gagal menghapus berkas retensi %s: %s", file_field.name, exc)
    return False


class Command(BaseCommand):
    help = "Membersihkan dan menganonimkan data pribadi kedaluwarsa sesuai kebijakan retensi UU PDP."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Simulasikan perhitungan data yang akan dibersihkan tanpa mengubah database.',
        )
        parser.add_argument(
            '--kunjungan-days',
            type=int,
            default=getattr(settings, 'PDP_RETENTION_DAYS', 365),
            help='Masa retensi catatan kunjungan selesai/ditolak/batal (hari).',
        )
        parser.add_argument(
            '--chat-days',
            type=int,
            default=getattr(settings, 'PDP_CHAT_RETENTION_DAYS', 180),
            help='Masa retensi pesan chat dan lampirannya (hari).',
        )
        parser.add_argument(
            '--log-days',
            type=int,
            default=getattr(settings, 'PDP_LOG_RETENTION_DAYS', 90),
            help='Masa retensi log percobaan login & notifikasi terbaca (hari).',
        )
        parser.add_argument(
            '--inactive-days',
            type=int,
            default=getattr(settings, 'PDP_ANONYMIZE_INACTIVE_DAYS', 730),
            help='Batas inaktivitas sebelum akun Tamu non-admin dianonimkan (hari).',
        )

    def handle(self, *args, **options):
        dry_run = bool(options['dry_run'])
        now = timezone.now()

        kunjungan_cutoff = now - timedelta(days=max(1, options['kunjungan_days']))
        chat_cutoff = now - timedelta(days=max(1, options['chat_days']))
        log_cutoff = now - timedelta(days=max(1, options['log_days']))
        inactive_cutoff = now - timedelta(days=max(1, options['inactive_days']))

        summary = {
            'dry_run': dry_run,
            'expired_django_sessions': 0,
            'expired_app_sessions': 0,
            'deleted_login_attempts': 0,
            'deleted_read_notifications': 0,
            'deleted_chat_messages': 0,
            'deleted_legacy_messages': 0,
            'deleted_media_files': 0,
            'redacted_visit_records': 0,
            'deleted_visit_notes': 0,
            'anonymized_tamu_accounts': 0,
        }

        # 1. Session kedaluwarsa
        django_sess_qs = DjangoSession.objects.filter(expire_date__lt=now)
        app_sess_qs = AppSession.objects.filter(expires_at__lt=now)
        summary['expired_django_sessions'] = django_sess_qs.count()
        summary['expired_app_sessions'] = app_sess_qs.count()

        # 2. Log login & notifikasi lama
        login_qs = LoginAttempt.objects.filter(timestamp__lt=log_cutoff)
        notif_qs = Notification.objects.filter(status='read', created_at__lt=log_cutoff)
        summary['deleted_login_attempts'] = login_qs.count()
        summary['deleted_read_notifications'] = notif_qs.count()

        # 3. Chat & lampiran lama
        chat_qs = ChatMessage.objects.filter(created_at__lt=chat_cutoff)
        legacy_msg_qs = Message.objects.filter(created_at__lt=chat_cutoff)
        summary['deleted_chat_messages'] = chat_qs.count()
        summary['deleted_legacy_messages'] = legacy_msg_qs.count()

        # 4. Catatan sensitif kunjungan terminal lama (status statistik kunjungan tetap dipertahankan)
        terminal_statuses = [
            Kunjungan.Status.COMPLETED,
            Kunjungan.Status.CANCELLED,
            Kunjungan.Status.DITOLAK_ADMIN,
            Kunjungan.Status.DITOLAK_PEGAWAI,
        ]
        old_visits_qs = Kunjungan.objects.filter(
            status__in=terminal_statuses,
            arrival_time__lt=kunjungan_cutoff,
        ).filter(
            (Q(notes__isnull=False) & ~Q(notes='') & ~Q(notes=_REDACTED_MARKER))
            | (Q(admin_notes__isnull=False) & ~Q(admin_notes='') & ~Q(admin_notes=_REDACTED_MARKER))
            | (Q(rejection_reason__isnull=False) & ~Q(rejection_reason='') & ~Q(rejection_reason=_REDACTED_MARKER))
        )
        old_notes_qs = KunjunganNote.objects.filter(
            kunjungan__status__in=terminal_statuses,
            kunjungan__arrival_time__lt=kunjungan_cutoff,
        )
        summary['redacted_visit_records'] = old_visits_qs.count()
        summary['deleted_visit_notes'] = old_notes_qs.count()

        # 5. Anonimisasi Tamu inaktif jangka panjang tanpa aktivitas kunjungan baru
        recent_visit_tamu_ids = Kunjungan.objects.filter(
            arrival_time__gte=inactive_cutoff
        ).values_list('tamu_id', flat=True)

        inactive_tamu_qs = (
            Tamu.objects.filter(is_admin=False)
            .exclude(Tamu.nik_lookup_q('admin'))
            .exclude(email__endswith='@redacted.local')
            .exclude(pk__in=recent_visit_tamu_ids)
            .filter(
                Q(last_login__lt=inactive_cutoff)
                | (Q(last_login__isnull=True) & Q(registration_date__lt=inactive_cutoff))
            )
        )
        summary['anonymized_tamu_accounts'] = inactive_tamu_qs.count()

        if not dry_run:
            # Kumpulkan file fisik sebelum penghapusan DB
            chat_files = [m.attachment for m in chat_qs.exclude(attachment='').exclude(attachment__isnull=True)]
            legacy_files = [m.attachment_path for m in legacy_msg_qs.exclude(attachment_path='').exclude(attachment_path__isnull=True)]
            tamu_targets = list(inactive_tamu_qs)
            avatar_files = [t.profile_picture for t in tamu_targets if t.profile_picture]

            with transaction.atomic():
                django_sess_qs.delete()
                app_sess_qs.delete()
                login_qs.delete()
                notif_qs.delete()
                chat_qs.delete()
                legacy_msg_qs.delete()
                old_notes_qs.delete()
                old_visits_qs.update(
                    notes=_REDACTED_MARKER,
                    admin_notes=_REDACTED_MARKER,
                    rejection_reason=_REDACTED_MARKER,
                )

                for tamu in tamu_targets:
                    tamu.name = f"Tamu Anonim ({str(tamu.id)[:8]})"
                    tamu.email = f"anonymized-{tamu.id}@redacted.local"
                    tamu.phone = '-'
                    tamu.nik = None
                    tamu.nik_hash = None
                    tamu.instansi = None
                    tamu.google_id = None
                    tamu.password = None
                    tamu.profile_picture = None
                    tamu.account_status = 'inactive'
                    tamu.save()

                AuditLog.objects.create(
                    user_id='system_pdp_retention',
                    user_type='admin',
                    action='delete',
                    table_name='pdp_retention',
                    record_id='scheduled_purge',
                    new_value=summary,
                )

            deleted_media = 0
            for f in (*chat_files, *legacy_files, *avatar_files):
                if _safe_delete_stored_file(f):
                    deleted_media += 1
            summary['deleted_media_files'] = deleted_media

        mode_label = "DRY-RUN" if dry_run else "EXECUTED"
        self.stdout.write(self.style.SUCCESS(f"[UU PDP RETENTION - {mode_label}] Ringkasan:"))
        for k, v in summary.items():
            if k != 'dry_run':
                self.stdout.write(f"  - {k}: {v}")
        logger.info("UU PDP retention %s completed: %s", mode_label, summary)
