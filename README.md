<div align="center">

<h1>&#x1F4D2; Buku Tamu Digital Diskominfosantik</h1>

<p><strong>Sistem Informasi Manajemen Kunjungan &amp; Buku Tamu Digital Berbasis Web Terintegrasi AI Chatbot, QR Code Check-In, dan Survei IKM</strong></p>
<p><em>Dinas Komunikasi, Informatika, Statistik dan Persandian (Diskominfosantik) Kabupaten Bekasi</em></p>

<p>
  <a href="https://bukutamudigital.onrender.com/"><img src="https://img.shields.io/badge/Live_Website-bukutamudigital.onrender.com-0a2558?style=for-the-badge&logo=googlechrome&logoColor=white" /></a>
  <img src="https://img.shields.io/badge/Django-5.x-092E20?style=for-the-badge&logo=django&logoColor=white" />
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/MySQL_%2F_TiDB-Database-4479A1?style=for-the-badge&logo=mysql&logoColor=white" />
</p>
<p>
  <img src="https://img.shields.io/badge/WebSocket-Django_Channels_%2B_Daphne-FF6B35?style=for-the-badge&logoColor=white" />
  <img src="https://img.shields.io/badge/Firebase-Google_SSO-FFCA28?style=for-the-badge&logo=firebase&logoColor=black" />
  <img src="https://img.shields.io/badge/n8n_%2B_NLP-Hybrid_AI_Chatbot-EA4B71?style=for-the-badge&logo=n8n&logoColor=white" />
  <img src="https://img.shields.io/badge/Cloudinary-Media_Storage-3448C5?style=for-the-badge&logo=cloudinary&logoColor=white" />
</p>

</div>

---

## &#x1F4CB; Daftar Isi

- [Tentang Proyek](#-tentang-proyek)
- [Fitur Unggulan](#-fitur-unggulan)
- [Hak Akses dan Daftar Akun Login](#-hak-akses-dan-daftar-akun-login)
  - [A. Akun Tamu (Pengunjung)](#a-akun-tamu-pengunjung)
  - [B. Akun Admin (Resepsionis & Pengelola)](#b-akun-admin-resepsionis--pengelola)
  - [C. Daftar Lengkap 17 Akun Pegawai Resmi](#c-daftar-lengkap-17-akun-pegawai-resmi)
- [Alur Kerja Sistem](#-alur-kerja-sistem)
- [Teknologi yang Digunakan](#-teknologi-yang-digunakan)
- [Arsitektur dan Struktur Proyek](#-arsitektur-dan-struktur-proyek)
- [Instalasi dan Konfigurasi Lokal](#-instalasi-dan-konfigurasi-lokal)
- [Konfigurasi Environment (.env)](#-konfigurasi-environment-env)
- [Deployment (Render & Cloud)](#-deployment-render--cloud)

---

## &#x1F3AF; Tentang Proyek

**Buku Tamu Digital Diskominfosantik** adalah platform web modern yang mendigitalisasi seluruh proses administrasi penerimaan tamu di lingkungan **Dinas Komunikasi, Informatika, Statistik dan Persandian (Diskominfosantik) Kabupaten Bekasi**. Sistem ini menggantikan pencatatan buku fisik konvensional menjadi ekosistem layanan digital dari hulu ke hilir: mulai dari pendaftaran janji temu daring (*online booking*), pemindaian tiket **QR Code** di pos resepsionis, notifikasi *chime real-time* ke pegawai tujuan, hingga pengukuran **Indeks Kepuasan Masyarakat (IKM)**.

- **URL Website (Production)**: [https://bukutamudigital.onrender.com/](https://bukutamudigital.onrender.com/)

### Tiga Portal Pengguna Terintegrasi

| Portal | Peran Pengguna | Deskripsi Fungsi Utama |
|---|---|---|
| &#x1F9D1; **Portal Tamu** | Masyarakat / Tamu Instansi | Mendaftar akun (Manual / Google SSO), mengajukan jadwal kunjungan, mengunduh tiket QR Code, konsultasi via Chatbot AI & Live Chat, serta mengisi survei IKM. |
| &#x1F6E1;&#xFE0F; **Portal Admin** | Resepsionis & Administrator | Memverifikasi pengajuan tamu, memindai (*scan*) QR Code kedatangan tamu di lobi, mengelola kuota kalender, memantau statistik & IKM, serta mencetak laporan Excel/PDF. |
| &#x1F454; **Portal Pegawai** | Pejabat & Staf Diskominfosantik | Menerima notifikasi kedatangan tamu secara *real-time*, menyetujui/menolak janji temu, berkomunikasi dengan tamu via Live Chat, dan mencetak rekap kunjungan bidang. |

---

## &#x2728; Fitur Unggulan

### &#x1F464; 1. Portal Tamu (Pengunjung)
- **Autentikasi Modern & Google SSO (Firebase)**: Masuk instan satu klik menggunakan tombol **"Masuk dengan Google"** (tersedia di *Landing Page* `/` maupun halaman `/masuk/`) atau pendaftaran manual dengan Email/NIK.
- **Keamanan Grid Image CAPTCHA Server-Bound**: Dilengkapi verifikasi gambar 4x4 (*21 variasi puzzle server-side*) dengan deteksi trajektori klik manusia untuk mencegah serangan bot.
- **Formulir Booking Kunjungan Interaktif**: Pengecekan otomatis **Kuota Harian** dan **Kalender Hari Libur Nasional / Akhir Pekan** secara *real-time*, pemilihan Bidang/Unit Tujuan, pemilihan Pegawai yang ingin ditemui, jumlah rombongan, dan jenis kartu identitas.
- **Hybrid AI Chatbot & Auto-Routing (NLP + n8n)**: Asisten cerdas berarsitektur *Dual-Engine NLP* (pencocokan *Fuzzy-Token & Levenshtein Distance* lokal yang terhubung dengan *Webhook* AI **n8n**) untuk membantu tamu menemukan bidang dan pegawai yang tepat.
- **Tiket & Kartu Kunjungan Digital Ber-QR Code**: Penerbitan tiket kunjungan resmi (PDF/Cetak) lengkap dengan **QR Code** dan **8 Karakter Kode Tiket Unik** setelah jadwal disetujui.
- **Live Chat Real-Time (WebSocket)**: Obrolan langsung dua arah dengan Admin Resepsionis maupun Pegawai Tujuan (mendukung pengiriman lampiran foto/dokumen).
- **Survei Kepuasan Masyarakat (IKM)**: Pengisian *rating* bintang dan ulasan pelayanan pasca-kunjungan sesuai standar **PermenPAN-RB No. 14 Tahun 2017**.

### &#x1F6E1;&#xFE0F; 2. Portal Admin & Pos Resepsionis
- **Scanner Kamera QR Code (Laptop & Mobile)**: Pemindaian tiket QR Code tamu secara langsung menggunakan webcam laptop atau kamera HP (dilengkapi *multi-stage camera fallback*, pemilih perangkat kamera, fitur **Scan File / Foto QR**, serta input kode tiket manual 8 karakter). Status tamu otomatis berubah menjadi **Hadir di Kantor (`In Progress`)** dalam 1 detik.
- **Dashboard Analitik & Statistik Visual**: Ringkasan metrik kunjungan harian/bulanan, grafik distribusi per bidang, dan pemantauan aktivitas langsung (*live activity*).
- **Manajemen Kunjungan & Walk-in Manual**: Verifikasi pengajuan tamu, input kunjungan langsung (*walk-in*) di meja resepsionis, impor Excel, serta ekspor laporan lengkap ke **Microsoft Excel (`.xlsx`)** dan **PDF**.
- **Rekapitulasi Survei IKM & Rating**: Analisis nilai Indeks Kepuasan Masyarakat, grafik distribusi kepuasan, dan cetak laporan resmi IKM.
- **Manajemen Kalender & Kuota Harian**: Pengaturan batas kuota tamu per hari, aktivasi hari libur/cuti bersama, dan impor jadwal kalender via CSV.
- **Manajemen Pengguna, Pegawai, Instansi & Audit Log**: Pengelolaan status akun Tamu dan Pegawai, pengaturan profil instansi, serta pencatatan jejak aktivitas keamanan (*Audit Log* + Cetak PDF).

### &#x1F454; 3. Portal Pegawai Diskominfosantik
- **Notifikasi Real-Time & Suara Lonceng (*Chime Alert*)**: Pemberitahuan instan melalui WebSocket (lengkap dengan lencana angka notifikasi dan efek suara) saat ada tamu yang mengajukan janji temu atau ketika tamu sudah tiba di lobi kantor.
- **Approval Jadwal Kunjungan**: Wewenang menyetujui (*Approve*) atau menolak (*Reject*) permohonan kunjungan yang ditujukan langsung kepada pegawai terkait beserta catatan alasan.
- **Manajemen Status & Cetak Rekap PDF**: Memantau daftar tamu yang sedang hadir di kantor, menandai kunjungan selesai (*Completed*), dan mencetak laporan kunjungan pegawai dalam format PDF.
- **Live Chat Khusus Pegawai**: Berkomunikasi langsung dengan tamu untuk koordinasi waktu atau dokumen sebelum maupun saat kunjungan berlangsung.

---

## &#x1F465; Hak Akses dan Daftar Akun Login

Berikut adalah rincian akses masuk beserta daftar akun resmi yang dapat digunakan pada sistem **Buku Tamu Digital**:

---

### &#x1F9D1; A. Akun Tamu (Pengunjung)

Pengunjung umum atau perwakilan instansi luar yang ingin mengajukan jadwal kunjungan ke Diskominfosantik Kabupaten Bekasi.

| Informasi | Detail |
|---|---|
| **URL Halaman Utama** | `/` ([https://bukutamudigital.onrender.com/](https://bukutamudigital.onrender.com/)) |
| **URL Login Tamu** | `/masuk/` ([https://bukutamudigital.onrender.com/masuk/](https://bukutamudigital.onrender.com/masuk/)) |
| **URL Registrasi Tamu** | `/daftar/` ([https://bukutamudigital.onrender.com/daftar/](https://bukutamudigital.onrender.com/daftar/)) |
| **Metode Autentikasi** | **1. Login Instan Google SSO** (Tombol *"Masuk dengan Google"* di Beranda / Halaman Masuk)<br>**2. Login Manual** menggunakan **Email / NIK** dan **Password** yang didaftarkan melalui `/daftar/` |

> &#x1F4A1; **Catatan Penggunaan Akun Tamu:**
> - Tamu baru dapat langsung mengklik tombol **"Masuk dengan Google"** tanpa perlu mengisi formulir pendaftaran manual; sistem akan otomatis membuatkan akun Tamu aktif dan mengarahkan ke **Dashboard Tamu** (`/dashboard/`).
> - Jika mendaftar secara manual melalui `/daftar/`, lengkapi Nama Lengkap, NIK (16 digit), Nomor Telepon, Instansi, Email, Password, serta selesaikan verifikasi **Grid CAPTCHA**.

---

### &#x1F6E1;&#xFE0F; B. Akun Admin (Resepsionis & Pengelola)

Petugas resepsionis lobi dan pengelola sistem yang memiliki akses ke **Admin Portal** (Dashboard, Statistik, Survei IKM, Daftar Kunjungan, Scan Tiket QR, Kalender Kunjungan, Chat Admin, Manajemen Pengguna/Pegawai, Pengaturan Instansi, dan Audit Log).

| Informasi | Detail |
|---|---|
| **URL Login Admin** | `/admin-portal/login/` ([https://bukutamudigital.onrender.com/admin-portal/login/](https://bukutamudigital.onrender.com/admin-portal/login/)) |
| **URL Dashboard Admin** | `/admin-portal/` |
| **Nama Akun** | Administrator |
| **Username** | `admin` |
| **Email** | `admin@diskominfosantik.bekasikab.go.id` |
| **Password** | `AdminBekasi2026!` |

---

### &#x1F454; C. Daftar Lengkap 17 Akun Pegawai Resmi

Seluruh pegawai resmi **Diskominfosantik Kabupaten Bekasi** (17 pegawai yang tersebar di 6 Bidang / Sekretariat) memiliki akses ke **Portal Pegawai** untuk menyetujui kunjungan, menerima notifikasi kedatangan tamu, dan membalas pesan tamu.

| Informasi | Detail |
|---|---|
| **URL Login Pegawai** | `/pegawai-portal/login/` ([https://bukutamudigital.onrender.com/pegawai-portal/login/](https://bukutamudigital.onrender.com/pegawai-portal/login/)) *(juga mendukung login melalui `/admin-portal/login/`)* |
| **URL Dashboard Pegawai** | `/pegawai-portal/` |
| **Username / Identifier** | Dapat menggunakan **Username** atau **Email** masing-masing pegawai di bawah ini |
| **Password Default (Semua Pegawai)** | `Diskominfo@2025` |

#### Tabel 17 Akun Pegawai Resmi Diskominfosantik Kabupaten Bekasi

| No | Nama Pegawai | Jabatan | Bidang / Unit Kerja | Username | Email | Password |
|:---:|---|---|---|---|---|---|
| 1 | **Drs. Ahmad Fauzi, M.Kom** | Kepala Bidang E-Government | Bidang E-Government | `ahmad.fauzi` | `ahmad.fauzi@diskominfosantik.go.id` | `Diskominfo@2025` |
| 2 | **Siti Rahayu, S.Kom** | Analis Sistem Informasi | Bidang E-Government | `siti.rahayu` | `siti.rahayu@diskominfosantik.go.id` | `Diskominfo@2025` |
| 3 | **Budi Santoso, S.T** | Pengembang Perangkat Lunak | Bidang E-Government | `budi.santoso` | `budi.santoso@diskominfosantik.go.id` | `Diskominfo@2025` |
| 4 | **Ir. Dewi Kartika, M.Si** | Kepala Bidang Informasi dan Komunikasi Publik | Bidang Informasi dan Komunikasi Publik | `dewi.kartika` | `dewi.kartika@diskominfosantik.go.id` | `Diskominfo@2025` |
| 5 | **Rudi Hermawan, S.Sos** | Pengelola Informasi Publik | Bidang Informasi dan Komunikasi Publik | `rudi.hermawan` | `rudi.hermawan@diskominfosantik.go.id` | `Diskominfo@2025` |
| 6 | **Fitri Handayani, S.I.Kom** | Penyusun Konten Media | Bidang Informasi dan Komunikasi Publik | `fitri.handayani` | `fitri.handayani@diskominfosantik.go.id` | `Diskominfo@2025` |
| 7 | **Kolonel (Purn) Hendra Wijaya, M.T** | Kepala Bidang Persandian | Bidang Persandian | `hendra.wijaya` | `hendra.wijaya@diskominfosantik.go.id` | `Diskominfo@2025` |
| 8 | **Maya Kurniawati, S.Kom** | Analis Keamanan Siber | Bidang Persandian | `maya.kurniawati` | `maya.kurniawati@diskominfosantik.go.id` | `Diskominfo@2025` |
| 9 | **Dr. Agus Priyono, M.Stat** | Kepala Bidang Statistik | Bidang Statistik | `agus.priyono` | `agus.priyono@diskominfosantik.go.id` | `Diskominfo@2025` |
| 10 | **Rina Susanti, S.Stat** | Statistisi Ahli Pertama | Bidang Statistik | `rina.susanti` | `rina.susanti@diskominfosantik.go.id` | `Diskominfo@2025` |
| 11 | **Doni Prasetyo, S.Si** | Pengolah Data Statistik | Bidang Statistik | `doni.prasetyo` | `doni.prasetyo@diskominfosantik.go.id` | `Diskominfo@2025` |
| 12 | **Ir. Yusuf Efendi, M.T** | Kepala Bidang Teknologi Informasi dan Komunikasi | Bidang Teknologi Informasi dan Komunikasi | `yusuf.efendi` | `yusuf.efendi@diskominfosantik.go.id` | `Diskominfo@2025` |
| 13 | **Novita Sari, S.T** | Administrator Jaringan | Bidang Teknologi Informasi dan Komunikasi | `novita.sari` | `novita.sari@diskominfosantik.go.id` | `Diskominfo@2025` |
| 14 | **Guntur Wibowo, S.Kom** | Teknisi Infrastruktur TIK | Bidang Teknologi Informasi dan Komunikasi | `guntur.wibowo` | `guntur.wibowo@diskominfosantik.go.id` | `Diskominfo@2025` |
| 15 | **Dra. Lestari Wulandari, M.AP** | Sekretaris | Sekretariat | `lestari.wulandari` | `lestari.wulandari@diskominfosantik.go.id` | `Diskominfo@2025` |
| 16 | **Bagas Nugroho, S.AP** | Pengelola Kepegawaian | Sekretariat | `bagas.nugroho` | `bagas.nugroho@diskominfosantik.go.id` | `Diskominfo@2025` |
| 17 | **Anisa Putri, A.Md** | Pengadministrasi Umum | Sekretariat | `anisa.putri` | `anisa.putri@diskominfosantik.go.id` | `Diskominfo@2025` |

---

## &#x1F504; Alur Kerja Sistem

```text
ALUR KUNJUNGAN BUKU TAMU DIGITAL DISKOMINFOSANTIK
=================================================

1. REGISTRASI & LOGIN TAMU
   Tamu masuk via Google SSO (1-Klik) atau daftar akun manual (+ Grid CAPTCHA)

2. PENGAJUAN KUNJUNGAN (BOOKING) & AUTO-ROUTING AI
   - Tamu memilih Tanggal & Jam (validasi Kuota Harian & Hari Libur otomatis)
   - Tamu memilih Bidang & Pegawai Tujuan (dibantu Chatbot AI / n8n Auto-Routing)
   - Status Awal: MENUNGGU VERIFIKASI ADMIN (menunggu_admin)

3. VERIFIKASI BERJENJANG (ADMIN -> PEGAWAI)
   - Admin Resepsionis memeriksa kelengkapan & meneruskan ke Pegawai Tujuan
     -> Status: MENUNGGU PERSETUJUAN PEGAWAI (menunggu_pegawai)
   - Pegawai Tujuan menyetujui jadwal kunjungan dari Portal Pegawai
     -> Status: DISETUJUI / DIJADWALKAN (approved)
   - Sistem otomatis menerbitkan Tiket Kunjungan Digital ber-QR Code (8 Karakter)

4. KEDATANGAN DI KANTOR (SCAN QR CODE POS RESEPSIONIS)
   - Tamu menunjukkan QR Code di Pos Resepsionis / Keamanan
   - Admin memindai QR Code melalui menu "Scan Tiket QR" (/admin-portal/scan-tiket/)
   - Status otomatis berubah dalam 1 detik menjadi: HADIR DI KANTOR (in_progress)
   - Pegawai Tujuan menerima Notifikasi Lonceng (Chime Alert) bahwa tamu telah tiba

5. PENYELESAIAN KUNJUNGAN & SURVEI IKM
   - Setelah pertemuan selesai, status diubah menjadi: SELESAI (completed)
   - Tamu mengisi Survei Indeks Kepuasan Masyarakat (IKM) & ulasan pelayanan
   - Data terekam di Dashboard Statistik, Laporan IKM, dan Audit Log (Excel / PDF)
```

---

## &#x1F6E0; Teknologi yang Digunakan

| Kategori | Teknologi & Pustaka |
|---|---|
| **Backend Framework** | Python 3.10+, Django 5.x |
| **Server ASGI & Real-Time** | Daphne >= 4.1, Django Channels >= 4.1, `channels-redis` (WebSocket) |
| **Database** | MySQL 8.0 / TiDB Cloud Serverless (`mysqlclient`) |
| **Autentikasi & SSO** | Firebase Authentication (Google OAuth 2.0 Popup) & `firebase-admin` SDK |
| **AI & Chatbot Engine** | Hybrid Dual-Engine NLP (*Fuzzy-Token & Levenshtein*) + **n8n Workflow Webhook** |
| **Frontend & UI** | HTML5, CSS3, Bootstrap 5.3, Font Awesome 6, Chart.js, `html5-qrcode` |
| **Penyimpanan Media Cloud** | Cloudinary (`cloudinary`, `django-cloudinary-storage`) & WhiteNoise (Static Files) |
| **Laporan & Ekspor Data** | `openpyxl` & `pandas` (Ekspor/Impor Excel), Cetak PDF Kunjungan, Kartu QR, & IKM |

---

## &#x1F4C1; Arsitektur dan Struktur Proyek

```text
bukudigital/
├── bukudigital/                         # Konfigurasi inti proyek Django
│   ├── settings.py                      # Konfigurasi DB, Channels, Firebase, Cloudinary, n8n
│   ├── urls.py                          # Routing URL utama
│   ├── asgi.py                          # Konfigurasi ASGI (HTTP + WebSocket via Daphne)
│   └── wsgi.py                          # Konfigurasi WSGI
│
├── guest_book/                          # Aplikasi utama Buku Tamu Digital
│   ├── models.py                        # Model DB (Tamu, Pegawai, Admin, Departemen, Kunjungan, IKM, Chat, dll.)
│   ├── consumers.py                     # WebSocket Consumers (Live Chat & Real-time Notification)
│   ├── routing.py                       # Routing WebSocket (ws/chat/, ws/notifications/)
│   ├── context_processors.py            # Context global untuk badge notifikasi & sesi pengguna
│   ├── validators.py                    # Validasi kalender libur nasional & jam operasional
│   ├── forms.py                         # Form validasi Tamu, Kunjungan, dan Pesan
│   ├── utils.py                         # Utilitas notifikasi, NLP lokal, dan integrasi n8n Webhook
│   ├── urls.py                          # Daftar lengkap endpoint URL aplikasi
│   │
│   ├── management/commands/             # Perintah manajemen otomatis (CLI)
│   │   ├── setup_admin.py               # Inisialisasi akun Admin, Instansi, Kalender, & Pegawai
│   │   └── seed_pegawai.py              # Sinkronisasi 17 Pegawai Resmi Diskominfosantik di 6 Bidang
│   │
│   ├── views/                           # Modul logika bisnis terpisah per peran
│   │   ├── auth.py                      # Autentikasi Tamu, Admin, Pegawai, Firebase SSO, & Grid CAPTCHA
│   │   ├── tamu.py                      # Views Portal Tamu (Booking, Tiket QR, Riwayat, IKM, Profil)
│   │   ├── admin.py                     # Views Portal Admin (Dashboard, Scan QR, Kalender, Statistik, IKM)
│   │   ├── pegawai.py                   # Views Portal Pegawai (Dashboard, Approval, Chat, Cetak PDF)
│   │   ├── api.py                       # REST API Internal (Scan QR, Kuota, Chat, Chatbot n8n, Statistik)
│   │   └── api_notifikasi.py            # API manajemen notifikasi lintas portal
│   │
│   ├── templates/guest_book/            # Template antarmuka pengguna (Responsive Desktop & Mobile)
│   │   ├── tamu_landing.html            # Landing Page publik + Login Google 1-Klik
│   │   ├── tamu_tentang_kami.html       # Halaman Profil & Visi Misi Diskominfosantik
│   │   ├── tamu_kebijakan_privasi.html  # Halaman Kebijakan Privasi & Keamanan Data
│   │   ├── tamu_login.html              # Halaman Login Tamu
│   │   ├── tamu_register.html           # Halaman Registrasi Tamu + Grid CAPTCHA
│   │   ├── tamu_dashboard.html          # Dashboard Portal Tamu
│   │   ├── tamu_kunjungan_baru.html     # Formulir Pendaftaran Kunjungan Tamu
│   │   ├── admin_dashboard.html         # Dashboard Portal Admin
│   │   ├── admin_scan_tiket.html        # Halaman Scanner Kamera QR Code Resepsionis
│   │   ├── admin_ikm.html               # Halaman Laporan Survei IKM & Rating
│   │   ├── pegawai_dashboard.html       # Dashboard Portal Pegawai
│   │   └── ...
│   │
│   └── static/                          # Aset statis aplikasi (CSS, gambar CAPTCHA, logo, suara chime)
│
├── build.sh                             # Script build otomatis untuk deployment di Render
├── requirements.txt                     # Daftar pustaka Python yang dibutuhkan
└── manage.py                            # Script manajemen Django
```

---

## &#x2699;&#xFE0F; Instalasi dan Konfigurasi Lokal

### 1. Prasyarat
- **Python** 3.10 atau lebih baru
- **MySQL** 8.0+ (misalnya menggunakan Laragon / XAMPP) atau TiDB Cloud
- **Git**

### 2. Langkah Instalasi

```bash
# 1. Clone repositori
git clone https://github.com/MuhArifyanto/bukutamudigital.git
cd bukutamudigital

# 2. Buat dan aktifkan virtual environment
python -m venv venv
# Windows (PowerShell / CMD):
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate

# 3. Install seluruh dependensi
pip install -r requirements.txt

# 4. Jalankan migrasi database
python manage.py migrate

# 5. Buat tabel cache database
python manage.py createcachetable

# 6. Inisialisasi otomatis akun Admin, Instansi, Kalender Libur, dan 17 Pegawai Resmi
python manage.py setup_admin
```

### 3. Menjalankan Server Lokal

```bash
# Menjalankan server development (mendukung HTTP & WebSocket via ASGI/Daphne)
python manage.py runserver
```

Buka browser dan akses:
- **Halaman Utama / Portal Tamu**: `http://127.0.0.1:8000/`
- **Login Tamu**: `http://127.0.0.1:8000/masuk/`
- **Login Admin Resepsionis**: `http://127.0.0.1:8000/admin-portal/login/`
- **Login Pegawai Diskominfosantik**: `http://127.0.0.1:8000/pegawai-portal/login/`

---

## &#x1F511; Konfigurasi Environment (`.env`)

Buat file `.env` pada direktori utama proyek (`bukudigital/.env`) dengan konfigurasi berikut:

```env
# Konfigurasi Inti Django
SECRET_KEY=ganti-dengan-secret-key-anda
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost,bukutamudigital.onrender.com

# Database (MySQL Lokal atau TiDB Cloud)
DB_NAME=bukudigital
DB_USER=root
DB_PASSWORD=password_mysql_anda
DB_HOST=127.0.0.1
DB_PORT=3306

# Kredensial Default Admin (Opsional - digunakan oleh setup_admin)
ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@diskominfosantik.bekasikab.go.id
ADMIN_PASSWORD=AdminBekasi2026!

# Email SMTP (Gmail App Password untuk Reset Password & Notifikasi)
EMAIL_HOST_USER=email_anda@gmail.com
EMAIL_HOST_PASSWORD=16_karakter_app_password_gmail

# Integrasi Firebase (Google SSO)
FIREBASE_PROJECT_ID=bukutamudigital-43ae7
FIREBASE_WEBHOOK_SECRET=rahasia-webhook-firebase

# Integrasi AI Chatbot & Auto-Routing (n8n Webhook)
N8N_WEBHOOK_URL=https://url-n8n-anda/webhook/auto-routing
N8N_CHAT_WEBHOOK_URL=https://url-n8n-anda/webhook/chatbot

# Penyimpanan Media Cloud (Cloudinary - Opsional di Lokal, Wajib di Production)
CLOUDINARY_CLOUD_NAME=nama_cloud_anda
CLOUDINARY_API_KEY=api_key_cloudinary
CLOUDINARY_API_SECRET=api_secret_cloudinary
```

> &#x26A0;&#xFE0F; **Catatan Keamanan:** Jangan pernah meng-commit file `.env`, `firebase_credentials.json`, atau `google_credentials.json` ke repositori publik.

---

## &#x1F680; Deployment (Render & Cloud)

Proyek ini telah dikonfigurasi siap pakai untuk *deployment* di **Render** dengan dukungan penuh WebSocket (Daphne ASGI):

1. **Build Command** di Render:
   ```bash
   ./build.sh
   ```
   *(Otomatis menginstal paket dari `requirements.txt`, menjalankan `collectstatic`, `migrate`, `createcachetable`, serta `python manage.py setup_admin` untuk memastikan akun Admin dan ke-17 Pegawai Resmi langsung tersedia di database produksi).*

2. **Start Command** di Render:
   ```bash
   daphne -b 0.0.0.0 -p $PORT bukudigital.asgi:application
   ```

---

<div align="center">

**Dinas Komunikasi, Informatika, Statistik dan Persandian (Diskominfosantik) Kabupaten Bekasi**

*Buku Tamu Digital &mdash; Mewujudkan Tata Kelola Administrasi Pelayanan Publik yang Modern, Transparan, dan Akuntabel*

</div>
