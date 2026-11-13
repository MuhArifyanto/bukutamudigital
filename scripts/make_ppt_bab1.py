# -*- coding: utf-8 -*-
"""
Generator Presentasi PowerPoint (PPTX) — BAB I PENDAHULUAN
Judul: Implementasi Agent AI Berbasis Natural Language Processing (NLP)
       pada Sistem Buku Tamu Digital di Diskominfosantik Kabupaten Bekasi
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

# Palet Warna Profesional Akademik (Navy, Royal Blue, Emerald, Slate, White)
NAVY_DARK = RGBColor(11, 44, 86)       # #0B2C56
BLUE_PRIMARY = RGBColor(30, 64, 175)   # #1E40AF
BLUE_LIGHT = RGBColor(239, 246, 255)   # #EFF6FF
BLUE_BORDER = RGBColor(191, 219, 254)  # #BFDBFE
ACCENT_GOLD = RGBColor(245, 158, 11)   # #F59E0B
ACCENT_GREEN = RGBColor(16, 185, 129)  # #10B981
GREEN_LIGHT = RGBColor(236, 253, 245)  # #ECFDF5
BG_LIGHT = RGBColor(248, 250, 252)     # #F8FAFC
WHITE = RGBColor(255, 255, 255)
TEXT_DARK = RGBColor(15, 23, 42)       # #0F172A
TEXT_MUTED = RGBColor(71, 85, 105)     # #475569
BORDER_GRAY = RGBColor(226, 232, 240)  # #E2E8F0


def set_slide_bg(slide, color):
    background = slide.background
    fill = background.fill
    fill.solid()
    fill.fore_color.rgb = color


def add_header_banner(slide, section_badge, title_text, subtitle_text=""):
    """Menambahkan header konsisten pada setiap slide isi."""
    # Top bar navy tipis
    top_bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(13.333), Inches(0.12)
    )
    top_bar.fill.solid()
    top_bar.fill.fore_color.rgb = NAVY_DARK
    top_bar.line.fill.background()

    # Badge sub-bab
    badge = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.6), Inches(0.32), Inches(2.2), Inches(0.34)
    )
    badge.fill.solid()
    badge.fill.fore_color.rgb = BLUE_LIGHT
    badge.line.color.rgb = BLUE_BORDER
    badge.line.width = Pt(1)
    tf_b = badge.text_frame
    tf_b.word_wrap = False
    tf_b.margin_left = tf_b.margin_right = tf_b.margin_top = tf_b.margin_bottom = 0
    p_b = tf_b.paragraphs[0]
    p_b.alignment = PP_ALIGN.CENTER
    r_b = p_b.add_run()
    r_b.text = section_badge
    r_b.font.name = "Calibri"
    r_b.font.size = Pt(11)
    r_b.font.bold = True
    r_b.font.color.rgb = BLUE_PRIMARY

    # Title
    tb = slide.shapes.add_textbox(Inches(0.6), Inches(0.70), Inches(12.1), Inches(0.65))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = title_text
    r.font.name = "Calibri"
    r.font.size = Pt(24)
    r.font.bold = True
    r.font.color.rgb = NAVY_DARK

    if subtitle_text:
        p2 = tf.add_paragraph()
        r2 = p2.add_run()
        r2.text = subtitle_text
        r2.font.name = "Calibri"
        r2.font.size = Pt(13)
        r2.font.color.rgb = TEXT_MUTED

    # Garis pemisah tipis
    line = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0.6), Inches(1.42), Inches(12.133), Inches(0.02)
    )
    line.fill.solid()
    line.fill.fore_color.rgb = BORDER_GRAY
    line.line.fill.background()


def add_footer(slide, page_num, total_pages=8):
    """Menambahkan footer nomor halaman & identitas singkat."""
    tb = slide.shapes.add_textbox(Inches(0.6), Inches(7.08), Inches(12.133), Inches(0.3))
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]
    r = p.add_run()
    r.text = f"BAB I Pendahuluan  |  Muhammad Arif Mulyanto (312310359) — Universitas Pelita Bangsa                                                                           Slide {page_num} / {total_pages}"
    r.font.name = "Calibri"
    r.font.size = Pt(10)
    r.font.color.rgb = TEXT_MUTED


def add_card(slide, left, top, width, height, title, bullets, accent_color=BLUE_PRIMARY, bg_color=WHITE, border_color=BORDER_GRAY):
    """Membuat komponen kartu rapi dengan aksen warna di bagian atas/kiri."""
    card = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height
    )
    card.adjustments[0] = 0.03
    card.fill.solid()
    card.fill.fore_color.rgb = bg_color
    card.line.color.rgb = border_color
    card.line.width = Pt(1.2)

    # Strip aksen di atas kartu
    strip = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, left + Inches(0.15), top, width - Inches(0.3), Inches(0.07)
    )
    strip.fill.solid()
    strip.fill.fore_color.rgb = accent_color
    strip.line.fill.background()

    tb = slide.shapes.add_textbox(left + Inches(0.22), top + Inches(0.18), width - Inches(0.44), height - Inches(0.3))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0

    p_title = tf.paragraphs[0]
    p_title.space_after = Pt(8)
    r_t = p_title.add_run()
    r_t.text = title
    r_t.font.name = "Calibri"
    r_t.font.size = Pt(15)
    r_t.font.bold = True
    r_t.font.color.rgb = NAVY_DARK

    for b_text in bullets:
        p = tf.add_paragraph()
        p.space_after = Pt(5)
        p.line_spacing = 1.15
        r_b = p.add_run()
        r_b.text = f"•  {b_text}"
        r_b.font.name = "Calibri"
        r_b.font.size = Pt(12.5)
        r_b.font.color.rgb = TEXT_DARK


def add_speaker_notes(slide, notes_text):
    notes_slide = slide.notes_slide
    tf = notes_slide.notes_text_frame
    tf.text = notes_text


def build_presentation(output_path="PPT_BAB_1_PENDAHULUAN.pptx"):
    prs = Presentation()
    # Set Widescreen 16:9 (13.333 x 7.5 inches)
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    # =========================================================================
    # SLIDE 1: COVER / JUDUL PENELITIAN
    # =========================================================================
    s1 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s1, NAVY_DARK)

    # Dekorasi aksen kanan
    deco = s1.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(0.25), Inches(7.5)
    )
    deco.fill.solid()
    deco.fill.fore_color.rgb = ACCENT_GOLD
    deco.line.fill.background()

    # Badge Kategori Presentasi
    b1 = s1.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.9), Inches(0.8), Inches(4.5), Inches(0.42)
    )
    b1.fill.solid()
    b1.fill.fore_color.rgb = RGBColor(23, 62, 118)
    b1.line.color.rgb = ACCENT_GOLD
    b1.line.width = Pt(1.2)
    tf_b1 = b1.text_frame
    p_b1 = tf_b1.paragraphs[0]
    p_b1.alignment = PP_ALIGN.CENTER
    r_b1 = p_b1.add_run()
    r_b1.text = "PRESENTASI BAB I — PENDAHULUAN"
    r_b1.font.name = "Calibri"
    r_b1.font.size = Pt(12)
    r_b1.font.bold = True
    r_b1.font.color.rgb = ACCENT_GOLD

    # Judul Utama
    tb_title = s1.shapes.add_textbox(Inches(0.9), Inches(1.45), Inches(11.4), Inches(2.3))
    tf_title = tb_title.text_frame
    tf_title.word_wrap = True
    p_t = tf_title.paragraphs[0]
    p_t.space_after = Pt(10)
    r_t = p_t.add_run()
    r_t.text = "IMPLEMENTASI AGENT AI BERBASIS NATURAL LANGUAGE PROCESSING (NLP) PADA SISTEM BUKU TAMU DIGITAL DI DISKOMINFOSANTIK KABUPATEN BEKASI"
    r_t.font.name = "Calibri"
    r_t.font.size = Pt(28)
    r_t.font.bold = True
    r_t.font.color.rgb = WHITE

    p_sub = tf_title.add_paragraph()
    r_sub = p_sub.add_run()
    r_sub.text = "Otomatisasi Interaksi Tamu, Klasifikasi Intent & Rekomendasi Bidang, Conversational Booking, Scan QR Code, dan Hybrid Human-Handoff"
    r_sub.font.name = "Calibri"
    r_sub.font.size = Pt(14)
    r_sub.font.color.rgb = RGBColor(191, 219, 254)

    # Kotak Identitas Mahasiswa & Dosen
    id_box = s1.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.9), Inches(4.15), Inches(11.4), Inches(2.45)
    )
    id_box.adjustments[0] = 0.03
    id_box.fill.solid()
    id_box.fill.fore_color.rgb = RGBColor(17, 54, 102)
    id_box.line.color.rgb = RGBColor(59, 130, 246)
    id_box.line.width = Pt(1)

    tb_id = s1.shapes.add_textbox(Inches(1.2), Inches(4.35), Inches(10.8), Inches(2.1))
    tf_id = tb_id.text_frame
    tf_id.word_wrap = True

    info_lines = [
        ("Disusun Oleh", "Muhammad Arif Mulyanto  (NIM: 312310359  |  Kelas: I231C)"),
        ("Dosen Pengampu", "Abdul Halim Anshor, S.Kom., M.Kom."),
        ("Lokasi Studi Kasus", "Dinas Komunikasi, Informatika, Persandian, dan Statistik (Diskominfosantik) Kab. Bekasi"),
        ("Program Studi", "Teknik Informatika — Fakultas Teknik — Universitas Pelita Bangsa (2026)"),
    ]
    for idx, (label, val) in enumerate(info_lines):
        p = tf_id.paragraphs[0] if idx == 0 else tf_id.add_paragraph()
        p.space_after = Pt(6)
        r1 = p.add_run()
        r1.text = f"{label:<20}:  "
        r1.font.name = "Calibri"
        r1.font.size = Pt(14)
        r1.font.bold = True
        r1.font.color.rgb = ACCENT_GOLD

        r2 = p.add_run()
        r2.text = val
        r2.font.name = "Calibri"
        r2.font.size = Pt(14)
        r2.font.color.rgb = WHITE

    add_speaker_notes(
        s1,
        "Assalamualaikum wr. wb. / Selamat pagi/siang. Pada kesempatan ini saya Muhammad Arif Mulyanto "
        "akan mempresentasikan Bab 1 Pendahuluan dari penelitian saya yang berjudul Implementasi Agent AI "
        "Berbasis Natural Language Processing pada Sistem Buku Tamu Digital di Diskominfosantik Kabupaten Bekasi."
    )

    # =========================================================================
    # SLIDE 2: 1.1 LATAR BELAKANG MASALAH (KONDISI LAPANGAN & KENDALA)
    # =========================================================================
    s2 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s2, BG_LIGHT)
    add_header_banner(
        s2,
        "1.1 LATAR BELAKANG",
        "Permasalahan Penerimaan Tamu di Diskominfosantik Kab. Bekasi",
        "Mengapa sistem buku tamu konvensional dan formulir web statis belum cukup optimal?"
    )

    add_card(
        s2, Inches(0.6), Inches(1.65), Inches(5.9), Inches(2.45),
        "1. Kelemahan Buku Tamu Kertas / Manual",
        [
            "Risiko kehilangan data fisik & sulit menelusuri riwayat kunjungan (tracking).",
            "Tidak ada validasi kuota harian maupun jadwal ketersediaan pegawai.",
            "Rekapitulasi laporan bulanan/tahunan dan survei kepuasan (IKM) lambat."
        ],
        accent_color=RGBColor(239, 68, 68)
    )

    add_card(
        s2, Inches(6.8), Inches(1.65), Inches(5.9), Inches(2.45),
        "2. Kebingungan Tamu Memilih Bidang Tujuan",
        [
            "Tamu luar sering tidak hafal pembagian tupoksi 6 Bidang di Diskominfosantik.",
            "Contoh nyata: Pengurusan TTE (Sertifikat Elektronik) sering salah diajukan ke Bidang TIK/E-Gov, padahal ditangani Bidang Persandian.",
            "Akibatnya terjadi penolakan atau disposisi ulang yang memakan waktu."
        ],
        accent_color=ACCENT_GOLD
    )

    add_card(
        s2, Inches(0.6), Inches(4.35), Inches(5.9), Inches(2.45),
        "3. Beban Pertanyaan Berulang di Resepsionis",
        [
            "Petugas loket kewalahan menjawab pertanyaan berulang (status tiket, syarat berkas TTE/Hosting/PKL, jam layanan, lokasi gedung).",
            "Petugas manusia tidak dapat bersiaga 24 jam di luar jam kerja operasional."
        ],
        accent_color=BLUE_PRIMARY
    )

    add_card(
        s2, Inches(6.8), Inches(4.35), Inches(5.9), Inches(2.45),
        "4. Keterbatasan Formulir Web Konvensional",
        [
            "Pengisian formulir dropdown statis terasa kaku bagi masyarakat umum.",
            "Saat tamu tiba di lobi, tetap dibutuhkan proses check-in cepat (seperti Scan QR Code) agar tidak terjadi antrean di meja resepsionis."
        ],
        accent_color=ACCENT_GREEN
    )

    add_footer(s2, 2)
    add_speaker_notes(
        s2,
        "Latar belakang masalah berangkat dari 4 kondisi nyata di Diskominfosantik Kabupaten Bekasi: "
        "(1) pencatatan manual rawan hilang dan sulit direkap, (2) tamu sering salah memilih bidang tujuan "
        "karena tidak tahu tupoksi 6 bidang yang ada, (3) resepsionis terbebani pertanyaan berulang seputar syarat layanan, "
        "dan (4) formulir statis kurang interaktif."
    )

    # =========================================================================
    # SLIDE 3: 1.1 SOLUSI YANG DIUSULKAN (ARSITEKTUR AGENT AI & BUKU TAMU)
    # =========================================================================
    s3 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s3, BG_LIGHT)
    add_header_banner(
        s3,
        "1.1 SOLUSI SISTEM",
        "Solusi: Buku Tamu Digital Terintegrasi Agent AI Berbasis NLP",
        "Transformasi dari formulir statis menjadi layanan percakapan cerdas, terarah, dan real-time"
    )

    add_card(
        s3, Inches(0.6), Inches(1.65), Inches(3.9), Inches(5.15),
        "A. Pemahaman Bahasa Alami (NLP)",
        [
            "Menganalisis pesan chat tamu menggunakan Intent Classification & Entity Extraction.",
            "Toleransi salah ketik (Fuzzy Matching) untuk mengenali kata kunci layanan.",
            "Menjawab otomatis SOP layanan (TTE, Domain/Hosting, Magang/PKL, Statistik) & profil pejabat 24/7.",
            "Arsitektur Hibrida Dwi-Jalur: Webhook N8N + Mesin Semantik Lokal Django (tetap aktif meski N8N offline)."
        ],
        accent_color=BLUE_PRIMARY
    )

    add_card(
        s3, Inches(4.72), Inches(1.65), Inches(3.9), Inches(5.15),
        "B. Disposisi Cerdas & Chat Booking",
        [
            "Rekomendasi otomatis ke 6 Bidang & 17 Pegawai Resmi sesuai keperluan tamu.",
            "Conversational Booking: tamu dapat mendaftar kunjungan, cek tiket, reschedule, atau batal langsung lewat chat.",
            "Validasi otomatis kuota harian dan hari libur kalender.",
            "3-Strike Auto-Handoff: otomatis mengalihkan chat ke Admin manusia jika bot gagal paham 3x."
        ],
        accent_color=ACCENT_GREEN
    )

    add_card(
        s3, Inches(8.84), Inches(1.65), Inches(3.9), Inches(5.15),
        "C. Workflow 3 Portal, QR & IKM",
        [
            "Terintegrasi 3 Portal: Portal Tamu, Portal Pegawai (Approve/Delegasi), & Portal Admin.",
            "Notifikasi real-time via WebSocket dengan peringatan suara (Chime Alert).",
            "Check-in 1 detik di lobi resepsionis menggunakan Scanner Kamera QR Code (Laptop/Mobile).",
            "Evaluasi kepuasan tamu dengan Survei IKM (5 kriteria sesuai PermenPAN-RB)."
        ],
        accent_color=ACCENT_GOLD
    )

    add_footer(s3, 3)
    add_speaker_notes(
        s3,
        "Untuk menjawab permasalahan tadi, penelitian ini mengimplementasikan Agent AI berbasis NLP ke dalam "
        "Sistem Buku Tamu Digital. Sistem ini memiliki kemampuan klasifikasi maksud pesan tamu, merekomendasikan bidang/pegawai, "
        "melakukan pendaftaran kunjungan langsung dari chat, mengalihkan ke admin jika diperlukan, serta dilengkapi scanner QR Code di resepsionis."
    )

    # =========================================================================
    # SLIDE 4: 1.2 IDENTIFIKASI MASALAH
    # =========================================================================
    s4 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s4, BG_LIGHT)
    add_header_banner(
        s4,
        "1.2 IDENTIFIKASI MASALAH",
        "Empat Poin Identifikasi Masalah Utama",
        "Fokus permasalahan teknis dan operasional yang diselesaikan dalam penelitian ini"
    )

    ident_items = [
        (
            "01. Ketidaksesuaian Pemilihan Bidang & Pegawai Tujuan",
            "Tamu luar sering kesulitan memahami struktur pembagian tugas pada 6 divisi teknis Diskominfosantik, sehingga pengajuan kunjungan kerap salah sasaran dan harus didisposisi ulang."
        ),
        (
            "02. Keterlambatan Respons Informasi Layanan yang Repetitif",
            "Pertanyaan rutin mengenai status verifikasi tiket, sisa kuota harian, jadwal operasional, serta syarat berkas SOP layanan membebani petugas front office dan tidak terlayani di luar jam kerja."
        ),
        (
            "03. Kekakuan Antarmuka Formulir Pendaftaran Konvensional",
            "Pengisian formulir berbasis dropdown statis kurang memandu tamu secara interaktif jika dibandingkan dengan komunikasi percakapan bahasa alami (conversational interface)."
        ),
        (
            "04. Risiko Kegagalan Bot (Bot Failure) pada Kasus Kompleks",
            "Diperlukan mekanisme kontrol toleransi kesalahan (fault tolerance) agar percakapan yang ambigu atau keluhan sensitif dapat dialihkan secara mulus ke petugas admin manusia."
        ),
    ]

    for i, (heading, desc) in enumerate(ident_items):
        top_pos = Inches(1.65 + i * 1.32)
        box = s4.shapes.add_shape(
            MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.6), top_pos, Inches(12.133), Inches(1.15)
        )
        box.adjustments[0] = 0.04
        box.fill.solid()
        box.fill.fore_color.rgb = WHITE
        box.line.color.rgb = BORDER_GRAY
        box.line.width = Pt(1)

        left_bar = s4.shapes.add_shape(
            MSO_SHAPE.RECTANGLE, Inches(0.6), top_pos, Inches(0.14), Inches(1.15)
        )
        left_bar.fill.solid()
        left_bar.fill.fore_color.rgb = BLUE_PRIMARY if i % 2 == 0 else ACCENT_GREEN
        left_bar.line.fill.background()

        tb = s4.shapes.add_textbox(Inches(0.95), top_pos + Inches(0.12), Inches(11.6), Inches(0.95))
        tf = tb.text_frame
        tf.word_wrap = True
        p1 = tf.paragraphs[0]
        p1.space_after = Pt(3)
        r1 = p1.add_run()
        r1.text = heading
        r1.font.name = "Calibri"
        r1.font.size = Pt(14.5)
        r1.font.bold = True
        r1.font.color.rgb = NAVY_DARK

        p2 = tf.add_paragraph()
        r2 = p2.add_run()
        r2.text = desc
        r2.font.name = "Calibri"
        r2.font.size = Pt(12.5)
        r2.font.color.rgb = TEXT_MUTED

    add_footer(s4, 4)
    add_speaker_notes(
        s4,
        "Dari latar belakang tersebut, diidentifikasi 4 masalah utama: kesalahan pemilihan bidang oleh tamu, "
        "keterlambatan respons pertanyaan berulang, kekakuan form statis, dan perlunya mitigasi risiko saat bot gagal memahami pesan tamu."
    )

    # =========================================================================
    # SLIDE 5: 1.2 BATASAN MASALAH
    # =========================================================================
    s5 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s5, BG_LIGHT)
    add_header_banner(
        s5,
        "1.2 BATASAN MASALAH",
        "Ruang Lingkup dan Batasan Masalah Penelitian",
        "Pembatasan cakupan sistem agar penelitian terfokus, terukur, dan sesuai studi kasus"
    )

    add_card(
        s5, Inches(0.6), Inches(1.65), Inches(5.9), Inches(2.45),
        "1. Platform & Arsitektur Teknologi",
        [
            "Sistem dikembangkan berbasis web menggunakan framework Python Django, Django Channels (ASGI/Daphne WebSocket), dan database relasional MySQL / TiDB.",
            "Terdiri atas 3 portal akses: Tamu, Pegawai, dan Admin/Resepsionis."
        ],
        accent_color=BLUE_PRIMARY
    )

    add_card(
        s5, Inches(6.8), Inches(1.65), Inches(5.9), Inches(2.45),
        "2. Cakupan Struktur Organisasi (6 Bidang)",
        [
            "Rekomendasi disposisi otomatis difokuskan pada 6 divisi di Diskominfosantik Kab. Bekasi:",
            "Bidang TIK, Bidang E-Government, Bidang Persandian, Bidang IKP, Bidang Statistik, dan Sekretariat."
        ],
        accent_color=ACCENT_GREEN
    )

    add_card(
        s5, Inches(0.6), Inches(4.35), Inches(5.9), Inches(2.45),
        "3. Domain Bahasa & Taksonomi 7 Intent",
        [
            "Menggunakan Bahasa Indonesia pada 7 kategori intent utama:",
            "sapaan, cek_status_kunjungan, jadwal_kuota, info_layanan_dan_pegawai, buat_kunjungan, keluhan_dan_masukan, serta di_luar_konteks."
        ],
        accent_color=ACCENT_GOLD
    )

    add_card(
        s5, Inches(6.8), Inches(4.35), Inches(5.9), Inches(2.45),
        "4. Mekanisme Mesin AI Hibrida Dwi-Jalur",
        [
            "Menggabungkan orchestrator webhook N8N dengan mesin inferensi semantik lokal pada Django.",
            "Menjamin ketersediaan layanan (High Availability) apabila jaringan eksternal mengalami gangguan/timeout."
        ],
        accent_color=NAVY_DARK
    )

    add_footer(s5, 5)
    add_speaker_notes(
        s5,
        "Batasan masalah dalam penelitian ini mencakup: (1) berbasis web Django, WebSocket, dan MySQL, "
        "(2) pemetaan difokuskan pada 6 bidang kerja di Diskominfosantik Kabupaten Bekasi, "
        "(3) domain percakapan Bahasa Indonesia dengan 7 kategori intent, serta (4) arsitektur AI hibrida N8N dan lokal."
    )

    # =========================================================================
    # SLIDE 6: 1.3 RUMUSAN MASALAH (RESEARCH QUESTIONS)
    # =========================================================================
    s6 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s6, BG_LIGHT)
    add_header_banner(
        s6,
        "1.3 RUMUSAN MASALAH",
        "Rumusan Masalah Penelitian (Research Questions / RQ1 – RQ4)",
        "Pertanyaan penelitian utama yang dijawab melalui perancangan dan pengujian sistem"
    )

    rqs = [
        ("RQ1", "Model NLP & Disposisi Bidang",
         "Bagaimana merancang model NLP (Intent Classification & Entity Recognition) untuk memetakan keperluan kunjungan tamu ke bidang kedinasan dan pegawai yang tepat di Diskominfosantik Kabupaten Bekasi?"),
        ("RQ2", "Integrasi Conversational Booking",
         "Bagaimana mengintegrasikan Agent AI ke dalam alur Conversational Booking pada sistem web Django berbasis protokol komunikasi real-time WebSocket?"),
        ("RQ3", "Mekanisme Hybrid Human-Handoff",
         "Bagaimana mekanisme hybrid human-handoff (aturan 3-strike toleransi kesalahan) dirancang untuk menangani kegagalan inferensi AI atau eskalasi komplain tamu?"),
        ("RQ4", "Evaluasi Akurasi, Latensi & Usability",
         "Bagaimana performa akurasi klasifikasi intent, waktu respons (latency), serta tingkat penerimaan pengguna (usability) terhadap sistem Buku Tamu Digital ber-AI tersebut?"),
    ]

    for idx, (code, short_t, question) in enumerate(rqs):
        col = idx % 2
        row = idx // 2
        left_p = Inches(0.6 if col == 0 else 6.8)
        top_p = Inches(1.65 if row == 0 else 4.35)
        add_card(
            s6, left_p, top_p, Inches(5.9), Inches(2.45),
            f"{code} — {short_t}",
            [question],
            accent_color=BLUE_PRIMARY if col == 0 else ACCENT_GREEN
        )

    add_footer(s6, 6)
    add_speaker_notes(
        s6,
        "Rumusan masalah terbagi menjadi 4 Research Questions (RQ1 sampai RQ4): mulai dari perancangan model NLP untuk pemetaan bidang, "
        "integrasi conversational booking via WebSocket, perancangan 3-strike human handoff, hingga pengujian akurasi, latensi, dan usability."
    )

    # =========================================================================
    # SLIDE 7: 1.3 TUJUAN PENELITIAN (RESEARCH OBJECTIVES)
    # =========================================================================
    s7 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s7, BG_LIGHT)
    add_header_banner(
        s7,
        "1.3 TUJUAN PENELITIAN",
        "Tujuan Penelitian (Research Objectives / RO1 – RO4)",
        "Penyelarasan langsung antara Rumusan Masalah (RQ) dengan Target Capaian Penelitian (RO)"
    )

    table_shape = s7.shapes.add_table(5, 3, Inches(0.6), Inches(1.65), Inches(12.133), Inches(5.1))
    table = table_shape.table
    table.columns[0].width = Inches(1.2)
    table.columns[1].width = Inches(3.3)
    table.columns[2].width = Inches(7.633)

    headers = ["Kode", "Fokus Capaian", "Tujuan Penelitian (Research Objectives)"]
    for c_idx, h_text in enumerate(headers):
        cell = table.cell(0, c_idx)
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY_DARK
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = cell.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER if c_idx == 0 else PP_ALIGN.LEFT
        r = p.add_run()
        r.text = h_text
        r.font.name = "Calibri"
        r.font.size = Pt(13)
        r.font.bold = True
        r.font.color.rgb = WHITE

    ro_data = [
        ("RO1\n(Menjawab RQ1)", "Algoritma NLP & Routing 6 Bidang",
         "Merancang algoritma NLP hibrida yang mampu mengklasifikasikan 7 intent percakapan tamu dan merekomendasikan bidang kedinasan serta pegawai tujuan secara akurat."),
        ("RO2\n(Menjawab RQ2)", "Modul Conversational Booking Real-Time",
         "Membangun modul percakapan interaktif multi-turn yang dapat memproses pendaftaran kunjungan, cek sisa kuota harian, reschedule, dan pembuatan tiket QR langsung ke database."),
        ("RO3\n(Menjawab RQ3)", "Kontrol 3-Strike Auto-Handoff ke Admin",
         "Mengembangkan mekanisme peralihan sesi otomatis dari AI Chatbot ke Admin manusia ketika terjadi 3 kali ketidaksesuaian konteks atau komplain sensitif."),
        ("RO4\n(Menjawab RQ4)", "Evaluasi Performa & Kepuasan Pengguna",
         "Mengevaluasi kinerja sistem melalui Confusion Matrix (akurasi, presisi, recall, F1-score), uji latensi WebSocket, Black-Box Testing, serta kuesioner SUS & Survei IKM."),
    ]

    for r_idx, row_vals in enumerate(ro_data, start=1):
        bg_row = WHITE if r_idx % 2 == 1 else BLUE_LIGHT
        for c_idx, val in enumerate(row_vals):
            cell = table.cell(r_idx, c_idx)
            cell.fill.solid()
            cell.fill.fore_color.rgb = bg_row
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER if c_idx == 0 else PP_ALIGN.LEFT
            r = p.add_run()
            r.text = val
            r.font.name = "Calibri"
            r.font.size = Pt(12)
            r.font.bold = (c_idx < 2)
            r.font.color.rgb = NAVY_DARK if c_idx < 2 else TEXT_DARK

    add_footer(s7, 7)
    add_speaker_notes(
        s7,
        "Slide ini memetakan 4 Tujuan Penelitian (RO1 hingga RO4) yang menjawab langsung keempat rumusan masalah sebelumnya."
    )

    # =========================================================================
    # SLIDE 8: 1.4 MANFAAT DAN KONTRIBUSI PENELITIAN
    # =========================================================================
    s8 = prs.slides.add_slide(blank_layout)
    set_slide_bg(s8, BG_LIGHT)
    add_header_banner(
        s8,
        "1.4 MANFAAT PENELITIAN",
        "Manfaat Teoritis (Akademis) & Manfaat Praktis",
        "Dampak positif implementasi sistem bagi pengembangan ilmu informatika dan instansi Diskominfosantik"
    )

    add_card(
        s8, Inches(0.6), Inches(1.65), Inches(5.9), Inches(5.1),
        "Manfaat Teoritis (Akademis)",
        [
            "Menjadi referensi ilmiah penerapan arsitektur Conversational Agent dwi-jalur (Webhook N8N + Local NLP Engine) pada layanan E-Government daerah.",
            "Mendemonstrasikan integrasi NLP bahasa Indonesia dengan transaksi basis data secara real-time melalui protokol WebSocket (Django Channels).",
            "Menyediakan model penanganan kegagalan bot melalui skema 3-Strike Fault Tolerance & Human-in-the-Loop."
        ],
        accent_color=BLUE_PRIMARY,
        bg_color=WHITE
    )

    add_card(
        s8, Inches(6.8), Inches(1.65), Inches(5.9), Inches(5.1),
        "Manfaat Praktis (Instansi & Masyarakat)",
        [
            "Bagi Tamu / Masyarakat: Kemudahan mendaftar kunjungan dari rumah, konsultasi syarat berkas 24/7 via Chatbot, & kepastian jadwal sebelum datang.",
            "Bagi Resepsionis & Admin: Check-in tamu hanya 1 detik dengan Scan Kamera QR Code, mengurangi beban tanya-jawab berulang, & rekap laporan/IKM otomatis.",
            "Bagi Pegawai Dinas: Menerima notifikasi kedatangan tamu secara instan dan dapat melakukan persetujuan/delegasi ke rekan satu bidang."
        ],
        accent_color=ACCENT_GREEN,
        bg_color=WHITE
    )

    add_footer(s8, 8)
    add_speaker_notes(
        s8,
        "Sebagai penutup Bab 1, penelitian ini memberikan kontribusi teoritis pada bidang AI/NLP dan rekayasa perangkat lunak web, "
        "serta manfaat praktis langsung bagi masyarakat/tamu, petugas resepsionis, dan pegawai di lingkungan Diskominfosantik Kabupaten Bekasi. Terima kasih."
    )

    prs.save(output_path)
    print(f"PPTX_CREATED: {os.path.abspath(output_path)}")


if __name__ == "__main__":
    build_presentation("PPT_BAB_1_PENDAHULUAN.pptx")

