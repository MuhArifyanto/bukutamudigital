"""
views/api.py — Re-export dari sub-modul api_notifikasi, api_chat, api_admin.

File ini dipertahankan agar import lama tetap berfungsi selama masa transisi.
Logika bisnis sudah dipecah ke:
  - api_notifikasi.py → notifikasi, status kunjungan
  - api_chat.py       → chat (send, upload, history, delete, search)
  - api_admin.py      → kalender, kunjungan, profil, webhook, stats, debug
"""

from .api_notifikasi import (  # noqa: F401
    api_mark_notification_read,
    api_mark_all_notifications_read,
    api_update_kunjungan_status,
    api_get_unread_count,
    api_get_recent_notifications,
)

from .api_chat import (  # noqa: F401
    api_send_chat_message,
    api_upload_chat_file,
    api_search_users,
    api_get_chat_messages,
    api_delete_chat_message,
)

from .api_admin import (  # noqa: F401
    api_update_quota,
    api_toggle_holiday,
    api_import_calendar_csv,
    api_google_holidays,
    api_check_quota,
    api_quick_checkin,
    api_get_visits_by_date,
    api_import_visits_excel,
    api_update_profile_picture,
    api_tamu_update_profile_picture,
    api_tamu_update_profile_data,
    api_update_profile_data,
    api_change_password,
    api_update_notification_settings,
    api_toggle_user_status,
    api_dashboard_stats,
    api_debug_calendar_settings,
    api_debug_counts,
    api_webhook_delete_user,
)
