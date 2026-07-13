<div align="center">

<h1>&#x1F4D2; Buku Tamu Digital</h1>

<p><strong>Sistem Informasi Buku Tamu Digital berbasis Web &mdash; Modern, Aman, dan Efisien</strong></p>

<p>
  <img src="https://img.shields.io/badge/Django-%3E%3D5.0-092E20?style=for-the-badge&logo=django&logoColor=white" />
  <img src="https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/MySQL-Database-4479A1?style=for-the-badge&logo=mysql&logoColor=white" />
  <img src="https://img.shields.io/badge/WebSocket-Real--time-FF6B35?style=for-the-badge&logoColor=white" />
  <img src="https://img.shields.io/badge/Firebase-SSO-FFCA28?style=for-the-badge&logo=firebase&logoColor=black" />
</p>

<p>
  <img src="https://img.shields.io/badge/Status-Active-brightgreen?style=flat-square" />
  <img src="https://img.shields.io/badge/Language-Indonesia-red?style=flat-square" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" />
</p>

</div>

---

## &#x1F4CB; Daftar Isi

- [Tentang Proyek](#tentang-proyek)
- [Fitur Unggulan](#fitur-unggulan)
- [Teknologi yang Digunakan](#teknologi-yang-digunakan)
- [Arsitektur dan Struktur Proyek](#arsitektur-dan-struktur-proyek)
- [Hak Akses dan Cara Login](#hak-akses-dan-cara-login)
- [Alur Kerja Sistem](#alur-kerja-sistem)
- [Instalasi dan Konfigurasi](#instalasi-dan-konfigurasi)
- [Konfigurasi Environment](#konfigurasi-environment)
- [Menjalankan Aplikasi](#menjalankan-aplikasi)
- [Catatan Tambahan](#catatan-tambahan)

---

## &#x1F3AF; Tentang Proyek

**Buku Tamu Digital** adalah aplikasi web yang dirancang untuk menggantikan buku tamu konvensional (fisik) menjadi sistem digital yang modern, aman, dan terintegrasi. Sistem ini memungkinkan pengelolaan kunjungan tamu secara digital mulai dari pendaftaran, pemesanan jadwal, verifikasi, hingga pelaporan &mdash; semua dalam satu platform.

Proyek ini awalnya dikembangkan untuk kebutuhan **Diskominfosantik Kabupaten Bekasi**, namun dapat diadaptasi untuk instansi pemerintah maupun swasta lainnya.

### Tiga Peran Pengguna Utama

| Peran | Deskripsi |
|---|---|
| &#x1F9D1; **Tamu (User)** | Pengunjung yang mendaftar, memesan kunjungan, dan memantau status |
| &#x1F6E1;&#xFE0F; **Admin** | Pengelola sistem dengan akses penuh ke seluruh data dan konfigurasi |
| &#x1F454; **Pegawai / Teknisi** | Petugas yang menyetujui, menolak, atau melayani kunjungan di bidangnya |

---

## &#x2728; Fitur Unggulan

### &#x1F464; Portal Tamu
- **Registrasi & Login** &mdash; Daftar manual atau via **Google SSO** (Firebase)
- **Verifikasi CAPTCHA** &mdash; Keamanan registrasi dengan CAPTCHA otomatis
- **Pemesanan Kunjungan** &mdash; Pilih tanggal, tujuan departemen, dan isi detail kunjungan
- **Kartu Kunjungan Digital** &mdash; Cetak/unduh kartu identitas kunjungan (PDF)
- **Riwayat Kunjungan** &mdash; Pantau semua riwayat dan status kunjungan
- **Chat Real-time** &mdash; Komunikasi langsung dengan Admin/Pegawai via WebSocket
- **Notifikasi** &mdash; Pemberitahuan status kunjungan secara real-time

### &#x1F6E1;&#xFE0F; Portal Admin
- **Dashboard Statistik** &mdash; Grafik dan laporan kunjungan komprehensif
- **Manajemen Kunjungan** &mdash; Verifikasi, approval, dan perubahan status kunjungan
- **Kalender & Kuota Harian** &mdash; Atur kuota kunjungan per hari dan jadwal hari libur
- **Manajemen Pengguna** &mdash; Kelola akun Tamu, Pegawai, dan Admin
- **Pengaturan Instansi** &mdash; Konfigurasi profil, logo, jam operasional instansi
- **Chat Real-time** &mdash; Balas pesan tamu secara langsung
- **Audit Log** &mdash; Pencatatan semua perubahan data di sistem
- **Ekspor Laporan** &mdash; Unduh rekapitulasi data dalam format **Excel / PDF**
- **Notifikasi Sistem** &mdash; Alert real-time untuk setiap aktivitas penting

### &#x1F454; Portal Pegawai / Teknisi
- **Approval Kunjungan** &mdash; Terima atau tolak kunjungan yang ditujukan ke bidang
- **Chat Real-time** &mdash; Komunikasi dengan tamu sebelum/selama kunjungan
- **Riwayat Tugas** &mdash; Pantau kunjungan yang pernah ditangani

### &#x1F510; Keamanan
- Login attempt tracking & IP logging
- Session management dengan database
- CSRF protection & XSS filtering
- Security headers aktif di production
- 2FA (Two-Factor Authentication) untuk Admin
- Password hashing menggunakan Django built-in auth

---

## &#x1F6E0; Teknologi yang Digunakan

| Kategori | Teknologi |
|---|---|
| **Backend Framework** | Django >= 5.0 |
| **Real-time** | Django Channels >= 4.1 + Daphne (ASGI) |
| **Database** | MySQL (via `mysqlclient`) |
| **Autentikasi SSO** | Google OAuth 2.0 + Firebase Admin SDK |
| **Email** | Gmail SMTP |
| **Ekspor Data** | OpenPyXL (Excel) |
| **Environment** | python-dotenv |
| **HTTP Client** | Requests |

---

## &#x1F4C1; Arsitektur dan Struktur Proyek

```
bukudigital/
|
+-- bukudigital/                  # Konfigurasi utama Django
|   +-- settings.py               # Pengaturan aplikasi (DB, Email, Firebase, dll.)
|   +-- urls.py                   # URL routing utama
|   +-- asgi.py                   # ASGI config untuk WebSocket (Daphne)
|   +-- wsgi.py
|
+-- guest_book/                   # Aplikasi utama
|   +-- models.py                 # Semua model database
|   +-- consumers.py              # WebSocket consumer (chat real-time)
|   +-- routing.py                # WebSocket URL routing
|   +-- signals.py                # Django signals
|   +-- forms.py                  # Form validasi
|   +-- utils.py                  # Fungsi utilitas
|   +-- urls.py                   # URL routing aplikasi
|   |
|   +-- views/                    # Views (logika halaman)
|   |   +-- admin.py              # Views portal admin
|   |   +-- tamu.py               # Views portal tamu
|   |   +-- auth.py               # Views autentikasi
|   |   +-- api.py                # API endpoints
|   |
|   +-- templates/guest_book/     # HTML Templates (33 template)
|   |   +-- tamu_landing.html     # Halaman utama publik
|   |   +-- tamu_dashboard.html   # Dashboard tamu
|   |   +-- admin_dashboard.html  # Dashboard admin
|   |   +-- admin_statistik.html  # Halaman statistik
|   |   +-- admin_kalender.html   # Manajemen kalender
|   |   +-- ...
|   |
|   +-- static/                   # Aset statis (CSS, JS, gambar)
|
+-- static/                       # Static files global
+-- media/                        # Upload files (foto profil, lampiran)
+-- manage.py                     # Django management script
+-- requirements.txt              # Dependensi Python
+-- .env                          # Konfigurasi environment (tidak di-commit)
```

### &#x1F5C4;&#xFE0F; Relasi Model Database

```
Instansi
Departemen <-------- Pegawai
                        |
Tamu ---- Kunjungan ----+
              |
              +-- KunjunganStatusHistory
              +-- KunjunganNote

Tamu ---- ChatMessage    (Real-time via WebSocket)
      --- Message / MessageReply
      --- Notification
      --- Session / LoginAttempt / AuditLog
```

---

## &#x1F465; Hak Akses dan Cara Login

### &#x1F9D1; A. Tamu (User)

Pengguna umum yang ingin melakukan kunjungan atau melihat riwayat kunjungan.

| Info | Detail |
|---|---|
| **URL Login** | `/masuk/` |
| **URL Daftar** | `/daftar/` |
| **Login dengan** | Email + Password **atau** Google SSO |

**Akun Testing:**
```
Username : user
Password : user123
```

> &#x1F4A1; Anda dapat mendaftar akun baru melalui `/daftar/` jika belum memiliki akun.

---

### &#x1F6E1;&#xFE0F; B. Admin

Pengelola sistem dengan akses penuh ke seluruh fitur manajemen.

| Info | Detail |
|---|---|
| **URL Login** | `/admin-portal/login/` |
| **Akses** | Dashboard, Statistik, Kunjungan, Kalender, Pengguna, Instansi, Chat, Audit Log |

**Akun Testing (default):**
```
Username : admin
Password : admin123
```

> &#x26A0;&#xFE0F; Segera ganti password default setelah instalasi pertama.

---

### &#x1F454; C. Pegawai / Teknisi

Petugas yang bertanggung jawab menerima dan mengelola kunjungan di bidang masing-masing.

| Info | Detail |
|---|---|
| **URL Login** | `/admin-portal/login/` |
| **Akses** | Approval kunjungan, chat, riwayat tugas |

**Akun Testing (default):**
```
Username : teknisi
Password : teknisi123
```

> &#x1F4A1; Akun pegawai dibuat dan dikelola oleh Admin melalui menu **Manajemen Pengguna**.

---

## &#x1F504; Alur Kerja Sistem

```
ALUR KUNJUNGAN
==============

1. REGISTRASI / LOGIN
   Tamu daftar di /daftar/ (+ CAPTCHA) atau login Google SSO

2. PENGAJUAN KUNJUNGAN (BOOKING)
   Pilih tanggal -> Pilih Departemen/Pegawai -> Isi tujuan kunjungan
   Sistem cek kuota harian dan hari libur

3. STATUS: PENDING
   Admin dan Pegawai menerima notifikasi

4. VERIFIKASI OLEH ADMIN / PEGAWAI
   [v] Disetujui  -> Status: IN PROGRESS
   [x] Ditolak    -> Status: CANCELLED
   [+] Selesai    -> Status: COMPLETED

5. CETAK KARTU KUNJUNGAN
   Tamu dapat mengunduh/mencetak kartu identitas kunjungan (PDF)

6. CHAT REAL-TIME (kapan saja)
   Tamu <-> Admin / Pegawai via WebSocket

7. AUDIT DAN LAPORAN
   Admin ekspor rekapitulasi data ke Excel / PDF
```

---

## &#x2699;&#xFE0F; Instalasi dan Konfigurasi

### Prasyarat

Pastikan sistem Anda sudah terpasang:

- **Python** 3.10+
- **MySQL** 8.0+
- **pip** (Python package manager)
- **Git**

### Langkah Instalasi

**1. Clone repositori**
```bash
git clone https://github.com/MuhArifyanto/bukutamudigital.git
cd bukutamudigital
```

**2. Buat dan aktifkan virtual environment**
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux / macOS
python -m venv venv
source venv/bin/activate
```

**3. Install dependensi**
```bash
pip install -r requirements.txt
```

**4. Buat database MySQL**
```sql
CREATE DATABASE bukudigital CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

**5. Konfigurasi file environment**
```bash
# Buat file .env baru dan isi sesuai panduan di bawah
copy .env.example .env
```

**6. Jalankan migrasi database**
```bash
python manage.py migrate
```

**7. Buat akun superuser (Admin utama)**
```bash
python manage.py createsuperuser
```

**8. Kumpulkan file statis**
```bash
python manage.py collectstatic
```

---

## &#x1F511; Konfigurasi Environment

Buat file `.env` di root direktori proyek dengan isi berikut:

```env
# Django Core
SECRET_KEY=your-super-secret-key-here
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost

# Database (MySQL)
DB_NAME=bukudigital
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_HOST=127.0.0.1
DB_PORT=3306

# Email (Gmail SMTP)
EMAIL_HOST_USER=your_email@gmail.com
EMAIL_HOST_PASSWORD=your_16_char_app_password

# Firebase / Google SSO
FIREBASE_WEBHOOK_SECRET=your-firebase-webhook-secret
```

> &#x26A0;&#xFE0F; **PENTING:** Jangan pernah commit file `.env`, `google_credentials.json`, atau `firebase_credentials.json` ke repositori publik!

---

## &#x1F680; Menjalankan Aplikasi

### Mode Development
```bash
python manage.py runserver
```
Akses aplikasi di: `http://127.0.0.1:8000/`

### Mode Production (dengan Daphne/ASGI untuk WebSocket)
```bash
daphne -b 0.0.0.0 -p 8000 bukudigital.asgi:application
```

### URL Penting

| Halaman | URL |
|---|---|
| Landing Page | `http://127.0.0.1:8000/` |
| Login Tamu | `http://127.0.0.1:8000/masuk/` |
| Daftar Tamu | `http://127.0.0.1:8000/daftar/` |
| Dashboard Tamu | `http://127.0.0.1:8000/dashboard/` |
| Login Admin/Pegawai | `http://127.0.0.1:8000/admin-portal/login/` |
| Dashboard Admin | `http://127.0.0.1:8000/admin-portal/` |

---

## &#x1F4DD; Catatan Tambahan

- **Migrasi wajib dijalankan** sebelum pertama kali menggunakan aplikasi:
  ```bash
  python manage.py migrate
  ```

- **Google SSO / Firebase**: Jika fitur ini akan digunakan, pastikan file `google_credentials.json` dan `firebase_credentials.json` sudah dikonfigurasi dengan benar dan diletakkan di root direktori proyek.

- **WebSocket (Chat Real-time)**: Fitur chat menggunakan Django Channels dengan `InMemoryChannelLayer` (development). Untuk production, disarankan menggunakan **Redis** sebagai channel layer:
  ```python
  # settings.py (production)
  CHANNEL_LAYERS = {
      "default": {
          "BACKEND": "channels_redis.core.RedisChannelLayer",
          "CONFIG": {"hosts": [("127.0.0.1", 6379)]},
      }
  }
  ```

- **Email**: Gunakan **App Password** Gmail (16 karakter) bukan password akun biasa. Aktifkan 2FA Gmail terlebih dahulu untuk mendapatkan App Password.

- **Security di Production**: Set `DEBUG=False` dan pastikan `ALLOWED_HOSTS` diisi dengan domain yang benar.

---

<div align="center">

**Dikembangkan dengan &#x2764;&#xFE0F; menggunakan Django**

*Buku Tamu Digital &mdash; Solusi Modern untuk Manajemen Kunjungan Instansi*

</div>
