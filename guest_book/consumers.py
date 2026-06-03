import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from .models import ChatMessage

class ChatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.session_id = self.scope['url_route']['kwargs']['session_id']
        self.room_group_name = f'chat_{self.session_id}'

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        action = text_data_json.get('action', 'create')
        message = text_data_json.get('message')
        sender_id = text_data_json.get('sender_id')
        sender_type = text_data_json.get('sender_type')
        message_type = text_data_json.get('message_type', 'text')
        file_path = text_data_json.get('file_path')
        file_url = text_data_json.get('file_url')
        message_id = text_data_json.get('message_id')
        
        print(f"\n[DEBUG] Action: {action}")
        print(f"[DEBUG] Message ID: {message_id}")
        print(f"[DEBUG] Sender ID: {sender_id}")
        print(f"[DEBUG] Sender Type: {sender_type}")

        if action == 'create':
            if not message or not sender_id or not sender_type:
                return

            # Backend file extension validation
            if message_type in ['file', 'image'] and message:
                allowed_extensions = ['doc', 'docx', 'xls', 'xlsx', 'png', 'jpg', 'jpeg', 'svg']
                ext = message.split('.')[-1].lower() if '.' in message else ''
                if ext not in allowed_extensions:
                    await self.send(text_data=json.dumps({
                        'action': 'error',
                        'message': 'Format file ditolak oleh server karena alasan keamanan.'
                    }))
                    return

            # Save message to database
            msg = await self.save_message(sender_id, sender_type, message, message_type, file_path)

            # Create notification for admin if sender is tamu
            if sender_type == 'tamu':
                await self.create_notification(sender_id, message)
            elif sender_type == 'admin':
                from .utils import send_notification
                await database_sync_to_async(send_notification)(
                    recipient_id=self.session_id,
                    recipient_type='tamu',
                    notification_type='message_replied',
                    title='Pesan Dibalas oleh Admin',
                    message=f'Admin: {message}',
                    related_object_id='admin'
                )

            # Send message to room group
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
        elif action == 'edit':
            if not message_id or not message:
                return
            
            # Update message in database
            success, error_msg = await self.edit_message(message_id, sender_id, message)
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
            if not message_id:
                return
            
            # Delete message (soft delete)
            success = await self.delete_message(message_id, sender_id)
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
                    'message': "Gagal menghapus pesan"
                }))

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
            'created_at': event['created_at']
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
    def create_notification(self, sender_id, message):
        from .models import Tamu
        from .utils import send_notification
        
        tamu = None
        try:
            import uuid
            # Handle if sender_id is a valid UUID or session string
            uuid_obj = uuid.UUID(str(sender_id))
            tamu = Tamu.objects.filter(id=uuid_obj).first()
        except (ValueError, TypeError):
            pass
            
        tamu_name = tamu.name if tamu else "Tamu"
        
        send_notification(
            recipient_id='admin',
            recipient_type='admin',
            notification_type='message_received',
            title='Pesan Baru dari Tamu',
            message=f'{tamu_name} mengirim pesan: {message}',
            related_object_id=self.session_id
        )

    @database_sync_to_async
    def edit_message(self, message_id, sender_id, new_content):
        from datetime import timedelta
        from django.utils import timezone
        import uuid
        
        try:
            msg = ChatMessage.objects.get(id=uuid.UUID(message_id), sender_id=sender_id)
            # Cek batas waktu 2 menit
            if timezone.now() - msg.created_at > timedelta(minutes=2):
                return False, "Waktu edit sudah habis (maksimal 2 menit)"
            
            msg.content = new_content
            msg.save()
            return True, ""
        except (ChatMessage.DoesNotExist, ValueError):
            return False, "Pesan tidak ditemukan atau Anda tidak berhak mengedit"

    @database_sync_to_async
    def delete_message(self, message_id, sender_id):
        import uuid
        try:
            msg = ChatMessage.objects.get(id=uuid.UUID(message_id), sender_id=sender_id)
            old_content = msg.content
            msg.content = "Pesan ini telah dihapus"
            msg.message_type = 'deleted'
            msg.save()
            
            if sender_id == 'admin':
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
                
            return True
        except (ChatMessage.DoesNotExist, ValueError):
            return False

class NotificationConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Default group untuk Admin
        self.group_name = 'notifications_admin'
        
        # Cek apakah user adalah Tamu (berdasarkan session)
        session = self.scope.get('session')
        if session and session.get('tamu_id'):
            self.group_name = 'notifications_tamu'
            
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )

    async def send_notification(self, event):
        await self.send(text_data=json.dumps(event['data']))
