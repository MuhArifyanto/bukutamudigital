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

                if (this.isUnloading) {
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
        if (this.authRejected || this.isUnloading) return;

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
}

// Export global untuk pemakaian di template
window.ChatClient = ChatClient;
