"""
Observabilitas, Logging JSON Terstruktur, Monitoring Error 500, dan Deteksi Lonjakan Login Gagal.

Dirancang tanpa mengirim PII mentah (NIK, password, email mentah, token) ke log JSON,
Sentry, atau webhook eksternal.
"""
import json
import logging
import sys
import threading
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger('guest_book')
security_logger = logging.getLogger('guest_book.security')


class StructuredJsonFormatter(logging.Formatter):
    """Formatter log JSON satu baris untuk agregasi Docker/Render/ELK/Datadog."""

    _EXTRA_FIELDS = (
        'event_type',
        'status_code',
        'request_path',
        'method',
        'error_type',
        'client_ip',
        'attempt_count',
    )

    def format(self, record):
        payload = {
            'timestamp': datetime.fromtimestamp(record.created, tz=dt_timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'module': record.module,
            'line': record.lineno,
            'message': record.getMessage(),
        }
        for field in self._EXTRA_FIELDS:
            val = getattr(record, field, None)
            if val is not None:
                payload[field] = val
        if record.exc_info:
            payload['exception'] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _capture_sentry(title, *, exc=None, level='error', extra=None):
    """Kirim error/peringatan ke Sentry jika SENTRY_DSN aktif dan sentry-sdk terpasang."""
    if not getattr(settings, 'SENTRY_DSN', ''):
        return False
    import importlib
    try:
        sentry_sdk = importlib.import_module('sentry_sdk')
    except ImportError:
        return False

    try:
        with sentry_sdk.push_scope() as scope:
            if extra:
                for key, val in extra.items():
                    scope.set_extra(key, val)
            if exc is not None:
                sentry_sdk.capture_exception(exc)
            else:
                sentry_sdk.capture_message(title, level=level)
        return True
    except Exception:
        return False


def _post_webhook_sync(url, payload):
    try:
        import requests
        requests.post(url, json=payload, timeout=3)
    except Exception:
        logger.debug("Gagal mengirim webhook alert ke endpoint monitoring.", exc_info=False)


def dispatch_alert_webhook(payload, async_send=None):
    """Kirim payload JSON alert ke SECURITY_ALERT_WEBHOOK_URL jika dikonfigurasi."""
    url = getattr(settings, 'SECURITY_ALERT_WEBHOOK_URL', '').strip()
    if not url or not url.startswith(('https://', 'http://')):
        return False

    if async_send is None:
        async_send = not getattr(settings, 'SECURITY_ALERT_SYNC', 'test' in sys.argv)

    if async_send:
        threading.Thread(target=_post_webhook_sync, args=(url, payload), daemon=True).start()
    else:
        _post_webhook_sync(url, payload)
    return True


def dispatch_security_alert(
    title,
    message,
    *,
    event_type='security_alert',
    severity='critical',
    context=None,
    cooldown_key=None,
    cooldown_seconds=600,
):
    """
    Catat alert operasional/keamanan ke log terstruktur, notifikasi in-app admin,
    webhook opsional, dan Sentry dengan mekanisme cooldown cache agar tidak banjir alert.
    """
    if cooldown_key:
        try:
            acquired = cache.add(cooldown_key, '1', max(int(cooldown_seconds), 1))
            if not acquired:
                return False
        except Exception:
            # Tetap lanjutkan logging jika backend cache sementara bermasalah
            pass

    extra_ctx = {'event_type': event_type}
    if context:
        extra_ctx.update(context)

    log_fn = security_logger.critical if severity == 'critical' else security_logger.error
    log_fn("%s | %s", title, message, extra=extra_ctx)

    try:
        from .utils import send_notification
        send_notification(
            recipient_id='admin',
            recipient_type='admin',
            notification_type='system_alert',
            title=str(title)[:250],
            message=str(message)[:1000],
            related_object_id=event_type,
        )
    except Exception:
        # Jangan pernah gagalkan request jika DB sedang bermasalah saat error 500
        pass

    _capture_sentry(title, level='error' if severity == 'error' else 'fatal', extra=extra_ctx)

    webhook_payload = {
        'event_type': event_type,
        'severity': severity,
        'title': title,
        'message': message,
        'timestamp': timezone.now().isoformat(),
        'context': context or {},
    }
    dispatch_alert_webhook(webhook_payload)

    try:
        if getattr(settings, 'ADMINS', None) and getattr(settings, 'EMAIL_HOST_USER', None):
            from django.core.mail import mail_admins
            mail_admins(subject=f"[ALERT] {title}", message=message, fail_silently=True)
    except Exception:
        pass

    return True


def evaluate_login_attempt_spike(instance):
    """
    Deteksi lonjakan kegagalan LoginAttempt pada jendela waktu berjalan (per-IP & global)
    dan kirim alert ter-throttle ke admin & kanal monitoring.
    """
    if not instance or instance.success:
        return False

    from .models import LoginAttempt

    window_seconds = int(getattr(settings, 'LOGIN_SPIKE_WINDOW_SECONDS', 300))
    ip_threshold = int(getattr(settings, 'LOGIN_SPIKE_IP_THRESHOLD', 10))
    global_threshold = int(getattr(settings, 'LOGIN_SPIKE_GLOBAL_THRESHOLD', 25))
    cooldown_seconds = int(getattr(settings, 'LOGIN_ALERT_COOLDOWN_SECONDS', 600))

    since = timezone.now() - timedelta(seconds=window_seconds)
    triggered = False

    if instance.ip_address and ip_threshold > 0:
        ip_fail_count = LoginAttempt.objects.filter(
            success=False,
            ip_address=instance.ip_address,
            timestamp__gte=since,
        ).count()
        if ip_fail_count >= ip_threshold:
            triggered = dispatch_security_alert(
                title=f"Lonjakan Login Gagal dari IP {instance.ip_address}",
                message=(
                    f"Terdeteksi {ip_fail_count} percobaan login gagal dari IP "
                    f"{instance.ip_address} ({instance.user_type}) dalam {window_seconds} detik terakhir."
                ),
                event_type='login_failure_spike_ip',
                severity='critical',
                context={
                    'client_ip': instance.ip_address,
                    'attempt_count': ip_fail_count,
                },
                cooldown_key=f"alert:login_spike:ip:{instance.ip_address}",
                cooldown_seconds=cooldown_seconds,
            ) or triggered

    if global_threshold > 0:
        global_fail_count = LoginAttempt.objects.filter(
            success=False,
            timestamp__gte=since,
        ).count()
        if global_fail_count >= global_threshold:
            triggered = dispatch_security_alert(
                title="Lonjakan Global Percobaan Login Gagal",
                message=(
                    f"Terdeteksi {global_fail_count} percobaan login gagal di seluruh sistem "
                    f"dalam {window_seconds} detik terakhir."
                ),
                event_type='login_failure_spike_global',
                severity='critical',
                context={'attempt_count': global_fail_count},
                cooldown_key="alert:login_spike:global",
                cooldown_seconds=cooldown_seconds,
            ) or triggered

    return triggered


def _increment_error_counter(cache_key, window_seconds):
    try:
        added = cache.add(cache_key, 1, max(int(window_seconds), 1))
        if added:
            return 1
        return cache.incr(cache_key)
    except Exception:
        return 1


def report_server_error(request, exc=None, status_code=500):
    """
    Catat error HTTP 500 ke logger terstruktur dan Sentry, lalu picu alert admin/webhook
    ketika ambang lonjakan error 500 terpenuhi.
    """
    path = getattr(request, 'path', '<unknown>')[:200]
    method = getattr(request, 'method', 'GET')
    exc_name = type(exc).__name__ if exc is not None else f"HTTP_{status_code}"

    log_extra = {
        'event_type': 'server_error_500',
        'status_code': status_code,
        'request_path': path,
        'method': method,
        'error_type': exc_name,
    }
    if exc is not None:
        logger.error(
            "HTTP %s pada %s %s (%s)",
            status_code,
            method,
            path,
            exc_name,
            exc_info=exc,
            extra=log_extra,
        )
    else:
        logger.error(
            "HTTP %s pada %s %s",
            status_code,
            method,
            path,
            extra=log_extra,
        )

    _capture_sentry(
        f"HTTP {status_code} pada {method} {path}",
        exc=exc,
        level='error',
        extra=log_extra,
    )

    window_seconds = int(getattr(settings, 'SERVER_ERROR_SPIKE_WINDOW_SECONDS', 300))
    threshold = int(getattr(settings, 'SERVER_ERROR_SPIKE_THRESHOLD', 3))
    cooldown_seconds = int(getattr(settings, 'SERVER_ERROR_ALERT_COOLDOWN_SECONDS', 300))

    count = _increment_error_counter('monitoring:http500_count', window_seconds)
    if count >= max(threshold, 1):
        dispatch_security_alert(
            title=f"Lonjakan Error HTTP {status_code} ({count}x)",
            message=(
                f"Terdeteksi {count} error server ({status_code} {exc_name}) dalam "
                f"{window_seconds} detik terakhir (endpoint terakhir: {method} {path})."
            ),
            event_type='server_error_500_spike',
            severity='error',
            context={
                'status_code': status_code,
                'request_path': path,
                'method': method,
                'error_type': exc_name,
                'attempt_count': count,
            },
            cooldown_key='alert:http_500_spike',
            cooldown_seconds=cooldown_seconds,
        )


class ErrorAlertMiddleware:
    """
    Middleware pemantau unhandled exception dan respons 5xx (>=500, kecuali /healthz/).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            response.status_code >= 500
            and request.path != '/healthz/'
            and not getattr(request, '_error_alert_reported', False)
        ):
            report_server_error(request, exc=None, status_code=response.status_code)
        return response

    def process_exception(self, request, exception):
        from django.core.exceptions import PermissionDenied, SuspiciousOperation
        from django.http import Http404

        # Http404 / PermissionDenied / SuspiciousOperation ditangani Django menjadi 404/403/400, bukan HTTP 500
        if isinstance(exception, (Http404, PermissionDenied, SuspiciousOperation)):
            return None

        request._error_alert_reported = True
        report_server_error(request, exc=exception, status_code=500)
        return None
