import json
import logging
import re
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.utils import timezone
from .models import ChatMessage, Kunjungan

logger = logging.getLogger(__name__)

_SAFE_CHAT_ATTACHMENT_PATH_RE = re.compile(r'^chat_attachments/[A-Za-z0-9._-]+$')
_IMAGE_CHAT_EXTENSIONS = {'png', 'jpg', 'jpeg'}
_DOC_CHAT_EXTENSIONS = {'doc', 'docx', 'xls', 'xlsx', 'pdf'}
_ALL_CHAT_EXTENSIONS = _IMAGE_CHAT_EXTENSIONS | _DOC_CHAT_EXTENSIONS


def _resolve_ws_identity(user, session):
    """
    Menentukan identitas WebSocket murni dari database & sesi aktif sisi server.
    Fail closed (return None) bila sesi palsu, akun nonaktif/dihapus, atau 2FA belum lolos.
    """
    session = session or {}

    # 1. Django Staff / Admin Auth (dengan verifikasi active & 2FA)
    if (
        user
        and getattr(user, 'is_authenticated', False)
        and getattr(user, 'is_staff', False)
        and getattr(user, 'is_active', False)
    ):
        from .views.base import ADMIN_2FA_VERIFIED_SESSION_KEY, resolve_admin_record
        from .security_utils import decrypt_secret

        admin_record = resolve_admin_record(user)
        if admin_record and admin_record.two_fa_enabled and admin_record.two_fa_secret:
            if decrypt_secret(admin_record.two_fa_secret):
                if session.get(ADMIN_2FA_VERIFIED_SESSION_KEY) != str(user.pk):
                    return None
        full_name = getattr(user, 'get_full_name', lambda: '')() or user.username
        return {'type': 'admin', 'id': 'admin', 'name': full_name or 'Administrator'}

    # 2. Sesi Tamu aktif di DB
    tamu_id = session.get('tamu_id')
    if tamu_id:
        try:
            from .models import Admin, Tamu

            tamu = Tamu.objects.filter(id=tamu_id, account_status='active').first()
            if not tamu:
                return None
            if tamu.is_admin:
                if (
                    tamu.email
                    and Admin.objects.filter(
                        email__iexact=tamu.email,
                        account_status='active',
                        two_fa_enabled=True,
                    ).exists()
                ):
                    return None
                return {'type': 'admin', 'id': 'admin', 'name': tamu.name}
            return {'type': 'tamu', 'id': str(tamu.id), 'name': tamu.name}
        except (ValueError, TypeError, ValidationError):
            return None

    # 3. Sesi Pegawai aktif di DB
    pegawai_id = session.get('pegawai_id')
    if pegawai_id:
        try:
            from .models import Pegawai

            pegawai = Pegawai.objects.filter(id=pegawai_id, account_status='active').first()
            if not pegawai:
                return None
            return {'type': 'pegawai', 'id': str(pegawai.id), 'name': pegawai.name}
        except (ValueError, TypeError, ValidationError):
            return None

    return None


class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.room_group_name = f'chat_{self.session_id}'
        self.message_timestamps = []

        # 1. Resolusi identitas pengirim murni dari server (session & auth scope)
        self.identity = await self.resolve_identity()
        if not self.identity:
            await self.close(code=4003)  # Forbidden / Unauthorized
            return

        # 2. Validasi izin akses room / percakapan
        has_permission = await self.check_chat_permission()
        if not has_permission:
            await self.close(code=4003)  # Forbidden
            return

        # 3. Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    @database_sync_to_async
    def resolve_identity(self):
        """
        Menentukan identitas pengguna yang terhubung murni dari sisi server & database.
        Mengembalikan dict {'type': 'admin'|'pegawai'|'tamu', 'id': str, 'name': str}
        atau None jika anonim / nonaktif / tidak valid.
        """
        return _resolve_ws_identity(self.scope.get('user'), self.scope.get('session', {}))

    @database_sync_to_async
    def check_chat_permission(self):
        """
        Validasi apakah pengguna memiliki hak akses ke ruang percakapan (session_id).
        Aturan:
        - Admin: Akses universal ke seluruh room chat.
        - Pegawai: Hanya ke pegawai_admin_{pegawai_id} miliknya atau kunjungan_{id} jika ditugaskan.
        - Tamu: Hanya ke tamu_{tamu_id} miliknya atau kunjungan_{id} miliknya.
        """
        if not self.identity:
            return False

        from .models import ChatRoom
        from .permissions import PermissionManager

        user_type = self.identity['type']
        user_id = self.identity['id']
        parsed = ChatRoom.parse_session_id(self.session_id)
        room_type = parsed['room_type']
        entity_uuid = parsed['entity_uuid']

        # Admin memiliki hak akses universal
        if user_type == 'admin':
            return True

        # Pegawai
        if user_type == 'pegawai':
            if room_type == ChatRoom.RoomType.PEGAWAI_ADMIN:
                target_pegawai_id = str(entity_uuid) if entity_uuid else self.session_id.replace('pegawai_admin_', '', 1)
                return user_id == target_pegawai_id

            if room_type == ChatRoom.RoomType.KUNJUNGAN and entity_uuid is not None:
                try:
                    kunjungan = Kunjungan.objects.select_related('pegawai', 'tamu').get(id=entity_uuid)
                    if not PermissionManager.can_access_chat_pegawai_tamu(kunjungan):
                        return False
                    return str(kunjungan.pegawai_id) == user_id
                except Kunjungan.DoesNotExist:
                    return False
            return False

        # Tamu
        if user_type == 'tamu':
            if room_type == ChatRoom.RoomType.TAMU_ADMIN or self.session_id == user_id:
                target_tamu_id = (
                    str(entity_uuid)
                    if entity_uuid
                    else (self.session_id.replace('tamu_', '', 1) if self.session_id.startswith('tamu_') else self.session_id)
                )
                return user_id == target_tamu_id

            if room_type == ChatRoom.RoomType.KUNJUNGAN and entity_uuid is not None:
                try:
                    kunjungan = Kunjungan.objects.select_related('pegawai', 'tamu').get(id=entity_uuid)
                    if not PermissionManager.can_access_chat_pegawai_tamu(kunjungan):
                        return False
                    return str(kunjungan.tamu_id) == user_id
                except Kunjungan.DoesNotExist:
                    return False
            return False

        return False

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        # 1. Validasi struktur JSON
        try:
            text_data_json = json.loads(text_data)
        except Exception:
            await self.send(text_data=json.dumps({
                'action': 'error',
                'message': 'Format data tidak valid (harus JSON).'
            }))
            return

        if not isinstance(text_data_json, dict):
            await self.send(text_data=json.dumps({
                'action': 'error',
                'message': 'Payload harus berupa object JSON.'
            }))
            return

        action = text_data_json.get('action', 'create')

        # 2. Keep-alive ping/pong
        if action == 'ping' or text_data_json.get('type') == 'ping':
            await self.send(text_data=json.dumps({'action': 'pong', 'type': 'pong'}))
            return

        # 3. Rate Limiting per koneksi: maksimal 5 pesan per detik
        now_ts = timezone.now().timestamp()
        self.message_timestamps = [ts for ts in self.message_timestamps if now_ts - ts < 1.0]
        if len(self.message_timestamps) >= 5:
            await self.send(text_data=json.dumps({
                'action': 'error',
                'message': 'Pengiriman pesan terlalu cepat. Mohon tunggu sejenak.'
            }))
            return
        self.message_timestamps.append(now_ts)

        # 4. Validasi aksi yang didukung
        if action not in ['create', 'edit', 'delete', 'reset_ai']:
            await self.send(text_data=json.dumps({
                'action': 'error',
                'message': f'Aksi "{action}" tidak dikenal.'
            }))
            return

        # 5. Verifikasi ulang status akun aktif di database pada setiap aksi mutasi (K-3)
        fresh_identity = await self.resolve_identity()
        if not fresh_identity:
            await self.close(code=4003)
            return
        self.identity = fresh_identity

        # Identitas murni dari server (mengabaikan total field sender_id & sender_type dari klien)
        sender_id = self.identity['id']
        sender_type = self.identity['type']

        if action == 'reset_ai':
            if self.session_id.startswith('kunjungan_') or sender_type not in ('tamu', 'admin'):
                await self.send(text_data=json.dumps({
                    'action': 'error',
                    'message': 'Aksi reset AI hanya diizinkan pada percakapan layanan umum.'
                }))
                return
            await self._reset_ai_session()
            await self.send(text_data=json.dumps({
                'action': 'reset_ai',
                'success': True,
                'handoff_active': False,
            }))
            return

        if action == 'create':
            raw_message = text_data_json.get('message')
            if not raw_message or not isinstance(raw_message, str) or not raw_message.strip():
                await self.send(text_data=json.dumps({
                    'action': 'error',
                    'message': 'Pesan tidak boleh kosong.'
                }))
                return

            message = raw_message.strip()
            if len(message) > 2000:
                await self.send(text_data=json.dumps({
                    'action': 'error',
                    'message': 'Pesan terlalu panjang (maksimal 2000 karakter).'
                }))
                return

            message_type = text_data_json.get('message_type', 'text')
            if message_type not in ('text', 'image', 'file'):
                await self.send(text_data=json.dumps({
                    'action': 'error',
                    'message': 'Tipe pesan tidak valid.'
                }))
                return

            file_path = None
            file_url = None
            if message_type in ('file', 'image'):
                raw_path = text_data_json.get('file_path')
                if (
                    not isinstance(raw_path, str)
                    or '..' in raw_path
                    or '\\' in raw_path
                    or not _SAFE_CHAT_ATTACHMENT_PATH_RE.match(raw_path)
                ):
                    await self.send(text_data=json.dumps({
                        'action': 'error',
                        'message': 'Path lampiran tidak valid atau tidak diizinkan.'
                    }))
                    return

                ext = raw_path.rsplit('.', 1)[-1].lower() if '.' in raw_path else ''
                expected_exts = _IMAGE_CHAT_EXTENSIONS if message_type == 'image' else _DOC_CHAT_EXTENSIONS
                if ext not in expected_exts or ext not in _ALL_CHAT_EXTENSIONS:
                    await self.send(text_data=json.dumps({
                        'action': 'error',
                        'message': 'Format file ditolak oleh server karena alasan keamanan.'
                    }))
                    return

                exists_in_storage = await database_sync_to_async(default_storage.exists)(raw_path)
                if not exists_in_storage:
                    await self.send(text_data=json.dumps({
                        'action': 'error',
                        'message': 'File lampiran tidak ditemukan di penyimpanan server.'
                    }))
                    return

                file_path = raw_path
                # Selalu bentuk file_url murni di server (abaikan file_url kiriman klien)
                file_url = await database_sync_to_async(default_storage.url)(file_path)

            # Save message to database
            msg = await self.save_message(sender_id, sender_type, message, message_type, file_path)

            # Create notification based on server identity & session context
            if self.session_id.startswith('kunjungan_') and sender_type in ('tamu', 'pegawai'):
                await self._notify_kunjungan_counterpart(sender_type, message)
            elif sender_type == 'tamu' and (not (bool(text_data_json.get('ai_assistant')) and message_type == 'text') or self._is_handed_off()):
                await self._notify_admin_new_message(sender_id, message, sender_label='Tamu')
            elif sender_type == 'pegawai':
                await self._notify_admin_new_message(sender_id, message, sender_label='Pegawai')
            elif sender_type == 'admin':
                from .utils import set_session_handoff_to_admin
                set_session_handoff_to_admin(self.session_id, active=True)
                await self._notify_recipient_from_admin(message)

            await self._broadcast_sidebar_update(msg, sender_id, sender_type, message, message_type)

            # Broadcast message to room group
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'chat_message',
                    'message_id': str(msg.id),
                    'message': message,
                    'sender_id': sender_id,
                    'sender_type': sender_type,
                    'message_type': message_type,
                    'file_url': file_url,
                    'created_at': timezone.localtime(msg.created_at).strftime('%H:%M')
                }
            )

            from .utils import is_session_handed_off_to_admin, process_n8n_chat_assistant
            if (
                sender_type == 'tamu'
                and not self.session_id.startswith('kunjungan_')
                and bool(text_data_json.get('ai_assistant'))
                and message_type == 'text'
                and not is_session_handed_off_to_admin(self.session_id)
            ):
                import threading
                threading.Thread(
                    target=process_n8n_chat_assistant,
                    args=(self.session_id, sender_id, message, self.room_group_name),
                    daemon=True,
                ).start()

        elif action == 'edit':
            message_id = text_data_json.get('message_id')
            raw_message = text_data_json.get('message')
            if not message_id or not raw_message or not isinstance(raw_message, str) or not raw_message.strip():
                await self.send(text_data=json.dumps({
                    'action': 'error',
                    'message': 'Data edit pesan tidak lengkap.'
                }))
                return

            message = raw_message.strip()
            if len(message) > 2000:
                await self.send(text_data=json.dumps({
                    'action': 'error',
                    'message': 'Pesan terlalu panjang (maksimal 2000 karakter).'
                }))
                return

            # Update message in database
            success, error_msg = await self.edit_message(message_id, sender_id, sender_type, message)
            if success:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message_updated',
                        'message_id': message_id,
                        'message': message,
                        'action': 'edit'
                    }
                )
            else:
                await self.send(text_data=json.dumps({
                    'action': 'error',
                    'message': error_msg
                }))

        elif action == 'delete':
            message_id = text_data_json.get('message_id')
            if not message_id:
                await self.send(text_data=json.dumps({
                    'action': 'error',
                    'message': 'ID pesan wajib diisi.'
                }))
                return

            # Delete message (soft delete)
            success, error_msg = await self.delete_message(message_id, sender_id, sender_type)
            if success:
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'chat_message_updated',
                        'message_id': message_id,
                        'message': 'Pesan ini telah dihapus',
                        'action': 'delete'
                    }
                )
            else:
                await self.send(text_data=json.dumps({
                    'action': 'error',
                    'message': error_msg or "Gagal menghapus pesan"
                }))

    def _is_handed_off(self):
        from .utils import is_session_handed_off_to_admin
        return is_session_handed_off_to_admin(self.session_id)

    @database_sync_to_async
    def _reset_ai_session(self):
        from .utils import reset_session_ai_mode
        reset_session_ai_mode(self.session_id)

    # Receive message from room group
    async def chat_message(self, event):
        # Send message to WebSocket
        await self.send(text_data=json.dumps({
            'message_id': event.get('message_id'),
            'message': event['message'],
            'sender_id': event['sender_id'],
            'sender_type': event['sender_type'],
            'message_type': event.get('message_type', 'text'),
            'file_url': event.get('file_url'),
            'created_at': event['created_at'],
            'handoff_active': event.get('handoff_active', False),
            'strike_count': event.get('strike_count', 0),
        }))

    # Receive update from room group
    async def chat_message_updated(self, event):
        # Send update to WebSocket
        await self.send(text_data=json.dumps({
            'message_id': event['message_id'],
            'message': event['message'],
            'action': event['action']
        }))

    @database_sync_to_async
    def _broadcast_sidebar_update(self, msg, sender_id, sender_type, message, message_type):
        from .utils import send_chat_sidebar_update
        send_chat_sidebar_update(
            session_id=self.session_id,
            sender_id=sender_id,
            sender_type=sender_type,
            message=message,
            message_type=message_type,
            message_id=msg.id,
            created_at_dt=msg.created_at,
        )

    @database_sync_to_async
    def save_message(self, sender_id, sender_type, content, message_type='text', file_path=None):
        return ChatMessage.objects.create(
            session_id=self.session_id,
            sender_id=sender_id,
            sender_type=sender_type,
            content=content,
            message_type=message_type,
            attachment=file_path
        )

    @database_sync_to_async
    def _notify_kunjungan_counterpart(self, sender_type, message):
        """
        Kirim notifikasi saat Tamu atau Pegawai mengirim pesan di ruang chat kunjungan_{id}.
        - Tamu mengirim -> notifikasi ke Pegawai yang ditugaskan.
        - Pegawai mengirim -> notifikasi ke Tamu pemilik kunjungan.
        """
        from .utils import send_notification
        kunjungan_id = self.session_id.replace('kunjungan_', '')
        try:
            kunjungan = Kunjungan.objects.select_related('tamu', 'pegawai').get(id=kunjungan_id)
        except Exception:
            return

        if sender_type == 'tamu' and kunjungan.pegawai:
            tamu_name = kunjungan.tamu.name if kunjungan.tamu else 'Tamu'
            send_notification(
                recipient_id=str(kunjungan.pegawai.id),
                recipient_type='pegawai',
                notification_type='message_received',
                title='Pesan Baru dari Tamu',
                message=f'{tamu_name}: {message}',
                related_object_id=self.session_id
            )
        elif sender_type == 'pegawai' and kunjungan.tamu:
            pegawai_name = kunjungan.pegawai.name if kunjungan.pegawai else 'Pegawai'
            send_notification(
                recipient_id=str(kunjungan.tamu.id),
                recipient_type='tamu',
                notification_type='message_received',
                title='Pesan Baru dari Pegawai',
                message=f'{pegawai_name}: {message}',
                related_object_id=self.session_id
            )

    @database_sync_to_async
    def _notify_admin_new_message(self, sender_id, message, sender_label='Tamu'):
        """
        Kirim notifikasi ke grup admin saat tamu atau pegawai mengirim pesan.
        Notifikasi dikirim ke group 'notif_admin' yang diikuti oleh semua admin.
        """
        from .utils import send_notification

        sender_name = sender_label
        try:
            import uuid as _uuid
            uid = _uuid.UUID(str(sender_id))
            if sender_label == 'Tamu':
                from .models import Tamu
                obj = Tamu.objects.filter(id=uid).first()
            else:
                from .models import Pegawai
                obj = Pegawai.objects.filter(id=uid).first()
            if obj:
                sender_name = obj.name
        except (ValueError, TypeError):
            pass

        send_notification(
            recipient_id='admin',
            recipient_type='admin',
            notification_type='message_received',
            title=f'Pesan Baru dari {sender_label}',
            message=f'{sender_name}: {message}',
            related_object_id=self.session_id
        )

    @database_sync_to_async
    def _notify_recipient_from_admin(self, message):
        """
        Kirim notifikasi dari Admin ke lawan bicara di percakapan ini
        sesuai relasi room di database server.
        """
        from .utils import send_notification
        if self.session_id.startswith('pegawai_admin_'):
            pegawai_id = self.session_id.replace('pegawai_admin_', '')
            send_notification(
                recipient_id=pegawai_id,
                recipient_type='pegawai',
                notification_type='message_replied',
                title='Pesan Baru dari Admin',
                message=f'Admin: {message}',
                related_object_id=self.session_id
            )
        elif self.session_id.startswith('kunjungan_'):
            kunjungan_id = self.session_id.replace('kunjungan_', '')
            try:
                kunjungan = Kunjungan.objects.select_related('tamu', 'pegawai').get(id=kunjungan_id)
                if kunjungan.tamu:
                    send_notification(
                        recipient_id=str(kunjungan.tamu.id),
                        recipient_type='tamu',
                        notification_type='message_replied',
                        title='Pesan Baru dari Admin',
                        message=f'Admin: {message}',
                        related_object_id=self.session_id
                    )
            except Exception:
                pass
        else:
            tamu_id = self.session_id.replace('tamu_', '') if self.session_id.startswith('tamu_') else self.session_id
            send_notification(
                recipient_id=tamu_id,
                recipient_type='tamu',
                notification_type='message_replied',
                title='Pesan Dibalas oleh Admin',
                message=f'Admin: {message}',
                related_object_id='admin'
            )

    @database_sync_to_async
    def edit_message(self, message_id, sender_id, sender_type, new_content):
        from datetime import timedelta
        import uuid
        
        try:
            msg_uuid = uuid.UUID(str(message_id))
        except (ValueError, TypeError):
            return False, "ID pesan tidak valid"

        try:
            msg = ChatMessage.objects.get(id=msg_uuid, session_id=self.session_id)
            
            # Pengirim harus pemilik pesan atau Admin
            if sender_type != 'admin' and (msg.sender_id != sender_id or msg.sender_type != sender_type):
                return False, "Anda tidak memiliki izin untuk mengedit pesan ini"

            # Cek batas waktu 2 menit
            if timezone.now() - msg.created_at > timedelta(minutes=2):
                return False, "Waktu edit sudah habis (maksimal 2 menit)"
            
            msg.content = new_content
            msg.save(update_fields=['content'])
            return True, ""
        except ChatMessage.DoesNotExist:
            return False, "Pesan tidak ditemukan atau Anda tidak berhak mengedit"

    @database_sync_to_async
    def delete_message(self, message_id, sender_id, sender_type):
        import uuid
        try:
            msg_uuid = uuid.UUID(str(message_id))
        except (ValueError, TypeError):
            return False, "ID pesan tidak valid"

        try:
            msg = ChatMessage.objects.get(id=msg_uuid, session_id=self.session_id)
            
            # Pengirim harus pemilik pesan atau Admin
            if sender_type != 'admin' and (msg.sender_id != sender_id or msg.sender_type != sender_type):
                return False, "Anda tidak memiliki izin untuk menghapus pesan ini"

            old_content = msg.content
            msg.content = "Pesan ini telah dihapus"
            msg.message_type = 'deleted'
            msg.save(update_fields=['content', 'message_type'])
            
            if sender_type == 'admin':
                from .views.base import record_audit_log
                record_audit_log(
                    user_id='admin',
                    user_type='admin',
                    action='delete',
                    table_name='chat_message',
                    record_id=str(msg.id),
                    old_value=f"Menghapus chat: {old_content[:50]}...",
                    ip_address='WebSocket'
                )
                
            return True, ""
        except ChatMessage.DoesNotExist:
            return False, "Pesan tidak ditemukan"


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer untuk notifikasi real-time.
    Mendukung channel groups ganda (notif_admin & admin_notifications) dan audio chime alert.
    """

    async def connect(self):
        session = self.scope.get('session', {})
        user = self.scope.get('user')

        identity = await database_sync_to_async(_resolve_ws_identity)(user, session)
        self.groups = []
        if not identity:
            await self.close(code=4003)
            return

        self.identity = identity
        if identity['type'] == 'admin':
            self.groups = ['notif_admin', 'admin_notifications']
            self.group_name = 'notif_admin'
        elif identity['type'] == 'pegawai':
            pid = identity['id']
            self.groups = [f"notif_pegawai_{pid}", f"notifications_pegawai_{pid}"]
            self.group_name = f"notif_pegawai_{pid}"
        elif identity['type'] == 'tamu':
            tid = identity['id']
            self.groups = [f"notif_tamu_{tid}", f"notifications_tamu_{tid}"]
            self.group_name = f"notif_tamu_{tid}"
        else:
            await self.close(code=4003)
            return

        self._seen_notif_ids = set()
        for grp in self.groups:
            await self.channel_layer.group_add(grp, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'groups'):
            for grp in self.groups:
                await self.channel_layer.group_discard(grp, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            if data.get('action') == 'ping' or data.get('type') == 'ping':
                await self.send(text_data=json.dumps({'action': 'pong', 'type': 'pong'}))
        except Exception:
            pass

    async def _send_deduped(self, payload):
        if not hasattr(self, '_seen_notif_ids'):
            self._seen_notif_ids = set()
        notif_id = payload.get('id') if isinstance(payload, dict) else None
        if notif_id:
            if notif_id in self._seen_notif_ids:
                return
            self._seen_notif_ids.add(notif_id)
            if len(self._seen_notif_ids) > 200:
                self._seen_notif_ids.clear()
        await self.send(text_data=json.dumps(payload))

    async def send_notification(self, event):
        payload = event.get('data') or event.get('notification') or event
        await self._send_deduped(payload)

    async def notification_message(self, event):
        payload = event.get('notification') or event.get('data') or event
        await self._send_deduped(payload)
