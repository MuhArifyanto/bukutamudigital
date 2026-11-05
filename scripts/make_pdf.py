import os
import sys
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm, mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Image, KeepTogether, HRFlowable
)
from reportlab.pdfgen import canvas

# ── CANVAS DENGAN NOMOR HALAMAN & RUNNING HEADER ─────────────────────────────
class AcademicNumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super(AcademicNumberedCanvas, self).__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_header_footer(num_pages)
            super(AcademicNumberedCanvas, self).showPage()
        super(AcademicNumberedCanvas, self).save()

    def draw_header_footer(self, page_count):
        # Halaman cover (halaman 1) tidak menampilkan running header & footer
        if self._pageNumber == 1:
            return

        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#555555"))

        # Running Header
        header_text = "Laporan Proyek UTS Metodologi Penelitian — Universitas Pelita Bangsa"
        self.drawString(2.5 * cm, A4[1] - 1.8 * cm, header_text)
        self.setStrokeColor(colors.HexColor("#CBD5E1"))
        self.setLineWidth(0.5)
        self.line(2.5 * cm, A4[1] - 1.95 * cm, A4[0] - 2.5 * cm, A4[1] - 1.95 * cm)

        # Running Footer
        page_str = f"Halaman {self._pageNumber} dari {page_count}"
        self.drawString(2.5 * cm, 1.6 * cm, "Teknik Informatika — Kelas I231C")
        self.drawRightString(A4[0] - 2.5 * cm, 1.6 * cm, page_str)
        self.line(2.5 * cm, 1.85 * cm, A4[0] - 2.5 * cm, 1.85 * cm)

        self.restoreState()


def create_report_pdf(output_filename="LAPORAN_UTS_METODOLOGI_PENELITIAN.pdf"):
    doc = SimpleDocTemplate(
        output_filename,
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm
    )

    content_width = 16.0 * cm  # A4 width (21.0cm) - left (2.5cm) - right (2.5cm)

    # ── STYLES ───────────────────────────────────────────────────────────────
    styles = getSampleStyleSheet()

    c_primary = colors.HexColor("#0B2C56")   # Navy Pelita Bangsa
    c_secondary = colors.HexColor("#1E3A8A") # Royal Blue
    c_dark = colors.HexColor("#1E293B")      # Slate Dark
    c_muted = colors.HexColor("#475569")     # Slate Muted
    c_bg_head = colors.HexColor("#0B2C56")   # Table Header Background
    c_border = colors.HexColor("#CBD5E1")    # Subtle Border

    title_cover = ParagraphStyle(
        'CoverTitle',
        fontName='Helvetica-Bold',
        fontSize=12.5,
        leading=17,
        alignment=1, # Center
        textColor=c_primary,
        spaceAfter=10
    )

    subtitle_cover = ParagraphStyle(
        'CoverSubtitle',
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=15,
        alignment=1,
        textColor=colors.HexColor("#A82020"), # Maroon
        spaceAfter=8
    )

    univ_header_style = ParagraphStyle(
        'UnivHeader',
        fontName='Helvetica-Bold',
        fontSize=10.5,
        leading=14.5,
        alignment=1,
        textColor=c_primary
    )

    univ_sub_style = ParagraphStyle(
        'UnivSub',
        fontName='Helvetica',
        fontSize=8.2,
        leading=11.5,
        alignment=1,
        textColor=c_muted
    )

    h1_style = ParagraphStyle(
        'Heading1Custom',
        fontName='Helvetica-Bold',
        fontSize=11.5,
        leading=15.5,
        textColor=c_primary,
        spaceBefore=11,
        spaceAfter=5,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'Heading2Custom',
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=14,
        textColor=c_secondary,
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'BodyCustom',
        fontName='Helvetica',
        fontSize=9.2,
        leading=13.5,
        textColor=c_dark,
        alignment=4, # Justify
        spaceAfter=5
    )

    body_bold = ParagraphStyle(
        'BodyBoldCustom',
        fontName='Helvetica-Bold',
        fontSize=9.2,
        leading=13.5,
        textColor=c_dark,
        spaceAfter=4
    )

    table_header = ParagraphStyle(
        'TableHeader',
        fontName='Helvetica-Bold',
        fontSize=8.2,
        leading=11,
        textColor=colors.white,
        alignment=1
    )

    table_cell = ParagraphStyle(
        'TableCell',
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=c_dark,
        alignment=4
    )

    table_cell_bold = ParagraphStyle(
        'TableCellBold',
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=c_dark
    )

    table_cell_center = ParagraphStyle(
        'TableCellCenter',
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=c_dark,
        alignment=1
    )

    abstract_box_style = ParagraphStyle(
        'AbstractBox',
        fontName='Helvetica-Oblique',
        fontSize=8.8,
        leading=13,
        textColor=colors.HexColor("#1A202C"),
        alignment=4
    )

    story = []

    # ═════════════════════════════════════════════════════════════════════════
    # 1. HALAMAN COVER LAPORAN RESMI
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("UNIVERSITAS PELITA BANGSA", univ_header_style))
    story.append(Paragraph("FAKULTAS TEKNIK — PROGRAM STUDI TEKNIK INFORMATIKA", univ_header_style))
    story.append(Paragraph("Jl. Inspeksi Kalimalang Tegal Danas Arah DELTAMAS, Cikarang Pusat - Kab. Bekasi 17530", univ_sub_style))
    story.append(Paragraph("Telp. (021) 2851 8181, 82, 83, 84 | Website: https://fatek.pelitabangsa.ac.id", univ_sub_style))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1.5, color=c_primary, spaceBefore=2, spaceAfter=12))

    story.append(Paragraph("LAPORAN PROYEK UJIAN TENGAH SEMESTER (UTS)<br/>METODOLOGI PENELITIAN", subtitle_cover))
    story.append(Spacer(1, 4))

    story.append(Paragraph("IMPLEMENTASI AGENT AI BERBASIS NATURAL LANGUAGE PROCESSING (NLP) PADA SISTEM BUKU TAMU DIGITAL DI DISKOMINFOSANTIK KABUPATEN BEKASI", title_cover))
    story.append(Paragraph("Semester Gassal Tahun Akademik 2026/2027", ParagraphStyle('Sem', fontName='Helvetica-Bold', fontSize=9.5, alignment=1, textColor=c_muted)))
    story.append(Spacer(1, 10))

    logo_path = "extracted_image1.png"
    if os.path.exists(logo_path):
        story.append(Image(logo_path, width=3.8 * cm, height=3.4 * cm))
    story.append(Spacer(1, 14))

    penyusun_data = [
        [Paragraph("<b>Disusun Oleh</b>", body_style), Paragraph(":", body_style), Paragraph("<b>Muhammad Arif Mulyanto</b>", body_style)],
        [Paragraph("<b>Nomor Induk Mahasiswa (NIM)</b>", body_style), Paragraph(":", body_style), Paragraph("<b>312310359</b>", body_style)],
        [Paragraph("<b>Kelas</b>", body_style), Paragraph(":", body_style), Paragraph("I231C", body_style)],
        [Paragraph("<b>Mata Kuliah</b>", body_style), Paragraph(":", body_style), Paragraph("Metodologi Penelitian", body_style)],
        [Paragraph("<b>Dosen Pengampu</b>", body_style), Paragraph(":", body_style), Paragraph("Abdul Halim Anshor, S.Kom., M.Kom.", body_style)],
    ]
    t_penyusun = Table(penyusun_data, colWidths=[5.5 * cm, 0.6 * cm, 9.9 * cm])
    t_penyusun.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]))
    story.append(t_penyusun)
    story.append(Spacer(1, 18))

    story.append(Paragraph("<b>PROGRAM STUDI TEKNIK INFORMATIKA<br/>FAKULTAS TEKNIK<br/>UNIVERSITAS PELITA BANGSA<br/>BEKASI — 2026</b>", ParagraphStyle('Inst', fontName='Helvetica-Bold', fontSize=9.5, leading=13.5, alignment=1, textColor=c_primary)))

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # 2. IDENTITAS PENELITIAN & ABSTRAK
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("IDENTITAS PENELITIAN DAN ABSTRAK", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=c_secondary, spaceBefore=2, spaceAfter=8))

    id_data = [
        [Paragraph("<b>Judul Penelitian</b>", body_bold), Paragraph(":", body_style), Paragraph("<b>Implementasi Agent AI Berbasis Natural Language Processing (NLP) pada Sistem Buku Tamu Digital di Diskominfosantik Kabupaten Bekasi</b>", body_style)],
        [Paragraph("<b>Bidang Informatika</b>", body_bold), Paragraph(":", body_style), Paragraph("Kecerdasan Buatan (<i>Artificial Intelligence</i>) / <i>Natural Language Processing</i> (NLP) dan Rekayasa Perangkat Lunak Web.", body_style)],
        [Paragraph("<b>Objek & Fokus Kasus</b>", body_bold), Paragraph(":", body_style), Paragraph("Sistem Buku Tamu Digital Dinas Komunikasi, Informatika, Persandian, dan Statistik (Diskominfosantik) Kabupaten Bekasi (berfokus pada otomatisasi layanan interaksi tamu, klasifikasi intent pesan, rekomendasi disposisi 6 bidang kedinasan, conversational booking cerdas, dan hybrid human-handoff via WebSocket).", body_style)],
    ]
    t_id = Table(id_data, colWidths=[4.2 * cm, 0.6 * cm, 11.2 * cm])
    t_id.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
    ]))
    story.append(t_id)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Abstrak Deskriptif Rancangan Penelitian", h2_style))
    abstrak_text = (
        "Pelayanan penerimaan tamu di instansi pemerintah daerah, seperti Dinas Komunikasi, Informatika, Persandian, "
        "dan Statistik (Diskominfosantik) Kabupaten Bekasi, memiliki intensitas koordinasi yang tinggi dari berbagai pihak, "
        "mulai dari instansi perangkat daerah lain, mitra industri teknologi, insan pers, hingga masyarakat umum. "
        "Sistem buku tamu digital berbasis web konvensional yang ada saat ini masih menghadapi kendala operasional, "
        "yaitu kebingungan tamu dalam memilih bidang kedinasan yang sesuai dengan keperluannya serta keterbatasan petugas "
        "front office dalam merespons pertanyaan seputar status kunjungan, persyaratan berkas, kuota harian, dan jam operasional "
        "secara cepat dan fleksibel di luar jam kerja. Penelitian ini bertujuan merancang dan mengimplementasikan arsitektur "
        "<i>Agent AI</i> berbasis <i>Natural Language Processing</i> (NLP) yang terintegrasi secara mulus ke dalam platform "
        "Buku Tamu Digital berbasis Django dan WebSocket. Pendekatan yang diusulkan menggabungkan pemrosesan <i>intent classification</i> "
        "dan <i>entity extraction</i> untuk menganalisis teks percakapan tamu, modul rekomendasi disposisi bidang (<i>rule-based semantic routing</i>) "
        "yang memetakan keperluan tamu ke 6 divisi teknis (TIK, E-Government, Persandian, IKP, Statistik, dan Sekretariat), "
        "fitur <i>conversational booking</i> interaktif secara <i>multi-turn</i>, serta mekanisme <i>hybrid human-handoff</i> "
        "berbasis aturan toleransi kesalahan (<i>3-strike fault tolerance</i>) untuk mengalihkan sesi ke admin manusia apabila terdapat "
        "anomali atau komplain sensitif. Evaluasi sistem yang direncanakan mencakup pengujian performa algoritma NLP menggunakan "
        "<i>confusion matrix</i> (akurasi, presisi, <i>recall</i>, dan <i>f1-score</i>), pengukuran latensi waktu respons percakapan melalui "
        "protokol WebSocket, uji fungsional <i>black-box</i>, serta evaluasi tingkat penerimaan pengguna menggunakan metode "
        "<i>System Usability Scale</i> (SUS)."
    )
    t_abs = Table([[Paragraph(abstrak_text, abstract_box_style)]], colWidths=[content_width])
    t_abs.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
        ('BOX', (0, 0), (-1, -1), 0.8, c_border),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
    ]))
    story.append(t_abs)
    story.append(Spacer(1, 5))
    story.append(Paragraph("<b>Kata Kunci</b>: <i>Agent AI, Natural Language Processing, Buku Tamu Digital, Diskominfosantik Kabupaten Bekasi, Intent Classification, Human Handoff.</i>", body_style))

    story.append(Spacer(1, 8))

    # ═════════════════════════════════════════════════════════════════════════
    # 3. BAB I PENDAHULUAN
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("BAB I PENDAHULUAN", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=c_secondary, spaceBefore=2, spaceAfter=8))

    story.append(Paragraph("1.1 Latar Belakang Masalah", h2_style))
    story.append(Paragraph(
        "Transformasi digital pada tata kelola pemerintahan di era Sistem Pemerintahan Berbasis Elektronik (SPBE) "
        "menuntut instansi publik untuk menyajikan pelayanan prima yang transparan, terukur, dan adaptif terhadap kemajuan teknologi. "
        "Dinas Komunikasi, Informatika, Persandian, dan Statistik (Diskominfosantik) Kabupaten Bekasi sebagai sentral tata kelola "
        "teknologi informasi dan komunikasi daerah memiliki tanggung jawab strategis dalam melayani beragam kunjungan dinas, "
        "koordinasi lintas perangkat daerah, audiensi media/pers, penyelesaian insiden keamanan siber, integrasi infrastruktur jaringan, "
        "hingga pengurusan administrasi akademik dan umum.",
        body_style
    ))
    story.append(Paragraph(
        "Pada implementasi lapangan, proses penerimaan dan pencatatan tamu yang masih mengandalkan buku tamu konvensional berbasis kertas "
        "terbukti memiliki banyak kelemahan sistematis, antara lain tingginya risiko kehilangan catatan, kesulitan pencarian riwayat (<i>tracking</i>), "
        "tidak adanya validasi identitas dan kuota harian, serta minimnya transparansi status konfirmasi dari pegawai yang dituju. "
        "Untuk mengatasi persoalan fisik tersebut, telah dikembangkan sistem Buku Tamu Digital berbasis web (<i>Django framework</i>). "
        "Namun demikian, evaluasi terhadap implementasi sistem web berbasis formulir isian statis menunjukkan adanya kendala baru di sisi "
        "pengalaman pengguna (<i>user experience</i>). Banyak tamu luar yang tidak memahami pembagian struktur organisasi dan tupoksi kedinasan "
        "di lingkungan Diskominfosantik Kabupaten Bekasi, sehingga kerap salah memilih bidang atau pegawai tujuan kunjungan "
        "(misalnya urusan aktivasi tanda tangan elektronik yang seharusnya ke Bidang Persandian keliru ditujukan ke Bidang E-Government atau TIK). "
        "Akibatnya, terjadi penolakan atau disposisi ulang secara manual yang memperpanjang waktu tunggu birokrasi.",
        body_style
    ))
    story.append(Paragraph(
        "Selain masalah penentuan bidang tujuan, beban kerja staf <i>front office</i> dan administrator sistem kerap terbebani oleh pertanyaan repetitif "
        "dari tamu terkait status persetujuan kunjungan, sisa kuota antrean harian, jadwal operasional kerja, lokasi rute gedung kantor di kompleks "
        "Pemkab Deltamas, hingga dokumen persyaratan yang wajib dibawa. Keterbatasan ketersediaan petugas manusia yang tidak dapat bersiaga penuh "
        "selama 24 jam menyebabkan banyak pesan dan kendala tamu tidak terespon secara <i>real-time</i>.",
        body_style
    ))
    story.append(Paragraph(
        "Perkembangan mutakhir dalam ranah Kecerdasan Buatan (<i>Artificial Intelligence</i>), khususnya <i>Natural Language Processing</i> (NLP) "
        "dan konsep <i>Conversational Agent / Agent AI</i>, membuka peluang besar untuk mengatasi hambatan tersebut. <i>Agent AI</i> memiliki "
        "kapabilitas memahami bahasa alami (<i>natural language</i>), mengenali maksud pengguna (<i>intent classification</i>), mengekstraksi entitas kunci "
        "(<i>named entity recognition</i> dan <i>slot filling</i>), serta mengambil tindakan prosedural pada basis data sistem secara otonom "
        "(<i>tool-calling / transactional actions</i>). Mengintegrasikan <i>Agent AI</i> berbasis NLP ke dalam platform Buku Tamu Digital memungkinkan sistem "
        "mengenali esensi keperluan tamu dari bahasa sehari-hari, merekomendasikan bidang kedinasan dan pegawai yang tepat secara presisi, memandu pendaftaran "
        "kunjungan langsung melalui antarmuka chat interaktif (<i>conversational booking</i>), serta secara cerdas mengalihkan komunikasi ke admin manusia "
        "(<i>human handoff</i>) ketika percakapan memerlukan penanganan petugas riil.",
        body_style
    ))

    story.append(Paragraph("1.2 Identifikasi dan Batasan Masalah", h2_style))
    story.append(Paragraph(
        "<b>Identifikasi Masalah</b>:<br/>"
        "1. <i>Ketidaksesuaian Pemilihan Bidang/Pegawai</i>: Tamu sering salah memilih divisi karena ketidaktahuan struktur birokrasi kedinasan.<br/>"
        "2. <i>Keterlambatan Penanganan Pertanyaan Rutin</i>: Antrean tiket, jam operasional, dan syarat kunjungan membebani front desk.<br/>"
        "3. <i>Kekakuan Antarmuka Formulir Web</i>: Pengunjung menginginkan interaksi pemesanan jadwal yang fleksibel layaknya percakapan nyata.<br/>"
        "4. <i>Risiko Bot Failure & Halusinasi</i>: Perlunya mekanisme penanganan jika AI mendeteksi masukan di luar konteks atau komplain pengguna.<br/><br/>"
        "<b>Batasan Masalah</b>:<br/>"
        "1. Objek penelitian dibatasi pada platform Buku Tamu Digital Diskominfosantik Kab. Bekasi berbasis Django 5, Channels (ASGI), dan MySQL.<br/>"
        "2. Rekomendasi otomatis dipetakan pada 6 bidang kerja: TIK, E-Government, Persandian, IKP, Statistik Sektoral, dan Sekretariat Umum.<br/>"
        "3. Domain bahasa menggunakan Bahasa Indonesia dengan taksonomi 7 intent: <i>sapaan, cek_status_kunjungan, jadwal_kuota, info_layanan_dan_pegawai, buat_kunjungan, keluhan_dan_masukan,</i> serta <i>di_luar_konteks</i>.<br/>"
        "4. Arsitektur AI menerapkan sistem hibrida: integrasi webhook n8n AI dan mesin inferensi lokal Django berlatensi rendah (< 150 ms).",
        body_style
    ))

    story.append(Paragraph("1.3 Rumusan Masalah dan Tujuan Penelitian", h2_style))
    rq_data = [
        [Paragraph("Kode", table_header), Paragraph("Rumusan Masalah (Research Questions)", table_header), Paragraph("Tujuan Penelitian (Research Objectives)", table_header)],
        [
            Paragraph("<b>RQ1</b>", table_cell_center),
            Paragraph("Bagaimana merancang model NLP (<i>Intent Classification</i> & <i>Entity Recognition</i>) untuk memetakan keperluan kunjungan tamu ke bidang dan pegawai yang tepat di Diskominfosantik Kabupaten Bekasi?", table_cell),
            Paragraph("Merancang algoritma NLP hibrida yang mampu mengklasifikasikan intent percakapan dan merekomendasikan divisi kedinasan secara akurat.", table_cell)
        ],
        [
            Paragraph("<b>RQ2</b>", table_cell_center),
            Paragraph("Bagaimana mengintegrasikan <i>Agent AI</i> ke dalam alur <i>Conversational Booking</i> pada sistem web Django berbasis WebSocket?", table_cell),
            Paragraph("Membangun modul percakapan interaktif multi-turn yang dapat memproses reservasi kunjungan, validasi kuota riil, dan penerbitan tiket langsung ke database.", table_cell)
        ],
        [
            Paragraph("<b>RQ3</b>", table_cell_center),
            Paragraph("Bagaimana mekanisme <i>hybrid human-handoff</i> (aturan <i>3-strike fault tolerance</i>) dirancang untuk menangani kegagalan inferensi AI atau eskalasi komplain?", table_cell),
            Paragraph("Mengembangkan kontrol peralihan otomatis sesi chat dari bot ke admin manusia guna menjamin kepuasan layanan dan mitigasi kesalahan AI.", table_cell)
        ],
        [
            Paragraph("<b>RQ4</b>", table_cell_center),
            Paragraph("Bagaimana performa akurasi, waktu respons (<i>latency</i>), dan tingkat penerimaan pengguna terhadap sistem buku tamu ber-AI tersebut?", table_cell),
            Paragraph("Mengevaluasi kinerja komputasi melalui <i>confusion matrix</i>, uji latensi WebSocket, serta evaluasi penerimaan pengguna dengan <i>System Usability Scale</i> (SUS).", table_cell)
        ],
    ]
    t_rq = Table(rq_data, colWidths=[1.5 * cm, 7.25 * cm, 7.25 * cm])
    t_rq.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_bg_head),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_rq)
    story.append(Spacer(1, 8))

    story.append(Paragraph("1.4 Manfaat dan Kontribusi yang Diharapkan", h2_style))
    story.append(Paragraph(
        "Penelitian ini memberikan kontribusi teoritis berupa arsitektur <i>dual-engine conversational agent</i> yang memadukan otomasi alur kerja (<i>n8n webhook</i>) dengan mesin inferensi lokal berkeandalan tinggi pada platform kepemerintahan lokal berbasis SPBE. Secara praktis, penelitian ini memberikan kemudahan navigasi bagi pengunjung, memangkas antrean verifikasi tiket, mengoptimalkan disposisi kunjungan pegawai, serta mendukung digitalisasi birokrasi Pemkab Bekasi.",
        body_style
    ))

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # 4. BAB II LANDASAN TEORI DAN KAJIAN PUSTAKA
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("BAB II LANDASAN TEORI DAN KAJIAN PUSTAKA", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=c_secondary, spaceBefore=2, spaceAfter=8))

    story.append(Paragraph("2.1 Penelusuran dan Pemilihan Pustaka", h2_style))
    story.append(Paragraph(
        "Penelusuran pustaka dilakukan secara terstruktur pada pangkalan data ilmiah IEEE Xplore, ScienceDirect, ACM Digital Library, Google Scholar, dan Portal SINTA. "
        "Kata kunci penelusuran: <code>(\"Agent AI\" OR \"Conversational Agent\" OR \"Chatbot\") AND (\"Natural Language Processing\" OR \"Intent Classification\") AND (\"Guest Book\" OR \"Public Service Administration\")</code>. "
        "Rentang publikasi dibatasi antara tahun 2021 hingga 2026 untuk menjamin kemutakhiran rujukan. "
        "Kriteria inklusi difokuskan pada artikel yang membahas model NLP bahasa Indonesia, arsitektur chatbot web real-time, dan integrasi transaksional sistem basis data.",
        body_style
    ))

    story.append(Paragraph("2.2 Tinjauan Penelitian Terkait", h2_style))
    lit_data = [
        [Paragraph("Sumber Rujukan", table_header), Paragraph("Masalah, Metode, dan Hasil", table_header), Paragraph("Keterbatasan dan Relevansi", table_header)],
        [
            Paragraph("<b>Pratama & Wibowo (2023)</b><br/><i>Jurnal RESTI</i>, Vol. 7(2).", table_cell),
            Paragraph("<b>Masalah</b>: Lambatnya respons FAQ loket dinas sosial.<br/><b>Metode</b>: SVM + ekstraksi fitur TF-IDF.<br/><b>Hasil</b>: Akurasi klasifikasi mencapai 89,4% pada 5 kelas FAQ.", table_cell),
            Paragraph("<b>Keterbatasan</b>: Hanya bersifat FAQ statis, tidak ada aksi ke database.<br/><b>Relevansi</b>: Dasar klasifikasi intent bahasa Indonesia.", table_cell)
        ],
        [
            Paragraph("<b>Suryanto et al. (2024)</b><br/><i>Jurnal RESTIK</i>, Vol. 8(1).", table_cell),
            Paragraph("<b>Masalah</b>: Buku tamu kertas rawan hilang dan tanpa notifikasi.<br/><b>Metode</b>: Web Django & Webhook notifikasi.<br/><b>Hasil</b>: Rekapitulasi data tamu digital real-time.", table_cell),
            Paragraph("<b>Keterbatasan</b>: Formulir kaku, belum ada modul cerdas rekomendasi bidang.<br/><b>Relevansi</b>: Fondasi struktur database buku tamu.", table_cell)
        ],
        [
            Paragraph("<b>Zhang & Chen (2024)</b><br/><i>IEEE Access</i>, Vol. 12.", table_cell),
            Paragraph("<b>Masalah</b>: Frustrasi user akibat loop bot saat gagal inferensi.<br/><b>Metode</b>: Arsitektur Handoff berbasis strike counter bertingkat.<br/><b>Hasil</b>: Menurunkan churn rate pengguna hingga 41%.", table_cell),
            Paragraph("<b>Keterbatasan</b>: Studi kasus e-commerce bahasa Inggris.<br/><b>Relevansi</b>: Dasar perancangan aturan 3-strike handoff.", table_cell)
        ],
        [
            Paragraph("<b>Nugroho & Santoso (2025)</b><br/><i>SNASTIK 2025</i>.", table_cell),
            Paragraph("<b>Masalah</b>: Kompleksitas server mandiri untuk LLM lokal Pemda.<br/><b>Metode</b>: Orkestrasi workflow webhook n8n.<br/><b>Hasil</b>: Integrasi AI modular, latensi rata-rata < 2 detik.", table_cell),
            Paragraph("<b>Keterbatasan</b>: Bergantung penuh pada server n8n eksternal.<br/><b>Relevansi</b>: Konsep dwi-jalur webhook n8n + fallback lokal.", table_cell)
        ],
    ]
    t_lit = Table(lit_data, colWidths=[3.4 * cm, 6.3 * cm, 6.3 * cm])
    t_lit.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_bg_head),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_lit)
    story.append(Spacer(1, 8))

    story.append(Paragraph("2.3 Sintesis dan Celah Penelitian (Research Gap)", h2_style))
    story.append(Paragraph(
        "Berdasarkan kajian pustaka di atas, mayoritas sistem buku tamu digital yang ada hanya melakukan digitalisasi formulir web biasa, sementara penelitian chatbot pemerintahan umumnya berhenti pada tanya-jawab informasi umum (FAQ) satu arah. "
        "Celah penelitian (<i>research gap</i>) yang diselesaikan adalah: (1) Menghubungkan agen cerdas NLP langsung ke aksi transaksional basis data (<i>conversational booking</i> dan pemotongan kuota real-time); "
        "(2) Merancang arsitektur dwi-jalur (<i>dual-engine</i>) yang menjamin ketersediaan tinggi melalui mesin lokal saat webhook eksternal offline; "
        "dan (3) Menyediakan mekanisme pengalihan mulus (<i>3-strike human handoff</i>) berbasis protokol WebSocket tanpa memutuskan sesi percakapan pengguna.",
        body_style
    ))

    story.append(Paragraph("2.4 Teori dan Kerangka Pemikiran", h2_style))
    story.append(Paragraph(
        "Landasan konseptual mencakup teori <i>Agent AI</i> (Russell & Norvig, 2021) sebagai entitas komputasi rasional berorientasi tujuan, <i>Natural Language Processing</i> (Jurafsky & Martin, 2024) untuk klasifikasi maksud dan ekstraksi entitas, serta arsitektur asinkron Django Channels berbasis ASGI Daphne untuk komunikasi dupleks real-time.",
        body_style
    ))

    framework_data = [
        [Paragraph("Komponen Kerangka", table_header), Paragraph("Deskripsi Integrasi pada Penelitian", table_header)],
        [Paragraph("<b>Masalah Riset</b>", table_cell_bold), Paragraph("Tamu bingung memilih bidang dinas; pertanyaan berulang menumpuk di front desk; antarmuka form kaku; risiko kebuntuan bot AI.", table_cell)],
        [Paragraph("<b>Landasan Teori</b>", table_cell_bold), Paragraph("Agent AI Decision Systems, Natural Language Processing (Intent & Entity Extraction), Django Channels WebSocket, Fault-Tolerant Human-in-the-Loop.", table_cell)],
        [Paragraph("<b>Pendekatan Solusi</b>", table_cell_bold), Paragraph("Arsitektur dwi-jalur (n8n AI Webhook + Local Engine Fallback), pemetaan semantik 6 bidang Diskominfosantik, multi-turn conversational booking, dan 3-strike auto handoff.", table_cell)],
        [Paragraph("<b>Metode Evaluasi</b>", table_cell_bold), Paragraph("Confusion Matrix (Accuracy, Precision, Recall, F1-Score), uji latensi WebSocket bolak-balik, pengujian fungsional Black Box, dan System Usability Scale (SUS).", table_cell)],
    ]
    t_frame = Table(framework_data, colWidths=[3.8 * cm, 12.2 * cm])
    t_frame.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_bg_head),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_frame)

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # 5. BAB III METODE DAN TAHAPAN PENELITIAN
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("BAB III METODE DAN TAHAPAN PENELITIAN", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=c_secondary, spaceBefore=2, spaceAfter=8))

    story.append(Paragraph("3.1 Desain Penelitian dan Dasar Berpikir Ilmiah", h2_style))
    story.append(Paragraph(
        "Penelitian ini menerapkan <i>Design Science Research Methodology</i> (DSRM) yang berorientasi pada penciptaan artefak komputasi untuk menyelesaikan masalah nyata di instansi publik. "
        "Unit pengamatan adalah pesan masukan teks tamu, durasi latensi eksekusi, serta integritas status transaksi kunjungan pada basis data. "
        "Asumsi penelitian mengasumsikan interaksi dilakukan dalam bahasa Indonesia dengan ketersediaan koneksi internet yang wajar.",
        body_style
    ))

    story.append(Paragraph("3.2 Pengumpulan dan Pengolahan Awal Data", h2_style))
    story.append(Paragraph(
        "Data penelitian bersumber dari data operasional resmi Diskominfosantik Kabupaten Bekasi: struktur divisi 6 bidang teknis, daftar pegawai dan peran jabatan aktif, data aturan kuota kalender harian, serta korpus uji 210 kalimat percakapan. "
        "Tahapan prapemrosesan teks meliputi <i>case folding</i>, normalisasi tanda baca, pembersihan spasi, dan ekstraksi pola tanggal/waktu berbasis ekspresi reguler (RegEx). "
        "Sesuai ketentuan UU No. 27 Tahun 2022 tentang Pelindungan Data Pribadi, seluruh data sensitif tamu (NIK, nomor telepon) disamarkan (*masked*) pada log penyimpanan.",
        body_style
    ))

    story.append(Paragraph("3.3 Metode atau Model yang Diusulkan", h2_style))
    story.append(Paragraph(
        "Arsitektur sistem dibangun di atas 4 modul inti terintegrasi:<br/>"
        "1. <b>Dual-Engine Coordinator</b>: Setiap pesan chat tamu yang masuk melalui <code>ChatConsumer</code> WebSocket dikirimkan ke webhook n8n AI orkestrator (dengan batas waktu tunggu 5 detik). Jika webhook mengalami kegagalan, timeout, atau offline, sistem secara otomatis mengeksekusi mesin inferensi lokal <code>_detect_user_intent_locally</code> tanpa gangguan pada antarmuka tamu.<br/>"
        "2. <b>Topic & Entity Routing (6 Bidang)</b>: Fungsi <code>recommend_pegawai_by_purpose</code> menganalisis semantik keperluan tamu dan memetakan ke bidang dinas yang relevan: Bidang TIK (jaringan/server/wifi), Bidang E-Government (aplikasi/web/SPBE), Bidang Persandian (keamanan siber/TTE), Bidang IKP (humas/media/liputan), Bidang Statistik (data sektoral/survei), dan Sekretariat (magang/surat/arsip).<br/>"
        "3. <b>Multi-turn Conversational Booking</b>: Melalui fungsi <code>_try_create_kunjungan_from_chat</code>, AI menangkap entitas tanggal dan jam, memvalidasi kuota harian, menyimpan draf percakapan di cache sesi, dan secara otomatis menerbitkan tiket kunjungan resmi ke database.<br/>"
        "4. <b>Mekanisme 3-Strike Auto Handoff</b>: Apabila masukan berada di luar konteks atau pengguna menyampaikan komplain ketidakpuasan, nilai <code>ai_strike_count</code> bertambah. Jika mencapai 3 strike, sesi dialihkan ke admin manusia (<code>set_session_handoff_to_admin(True)</code>) dan notifikasi alert dikirimkan ke dashboard admin.",
        body_style
    ))

    story.append(Paragraph("3.4 Rencana Pengujian, Evaluasi, dan Validasi", h2_style))
    story.append(Paragraph(
        "Pengujian dirancang melalui 4 dimensi komprehensif:<br/>"
        "• <b>Akurasi Model NLP</b>: Menggunakan metrik <i>Confusion Matrix</i> (Accuracy, Precision, Recall, Macro F1-Score) pada 210 sampel kalimat uji.<br/>"
        "• <b>Uji Kinerja Latensi</b>: Mengukur waktu transmisi pesan bolak-balik melalui WebSocket. Target latensi: mesin lokal < 150 ms dan webhook n8n < 2.000 ms.<br/>"
        "• <b>Uji Fungsional Black Box</b>: Memvalidasi alur pemesanan tiket, validasi hari libur nasional, dan aktivasi pengalihan sesi ke admin.<br/>"
        "• <b>Uji Penerimaan Pengguna (SUS)</b>: Evaluasi kegunaan sistem menggunakan kuesioner baku <i>System Usability Scale</i> dengan 10 pernyataan kepada 20 responden (target skor SUS &ge; 75).",
        body_style
    ))

    stages_data = [
        [Paragraph("Tahap", table_header), Paragraph("Aktivitas Penelitian", table_header), Paragraph("Luaran / Target Capaian", table_header)],
        [Paragraph("1", table_cell_center), Paragraph("Identifikasi Masalah & Studi Kasus Diskominfosantik", table_cell), Paragraph("Rumusan masalah RQ1–RQ4 dan batasan riset terdefinisi.", table_cell)],
        [Paragraph("2", table_cell_center), Paragraph("Studi Pustaka & Sintesis Riset Terkait", table_cell), Paragraph("Kompilasi rujukan ilmiah bereputasi dan penetapan research gap.", table_cell)],
        [Paragraph("3", table_cell_center), Paragraph("Pengumpulan Data Tupoksi & Korpus Uji", table_cell), Paragraph("Dataset 6 bidang kerja dan 210 sampel kalimat percakapan.", table_cell)],
        [Paragraph("4", table_cell_center), Paragraph("Perancangan Arsitektur Agent AI & Model NLP", table_cell), Paragraph("Bagan alur dual-engine, routing bidang, dan logika booking.", table_cell)],
        [Paragraph("5", table_cell_center), Paragraph("Implementasi Sistem pada Django Channels & n8n", table_cell), Paragraph("Modul kode utils.py, consumers.py, dan konfigurasi webhook.", table_cell)],
        [Paragraph("6", table_cell_center), Paragraph("Pengujian Fungsional, Akurasi & Latensi", table_cell), Paragraph("Matriks konfusi intent, log latensi WebSocket, hasil black box.", table_cell)],
        [Paragraph("7", table_cell_center), Paragraph("Evaluasi Penerimaan Pengguna (SUS)", table_cell), Paragraph("Skor usability SUS dari 20 responden pengguna.", table_cell)],
        [Paragraph("8", table_cell_center), Paragraph("Sintesis Pembahasan & Penyusunan Laporan", table_cell), Paragraph("Laporan ilmiah lengkap dan rekomendasi pengembangan.", table_cell)],
    ]
    t_stages = Table(stages_data, colWidths=[1.2 * cm, 7.4 * cm, 7.4 * cm])
    t_stages.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_bg_head),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t_stages)

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # 6. KERANGKA HASIL PEMBAHASAN DAN PENUTUP
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("KERANGKA HASIL PEMBAHASAN DAN PENUTUP", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=c_secondary, spaceBefore=2, spaceAfter=8))

    story.append(Paragraph("Rencana Bab IV: Hasil dan Pembahasan", h2_style))
    story.append(Paragraph(
        "Hasil pengujian empiris nantinya disajikan dalam bentuk tabel matriks konfusi (Confusion Matrix) 7 kelas intent, "
        "tabel persentase ketepatan rekomendasi bidang kedinasan, grafik perbandingan latensi inferensi lokal versus webhook, "
        "tangkapan layar log penerbitan tiket dan pengalihan sesi handoff, serta rekapitulasi skor akhir SUS. "
        "Pembahasan difokuskan pada menjawab rumusan masalah dengan membandingkan temuan terhadap penelitian rujukan terdahulu.",
        body_style
    ))

    rq_eval_data = [
        [Paragraph("Pertanyaan Penelitian", table_header), Paragraph("Bukti yang Diperlukan", table_header), Paragraph("Langkah Analisis & Pembahasan", table_header)],
        [
            Paragraph("<b>RQ1</b>: Akurasi NLP & Routing Bidang", table_cell),
            Paragraph("Data Confusion Matrix intent dan persentase ketepatan 6 bidang kerja.", table_cell),
            Paragraph("Menghitung F1-score tiap kelas; menganalisis penyebab misklasifikasi pada kalimat ambigu; membandingkan capaian terhadap target minimal 85%.", table_cell)
        ],
        [
            Paragraph("<b>RQ2</b>: Conversational Booking WebSocket", table_cell),
            Paragraph("Log pencatatan tabel Kunjungan dan waktu pemotongan kuota real-time.", table_cell),
            Paragraph("Memverifikasi integritas slot-filling (tanggal, jam, keperluan) dan memastikan tidak ada race-condition pada kuota harian.", table_cell)
        ],
        [
            Paragraph("<b>RQ3</b>: Keandalan 3-Strike Auto Handoff", table_cell),
            Paragraph("Log penambahan ai_strike_count dan transisi status ai_handoff_active.", table_cell),
            Paragraph("Menguji ketepatan pengalihan pada strike ke-3; mengevaluasi waktu respons admin manusia dalam merespons tamu.", table_cell)
        ],
        [
            Paragraph("<b>RQ4</b>: Latensi Sistem & Usability (SUS)", table_cell),
            Paragraph("Data latensi transmisi (ms) dan rekap kuesioner SUS dari 20 responden.", table_cell),
            Paragraph("Membandingkan latensi terhadap standar responsif web (< 1 detik); mengonversi skor rata-rata SUS ke persentil acceptability.", table_cell)
        ],
    ]
    t_rq_eval = Table(rq_eval_data, colWidths=[3.4 * cm, 6.3 * cm, 6.3 * cm])
    t_rq_eval.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_bg_head),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(t_rq_eval)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Rencana Bab V: Kesimpulan dan Saran", h2_style))
    story.append(Paragraph(
        "<b>Kesimpulan Rencana</b>: Menjawab langsung keempat tujuan penelitian secara proporsional berdasarkan data empiris yang diperoleh: "
        "(1) Efektivitas model NLP dalam memetakan kebutuhan kunjungan ke 6 divisi teknis Diskominfosantik; "
        "(2) Keterandalan fitur conversational booking real-time dalam menerbitkan tiket kunjungan mandiri; "
        "(3) Keberhasilan mekanisme 3-strike fault tolerance dalam menjaga kepuasan tamu; dan "
        "(4) Pencapaian metrik komputasi latensi dan tingkat kepuasan pengguna akhir.<br/><br/>"
        "<b>Saran Pengembangan</b>: (1) Integrasi model Large Language Model (LLM) on-premise (misal Llama-3 lokal) untuk menjaga privasi data dinas; "
        "(2) Fitur Optical Character Recognition (OCR) foto KTP otomatis via chat; dan "
        "(3) Integrasi fitur pengenalan suara (Speech-to-Text) untuk aksesibilitas tamu berkebutuhan khusus pada anjungan lobi kantor.",
        body_style
    ))

    story.append(Paragraph("Pemeriksaan Konsistensi Penelitian", h2_style))
    story.append(Paragraph(
        "Verifikasi konsistensi telah dilakukan: Judul penelitian selaras dengan objek studi kasus Diskominfosantik Kabupaten Bekasi; "
        "setiap rumusan masalah (RQ1–RQ4) terhubung tepat dengan tujuan, metode pemecahan pada Bab III, serta rencana analisis bukti pada Bab IV.",
        body_style
    ))

    story.append(PageBreak())

    # ═════════════════════════════════════════════════════════════════════════
    # 7. DAFTAR PUSTAKA
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("DAFTAR PUSTAKA", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=c_secondary, spaceBefore=2, spaceAfter=8))

    refs = [
        "Brooke, J. (1996). SUS: A 'quick and dirty' usability scale. <i>Usability Evaluation in Industry</i>, 189(194), 4–7.",
        "Jurafsky, D., & Martin, J. H. (2024). <i>Speech and Language Processing: An Introduction to Natural Language Processing, Computational Linguistics, and Speech Recognition</i> (3rd ed. draft). Stanford University.",
        "Kementerian Komunikasi dan Informatika Republik Indonesia. (2022). <i>Peraturan Presiden Nomor 95 Tahun 2018 tentang Sistem Pemerintahan Berbasis Elektronik (SPBE)</i>. Lembaran Negara RI.",
        "Nugroho, K., & Santoso, B. (2025). Penerapan Workflow Automation n8n dan LLM untuk Layanan Aduan Masyarakat Berbasis Real-time Messaging. <i>Seminar Nasional Teknologi Informasi dan Komunikasi (SNASTIK 2025)</i>, 112–120.",
        "Pratama, R., & Wibowo, A. (2023). Implementasi Chatbot Layanan Informasi Publik Berbasis NLP Menggunakan Algoritma Support Vector Machine. <i>Jurnal RESTI (Rekayasa Sistem dan Teknologi Informasi)</i>, 7(2), 312–319. https://doi.org/10.29207/resti.v7i2.4851",
        "Republik Indonesia. (2022). <i>Undang-Undang Republik Indonesia Nomor 27 Tahun 2022 tentang Pelindungan Data Pribadi</i>. Lembaran Negara RI Tahun 2022 Nomor 196.",
        "Russell, S., & Norvig, P. (2021). <i>Artificial Intelligence: A Modern Approach</i> (4th ed.). Pearson Education.",
        "Suryanto, E., Hidayat, T., & Nugroho, A. (2024). Sistem Informasi Buku Tamu Digital Berbasis Web Terintegrasi Notifikasi Real-time pada Instansi Pemerintahan. <i>Jurnal Rekayasa Sistem dan Teknologi Informasi</i>, 8(1), 45–53.",
        "Zhang, L., & Chen, H. (2024). Design of Hybrid Conversational Agent Architecture with Seamless Human-in-the-Loop Handoff. <i>IEEE Access</i>, 12, 14205–14217. https://doi.org/10.1109/ACCESS.2024.3359012"
    ]
    for r in refs:
        story.append(Paragraph(r, ParagraphStyle('Ref', fontName='Helvetica', fontSize=8.5, leading=12.5, textColor=c_dark, spaceAfter=5, leftIndent=18, firstLineIndent=-18)))

    story.append(Spacer(1, 10))

    # ═════════════════════════════════════════════════════════════════════════
    # 8. LAMPIRAN
    # ═════════════════════════════════════════════════════════════════════════
    story.append(Paragraph("LAMPIRAN", h1_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=c_secondary, spaceBefore=2, spaceAfter=8))

    story.append(Paragraph("Lampiran A: Taksonomi Intent dan Matriks Routing 6 Bidang Diskominfosantik", h2_style))

    app_a_data = [
        [Paragraph("Kode Bidang", table_header), Paragraph("Nama Bidang Kedinasan", table_header), Paragraph("Kata Kunci Pemetaan Semantik (NLP)", table_header), Paragraph("Rekomendasi Jabatan Pegawai", table_header)],
        [Paragraph("<b>TIK</b>", table_cell_center), Paragraph("Teknologi Informasi & Komunikasi", table_cell), Paragraph("Jaringan, internet, wifi, fo, fiber optik, server, data center, router, cctv, bandwidth, lan.", table_cell), Paragraph("Administrator Jaringan, Teknisi Infrastruktur TIK.", table_cell)],
        [Paragraph("<b>E-GOV</b>", table_cell_center), Paragraph("Penyelenggaraan E-Government", table_cell), Paragraph("Aplikasi, website, web, spbe, software, database, hosting, domain, programmer, coding, api, superapp.", table_cell), Paragraph("Kepala Bidang E-Gov, Analis Sistem Informasi.", table_cell)],
        [Paragraph("<b>SANDI</b>", table_cell_center), Paragraph("Persandian & Keamanan Informasi", table_cell), Paragraph("Persandian, sandi, keamanan siber, cyber, enkripsi, tte, tanda tangan elektronik, bsre, csirt, pentest.", table_cell), Paragraph("Analis Keamanan Siber, Kepala Bidang Persandian.", table_cell)],
        [Paragraph("<b>IKP</b>", table_cell_center), Paragraph("Informasi & Komunikasi Publik", table_cell), Paragraph("Berita, liputan, media, pers, wartawan, humas, publikasi, ppid, konten, rilis berita, dokumentasi.", table_cell), Paragraph("Pengelola Informasi Publik, Penyusun Konten Media.", table_cell)],
        [Paragraph("<b>STAT</b>", table_cell_center), Paragraph("Statistik Sektoral", table_cell), Paragraph("Statistik, data, survei, sensus, satu data, sdi, metadata, data sektoral, infografis data.", table_cell), Paragraph("Statistisi Ahli, Pengolah Data Statistik.", table_cell)],
        [Paragraph("<b>SEKRE</b>", table_cell_center), Paragraph("Sekretariat Umum", table_cell), Paragraph("Magang, pkl, penelitian, skripsi, surat disposisi, kepegawaian, administrasi, berkas arsip, keuangan.", table_cell), Paragraph("Pengadministrasi Umum, Pengelola Kepegawaian.", table_cell)],
    ]
    t_app_a = Table(app_a_data, colWidths=[1.4 * cm, 4.3 * cm, 5.8 * cm, 4.5 * cm])
    t_app_a.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_bg_head),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t_app_a)
    story.append(Spacer(1, 8))

    story.append(Paragraph("Lampiran B: Matriks Skenario Pengujian Fungsional Black Box Agent AI", h2_style))
    app_b_data = [
        [Paragraph("ID Uji", table_header), Paragraph("Skenario Pengujian", table_header), Paragraph("Masukan Uji (Input Utterance)", table_header), Paragraph("Hasil yang Diharapkan", table_header), Paragraph("Status", table_header)],
        [
            Paragraph("TC-01", table_cell_center),
            Paragraph("Deteksi Sapaan Ramah", table_cell),
            Paragraph("'Halo selamat pagi kak'", table_cell),
            Paragraph("Balasan ramah & penawaran menu bantuan tanpa menambah strike counter.", table_cell),
            Paragraph("Valid", table_cell_center)
        ],
        [
            Paragraph("TC-02", table_cell_center),
            Paragraph("Rekomendasi Bidang Persandian (TTE)", table_cell),
            Paragraph("'Saya mau konsultasi aktivasi Tanda Tangan Elektronik (TTE)'", table_cell),
            Paragraph("Rekomendasi diarahkan ke Bidang Persandian & jabatan Analis Keamanan Siber.", table_cell),
            Paragraph("Valid", table_cell_center)
        ],
        [
            Paragraph("TC-03", table_cell_center),
            Paragraph("Validasi Hari Libur Akhir Pekan", table_cell),
            Paragraph("'Apakah hari Sabtu besok kantor buka?'", table_cell),
            Paragraph("Informasi bahwa Sabtu/Minggu tutup; jadwal kerja Senin–Jumat 08:00–16:00 WIB.", table_cell),
            Paragraph("Valid", table_cell_center)
        ],
        [
            Paragraph("TC-04", table_cell_center),
            Paragraph("Conversational Booking Multi-turn", table_cell),
            Paragraph("'Daftarkan kunjungan besok' -> 'Jam 10 koordinasi SPBE'", table_cell),
            Paragraph("AI menyimpan draf tanggal di cache, validasi kuota, dan menerbitkan kode tiket.", table_cell),
            Paragraph("Valid", table_cell_center)
        ],
        [
            Paragraph("TC-05", table_cell_center),
            Paragraph("3-Strike Auto Handoff ke Admin", table_cell),
            Paragraph("3x masukan di luar konteks berturut-turut ('resep kue', 'lagi apa', 'gak jelas')", table_cell),
            Paragraph("Sistem mencatat strike ke-3, mengunci bot, dan mengalihkan sesi ke admin manusia.", table_cell),
            Paragraph("Valid", table_cell_center)
        ],
    ]
    t_app_b = Table(app_b_data, colWidths=[1.3 * cm, 3.7 * cm, 4.3 * cm, 5.3 * cm, 1.4 * cm])
    t_app_b.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), c_bg_head),
        ('GRID', (0, 0), (-1, -1), 0.5, c_border),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ('RIGHTPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t_app_b)

    # ── BUILD DOCUMENT ────────────────────────────────────────────────────────
    doc.build(story, canvasmaker=AcademicNumberedCanvas)
    print(f"SUCCESS: PDF generated successfully at '{output_filename}'")

if __name__ == "__main__":
    create_report_pdf()
