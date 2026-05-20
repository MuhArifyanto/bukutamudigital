"""
Sample data untuk testing Sistem Buku Tamu Digital
Jalankan dengan: python manage.py shell < guest_book/fixtures/sample_data.py
"""

from django.utils import timezone
from datetime import timedelta
from guest_book.models import (
    Tamu, Pegawai, Admin as AdminUser,
    Kunjungan, CalendarSettings,
    Message, Notification
)
import uuid

def create_sample_data():
    print("Creating sample data...")
    
    # ============================================================================
    # Create Sample Tamu (Guests)
    # ============================================================================
    print("\n1. Creating sample Tamu...")
    
    tamu1 = Tamu.objects.create(
        name="Budi Santoso",
        email="budi@example.com",
        phone="081234567890",
        password="hashed_password_here",
        registration_type="manual",
        account_status="active"
    )
    print(f"   ✓ Created Tamu: {tamu1.name}")
    
    tamu2 = Tamu.objects.create(
        name="Siti Nurhaliza",
        email="siti@example.com",
        phone="082345678901",
        password="hashed_password_here",
        registration_type="manual",
        account_status="active"
    )
    print(f"   ✓ Created Tamu: {tamu2.name}")
    
    tamu3 = Tamu.objects.create(
        name="Ahmad Wijaya",
        email="ahmad@gmail.com",
        phone="083456789012",
        registration_type="google_sso",
        google_id="google_id_123456",
        profile_picture="https://example.com/profile.jpg",
        account_status="active"
    )
    print(f"   ✓ Created Tamu (SSO): {tamu3.name}")
    
    # ============================================================================
    # Create Sample Pegawai (Employees)
    # ============================================================================
    print("\n2. Creating sample Pegawai...")
    
    pegawai1 = Pegawai.objects.create(
        name="Ibu Ratna",
        email="ratna@instansi.com",
        phone="081111111111",
        department="Bagian Tamu",
        password="hashed_password_here",
        account_status="active"
    )
    print(f"   ✓ Created Pegawai: {pegawai1.name} ({pegawai1.department})")
    
    pegawai2 = Pegawai.objects.create(
        name="Pak Hendra",
        email="hendra@instansi.com",
        phone="082222222222",
        department="Bagian Administrasi",
        password="hashed_password_here",
        account_status="active"
    )
    print(f"   ✓ Created Pegawai: {pegawai2.name} ({pegawai2.department})")
    
    # ============================================================================
    # Create Sample Admin
    # ============================================================================
    print("\n3. Creating sample Admin...")
    
    admin1 = AdminUser.objects.create(
        name="Admin Sistem",
        email="admin@instansi.com",
        phone="081999999999",
        password="hashed_password_here",
        account_status="active",
        two_fa_enabled=False
    )
    print(f"   ✓ Created Admin: {admin1.name}")
    
    # ============================================================================
    # Create Sample Kunjungan (Visits)
    # ============================================================================
    print("\n4. Creating sample Kunjungan...")
    
    now = timezone.now()
    
    # Visit hari ini - pending
    kunjungan1 = Kunjungan.objects.create(
        tamu=tamu1,
        pegawai=pegawai1,
        arrival_time=now + timedelta(hours=1),
        purpose="Konsultasi Bisnis",
        status="pending"
    )
    print(f"   ✓ Created Kunjungan: {tamu1.name} - {kunjungan1.purpose} (Pending)")
    
    # Visit hari ini - in progress
    kunjungan2 = Kunjungan.objects.create(
        tamu=tamu2,
        pegawai=pegawai2,
        arrival_time=now - timedelta(hours=1),
        purpose="Pertemuan Proyek",
        status="in_progress",
        notes="Sedang diskusi tentang timeline proyek"
    )
    print(f"   ✓ Created Kunjungan: {tamu2.name} - {kunjungan2.purpose} (In Progress)")
    
    # Visit kemarin - completed
    kunjungan3 = Kunjungan.objects.create(
        tamu=tamu3,
        pegawai=pegawai1,
        arrival_time=now - timedelta(days=1, hours=2),
        departure_time=now - timedelta(days=1, hours=1),
        purpose="Kunjungan Kerja Sama",
        status="completed",
        notes="Diskusi berhasil, akan ada follow-up minggu depan"
    )
    print(f"   ✓ Created Kunjungan: {tamu3.name} - {kunjungan3.purpose} (Completed)")
    
    # ============================================================================
    # Create Sample Calendar Settings
    # ============================================================================
    print("\n5. Creating sample Calendar Settings...")
    
    today = timezone.now().date()
    
    # Normal day
    cal1 = CalendarSettings.objects.create(
        date=today,
        daily_quota=50,
        is_holiday=False
    )
    print(f"   ✓ Created Calendar: {today} - Quota: {cal1.daily_quota}")
    
    # Holiday
    holiday_date = today + timedelta(days=7)
    cal2 = CalendarSettings.objects.create(
        date=holiday_date,
        daily_quota=0,
        is_holiday=True,
        holiday_name="Hari Raya Idul Fitri"
    )
    print(f"   ✓ Created Calendar: {holiday_date} - Holiday: {cal2.holiday_name}")
    
    # ============================================================================
    # Create Sample Messages
    # ============================================================================
    print("\n6. Creating sample Messages...")
    
    msg1 = Message.objects.create(
        sender_id=str(pegawai1.id),
        sender_type="pegawai",
        subject="Pertanyaan tentang Sistem",
        content="Bagaimana cara mengubah password di sistem?",
        status="pending"
    )
    print(f"   ✓ Created Message: {msg1.subject} (Pending)")
    
    msg2 = Message.objects.create(
        sender_id=str(tamu1.id),
        sender_type="tamu",
        subject="Laporan Masalah",
        content="Saya tidak bisa login ke sistem",
        status="read"
    )
    print(f"   ✓ Created Message: {msg2.subject} (Read)")
    
    # ============================================================================
    # Create Sample Notifications
    # ============================================================================
    print("\n7. Creating sample Notifications...")
    
    notif1 = Notification.objects.create(
        recipient_id=str(pegawai1.id),
        recipient_type="pegawai",
        notification_type="visit_registered",
        title="Kunjungan Baru",
        message=f"Tamu baru {tamu1.name} telah terdaftar untuk kunjungan",
        status="unread",
        related_object_id=str(kunjungan1.id)
    )
    print(f"   ✓ Created Notification: {notif1.title} (Unread)")
    
    notif2 = Notification.objects.create(
        recipient_id=str(admin1.id),
        recipient_type="admin",
        notification_type="message_received",
        title="Pesan Baru dari Pegawai",
        message=f"Pegawai {pegawai1.name} mengirim pesan baru",
        status="read",
        read_at=now,
        related_object_id=str(msg1.id)
    )
    print(f"   ✓ Created Notification: {notif2.title} (Read)")
    
    print("\n✅ Sample data created successfully!")
    print("\nSummary:")
    print(f"  - Tamu: {Tamu.objects.count()}")
    print(f"  - Pegawai: {Pegawai.objects.count()}")
    print(f"  - Admin: {AdminUser.objects.count()}")
    print(f"  - Kunjungan: {Kunjungan.objects.count()}")
    print(f"  - Calendar Settings: {CalendarSettings.objects.count()}")
    print(f"  - Messages: {Message.objects.count()}")
    print(f"  - Notifications: {Notification.objects.count()}")

if __name__ == "__main__":
    create_sample_data()
