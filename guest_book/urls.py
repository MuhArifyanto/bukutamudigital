from django.urls import path
from django.views.generic.base import RedirectView, TemplateView
from . import views
# views sekarang adalah package yang berisi auth, tamu, admin, dan api

app_name = 'tamu'

urlpatterns = [
    # Landing & Static Pages
    path('', views.landing_view, name='landing'),
    path('tentang/', views.tentang_kami_view, name='tentang_kami'),
    path('kebijakan-privasi/', views.kebijakan_privasi_view, name='kebijakan_privasi'),
    path('favicon.ico', RedirectView.as_view(url='/static/images/logo-diskominfosantik.png')),

    # Auth
    path('masuk/', views.login_view, name='login'),
    path('daftar/', views.register_view, name='register'),
    path('keluar/', views.logout_view, name='logout'),
    path('api/auth/firebase/', views.api_firebase_login, name='api_firebase_login'),
    
    # Password Reset
    path('password_reset/', views.tamu_password_reset_request, name='password_reset'),
    path('password_reset/done/', TemplateView.as_view(template_name='guest_book/registration/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', views.tamu_password_reset_confirm, name='password_reset_confirm'),
    path('reset/done/', TemplateView.as_view(template_name='guest_book/registration/password_reset_complete.html'), name='password_reset_complete'),

    # Dashboard
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('admin-portal/login/', views.admin_login_view, name='admin_login'),
    path('admin-portal/', views.admin_dashboard_view, name='admin_dashboard'),
    path('admin-portal/statistik/', views.admin_statistik_view, name='admin_statistik'),
    path('admin-portal/kunjungan/', views.admin_kunjungan_list_view, name='admin_kunjungan_list'),
    path('admin-portal/kunjungan/manual-create/', views.admin_kunjungan_manual_create, name='admin_kunjungan_manual_create'),
    path('admin-portal/kunjungan/export-excel/', views.admin_kunjungan_export_excel, name='admin_kunjungan_export_excel'),
    path('admin-portal/kunjungan/cetak-pdf/', views.admin_kunjungan_cetak_pdf, name='admin_kunjungan_cetak_pdf'),
    path('admin-portal/kunjungan/<uuid:pk>/', views.admin_kunjungan_detail_view, name='admin_kunjungan_detail'),
    path('admin-portal/kunjungan/<uuid:pk>/cetak-kartu/', views.admin_cetak_kartu_view, name='admin_cetak_kartu'),
    path('admin-portal/kalender/', views.admin_kalender_view, name='admin_kalender'),
    path('admin-portal/chat/', views.admin_chat_view, name='admin_chat'),
    path('admin-portal/profil/', views.admin_profil_view, name='admin_profil'),
    path('admin-portal/instansi/', views.admin_instansi_view, name='admin_instansi'),
    path('admin-portal/api/update-quota/', views.api_update_quota, name='api_update_quota'),
    path('admin-portal/api/toggle-holiday/', views.api_toggle_holiday, name='api_toggle_holiday'),
    path('api/dashboard/stats/', views.api_dashboard_stats, name='api_dashboard_stats'),
    path('api/debug/counts/', views.api_debug_counts, name='api_debug_counts'),
    path('admin-portal/api/import-calendar/', views.api_import_calendar_csv, name='api_import_calendar_csv'),
    path('admin-portal/api/import-visits/', views.api_import_visits_excel, name='api_import_visits_excel'),
    path('admin-portal/api/debug-calendar/', views.api_debug_calendar_settings, name='api_debug_calendar_settings'),
    path('admin-portal/kalender/download-template/', views.admin_kalender_download_template, name='admin_kalender_download_template'),
    path('admin-portal/api/chat/send/', views.api_send_chat_message, name='api_send_chat_send'),
    path('admin-portal/api/chat/messages/', views.api_get_chat_messages, name='api_get_chat_messages'),
    path('api/chat/upload/', views.api_upload_chat_file, name='api_upload_chat_file'),
    path('admin-portal/api/chat/search-users/', views.api_search_users, name='api_search_users'),
    path('api/profil/foto/', views.api_tamu_update_profile_picture, name='api_tamu_update_profile_picture'),
    path('api/profil/update/', views.api_tamu_update_profile_data, name='api_tamu_update_profile_data'),
    path('chat/', views.user_chat_view, name='user_chat'),
    path('riwayat/cetak/', views.tamu_kunjungan_cetak_pdf, name='tamu_kunjungan_cetak_pdf'),
    path('profil/', views.profil_view, name='profil'),
    path('admin-portal/api/kunjungan/quick/', views.api_quick_checkin, name='api_quick_checkin'),
    path('api/holidays/<int:year>/', views.api_google_holidays, name='api_google_holidays'),

    # Kunjungan
    path('kunjungan/baru/', views.kunjungan_baru_view, name='kunjungan_baru'),
    path('kunjungan/riwayat/', views.riwayat_view, name='riwayat'),
    path('kunjungan/null/', RedirectView.as_view(pattern_name='tamu:dashboard'), name='kunjungan_null'),
    path('kunjungan/<uuid:pk>/', views.kunjungan_detail_view, name='kunjungan_detail'),
    path('kunjungan/<uuid:pk>/cetak-kartu/', views.tamu_cetak_kartu_view, name='tamu_cetak_kartu'),
    path('kunjungan/<uuid:pk>/batal/', views.kunjungan_batal_view, name='kunjungan_batal'),

    # Pesan
    path('pesan/baru/', views.pesan_baru_view, name='pesan_baru'),

    # Notifikasi
    path('notifikasi/', views.notifications_view, name='notifications'),
    path('api/notifikasi/read/', views.api_mark_notification_read, name='api_mark_notification_read'),
    path('admin-portal/api/kunjungan/status/', views.api_update_kunjungan_status, name='api_update_kunjungan_status'),
    path('api/admin/change-password/', views.api_change_password, name='api_change_password'),
    path('api/admin/profile-picture/', views.api_update_profile_picture, name='api_update_profile_picture'),
    path('api/admin/profile-data/', views.api_update_profile_data, name='api_update_profile_data'),
    path('api/admin/notification-settings/', views.api_update_notification_settings, name='api_update_notification_settings'),
    path('api/admin/unread-count/', views.api_get_unread_count, name='api_get_unread_count'),
    path('api/admin/recent-notifications/', views.api_get_recent_notifications, name='api_get_recent_notifications'),
    path('api/admin/visits-by-date/', views.api_get_visits_by_date, name='api_get_visits_by_date'),
    path('api/check-quota/', views.api_check_quota, name='api_check_quota'),
]
