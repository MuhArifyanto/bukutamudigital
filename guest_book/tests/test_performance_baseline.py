"""
Benchmark baseline performa untuk LANGKAH 0.
Mengukur:
1. Portal Tamu:
   - Beranda (tamu:dashboard)
   - Form Kunjungan (tamu:kunjungan_baru)
   - Riwayat (tamu:riwayat)
   - Chat (tamu:user_chat)
2. Portal Pegawai:
   - Dashboard (tamu:pegawai_dashboard)
   - Daftar Kunjungan (tamu:pegawai_kunjungan_list)
3. Portal Admin:
   - Dashboard (tamu:admin_dashboard)
   - Daftar Kunjungan (tamu:admin_kunjungan_list)
   - Pengguna (tamu:admin_pengguna)
   - Laporan (tamu:admin_statistik)
"""

import time as pytime
import json
from datetime import datetime, date, timedelta, time as dt_time
from django.test import TestCase, Client
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.urls import reverse
from django.utils import timezone
from django.contrib.auth.models import User
from django.contrib.auth.hashers import make_password

from ..models import (
    Tamu, Pegawai, Departemen, Instansi,
    Kunjungan, KunjunganStatus, Notification,
    ChatMessage, CalendarSettings, KunjunganNote
)


class PerformanceBaselineMeasurementTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # 1. Instansi
        cls.instansi = Instansi.objects.create(
            nama="Diskominfosantik Kabupaten Bekasi",
            kapasitas_maksimal=50,
            status_operasional="Aktif",
            jam_buka=dt_time(8, 0),
            jam_tutup=dt_time(16, 0),
            hari_kerja="0,1,2,3,4"
        )

        # 2. Departemen (4)
        cls.deps = []
        dep_names = ["Bidang TIK", "Bidang IKP", "Sekretariat", "Bidang Statistik"]
        for i, name in enumerate(dep_names):
            d = Departemen.objects.create(nama=name, kode=f"DEP{i+1}")
            cls.deps.append(d)

        # 3. Pegawai (25)
        cls.pegawais = []
        for i in range(25):
            role = 'supervisor' if i < 4 else 'staff'
            p = Pegawai.objects.create(
                name=f"Pegawai {i+1:02d}",
                username=f"pegawai{i+1}",
                email=f"pegawai{i+1}@bekasikab.go.id",
                phone=f"0812000000{i+1:02d}",
                department_rel=cls.deps[i % 4],
                role=role,
                account_status="active",
                password=make_password("password123")
            )
            cls.pegawais.append(p)
        cls.pegawai_target = cls.pegawais[0]

        # 4. Admin Django & Admin Tamu
        cls.admin_django = User.objects.create_user(
            username="admin_utama",
            email="admin@bekasikab.go.id",
            password="adminpassword123",
            is_staff=True,
            is_superuser=True
        )
        cls.admin_tamu = Tamu.objects.create(
            name="Administrator",
            email="admin@bekasikab.go.id",
            phone="081199990000",
            nik="admin",
            instansi="Diskominfosantik",
            password=make_password("adminpassword123"),
            is_admin=True,
            account_status="active",
            registration_type="manual"
        )

        # 5. Tamu (150)
        cls.tamus = []
        now = timezone.now()
        for i in range(150):
            t = Tamu.objects.create(
                name=f"Tamu Sample {i+1:03d}",
                email=f"tamu{i+1}@example.com",
                phone=f"08130000{i+1:04d}",
                nik=f"321600000000{i+1:04d}",
                instansi=f"Instansi { (i % 15) + 1 }",
                password=make_password("password123"),
                account_status="active",
                registration_type="manual",
                registration_date=now - timedelta(days=150 - i)
            )
            cls.tamus.append(t)
        cls.tamu_target = cls.tamus[0]

        # 6. Kunjungan (300)
        statuses = [
            'menunggu_admin', 'menunggu_pegawai', 'disetujui',
            'in_progress', 'completed', 'cancelled', 'ditolak_admin'
        ]
        kunjungans = []
        for i in range(300):
            t = cls.tamus[i % 150]
            p = cls.pegawais[i % 25]
            # Sebarkan tanggal: 200 hari lampau, 30 hari ini, 70 hari ke depan
            if i < 200:
                day_offset = -(i % 30) - 1
            elif i < 230:
                day_offset = 0
            else:
                day_offset = (i % 7) + 1
            
            arr_time = now + timedelta(days=day_offset, hours=(i % 6) + 1)
            dep_time = arr_time + timedelta(hours=1)
            st = statuses[i % len(statuses)]
            k = Kunjungan(
                tamu=t,
                pegawai=p,
                purpose=f"Keperluan koordinasi agenda teknis nomor {i+1}",
                arrival_time=arr_time,
                departure_time=dep_time,
                status=st,
                created_at=now - timedelta(days=abs(day_offset) + 1)
            )
            kunjungs = kunjungans.append(k)
        Kunjungan.objects.bulk_create(kunjungans)

        # Kunjungan khusus untuk tamu_target agar ada riwayat & chat
        created_kunjungan = list(Kunjungan.objects.filter(tamu=cls.tamu_target))
        if len(created_kunjungan) < 5:
            for j in range(5):
                Kunjungan.objects.create(
                    tamu=cls.tamu_target,
                    pegawai=cls.pegawais[j % 5],
                    purpose=f"Konsultasi TIK {j+1}",
                    arrival_time=now - timedelta(days=j+1),
                    departure_time=now - timedelta(days=j+1, hours=-1),
                    status='completed'
                )

        # 7. ChatMessage (100)
        chat_msgs = []
        # Chat dengan admin untuk tamu_target
        admin_sess = str(cls.tamu_target.pk)
        for c in range(25):
            sender_type = 'tamu' if c % 2 == 0 else 'admin'
            sender_id = str(cls.tamu_target.pk) if sender_type == 'tamu' else str(cls.admin_tamu.pk)
            chat_msgs.append(ChatMessage(
                session_id=admin_sess,
                sender_id=sender_id,
                sender_type=sender_type,
                content=f"Pesan admin percakapan {c+1}",
                is_read=(c < 20)
            ))
        
        # Chat terkait kunjungan tamu_target dengan pegawai
        tamu_visits = list(Kunjungan.objects.filter(tamu=cls.tamu_target)[:3])
        for v in tamu_visits:
            v_sess = f"kunjungan_{v.id}"
            for c in range(15):
                sender_type = 'tamu' if c % 2 == 0 else 'pegawai'
                sender_id = str(cls.tamu_target.pk) if sender_type == 'tamu' else str(v.pegawai.id)
                chat_msgs.append(ChatMessage(
                    session_id=v_sess,
                    sender_id=sender_id,
                    sender_type=sender_type,
                    content=f"Pesan koordinasi kunjungan {c+1}",
                    is_read=True
                ))
        ChatMessage.objects.bulk_create(chat_msgs)

        # 8. Notifications (50)
        notifs = []
        for n in range(50):
            if n < 20:
                rec_id = str(cls.tamu_target.pk)
                rec_type = 'tamu'
            elif n < 35:
                rec_id = str(cls.pegawai_target.id)
                rec_type = 'pegawai'
            else:
                rec_id = 'admin'
                rec_type = 'admin'
            notifs.append(Notification(
                recipient_id=rec_id,
                recipient_type=rec_type,
                notification_type='system_alert',
                title=f"Notifikasi {n+1}",
                message=f"Isi detail notifikasi ke-{n+1}",
                status='unread' if n % 3 == 0 else 'read'
            ))
        Notification.objects.bulk_create(notifs)

        # 9. CalendarSettings (30 hari bulan ini)
        today = now.date()
        cal_settings = []
        for d in range(1, 29):
            dt = date(today.year, today.month, d)
            cal_settings.append(CalendarSettings(
                date=dt,
                daily_quota=50,
                is_holiday=(dt.weekday() >= 5),
                holiday_name="Akhir Pekan" if dt.weekday() >= 5 else ""
            ))
        CalendarSettings.objects.bulk_create(cal_settings, ignore_conflicts=True)

    def get_role_client(self, role):
        client = Client()
        session = client.session
        if role == 'tamu':
            session['tamu_id'] = str(self.tamu_target.pk)
            session.save()
        elif role == 'pegawai':
            session['pegawai_id'] = str(self.pegawai_target.pk)
            session['pegawai_name'] = self.pegawai_target.name
            session['pegawai_role'] = self.pegawai_target.role
            session.save()
        elif role == 'admin':
            client.force_login(self.admin_django)
            session = client.session
            session['tamu_id'] = str(self.admin_tamu.pk)
            session['is_admin'] = True
            session.save()
        return client

    def measure_url(self, role, url_name, kwargs=None):
        url = reverse(url_name, kwargs=kwargs) if kwargs else reverse(url_name)
        client = self.get_role_client(role)
        
        # Warm up 1x untuk cache / internal setup
        client.get(url)

        # Measure 3x run untuk rata-rata stabil
        times = []
        query_counts = []
        query_times = []
        all_queries = []

        for _ in range(3):
            with CaptureQueriesContext(connection) as ctx:
                t0 = pytime.perf_counter()
                resp = client.get(url)
                t1 = pytime.perf_counter()
            self.assertEqual(resp.status_code, 200, f"Failed rendering {url}: {resp.status_code}")
            times.append((t1 - t0) * 1000.0)
            query_counts.append(len(ctx.captured_queries))
            q_time = sum(float(q.get('time', 0.0)) for q in ctx.captured_queries) * 1000.0
            query_times.append(q_time)
            all_queries = ctx.captured_queries

        avg_time = sum(times) / len(times)
        avg_q_count = sum(query_counts) / len(query_counts)
        avg_q_time = sum(query_times) / len(query_times)

        # Analisis N+1 / Duplicate
        sql_list = [q['sql'] for q in all_queries]
        duplicates = len(sql_list) - len(set(sql_list))

        return {
            'url': url,
            'url_name': url_name,
            'role': role,
            'server_time_ms': round(avg_time, 2),
            'query_count': int(avg_q_count),
            'query_time_ms': round(avg_q_time, 2),
            'duplicates': duplicates,
            'sample_queries': [q['sql'][:120] for q in all_queries[:10]]
        }

    def test_run_benchmark_all_target_pages(self):
        targets = [
            # Portal Tamu
            ('tamu', 'tamu:dashboard', 'Tamu: Beranda (Dashboard)'),
            ('tamu', 'tamu:kunjungan_baru', 'Tamu: Form Kunjungan Baru'),
            ('tamu', 'tamu:riwayat', 'Tamu: Riwayat Kunjungan'),
            ('tamu', 'tamu:user_chat', 'Tamu: Chat Percakapan'),
            # Portal Pegawai
            ('pegawai', 'tamu:pegawai_dashboard', 'Pegawai: Dashboard Utama'),
            ('pegawai', 'tamu:pegawai_kunjungan_list', 'Pegawai: Daftar Kunjungan'),
            # Portal Admin
            ('admin', 'tamu:admin_dashboard', 'Admin: Dashboard Utama'),
            ('admin', 'tamu:admin_kunjungan_list', 'Admin: Daftar Kunjungan'),
            ('admin', 'tamu:admin_pengguna', 'Admin: Manajemen Pengguna'),
            ('admin', 'tamu:admin_statistik', 'Admin: Laporan & Statistik'),
        ]

        results = []
        for role, url_name, label in targets:
            m = self.measure_url(role, url_name)
            m['label'] = label
            results.append(m)

        import os
        scratch_dir = r"C:\Users\Admin\.gemini\antigravity-ide\brain\07880655-69a5-4396-8300-676e63ec84c6\scratch"
        os.makedirs(scratch_dir, exist_ok=True)
        with open(os.path.join(scratch_dir, "baseline_results.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        print("\n" + "="*80)
        print("BASELINE PERFORMANCE REPORT (LANGKAH 0)")
        print("="*80)
        print(f"{'Halaman':<32} | {'Queries':<7} | {'Query (ms)':<10} | {'Server (ms)':<11} | {'Duplikat':<8}")
        print("-"*80)
        for r in results:
            print(f"{r['label']:<32} | {r['query_count']:<7} | {r['query_time_ms']:<10} | {r['server_time_ms']:<11} | {r['duplicates']:<8}")
        print("="*80)
