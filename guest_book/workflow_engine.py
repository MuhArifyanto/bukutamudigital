"""
Workflow Engine untuk mengelola status transitions pada Kunjungan.
Memastikan hanya transisi yang valid yang diperbolehkan.
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone
from .models import Kunjungan, KunjunganStatus, KunjunganStatusHistory, KunjunganNote, Notification
import logging

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """
    Mengelola transisi status Kunjungan dan menegakkan aturan workflow.
    """
    
    # Transisi status yang valid
    VALID_TRANSITIONS = {
        KunjunganStatus.MENUNGGU_ADMIN: [KunjunganStatus.MENUNGGU_PEGAWAI, KunjunganStatus.DITOLAK_ADMIN, KunjunganStatus.CANCELLED],
        KunjunganStatus.MENUNGGU_PEGAWAI: [KunjunganStatus.DISETUJUI_PEGAWAI, KunjunganStatus.DITOLAK_PEGAWAI, KunjunganStatus.CANCELLED],
        KunjunganStatus.DISETUJUI_PEGAWAI: [KunjunganStatus.DISETUJUI, KunjunganStatus.CANCELLED],
        KunjunganStatus.DITOLAK_PEGAWAI: [],  # Terminal state
        KunjunganStatus.DITOLAK_ADMIN: [],    # Terminal state
        KunjunganStatus.DISETUJUI: [KunjunganStatus.IN_PROGRESS, KunjunganStatus.CANCELLED],
        KunjunganStatus.IN_PROGRESS: [KunjunganStatus.COMPLETED, KunjunganStatus.CANCELLED],
        KunjunganStatus.COMPLETED: [],  # Terminal state
        KunjunganStatus.CANCELLED: [],  # Terminal state
    }
    
    # Role yang diperlukan untuk setiap transisi
    REQUIRED_ROLES = {
        f'{KunjunganStatus.MENUNGGU_ADMIN} → {KunjunganStatus.MENUNGGU_PEGAWAI}': ['admin'],
        f'{KunjunganStatus.MENUNGGU_ADMIN} → {KunjunganStatus.DITOLAK_ADMIN}': ['admin'],
        f'{KunjunganStatus.MENUNGGU_PEGAWAI} → {KunjunganStatus.DISETUJUI_PEGAWAI}': ['pegawai'],
        f'{KunjunganStatus.MENUNGGU_PEGAWAI} → {KunjunganStatus.DITOLAK_PEGAWAI}': ['pegawai'],
        f'{KunjunganStatus.DISETUJUI_PEGAWAI} → {KunjunganStatus.DISETUJUI}': ['admin'],
        f'{KunjunganStatus.DISETUJUI} → {KunjunganStatus.IN_PROGRESS}': ['admin'],
        f'{KunjunganStatus.IN_PROGRESS} → {KunjunganStatus.COMPLETED}': ['admin'],
        f'* → {KunjunganStatus.CANCELLED}': ['admin'],
    }
    
    def __init__(self, kunjungan):
        self.kunjungan = kunjungan
    
    def can_transition(self, new_status, user_id, user_type):
        """
        Validasi apakah transisi diperbolehkan.
        
        Args:
            new_status: Status tujuan
            user_id: User yang melakukan transisi
            user_type: 'admin' atau 'pegawai'
        
        Returns:
            (bool, str): (is_valid, error_message)
        """
        old_status = self.kunjungan.status
        
        # 1. Cek apakah transisi valid
        if new_status not in self.VALID_TRANSITIONS.get(old_status, []):
            valid_next = ', '.join(self.VALID_TRANSITIONS.get(old_status, []))
            return False, f"Transisi dari '{old_status}' ke '{new_status}' tidak valid. Status valid berikutnya: {valid_next}"
        
        # 2. Cek permission user
        transition_key = f"{old_status} → {new_status}"
        required_roles = self.REQUIRED_ROLES.get(transition_key)
        if required_roles is None:
            wildcard_key = f"* → {new_status}"
            required_roles = self.REQUIRED_ROLES.get(wildcard_key, [])
        
        if user_type not in required_roles:
            return False, f"Anda tidak memiliki izin untuk melakukan transisi ini"
        
        # 3. Validasi tambahan untuk aksi pegawai
        if user_type == 'pegawai' and new_status in ['disetujui_pegawai', 'ditolak_pegawai']:
            if not self.kunjungan.pegawai or str(self.kunjungan.pegawai.id) != user_id:
                return False, "Anda hanya dapat merespon kunjungan yang ditujukan kepada Anda"
        
        return True, ""
    
    def transition(self, new_status, user_id, user_type, notes=None, rejection_reason=None):
        """
        Melakukan transisi status dengan semua side effects.
        
        Args:
            new_status: Status tujuan
            user_id: User yang melakukan transisi
            user_type: 'admin' atau 'pegawai'
            notes: Catatan opsional untuk history
            rejection_reason: Wajib untuk status ditolak_pegawai
        
        Returns:
            bool: Status keberhasilan
        
        Raises:
            ValidationError: Jika transisi tidak valid
            PermissionDenied: Jika user tidak memiliki izin
        """
        # Validasi transisi
        is_valid, error_msg = self.can_transition(new_status, user_id, user_type)
        if not is_valid:
            logger.warning(f"Invalid transition attempt: {error_msg}", extra={
                'kunjungan_id': str(self.kunjungan.id),
                'user_id': user_id,
                'user_type': user_type,
                'old_status': self.kunjungan.status,
                'new_status': new_status
            })
            raise PermissionDenied(error_msg)
        
        # Validasi alasan penolakan (wajib untuk ditolak_pegawai dan ditolak_admin)
        if new_status in ('ditolak_pegawai', 'ditolak_admin') and not rejection_reason:
            raise ValidationError("Alasan penolakan wajib diisi")
        
        old_status = self.kunjungan.status
        
        # Update kunjungan
        self.kunjungan.status = new_status
        if rejection_reason:
            self.kunjungan.rejection_reason = rejection_reason
        if new_status == 'completed':
            self.kunjungan.departure_time = timezone.now()
        self.kunjungan.save()
        
        # Catat history
        KunjunganStatusHistory.objects.create(
            kunjungan=self.kunjungan,
            old_status=old_status,
            new_status=new_status,
            changed_by_id=user_id,
            changed_by_type=user_type,
            notes=notes
        )
        
        # Buat note jika penolakan
        if new_status in ('ditolak_pegawai', 'ditolak_admin') and rejection_reason:
            KunjunganNote.objects.create(
                kunjungan=self.kunjungan,
                author_id=user_id,
                author_type=user_type,
                content=rejection_reason,
                note_type='rejection'
            )
        
        # Kirim notifikasi & pesan chat otomatis
        self._send_notifications(old_status, new_status, notes=notes, rejection_reason=rejection_reason)
        
        logger.info(f"Successful transition: {old_status} → {new_status}", extra={
            'kunjungan_id': str(self.kunjungan.id),
            'user_id': user_id,
            'user_type': user_type
        })
        
        return True
    
    def _send_notifications(self, old_status, new_status, notes=None, rejection_reason=None):
        """Mengirim notifikasi ke pihak terkait berdasarkan transisi."""
        from .utils import send_notification
        
        # Selalu notifikasi tamu
        try:
            tamu_message = self._get_tamu_notification_message(new_status)
            send_notification(
                recipient_id=str(self.kunjungan.tamu.id),
                recipient_type='tamu',
                notification_type=self._get_notification_type(new_status),
                title='Pembaruan Status Kunjungan',
                message=tamu_message,
                related_object_id=str(self.kunjungan.id)
            )
        except Exception as notif_err:
            logger.warning("Gagal mengirim notifikasi workflow ke tamu: %s", notif_err)

        # Kirim juga pesan chat otomatis real-time ke ruang Chat Tamu
        try:
            self._send_tamu_chat_status_update(new_status, notes=notes, rejection_reason=rejection_reason)
        except Exception as chat_err:
            logger.warning("Gagal mengirim pesan chat otomatis status kunjungan ke tamu: %s", chat_err)
        
        # Notifikasi pegawai
        if self.kunjungan.pegawai:
            if new_status in ['menunggu_pegawai', 'disetujui', 'in_progress', 'completed', 'cancelled']:
                try:
                    pegawai_message = self._get_pegawai_notification_message(new_status)
                    send_notification(
                        recipient_id=str(self.kunjungan.pegawai.id),
                        recipient_type='pegawai',
                        notification_type=self._get_notification_type(new_status),
                        title='Pembaruan Kunjungan',
                        message=pegawai_message,
                        related_object_id=str(self.kunjungan.id)
                    )
                except Exception as notif_err:
                    logger.warning("Gagal mengirim notifikasi workflow ke pegawai: %s", notif_err)
        
        # Notifikasi admin
        if new_status in ['menunggu_admin', 'disetujui_pegawai', 'ditolak_pegawai', 'cancelled']:
            try:
                admin_message = self._get_admin_notification_message(new_status)
                send_notification(
                    recipient_id='admin',
                    recipient_type='admin',
                    notification_type=self._get_notification_type(new_status),
                    title='Respon / Status Kunjungan',
                    message=admin_message,
                    related_object_id=str(self.kunjungan.id)
                )
            except Exception as notif_err:
                logger.warning("Gagal mengirim notifikasi workflow ke admin: %s", notif_err)

    def _send_tamu_chat_status_update(self, new_status, notes=None, rejection_reason=None):
        """Kirim pesan pembaruan status kunjungan secara real-time ke ruang Chat Tamu."""
        if not self.kunjungan or not self.kunjungan.tamu:
            return

        from .models import ChatMessage
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        ticket_code = str(self.kunjungan.id)[:8].upper()
        pegawai_name = self.kunjungan.pegawai.name if self.kunjungan.pegawai else "Pegawai Tujuan"
        dt_str = (
            timezone.localtime(self.kunjungan.arrival_time).strftime('%d/%m/%Y %H:%M')
            if self.kunjungan.arrival_time else '-'
        )

        status_badges = {
            'menunggu_pegawai': ('⏳ Diteruskan ke Pegawai Tujuan', f'Pengajuan kunjungan Anda telah diverifikasi oleh Admin dan diteruskan kepada **{pegawai_name}** untuk konfirmasi jadwal.'),
            'disetujui_pegawai': ('✅ Disetujui Pegawai (Menunggu ACC Admin)', f'**{pegawai_name}** telah menyetujui jadwal kunjungan Anda. Saat ini menunggu penerbitan Tiket/ACC Final dari Admin, dan Anda sudah dapat memulai percakapan dengan **{pegawai_name}** di menu Chat.'),
            'disetujui': ('🎉 DISETUJUI / ACC FINAL (Tiket Aktif)', 'Selamat! Kunjungan Anda telah di-ACC sepenuhnya oleh Admin.\n• **Tiket / Kartu Kunjungan** Anda sudah aktif dan dapat diunduh/dicetak melalui menu **Dashboard** atau **Aktifitas**.\n• Anda juga dapat mengirim pesan langsung kepada **' + pegawai_name + '** di daftar kontak Chat.'),
            'ditolak_admin': ('❌ Ditolak oleh Admin', 'Mohon maaf, pengajuan kunjungan Anda belum dapat disetujui oleh Admin.'),
            'ditolak_pegawai': ('❌ Ditolak / Usulan Jadwal Ulang dari Pegawai', f'Mohon maaf, **{pegawai_name}** belum dapat menerima kunjungan pada jadwal tersebut.'),
            'in_progress': ('🟢 Kunjungan Sedang Berlangsung', 'Status kunjungan Anda kini tercatat sedang berlangsung (Check-In). Selamat bertamu di Diskominfosantik Kabupaten Bekasi!'),
            'completed': ('🏁 Kunjungan Selesai', 'Kunjungan Anda telah selesai (Check-Out). Terima kasih telah berkunjung ke Diskominfosantik Kabupaten Bekasi!'),
            'cancelled': ('🚫 Kunjungan Dibatalkan', 'Jadwal kunjungan ini telah dibatalkan.'),
        }

        badge_title, detail_desc = status_badges.get(
            new_status,
            (f'ℹ️ Status Diperbarui: {new_status}', self._get_tamu_notification_message(new_status))
        )

        lines = [
            "🤖 Asisten AI Diskominfosantik:",
            f"🔔 **Pembaruan Status Kunjungan #{ticket_code}**",
            "",
            f"• **Status Terbaru**: {badge_title}",
            f"• **Jadwal**: {dt_str} WIB",
            f"• **Pegawai Tujuan**: {pegawai_name}",
            f"• **Keperluan**: {(self.kunjungan.purpose or '-')[:120]}",
        ]
        if rejection_reason:
            lines.append(f"• **Alasan / Catatan**: {rejection_reason}")
        elif notes:
            lines.append(f"• **Catatan**: {notes}")

        lines.extend(["", detail_desc])
        chat_text = "\n".join(lines)

        session_id = str(self.kunjungan.tamu.id)
        chat_msg = ChatMessage.objects.create(
            session_id=session_id,
            sender_id='admin',
            sender_type='admin',
            message_type='text',
            content=chat_text,
        )

        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"chat_{session_id}",
                {
                    'type': 'chat_message',
                    'message_id': str(chat_msg.id),
                    'message': chat_text,
                    'sender_id': 'admin',
                    'sender_type': 'admin',
                    'message_type': 'text',
                    'file_url': None,
                    'created_at': timezone.localtime(chat_msg.created_at).strftime('%H:%M'),
                },
            )
    
    def _get_notification_type(self, status):
        """Mapping status ke tipe notifikasi."""
        mapping = {
            'menunggu_admin': 'visit_registered',
            'menunggu_pegawai': 'visit_forwarded',
            'disetujui_pegawai': 'visit_approved',
            'ditolak_pegawai': 'visit_rejected',
            'ditolak_admin': 'visit_rejected_admin',
            'disetujui': 'visit_acc',
            'in_progress': 'visit_in_progress',
            'completed': 'visit_completed',
            'cancelled': 'system_alert',
        }
        return mapping.get(status, 'system_alert')
    
    def _get_tamu_notification_message(self, status):
        """Generate pesan notifikasi untuk Tamu."""
        pegawai_name = self.kunjungan.pegawai.name if self.kunjungan.pegawai else "Pegawai"
        
        messages = {
            'menunggu_admin': 'Permintaan kunjungan Anda sedang ditinjau oleh Admin',
            'menunggu_pegawai': f'Permintaan kunjungan Anda sedang ditinjau oleh {pegawai_name}',
            'disetujui_pegawai': f'{pegawai_name} telah menyetujui permintaan kunjungan Anda. Menunggu ACC Admin.',
            'ditolak_pegawai': f'Permintaan kunjungan Anda ditolak oleh {pegawai_name}.',
            'ditolak_admin': f'Permintaan kunjungan Anda ditolak oleh Admin karena jadwal tidak tersedia. Silakan ajukan kunjungan di tanggal lain.',
            'disetujui': 'Selamat! Permintaan kunjungan Anda telah di-ACC. Tiket kunjungan Anda sudah aktif.',
            'in_progress': 'Kunjungan Anda sedang berlangsung. Selamat bertamu!',
            'completed': 'Kunjungan Anda telah selesai. Terima kasih atas kunjungan Anda.',
            'cancelled': 'Permintaan kunjungan Anda telah dibatalkan.',
        }
        return messages.get(status, f'Status kunjungan diperbarui menjadi: {status}')
    
    def _get_pegawai_notification_message(self, status):
        """Generate pesan notifikasi untuk Pegawai."""
        tamu_name = self.kunjungan.tamu.name
        
        messages = {
            'menunggu_pegawai': f'Permintaan kunjungan baru dari {tamu_name} menunggu persetujuan Anda.',
            'disetujui': f'Admin telah memberikan ACC untuk kunjungan {tamu_name}.',
            'in_progress': f'Kunjungan {tamu_name} sedang berlangsung.',
            'completed': f'Kunjungan {tamu_name} telah selesai.',
            'cancelled': f'Kunjungan dari {tamu_name} telah dibatalkan.',
        }
        return messages.get(status, 'Status kunjungan diperbarui')
    
    def _get_admin_notification_message(self, status):
        """Generate pesan notifikasi untuk Admin."""
        tamu_name = self.kunjungan.tamu.name
        pegawai_name = self.kunjungan.pegawai.name if self.kunjungan.pegawai else "Pegawai"
        
        messages = {
            'menunggu_admin': f'Permintaan kunjungan baru dari {tamu_name}',
            'disetujui_pegawai': f'{pegawai_name} telah menyetujui kunjungan dari {tamu_name}. Menunggu ACC Anda.',
            'ditolak_pegawai': f'{pegawai_name} menolak kunjungan dari {tamu_name}.',
            'cancelled': f'Kunjungan dari {tamu_name} telah dibatalkan.',
        }
        return messages.get(status, 'Status kunjungan diperbarui')
