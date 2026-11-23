/**
 * chat_client.js — Modul WebSocket Client Terpadu untuk Buku Tamu Digital
 * 
 * Fitur:
 * 1. Skema aman otomatis: wss:// saat HTTPS (produksi/PaaS) dan ws:// untuk HTTP lokal.
 * 2. Exponential backoff reconnect: 1s, 2s, 4s, 8s sampai maksimal 15s + random jitter.
 * 3. Reset backoff counter saat onopen berhasil.
 * 4. Muat ulang riwayat pesan (history sync) saat connect/reconnect agar tidak ada pesan tertinggal.
 * 5. Proteksi tombol kirim: disabled dengan status "Menyambung ulang..." saat koneksi belum OPEN.
 * 6. Tidak reconnect jika ditolak autentikasi (code 4001/4003/4401/1008) atau saat user logout/tutup tab.
 * 7. Keep-alive ping ringan otomatis tiap 30 detik agar koneksi tidak diputus reverse proxy / load balancer.
 */

class ChatClient {
    constructor(options) {
        this.sessionId = options.sessionId;
        this.senderId = options.senderId;
        this.senderType = options.senderType;
        this.sendButton = options.sendButton;
        this.inputElement = options.inputElement;
        this.historyApiUrl = options.historyApiUrl || '/api/chat/messages/';
        this.onMessageReceived = options.onMessageReceived || (() => {});
        this.onMessageUpdated = options.onMessageUpdated || (() => {});
        this.onError = options.onError || (() => {});
        this.onStatusChange = options.onStatusChange || (() => {});

        this.socket = null;
        this.reconnectAttempts = 0;
        this.maxBackoffMs = 15000;
        this.pingInterval = null;
        this.reconnectTimeout = null;
        this.isUnloading = false;
        this.manualDisconnect = false;
        this.authRejected = false;
        this.lastMessageId = options.lastMessageId || null;
        if (!this.lastMessageId) {
            const allMsgs = document.querySelectorAll('.msg-group[data-id]');
            if (allMsgs.length > 0) {
                this.lastMessageId = allMsgs[allMsgs.length - 1].getAttribute('data-id') || null;
            }
        }
        this.originalSendBtnHtml = this.sendButton ? this.sendButton.innerHTML : null;

        // Cegah reconnect jika pengguna berpindah halaman atau menutup tab
        window.addEventListener('beforeunload', () => {
            this.isUnloading = true;
            this.disconnect();
        });
    }

    getWsUrl() {
        const wsScheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
        return `${wsScheme}://${window.location.host}/ws/chat/${encodeURIComponent(this.sessionId)}/`;
    }

    setButtonConnectingState(isInitial) {
        if (!this.sendButton) return;
        this.sendButton.disabled = true;
        const label = isInitial ? 'Menyambung...' : 'Menyambung ulang...';
        this.sendButton.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true" style="width: 0.85rem; height: 0.85rem;"></span> <span style="font-size: 0.75rem;">${label}</span>`;
    }

    setButtonConnectedState() {
        if (!this.sendButton) return;
        this.sendButton.disabled = false;
        if (this.originalSendBtnHtml) {
            this.sendButton.innerHTML = this.originalSendBtnHtml;
        } else {
            this.sendButton.innerHTML = '<i class="fas fa-paper-plane"></i>';
        }
    }

    setButtonDisabledAuth() {
        if (!this.sendButton) return;
        this.sendButton.disabled = true;
        this.sendButton.innerHTML = '<span style="font-size: 0.75rem; color: #ef4444;"><i class="fas fa-lock me-1"></i> Akses Ditolak</span>';
    }

    connect() {
        if (!this.sessionId || this.authRejected || this.isUnloading) return;

        this.manualDisconnect = false;
        this.setButtonConnectingState(this.reconnectAttempts === 0);
        this.onStatusChange('connecting');

        try {
            const url = this.getWsUrl();
            this.socket = new WebSocket(url);

            this.socket.onopen = (e) => {
                console.log(`[ChatClient] Terhubung ke chat session: ${this.sessionId}`);
                this.reconnectAttempts = 0;
                this.setButtonConnectedState();
                this.startPing();
                this.onStatusChange('connected');

                // Muat ulang riwayat pesan dari server setelah onopen/reconnect
                this.syncHistory();
            };

            this.socket.onmessage = (e) => {
                try {
                    const data = JSON.parse(e.data);
                    
                    // Abaikan pong keep-alive
                    if (data.action === 'pong' || data.type === 'pong') {
                        return;
                    }

                    if (data.action === 'error') {
                        this.onError(data.message);
                        return;
                    }

                    if (data.action === 'edit' || data.action === 'delete') {
                        this.onMessageUpdated(data);
                        return;
                    }

                    if (data.message_id) {
                        this.lastMessageId = data.message_id;
                    }

                    this.onMessageReceived(data, true);
                } catch (err) {
                    console.error('[ChatClient] Gagal memproses pesan masuk:', err);
                }
            };

            this.socket.onerror = (e) => {
                console.warn('[ChatClient] WebSocket error event:', e);
            };

            this.socket.onclose = (e) => {
                this.stopPing();
                console.log(`[ChatClient] Koneksi tertutup (code: ${e.code}, reason: ${e.reason})`);

                // 4001: Unauthorized, 4003: Forbidden, 4401: Auth Failed, 1008: Policy Violation
                if ([4001, 4003, 4401, 1008].includes(e.code)) {
                    console.error('[ChatClient] Penolakan autentikasi/izin. Reconnect dihentikan.');
                    this.authRejected = true;
                    this.setButtonDisabledAuth();
                    this.onStatusChange('auth_rejected');
                    return;
                }

                if (this.isUnloading || this.manualDisconnect) {
                    return;
                }

                this.scheduleReconnect();
            };
        } catch (err) {
            console.error('[ChatClient] Gagal menginisialisasi WebSocket:', err);
            this.scheduleReconnect();
        }
    }

    scheduleReconnect() {
        if (this.authRejected || this.isUnloading || this.manualDisconnect) return;

        this.setButtonConnectingState(false);
        this.onStatusChange('reconnecting');

        // Backoff: 1s, 2s, 4s, 8s, 15s (maksimal 15s)
        const baseDelay = Math.min(Math.pow(2, this.reconnectAttempts) * 1000, this.maxBackoffMs);
        // Tambahkan jitter acak (0 - 500 ms) agar request tidak bertumpuk
        const jitter = Math.floor(Math.random() * 500);
        const delay = baseDelay + jitter;

        this.reconnectAttempts++;
        console.log(`[ChatClient] Menyambung ulang dalam ${Math.round(delay)}ms (percobaan #${this.reconnectAttempts})...`);

        if (this.reconnectTimeout) {
            clearTimeout(this.reconnectTimeout);
        }

        this.reconnectTimeout = setTimeout(() => {
            this.connect();
        }, delay);
    }

    startPing() {
        this.stopPing();
        // Kirim ping tiap 30 detik
        this.pingInterval = setInterval(() => {
            if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                this.socket.send(JSON.stringify({ action: 'ping' }));
            }
        }, 30000);
    }

    stopPing() {
        if (this.pingInterval) {
            clearInterval(this.pingInterval);
            this.pingInterval = null;
        }
    }

    syncHistory() {
        if (!this.sessionId) return;
        
        let url = `${this.historyApiUrl}?session_id=${encodeURIComponent(this.sessionId)}`;
        if (this.lastMessageId) {
            url += `&last_id=${encodeURIComponent(this.lastMessageId)}`;
        }

        fetch(url)
            .then(res => res.json())
            .then(data => {
                if (data.success && Array.isArray(data.messages) && data.messages.length > 0) {
                    console.log(`[ChatClient] Sinkronisasi ${data.messages.length} pesan server.`);
                    data.messages.forEach(msg => {
                        // Cek apakah pesan sudah ada di DOM untuk menghindari duplikasi
                        const exists = document.querySelector(`.msg-group[data-id="${msg.id}"]`);
                        if (!exists) {
                            this.lastMessageId = msg.id;
                            this.onMessageReceived({
                                message_id: msg.id,
                                message: msg.content,
                                sender_id: msg.sender_id,
                                sender_type: msg.sender_type,
                                message_type: msg.message_type || 'text',
                                file_url: msg.file_url,
                                created_at: msg.created_at
                            }, false);
                        }
                    });
                }
            })
            .catch(err => console.warn('[ChatClient] Gagal sinkronisasi riwayat pesan:', err));
    }

    send(data) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            const payload = typeof data === 'string' ? data : JSON.stringify(data);
            this.socket.send(payload);
            return true;
        } else {
            alert('Koneksi sedang terputus. Mohon tunggu sistem menyambung ulang...');
            return false;
        }
    }

    disconnect() {
        this.manualDisconnect = true;
        this.stopPing();
        if (this.reconnectTimeout) {
            clearTimeout(this.reconnectTimeout);
            this.reconnectTimeout = null;
        }
        if (this.socket) {
            try {
                this.socket.close();
            } catch (e) {}
            this.socket = null;
        }
    }

    switchSession(newSessionId, lastMessageId = null) {
        if (!newSessionId) return;
        this.disconnect();
        this.sessionId = newSessionId;
        this.lastMessageId = lastMessageId || null;
        this.authRejected = false;
        this.reconnectAttempts = 0;
        this.manualDisconnect = false;
        this.connect();
    }
}

/**
 * Helper terpadu untuk perpindahan multi-room chat tanpa reload halaman
 * dan sinkronisasi sidebar real-time melalui channel global '/ws/notifications/'.
 */
const ChatMultiRoomHelper = {
    palette: ['#059669', '#b45309', '#0f766e', '#2563eb', '#7c3aed', '#c026d3', '#0284c7'],

    escapeHtml(text) {
        if (window.SecurityUtils && typeof window.SecurityUtils.escapeHtml === 'function') {
            return window.SecurityUtils.escapeHtml(text);
        }
        return String(text || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;')
            .replace(/`/g, '&#96;');
    },

    sanitizeFileUrl(rawUrl) {
        if (window.SecurityUtils && typeof window.SecurityUtils.sanitizeSafeUrl === 'function') {
            return window.SecurityUtils.sanitizeSafeUrl(rawUrl);
        }
        const trimmed = String(rawUrl || '').trim();
        if (!trimmed || /[\s\u0000-\u001f\u007f<>`"'\\]/.test(trimmed)) return null;
        if (trimmed.startsWith('/')) {
            return trimmed.startsWith('//') ? null : trimmed;
        }
        return /^https?:\/\//i.test(trimmed) ? trimmed : null;
    },

    colorizeAvatars(root = document) {
        root.querySelectorAll('.avatar-squircle').forEach(el => {
            const name = el.getAttribute('data-name') || '';
            let hash = 0;
            for (let i = 0; i < name.length; i++) {
                hash = name.charCodeAt(i) + ((hash << 5) - hash);
            }
            const colorIndex = Math.abs(hash) % ChatMultiRoomHelper.palette.length;
            el.style.backgroundColor = ChatMultiRoomHelper.palette[colorIndex];
        });
    },

    findSidebarItem(container, sessionId) {
        if (!container || !sessionId) return null;
        const items = container.querySelectorAll('.chat-item');
        for (const el of items) {
            if (el.getAttribute('data-session-id') === sessionId || el.getAttribute('data-id') === sessionId) {
                return el;
            }
        }
        return null;
    },

    setItemUnread(item, count) {
        if (!item) return;
        const safeCount = Math.max(0, parseInt(count || 0, 10) || 0);
        item.setAttribute('data-unread', String(safeCount));
        let badge = item.querySelector('.badge-unread');
        if (safeCount > 0) {
            if (!badge) {
                const snippetRow = item.querySelector('.last-msg')?.parentElement;
                if (snippetRow) {
                    badge = document.createElement('span');
                    badge.className = 'badge-unread';
                    snippetRow.appendChild(badge);
                }
            }
            if (badge) badge.textContent = String(safeCount);
        } else if (badge) {
            badge.remove();
        }
    },

    moveItemToTop(container, item) {
        if (!container || !item) return;
        const firstChat = container.querySelector('.chat-item');
        if (firstChat && firstChat !== item) {
            container.insertBefore(item, firstChat);
        } else if (!firstChat) {
            const filterEmpty = container.querySelector('#chatFilterEmpty');
            if (filterEmpty) container.insertBefore(item, filterEmpty);
            else container.appendChild(item);
        }
    },

    handleNotificationEvent(detail, options) {
        if (!detail || detail.event_type !== 'chat_sidebar_update' || !detail.session_id) return;
        const container = document.getElementById(options.containerId || 'chatListContainer');
        if (!container) return;

        let item = ChatMultiRoomHelper.findSidebarItem(container, detail.session_id);
        if (!item && typeof options.createItem === 'function') {
            item = options.createItem(detail);
            if (item) {
                const emptyBox = container.querySelector('.chat-empty-initial');
                if (emptyBox) emptyBox.remove();
                ChatMultiRoomHelper.colorizeAvatars(item);
            }
        }
        if (!item) return;

        const snippetEl = item.querySelector('.last-msg');
        if (snippetEl && detail.preview !== undefined) {
            snippetEl.textContent = detail.preview;
        }
        const timeEl = item.querySelector('.time');
        if (timeEl && detail.created_at) {
            timeEl.textContent = detail.created_at;
        }

        const activeSession = typeof options.getActiveSession === 'function' ? options.getActiveSession() : null;
        if (detail.session_id === activeSession) {
            ChatMultiRoomHelper.setItemUnread(item, 0);
        } else if (detail.sender_type && detail.sender_type !== options.mySenderType) {
            const cur = parseInt(item.getAttribute('data-unread') || '0', 10) || 0;
            ChatMultiRoomHelper.setItemUnread(item, cur + 1);
        }

        ChatMultiRoomHelper.moveItemToTop(container, item);
        if (typeof options.applyFilters === 'function') {
            options.applyFilters();
        }
    },

    updateActiveSidebarUi(containerId, sessionId) {
        const container = document.getElementById(containerId || 'chatListContainer');
        if (!container) return null;
        container.querySelectorAll('.chat-item.active').forEach(el => el.classList.remove('active'));
        const target = ChatMultiRoomHelper.findSidebarItem(container, sessionId);
        if (target) {
            target.classList.add('active');
            ChatMultiRoomHelper.setItemUnread(target, 0);
        }
        return target;
    },

    createMessageElement(msg, mySenderType, formatMessageFn) {
        const isSent = msg.sender_type === mySenderType;
        const type = isSent ? 'sent' : 'received';
        const content = msg.content ?? msg.message ?? '';
        const messageType = msg.message_type || 'text';
        const fileUrl = msg.file_url || null;
        const messageId = msg.id || msg.message_id || null;
        const isAi = content.indexOf('🤖') !== -1 || content.indexOf('Asisten AI') !== -1;

        const msgGroup = document.createElement('div');
        msgGroup.className = `msg-group ${type}${isAi ? ' is-ai-msg' : ''}`;
        if (messageId) msgGroup.setAttribute('data-id', messageId);
        msgGroup.setAttribute('data-created-at', msg.created_at_iso || new Date().toISOString());

        let bubbleContent = '';
        const safeFileUrl = fileUrl ? ChatMultiRoomHelper.sanitizeFileUrl(fileUrl) : null;
        if (messageType === 'deleted') {
            bubbleContent = '<span style="font-style: italic; opacity: 0.7;">Pesan ini telah dihapus</span>';
        } else if (messageType === 'image' && safeFileUrl) {
            bubbleContent = `<img src="${ChatMultiRoomHelper.escapeHtml(safeFileUrl)}" style="max-width: 240px; max-height: 240px; object-fit: contain; border-radius: 10px;" alt="Gambar">`;
        } else if (messageType === 'file' && safeFileUrl) {
            const rawFilename = safeFileUrl.split('/').pop();
            const filename = ChatMultiRoomHelper.escapeHtml(rawFilename);
            bubbleContent = `<a href="${ChatMultiRoomHelper.escapeHtml(safeFileUrl)}" target="_blank" rel="noopener noreferrer" class="file-card">
                <i class="fas fa-file-alt"></i>
                <div class="file-info">
                    <span class="file-name">${filename}</span>
                    <span class="file-size">Klik untuk mengunduh</span>
                </div>
            </a>`;
        } else if ((messageType === 'image' || messageType === 'file') && fileUrl) {
            bubbleContent = '<span style="font-style: italic; opacity: 0.7;">Lampiran tidak valid</span>';
        } else if (typeof formatMessageFn === 'function') {
            bubbleContent = formatMessageFn(content, isSent && !isAi);
        } else if (window.SecurityUtils && typeof window.SecurityUtils.formatChatMessageHtml === 'function') {
            bubbleContent = window.SecurityUtils.formatChatMessageHtml(content, isSent && !isAi);
        } else {
            bubbleContent = ChatMultiRoomHelper.escapeHtml(content);
        }

        let actionButtons = '';
        if (isSent && messageType !== 'deleted') {
            const editBtn = messageType === 'text'
                ? '<a href="#" class="edit-msg-btn" title="Edit pesan"><i class="fas fa-pencil-alt"></i></a>'
                : '';
            actionButtons = `${editBtn}<a href="#" class="delete-msg-btn" title="Hapus pesan"><i class="fas fa-trash"></i></a>`;
        }

        let ticks = '';
        if (isSent) {
            ticks = `<i class="fas fa-check-double msg-check${msg.is_read ? ' read' : ''}"></i>`;
        }

        msgGroup.innerHTML = `
            <div class="msg-bubble">${bubbleContent}</div>
            <div class="msg-meta-row">
                <span class="msg-time">${ChatMultiRoomHelper.escapeHtml(msg.created_at || '')}</span>
                ${ticks}
                ${actionButtons}
            </div>
        `;
        return msgGroup;
    },

    initMultiRoomChat(config) {
        let switchSeq = 0;

        if (config.backButtonId && config.chatCardId) {
            const backBtn = document.getElementById(config.backButtonId);
            const cardEl = document.getElementById(config.chatCardId);
            if (backBtn && cardEl) {
                backBtn.addEventListener('click', (e) => {
                    if (window.innerWidth <= 992) {
                        e.preventDefault();
                        cardEl.classList.remove('chat-active');
                    }
                });
            }
        }

        window.addEventListener('ws:notification', (e) => {
            ChatMultiRoomHelper.handleNotificationEvent(e.detail, {
                containerId: config.containerId || 'chatListContainer',
                getActiveSession: config.getActiveSession,
                mySenderType: config.mySenderType,
                applyFilters: config.applyFilters,
                createItem: config.createSidebarItemFromEvent,
            });
        });

        async function switchRoom(sessionId, opts = {}) {
            if (!sessionId) return;
            const mySeq = ++switchSeq;
            const pushState = opts.pushState !== false;

            if (typeof config.onResetEditMode === 'function') {
                config.onResetEditMode();
            }

            if (typeof config.setActiveSession === 'function') {
                config.setActiveSession(sessionId);
            }

            ChatMultiRoomHelper.updateActiveSidebarUi(config.containerId || 'chatListContainer', sessionId);
            if (typeof config.applyFilters === 'function') {
                config.applyFilters();
            }

            if (config.chatCardId) {
                const cardEl = document.getElementById(config.chatCardId);
                if (cardEl) cardEl.classList.add('chat-active');
            }

            if (pushState && window.history && window.history.pushState) {
                const url = new URL(window.location.href);
                if (url.searchParams.get('session') !== sessionId) {
                    url.searchParams.delete('guest');
                    url.searchParams.set('session', sessionId);
                    window.history.pushState({ session: sessionId }, '', url.pathname + url.search);
                }
            }

            try {
                const resp = await fetch(
                    `${config.historyApiUrl || '/api/chat/messages/'}?session_id=${encodeURIComponent(sessionId)}&mark_read=1`,
                    { headers: { 'Accept': 'application/json' } }
                );
                if (!resp.ok) {
                    throw new Error(`HTTP ${resp.status}`);
                }
                const data = await resp.json();
                if (mySeq !== switchSeq || !data.success) return;

                if (typeof config.ensureRoomVisible === 'function') {
                    config.ensureRoomVisible();
                }

                const meta = data.room_meta || {};
                const headerEl = document.querySelector('.chat-header');
                if (headerEl) {
                    const titleEl = headerEl.querySelector('.room-title');
                    const subEl = headerEl.querySelector('.room-subtitle');
                    const pillEl = headerEl.querySelector('.room-tag-pill');
                    const iconBox = headerEl.querySelector('.room-icon-square');
                    if (titleEl && meta.name) titleEl.textContent = meta.name;
                    if (subEl) subEl.textContent = meta.subtitle || 'Saluran komunikasi terverifikasi';
                    if (pillEl && meta.role_label) pillEl.textContent = meta.role_label;
                    if (iconBox && typeof config.getHeaderIconHtml === 'function') {
                        iconBox.innerHTML = config.getHeaderIconHtml(meta);
                    }
                }

                // Pastikan kontak tersedia di sidebar (khusus kasus memulai chat baru lewat pencarian)
                const container = document.getElementById(config.containerId || 'chatListContainer');
                if (container && !ChatMultiRoomHelper.findSidebarItem(container, sessionId) && typeof config.createSidebarItemFromMeta === 'function') {
                    const newItem = config.createSidebarItemFromMeta(meta, data.messages || []);
                    if (newItem) {
                        const emptyBox = container.querySelector('.chat-empty-initial');
                        if (emptyBox) emptyBox.remove();
                        ChatMultiRoomHelper.colorizeAvatars(newItem);
                        ChatMultiRoomHelper.moveItemToTop(container, newItem);
                        ChatMultiRoomHelper.updateActiveSidebarUi(config.containerId || 'chatListContainer', sessionId);
                        if (typeof config.applyFilters === 'function') {
                            config.applyFilters();
                        }
                    }
                }

                const msgArea = document.getElementById('messageArea');
                let newLastMsgId = null;
                if (msgArea) {
                    msgArea.innerHTML = '';
                    const messages = Array.isArray(data.messages) ? data.messages : [];
                    if (messages.length === 0) {
                        msgArea.innerHTML = `
                            <div class="empty-chat">
                                <div class="empty-chat-icon"><i class="fas fa-comments"></i></div>
                                <h5>Mulai percakapan</h5>
                                <p>${ChatMultiRoomHelper.escapeHtml(config.emptyRoomText || 'Kirim pesan untuk berkoordinasi secara langsung.')}</p>
                            </div>
                        `;
                    } else {
                        let prevDateLabel = null;
                        messages.forEach(m => {
                            if (m.date_label && m.date_label !== prevDateLabel) {
                                const sep = document.createElement('div');
                                sep.className = 'chat-date-separator';
                                sep.innerHTML = `<span>${ChatMultiRoomHelper.escapeHtml(m.date_label)}</span>`;
                                msgArea.appendChild(sep);
                                prevDateLabel = m.date_label;
                            }
                            msgArea.appendChild(
                                ChatMultiRoomHelper.createMessageElement(m, config.mySenderType, config.formatMessageFn)
                            );
                            newLastMsgId = m.id;
                        });
                        msgArea.scrollTop = msgArea.scrollHeight;
                    }
                }

                const existingSocket = typeof config.getChatSocket === 'function' ? config.getChatSocket() : null;
                if (existingSocket && typeof existingSocket.switchSession === 'function') {
                    existingSocket.switchSession(sessionId, newLastMsgId);
                } else if (typeof config.initChatSocket === 'function') {
                    config.initChatSocket(sessionId, newLastMsgId);
                }

                if (typeof config.onSyncBellBadge === 'function' && meta.unread_notifications_count !== null && meta.unread_notifications_count !== undefined) {
                    config.onSyncBellBadge(meta.unread_notifications_count);
                }
                if (typeof config.onRoomSwitched === 'function') {
                    config.onRoomSwitched(data);
                }
            } catch (err) {
                console.warn('[ChatMultiRoomHelper] Fallback reload karena gagal memuat room:', err);
                window.location.href = `?session=${encodeURIComponent(sessionId)}`;
            }
        }

        window.addEventListener('popstate', (event) => {
            const url = new URL(window.location.href);
            const targetSession = (event.state && event.state.session) || url.searchParams.get('session') || url.searchParams.get('guest');
            if (targetSession && targetSession !== config.getActiveSession()) {
                switchRoom(targetSession, { pushState: false });
            }
        });

        return switchRoom;
    },
};

// Export global untuk pemakaian di template
window.ChatClient = ChatClient;
window.ChatMultiRoomHelper = ChatMultiRoomHelper;
