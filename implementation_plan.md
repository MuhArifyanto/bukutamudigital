# Rencana Implementasi: Kekurangan Fitur & Sistem Admin

Dokumen ini merangkum rencana untuk menyelesaikan 4 daftar kekurangan fitur Admin yang Anda minta.

## ⚠️ User Review Required
Mohon periksa bagian "Open Questions" dan pastikan Anda setuju dengan pendekatan yang akan saya lakukan (terutama mengenai pembatasan peran dan deteksi tamu VIP). 

## ❓ Open Questions
1. **Definisi VIP**: Bagaimana sistem membedakan Tamu VIP dengan tamu biasa? Apakah berdasarkan nama instansi yang mengandung kata "Kementerian/Gubernur", atau Anda ingin saya menambahkan tombol centang (*checkbox*) "Tamu VIP" pada saat pendaftaran kunjungan? (Sementara ini saya akan asumsikan VIP berdasarkan *checkbox* atau *keyword* instansi).
2. **WhatsApp Bot**: Mengingat WhatsApp API resmi membutuhkan pihak ketiga (berbayar seperti Twilio/Fonnte), untuk saat ini saya akan membuat fungsi pengiriman **Email otomatis** ke Admin, dan menaruh "kerangka/wadah" (*mock*) untuk kode WhatsApp bot agar siap digunakan jika Anda sudah punya layanan pihak ketiga. Apakah Anda setuju?

---

## 🛠️ Proposed Changes

### 1. Audit Trail Menyeluruh
Menambahkan pencatatan ke tabel `AuditLog` untuk aktivitas sensitif yang belum tercover.
- **`guest_book/views/admin.py`**:
  - `[MODIFY]` Update `admin_instansi_view` untuk merekam *Audit Log* ketika Pengaturan Instansi disimpan/diubah.
- **`guest_book/views/api.py`**:
  - `[NEW]` Buat fungsi `api_delete_chat_message` agar Admin bisa menghapus chat, lalu catat aksinya ke dalam Audit Log.
  - `[MODIFY]` (Jika ada API perubahan data pegawai) Tambahkan *Audit Log* pada saat update profil pegawai.

---

### 2. Manajemen Blokir (Banning)
Membuat halaman khusus agar Admin bisa melihat dan memblokir/suspend tamu/pengguna.
- **`guest_book/models.py`**: (Sudah ada field `account_status = 'suspended'` pada model `Tamu`, siap digunakan).
- **`guest_book/views/admin.py`**:
  - `[NEW]` Buat view `admin_pengguna_view` untuk menampilkan tabel daftar Pengguna (Tamu).
- **`guest_book/views/api.py`**:
  - `[NEW]` Buat view `api_toggle_user_status` untuk mengubah status aktif/blokir via AJAX (tanpa *reload*).
- **`guest_book/templates/guest_book/admin_pengguna.html`**:
  - `[NEW]` Buat *template* antarmuka tabel pengguna dengan tombol "Blokir" (Merah) dan "Aktifkan" (Hijau).
- **`guest_book/templates/guest_book/admin_base.html`**:
  - `[MODIFY]` Tambahkan menu "Manajemen Pengguna" di *sidebar* kiri.

---

### 3. Pembatasan Peran (Role-Based Access Control)
Membatasi akses Operator agar tidak bisa merusak pengaturan sistem.
- **`guest_book/models.py`**:
  - `[MODIFY]` Tambahkan *field* baru `admin_role` pada model `Tamu` dengan pilihan `super_admin` atau `operator`.
- **`guest_book/views/base.py`**:
  - `[NEW]` Buat *decorator* `@super_admin_required` (hanya Super Admin yang diizinkan lewat).
- **`guest_book/views/admin.py`**:
  - `[MODIFY]` Terapkan `@super_admin_required` ke halaman: Pengaturan Instansi, Audit Log, dan Manajemen Pengguna.
- **`guest_book/templates/guest_book/admin_base.html`**:
  - `[MODIFY]` Sembunyikan tombol menu Pengaturan Instansi, Audit Log, dan Manajemen Pengguna jika Admin yang sedang *login* berstatus `operator`.

---

### 4. Pusat Notifikasi Email / WhatsApp (VIP)
- **`guest_book/views/tamu.py` & `api.py`**:
  - `[MODIFY]` Pada saat pembuatan Kunjungan Baru, tambahkan fungsi pengecekan apakah Tamu tersebut VIP.
  - `[MODIFY]` Jika VIP, panggil fungsi `send_mail` dari Django untuk mengirim notifikasi peringatan ke Email milik Admin secara *real-time*.

## ✅ Verification Plan
1. Mengubah peran salah satu Admin menjadi "Operator" di database, lalu memastikan menu sensitif hilang dan tidak bisa diakses via URL.
2. Memblokir akun salah satu Tamu, lalu mencoba login menggunakan akun tamu tersebut (seharusnya gagal dan muncul peringatan blokir).
3. Melakukan perubahan pada Pengaturan Instansi dan menghapus pesan, lalu memastikan keduanya masuk ke tabel Laporan Aktivitas (Audit Log).
