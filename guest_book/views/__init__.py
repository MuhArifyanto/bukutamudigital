# Package for guest_book views
from .auth import login_view, register_view, logout_view, api_firebase_login, admin_login_view, tamu_password_reset_request, tamu_password_reset_confirm
from .tamu import (
    landing_view, tentang_kami_view, kebijakan_privasi_view,
    dashboard_view, kunjungan_baru_view, riwayat_view,
    kunjungan_detail_view, kunjungan_batal_view, pesan_baru_view,
    notifications_view, user_chat_view, tamu_kunjungan_cetak_pdf,
    profil_view, tamu_cetak_kartu_view
)
from .admin import (
    admin_dashboard_view, admin_statistik_view, admin_kunjungan_list_view,
    admin_kunjungan_manual_create,
    admin_kunjungan_export_excel, admin_kunjungan_cetak_pdf,
    admin_kalender_view, admin_chat_view, admin_profil_view,
    admin_instansi_view, admin_notifications_view, admin_kalender_download_template,
    admin_kunjungan_detail_view, admin_cetak_kartu_view
)
from .api import (
    api_mark_notification_read, api_update_kunjungan_status,
    api_get_unread_count, api_update_quota, api_toggle_holiday,
    api_import_calendar_csv, api_send_chat_message,
    api_get_chat_messages, api_google_holidays, api_change_password,
    api_quick_checkin, api_upload_chat_file, api_update_profile_picture, api_update_profile_data,
    api_tamu_update_profile_picture, api_tamu_update_profile_data,
    api_get_recent_notifications,
    api_get_visits_by_date,
    api_dashboard_stats,
    api_check_quota,
    api_search_users,
    api_import_visits_excel,
    api_debug_calendar_settings,
    api_update_notification_settings,
    api_debug_counts
)
