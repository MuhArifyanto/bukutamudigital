"""
views/admin.py — Re-export dari sub-modul admin_dashboard, admin_kunjungan, admin_settings.

File ini dipertahankan agar import lama tetap berfungsi selama masa transisi.
Logika bisnis sudah dipecah ke:
  - admin_dashboard.py  → dashboard, statistik, kalender
  - admin_kunjungan.py  → list, detail, manual create, export, cetak PDF/kartu
  - admin_settings.py   → profil, instansi, pegawai, pengguna, audit log, chat, notifikasi
"""

from .admin_dashboard import (  # noqa: F401
    admin_dashboard_view,
    admin_statistik_view,
    admin_kalender_view,
    admin_kalender_download_template,
)

from .admin_kunjungan import (  # noqa: F401
    admin_kunjungan_detail_view,
    admin_cetak_kartu_view,
    admin_kunjungan_list_view,
    admin_kunjungan_manual_create,
    admin_kunjungan_export_excel,
    admin_kunjungan_cetak_pdf,
)

from .admin_settings import (  # noqa: F401
    admin_profil_view,
    admin_instansi_view,
    admin_notifications_view,
    admin_chat_view,
    admin_audit_log_view,
    admin_audit_log_cetak_pdf,
    admin_pengguna_view,
    admin_pegawai_view,
    admin_pegawai_update_role,
    admin_pegawai_update_status,
)
