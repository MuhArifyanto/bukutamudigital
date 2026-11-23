/**
 * Utilitas keamanan frontend terpadu & event handler CSP-compliant
 * (tanpa unsafe-inline script maupun inline on* attribute).
 */
(function (global) {
    'use strict';

    const _CONTROL_OR_SPACE_RE = /[\s\u0000-\u001f\u007f<>`"'\\]/;
    const _MD_LINK_RE = /\[([^\]]+)\]\(([^)\s]+)\)/g;

    function escapeHtml(value) {
        return String(value == null ? '' : value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;')
            .replace(/`/g, '&#96;');
    }

    function sanitizeHttpUrl(rawUrl) {
        if (typeof rawUrl !== 'string') return null;
        const trimmed = rawUrl.trim();
        if (!trimmed || !/^https?:\/\//i.test(trimmed)) return null;
        if (_CONTROL_OR_SPACE_RE.test(trimmed)) return null;
        try {
            const origin = (global.location && global.location.origin) || 'https://localhost';
            const parsed = new URL(trimmed, origin);
            if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
                return null;
            }
            if (!parsed.hostname) return null;
            return parsed.href;
        } catch (e) {
            return null;
        }
    }

    function sanitizeSafeUrl(rawUrl) {
        if (typeof rawUrl !== 'string') return null;
        const trimmed = rawUrl.trim();
        if (!trimmed || _CONTROL_OR_SPACE_RE.test(trimmed)) return null;

        // Izinkan path relatif same-origin (/...) namun tolak protocol-relative (//...)
        if (trimmed.startsWith('/')) {
            if (trimmed.startsWith('//') || trimmed.startsWith('/\\')) return null;
            try {
                const origin = (global.location && global.location.origin) || 'https://localhost';
                const parsed = new URL(trimmed, origin);
                if (parsed.origin !== origin) return null;
                return parsed.pathname + parsed.search + parsed.hash;
            } catch (e) {
                return null;
            }
        }
        return sanitizeHttpUrl(trimmed);
    }

    function _formatInlineMarkdown(escapedText) {
        return escapedText
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/\n/g, '<br>');
    }

    function _extractValidMarkdownLinks(escapedText, linkTokens, linkBuilder) {
        return escapedText.replace(
            /\[([^\]\n]+)\]\((https?:\/\/[^\s)]+)\)/g,
            function (fullMatch, label, escapedUrl) {
                if (/&quot;|&#39;|&lt;|&gt;|&#96;|&#x27;|&#x22;/i.test(escapedUrl)) {
                    return fullMatch;
                }
                const decodedUrl = escapedUrl.replace(/&amp;/g, '&');
                const safeHref = sanitizeHttpUrl(decodedUrl);
                if (!safeHref) {
                    return fullMatch;
                }
                const token = '\uE000L' + linkTokens.length + '\uE001';
                linkTokens.push(linkBuilder(label, escapeHtml(safeHref), safeHref));
                return token;
            }
        );
    }

    function formatChatMessageHtml(rawText, isSelf) {
        const clean = String(rawText == null ? '' : rawText).replace(/[\uE000\uE001]/g, '');
        const linkColor = isSelf ? '#bfdbfe' : '#2563eb';
        const linkTokens = [];
        let safe = _extractValidMarkdownLinks(escapeHtml(clean), linkTokens, function (label, safeHrefAttr) {
            return `<a href="${safeHrefAttr}" target="_blank" rel="noopener noreferrer" style="color: ${linkColor}; text-decoration: underline; font-weight: 600;">${label}</a>`;
        });
        safe = _formatInlineMarkdown(safe);
        return safe.replace(/\uE000L(\d+)\uE001/g, function (_, idx) {
            return linkTokens[Number(idx)] || '';
        });
    }

    function _formatChatBlockLines(text) {
        const lines = text.split('\n');
        const out = [];
        for (let i = 0; i < lines.length; i++) {
            const trimLine = lines[i].trim();
            if (!trimLine) continue;
            if (trimLine.startsWith('•') || trimLine.startsWith('-') || trimLine.startsWith('* ')) {
                const content = trimLine.replace(/^[•\-\*]\s*/, '').trim();
                out.push(`<div class="chat-list-row"><span class="chat-bullet-symbol">•</span><span class="chat-list-text">${content}</span></div>`);
            } else if (/^\d+\.\s+/.test(trimLine)) {
                const match = trimLine.match(/^(\d+\.)\s+(.*)$/);
                if (match) {
                    out.push(`<div class="chat-list-row"><span class="chat-num-symbol">${match[1]}</span><span class="chat-list-text">${match[2]}</span></div>`);
                } else {
                    out.push(`<div class="chat-text-row">${trimLine}</div>`);
                }
            } else {
                out.push(`<div class="chat-text-row">${trimLine}</div>`);
            }
        }
        return out.join('');
    }

    function formatRichChatMessage(rawText, isPureSent) {
        if (!rawText) return '';
        let cleaned = String(rawText || '').replace(/[\uE000\uE001]/g, '').trim();

        const chips = [];
        cleaned = cleaned.replace(/\[\[chip:([^|\]]+)(?:\|([^\]]+))?\]\]/g, function (_, action, label) {
            chips.push({ action: action.trim(), label: (label || action).trim() });
            return '';
        });

        cleaned = cleaned.replace(/👉\s*\**\s*(?:sentuh\s+)?pilihan\s+tindakan(?:\s+cepat)?:\s*\**\s*$/gim, '').trim();

        const aiPrefixRe = /^🤖\s*Asisten AI(?: Diskominfosantik)?:?\s*\n*/i;
        const isAiMessage = aiPrefixRe.test(cleaned);
        if (isAiMessage) {
            cleaned = cleaned.replace(aiPrefixRe, '').trim();
        }

        const linkTokens = [];
        let safe = _extractValidMarkdownLinks(escapeHtml(cleaned), linkTokens, function (label, safeHrefAttr, rawSafeHref) {
            const isMaps = rawSafeHref.indexOf('maps.google') !== -1 || rawSafeHref.indexOf('goo.gl') !== -1 || rawSafeHref.indexOf('/maps') !== -1;
            if (isMaps) {
                return `<a href="${safeHrefAttr}" target="_blank" rel="noopener noreferrer" class="chat-maps-btn"><i class="fas fa-map-marked-alt"></i> <span>${label}</span> <i class="fas fa-external-link-alt chat-ext-icon"></i></a>`;
            }
            return `<a href="${safeHrefAttr}" target="_blank" rel="noopener noreferrer" class="chat-link">${label} <i class="fas fa-external-link-alt chat-ext-icon"></i></a>`;
        });

        const strongColor = isPureSent ? 'color:#ffffff;' : '';
        safe = safe.replace(/\*\*([^*]+)\*\*/g, `<strong class="chat-bold" style="${strongColor}">$1</strong>`);
        safe = safe.replace(/(^|[^\*])\*([^\*\n]+)\*([^\*]|$)/g, '$1<em class="chat-italic">$2</em>$3');
        safe = safe.replace(/`([^`\n]+)`/g, '<code class="chat-code">$1</code>');

        function restoreLinks(html) {
            return html.replace(/\uE000L(\d+)\uE001/g, function (_, idx) {
                return linkTokens[Number(idx)] || '';
            });
        }

        if (isPureSent && !isAiMessage) {
            return restoreLinks(safe);
        }

        const blocks = safe.split(/\n{2,}/);
        let renderedHtml = '';

        if (isAiMessage) {
            renderedHtml += `
                <div class="ai-header-card">
                    <div class="ai-header-badge">
                        <i class="fas fa-robot"></i>
                        <span>Asisten AI Diskominfosantik</span>
                    </div>
                    <span class="ai-header-live"><span class="ai-live-dot"></span> Aktif</span>
                </div>
            `;
        }

        for (let i = 0; i < blocks.length; i++) {
            const block = blocks[i].trim();
            if (!block) continue;
            if (block.startsWith('⚠️')) {
                renderedHtml += `<div class="chat-callout callout-warning">${_formatChatBlockLines(block)}</div>`;
            } else if (block.startsWith('⏱️')) {
                renderedHtml += `<div class="chat-callout callout-sla">${_formatChatBlockLines(block)}</div>`;
            } else if (block.startsWith('📌') || block.startsWith('📋') || block.startsWith('✅')) {
                renderedHtml += `<div class="chat-callout callout-info">${_formatChatBlockLines(block)}</div>`;
            } else if (block.startsWith('💡')) {
                renderedHtml += `<div class="chat-callout callout-tip">${_formatChatBlockLines(block)}</div>`;
            } else if (block.startsWith('📍')) {
                renderedHtml += `<div class="chat-callout callout-location">${_formatChatBlockLines(block)}</div>`;
            } else {
                renderedHtml += `<div class="chat-block">${_formatChatBlockLines(block)}</div>`;
            }
        }

        if (chips.length > 0) {
            const chipsHtml = chips.map(function (c) {
                return `<button type="button" class="chat-action-chip" data-action="${escapeHtml(c.action)}">${escapeHtml(c.label)}</button>`;
            }).join('');
            renderedHtml += `
                <div class="chat-action-panel">
                    <div class="chat-action-title">
                        <i class="fas fa-hand-pointer"></i> <span>Pilihan Tindakan Cepat:</span>
                    </div>
                    <div class="chat-action-chips">${chipsHtml}</div>
                </div>
            `;
        }

        return restoreLinks(renderedHtml || safe);
    }

    function renderChatAttachmentHtml(messageType, fileUrl) {
        const safeUrl = fileUrl ? sanitizeSafeUrl(fileUrl) : null;
        if (!safeUrl) {
            return '<span style="font-style: italic; opacity: 0.7;">Lampiran tidak valid</span>';
        }
        const escapedUrl = escapeHtml(safeUrl);
        if (messageType === 'image') {
            return `<img src="${escapedUrl}" style="max-width: 240px; max-height: 240px; object-fit: contain; border-radius: 10px;" alt="Gambar">`;
        }
        const rawFilename = safeUrl.split('/').pop() || 'lampiran';
        return `<a href="${escapedUrl}" target="_blank" rel="noopener noreferrer" class="file-card">
            <i class="fas fa-file-alt"></i>
            <div class="file-info">
                <span class="file-name">${escapeHtml(rawFilename)}</span>
                <span class="file-size">Klik untuk mengunduh</span>
            </div>
        </a>`;
    }

    // Delegated handler CSP-compliant untuk fallback gambar, auto-print, auto-submit & konfirmasi form
    if (typeof document !== 'undefined') {
        document.addEventListener('error', function (e) {
            const target = e && e.target;
            if (!target || target.tagName !== 'IMG') return;
            if (target.dataset.hideOnError === '1') {
                target.style.display = 'none';
                return;
            }
            const fallback = target.getAttribute('data-fallback-src');
            if (fallback) {
                target.removeAttribute('data-fallback-src');
                const safeFallback = sanitizeSafeUrl(fallback);
                if (safeFallback) {
                    target.src = safeFallback;
                }
            }
        }, true);

        document.addEventListener('click', function (e) {
            const printBtn = e.target && e.target.closest ? e.target.closest('[data-action="print"]') : null;
            if (printBtn) {
                e.preventDefault();
                if (typeof global.print === 'function') {
                    global.print();
                }
            }
        });

        document.addEventListener('change', function (e) {
            const el = e.target;
            if (el && el.dataset && el.dataset.autoSubmit === '1' && el.form) {
                el.form.submit();
            }
        });

        document.addEventListener('submit', function (e) {
            const form = e.target;
            if (form && form.dataset && form.dataset.confirm) {
                if (!global.confirm(form.dataset.confirm)) {
                    e.preventDefault();
                }
            }
        });

        global.addEventListener('load', function () {
            if (document.body && document.body.dataset && document.body.dataset.autoPrint === '1') {
                if (typeof global.print === 'function') {
                    global.print();
                }
            }
        });
    }

    global.SecurityUtils = {
        escapeHtml: escapeHtml,
        sanitizeHttpUrl: sanitizeHttpUrl,
        sanitizeSafeUrl: sanitizeSafeUrl,
        formatChatMessageHtml: formatChatMessageHtml,
        formatRichChatMessage: formatRichChatMessage,
        renderChatAttachmentHtml: renderChatAttachmentHtml,
    };
})(window);
