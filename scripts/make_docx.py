import os
import docx
from docx.shared import Inches, Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, fill_hex):
    """Set warna latar belakang sel tabel."""
    shading_xml = f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>'
    cell._tc.get_or_add_tcPr().append(parse_xml(shading_xml))

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """Set margin internal (padding) sel tabel dalam dxa (1 pt = 20 dxa)."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement('w:tcMar')
    for m, val in [('top', top), ('bottom', bottom), ('left', left), ('right', right)]:
        node = OxmlElement(f'w:{m}')
        node.set(qn('w:w'), str(val))
        node.set(qn('w:type'), 'dxa')
        tcMar.append(node)
    tcPr.append(tcMar)

def set_table_borders(table, color="B0BEC5", sz="4", val="single"):
    """Set border tabel agar bersih dan profesional."""
    tblPr = table._tbl.tblPr
    borders_xml = f'''
    <w:tblBorders {nsdecls("w")}>
        <w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>
        <w:left w:val="none"/>
        <w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>
        <w:right w:val="none"/>
        <w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/>
        <w:insideV w:val="none"/>
    </w:tblBorders>
    '''
    tblPr.append(parse_xml(borders_xml))

def add_styled_paragraph(doc, text="", style='Normal', space_before=0, space_after=6, line_spacing=1.15, align=WD_ALIGN_PARAGRAPH.JUSTIFY):
    p = doc.add_paragraph(style=style)
    p.alignment = align
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = line_spacing
    if text:
        run = p.add_run(text)
        run.font.name = 'Times New Roman'
        run.font.size = Pt(12)
        run._r.get_or_add_rPr().get_or_add_rFonts().set(qn('w:ascii'), 'Times New Roman')
        run._r.get_or_add_rPr().get_or_add_rFonts().set(qn('w:hAnsi'), 'Times New Roman')
    return p

def create_docx_report(output_filename="LAPORAN_UTS_METODOLOGI_PENELITIAN.docx"):
    doc = docx.Document()

    # ── 1. PAGE SETUP (A4, MARGINS AKADEMIK) ──────────────────────────────────
    sections = doc.sections
    for section in sections:
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.left_margin = Cm(3.0)   # Standar jilid/makalah
        section.right_margin = Cm(2.5)
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(2.5)

    # Set default style font
    normal_style = doc.styles['Normal']
    normal_style.font.name = 'Times New Roman'
    normal_style.font.size = Pt(12)
    normal_style.font.color.rgb = RGBColor(0, 0, 0)

    # ═════════════════════════════════════════════════════════════════════════
    # 2. HALAMAN COVER
    # ═════════════════════════════════════════════════════════════════════════
    p_kop = doc.add_paragraph()
    p_kop.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_kop.paragraph_format.space_before = Pt(0)
    p_kop.paragraph_format.space_after = Pt(2)
    p_kop.paragraph_format.line_spacing = 1.15
    r = p_kop.add_run("LAPORAN PROYEK\nUJIAN TENGAH SEMESTER\nMETODOLOGI PENELITIAN")
    r.font.name = 'Times New Roman'
    r.font.size = Pt(14)
    r.font.bold = True

    p_sp = doc.add_paragraph()
    p_sp.paragraph_format.space_after = Pt(6)

    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(4)
    p_title.paragraph_format.space_after = Pt(8)
    p_title.paragraph_format.line_spacing = 1.15
    r_title = p_title.add_run("IMPLEMENTASI AGENT AI BERBASIS NATURAL LANGUAGE PROCESSING (NLP) PADA SISTEM BUKU TAMU DIGITAL DI DISKOMINFOSANTIK KABUPATEN BEKASI")
    r_title.font.name = 'Times New Roman'
    r_title.font.size = Pt(14)
    r_title.font.bold = True

    p_sem = doc.add_paragraph()
    p_sem.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sem.paragraph_format.space_after = Pt(14)
    r_sem = p_sem.add_run("Semester Gassal Tahun Akademik 2026/2027")
    r_sem.font.name = 'Times New Roman'
    r_sem.font.size = Pt(12)
    r_sem.font.bold = True

    # Logo UPB
    logo_path = "extracted_image1.png"
    if os.path.exists(logo_path):
        p_logo = doc.add_paragraph()
        p_logo.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p_logo.paragraph_format.space_after = Pt(18)
        run_logo = p_logo.add_run()
        run_logo.add_picture(logo_path, width=Inches(1.8))

    # Identitas Mahasiswa
    p_disusun = doc.add_paragraph()
    p_disusun.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_disusun.paragraph_format.space_after = Pt(4)
    r_dis = p_disusun.add_run("Disusun oleh:")
    r_dis.font.name = 'Times New Roman'
    r_dis.font.size = Pt(12)

    p_mhs = doc.add_paragraph()
    p_mhs.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_mhs.paragraph_format.space_after = Pt(14)
    p_mhs.paragraph_format.line_spacing = 1.15
    r_mhs = p_mhs.add_run("MUHAMMAD ARIF MULYANTO\n312310359\nKelas I231C")
    r_mhs.font.name = 'Times New Roman'
    r_mhs.font.size = Pt(12)
    r_mhs.font.bold = True

    p_dosen = doc.add_paragraph()
    p_dosen.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_dosen.paragraph_format.space_after = Pt(20)
    p_dosen.paragraph_format.line_spacing = 1.15
    r_dosen_lbl = p_dosen.add_run("Dosen Pengampu:\n")
    r_dosen_lbl.font.name = 'Times New Roman'
    r_dosen_lbl.font.size = Pt(12)
    r_dosen_val = p_dosen.add_run("Abdul Halim Anshor, S.Kom., M.Kom.")
    r_dosen_val.font.name = 'Times New Roman'
    r_dosen_val.font.size = Pt(12)
    r_dosen_val.font.bold = True

    p_inst = doc.add_paragraph()
    p_inst.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_inst.paragraph_format.space_after = Pt(0)
    p_inst.paragraph_format.line_spacing = 1.15
    r_inst = p_inst.add_run("PROGRAM STUDI TEKNIK INFORMATIKA\nFAKULTAS TEKNIK\nUNIVERSITAS PELITA BANGSA\nBEKASI\n2026")
    r_inst.font.name = 'Times New Roman'
    r_inst.font.size = Pt(12)
    r_inst.font.bold = True

    doc.add_page_break()

    # ═════════════════════════════════════════════════════════════════════════
    # 3. IDENTITAS PENELITIAN & ABSTRAK
    # ═════════════════════════════════════════════════════════════════════════
    p_sec = doc.add_paragraph()
    p_sec.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sec.paragraph_format.space_before = Pt(0)
    p_sec.paragraph_format.space_after = Pt(12)
    r_sec = p_sec.add_run("PETUNJUK PENYUSUNAN DAN ABSTRAK")
    r_sec.font.name = 'Times New Roman'
    r_sec.font.size = Pt(14)
    r_sec.font.bold = True

    # Identitas Penulis
    p_id_h = doc.add_paragraph()
    p_id_h.paragraph_format.space_after = Pt(4)
    r_id_h = p_id_h.add_run("Judul dan identitas penulis:")
    r_id_h.font.name = 'Times New Roman'
    r_id_h.font.size = Pt(12)
    r_id_h.font.bold = True

    id_items = [
        ("Judul penelitian", "Implementasi Agent AI Berbasis Natural Language Processing (NLP) pada Sistem Buku Tamu Digital di Diskominfosantik Kabupaten Bekasi"),
        ("Bidang Informatika", "Kecerdasan Buatan (Artificial Intelligence) / Natural Language Processing (NLP) dan Rekayasa Perangkat Lunak Web"),
        ("Objek & fokus studi kasus", "Sistem Buku Tamu Digital pada Dinas Komunikasi, Informatika, Persandian, dan Statistik (Diskominfosantik) Kabupaten Bekasi (berfokus pada otomatisasi layanan interaksi tamu, klasifikasi intent pesan, rekomendasi bidang/pegawai tujuan, conversational booking cerdas, dan hybrid human-handoff via WebSocket)")
    ]
    for lbl, val in id_items:
        p_item = doc.add_paragraph()
        p_item.paragraph_format.left_indent = Inches(0.2)
        p_item.paragraph_format.space_after = Pt(3)
        p_item.paragraph_format.line_spacing = 1.15
        r_lbl = p_item.add_run(f"• {lbl}: ")
        r_lbl.font.name = 'Times New Roman'
        r_lbl.font.size = Pt(12)
        r_lbl.font.bold = True
        r_val = p_item.add_run(val)
        r_val.font.name = 'Times New Roman'
        r_val.font.size = Pt(12)

    # Abstrak
    p_abs_h = doc.add_paragraph()
    p_abs_h.paragraph_format.space_before = Pt(10)
    p_abs_h.paragraph_format.space_after = Pt(4)
    r_abs_h = p_abs_h.add_run("Abstrak deskriptif rancangan penelitian:")
    r_abs_h.font.name = 'Times New Roman'
    r_abs_h.font.size = Pt(12)
    r_abs_h.font.bold = True

    p_abs = doc.add_paragraph()
    p_abs.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p_abs.paragraph_format.space_after = Pt(6)
    p_abs.paragraph_format.line_spacing = 1.15
    r_abs = p_abs.add_run(
        "Pelayanan penerimaan tamu di instansi pemerintah daerah, seperti Dinas Komunikasi, Informatika, Persandian, "
        "dan Statistik (Diskominfosantik) Kabupaten Bekasi, memiliki intensitas koordinasi yang tinggi dari berbagai pihak, "
        "mulai dari instansi perangkat daerah lain, mitra industri teknologi, insan pers, hingga masyarakat umum. "
        "Sistem buku tamu digital berbasis web konvensional yang ada saat ini masih menghadapi kendala operasional, "
        "yaitu kebingungan tamu dalam memilih bidang kedinasan yang sesuai dengan keperluannya serta keterbatasan petugas "
        "front office dalam merespons pertanyaan seputar status kunjungan, persyaratan berkas, kuota harian, dan jam operasional "
        "secara cepat dan fleksibel di luar jam kerja. Penelitian ini bertujuan merancang dan mengimplementasikan arsitektur "
        "Agent AI berbasis Natural Language Processing (NLP) yang terintegrasi secara mulus ke dalam platform "
        "Buku Tamu Digital berbasis Django dan WebSocket. Pendekatan yang diusulkan menggabungkan pemrosesan intent classification "
        "dan entity extraction untuk menganalisis teks percakapan tamu, modul rekomendasi disposisi bidang (rule-based semantic routing) "
        "yang memetakan keperluan tamu ke 6 divisi teknis (TIK, E-Government, Persandian, IKP, Statistik, dan Sekretariat), "
        "fitur conversational booking interaktif secara multi-turn, serta mekanisme hybrid human-handoff "
        "berbasis aturan toleransi kesalahan (3-strike fault tolerance) untuk mengalihkan sesi ke admin manusia apabila terdapat "
        "anomali atau komplain sensitif. Evaluasi sistem yang direncanakan mencakup pengujian performa algoritma NLP menggunakan "
        "confusion matrix (akurasi, presisi, recall, dan f1-score), pengukuran latensi waktu respons percakapan melalui "
        "protokol WebSocket, uji fungsional black-box, serta evaluasi tingkat penerimaan pengguna menggunakan metode "
        "System Usability Scale (SUS)."
    )
    r_abs.font.name = 'Times New Roman'
    r_abs.font.size = Pt(11)
    r_abs.font.italic = True

    p_kw = doc.add_paragraph()
    p_kw.paragraph_format.space_after = Pt(12)
    r_kw_lbl = p_kw.add_run("Kata kunci: ")
    r_kw_lbl.font.name = 'Times New Roman'
    r_kw_lbl.font.size = Pt(11)
    r_kw_lbl.font.bold = True
    r_kw_val = p_kw.add_run("Agent AI, Natural Language Processing, Buku Tamu Digital, Diskominfosantik Kabupaten Bekasi, Intent Classification, Human Handoff.")
    r_kw_val.font.name = 'Times New Roman'
    r_kw_val.font.size = Pt(11)
    r_kw_val.font.italic = True

    doc.add_page_break()

    # ═════════════════════════════════════════════════════════════════════════
    # 4. BAB I PENDAHULUAN
    # ═════════════════════════════════════════════════════════════════════════
    p_b1 = doc.add_paragraph()
    p_b1.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_b1.paragraph_format.space_before = Pt(0)
    p_b1.paragraph_format.space_after = Pt(12)
    p_b1.paragraph_format.line_spacing = 1.15
    r_b1 = p_b1.add_run("BAB I\nPENDAHULUAN")
    r_b1.font.name = 'Times New Roman'
    r_b1.font.size = Pt(14)
    r_b1.font.bold = True

    # 1.1 Latar Belakang Masalah
    p_11 = doc.add_paragraph()
    p_11.paragraph_format.space_before = Pt(6)
    p_11.paragraph_format.space_after = Pt(4)
    r_11 = p_11.add_run("1.1 Latar Belakang Masalah")
    r_11.font.name = 'Times New Roman'
    r_11.font.size = Pt(12)
    r_11.font.bold = True

    add_styled_paragraph(doc, 
        "Transformasi digital pada tata kelola pemerintahan di era Sistem Pemerintahan Berbasis Elektronik (SPBE) "
        "menuntut instansi publik untuk menyajikan pelayanan prima yang transparan, terukur, dan adaptif terhadap kemajuan teknologi. "
        "Dinas Komunikasi, Informatika, Persandian, dan Statistik (Diskominfosantik) Kabupaten Bekasi sebagai sentral tata kelola "
        "teknologi informasi dan komunikasi daerah memiliki tanggung jawab strategis dalam melayani beragam kunjungan dinas, "
        "koordinasi lintas perangkat daerah, audiensi media/pers, penyelesaian insiden keamanan siber, integrasi infrastruktur jaringan, "
        "hingga pengurusan administrasi akademik dan umum."
    )
    add_styled_paragraph(doc,
        "Pada implementasi lapangan, proses penerimaan dan pencatatan tamu yang masih mengandalkan buku tamu konvensional berbasis kertas "
        "terbukti memiliki banyak kelemahan sistematis, antara lain tingginya risiko kehilangan catatan, kesulitan pencarian riwayat (tracking), "
        "tidak adanya validasi identitas dan kuota harian, serta minimnya transparansi status konfirmasi dari pegawai yang dituju. "
        "Untuk mengatasi persoalan fisik tersebut, telah dikembangkan sistem Buku Tamu Digital berbasis web (Django framework). "
        "Namun demikian, evaluasi terhadap implementasi sistem web berbasis formulir isian statis menunjukkan adanya kendala baru di sisi "
        "pengalaman pengguna (user experience). Banyak tamu luar yang tidak memahami pembagian struktur organisasi dan tupoksi kedinasan "
        "di lingkungan Diskominfosantik Kabupaten Bekasi, sehingga kerap salah memilih bidang atau pegawai tujuan kunjungan "
        "(misalnya urusan aktivasi tanda tangan elektronik yang seharusnya ke Bidang Persandian keliru ditujukan ke Bidang E-Government atau TIK). "
        "Akibatnya, terjadi penolakan atau disposisi ulang secara manual yang memperpanjang waktu tunggu birokrasi."
    )
    add_styled_paragraph(doc,
        "Selain masalah penentuan bidang tujuan, beban kerja staf front office dan administrator sistem kerap terbebani oleh pertanyaan repetitif "
        "dari tamu terkait status persetujuan kunjungan, sisa kuota antrean harian, jadwal operasional kerja, lokasi rute gedung kantor di kompleks "
        "Pemkab Deltamas, hingga dokumen persyaratan yang wajib dibawa. Keterbatasan ketersediaan petugas manusia yang tidak dapat bersiaga penuh "
        "selama 24 jam menyebabkan banyak pesan dan kendala tamu tidak terespon secara real-time."
    )
    add_styled_paragraph(doc,
        "Perkembangan mutakhir dalam ranah Kecerdasan Buatan (Artificial Intelligence), khususnya Natural Language Processing (NLP) "
        "dan konsep Conversational Agent / Agent AI, membuka peluang besar untuk mengatasi hambatan tersebut. Agent AI memiliki "
        "kapabilitas memahami bahasa alami (natural language), mengenali maksud pengguna (intent classification), mengekstraksi entitas kunci "
        "(named entity recognition dan slot filling), serta mengambil tindakan prosedural pada basis data sistem secara otonom "
        "(tool-calling / transactional actions). Mengintegrasikan Agent AI berbasis NLP ke dalam platform Buku Tamu Digital memungkinkan sistem "
        "mengenali esensi keperluan tamu dari bahasa sehari-hari, merekomendasikan bidang kedinasan dan pegawai yang tepat secara presisi, memandu pendaftaran "
        "kunjungan langsung melalui antarmuka chat interaktif (conversational booking), serta secara cerdas mengalihkan komunikasi ke admin manusia "
        "(human handoff) ketika percakapan memerlukan penanganan petugas riil."
    )
    add_styled_paragraph(doc,
        "Oleh karena itu, penelitian rancangan ini disusun untuk memformulasikan, mengimplementasikan, dan menguji arsitektur Agent AI berbasis NLP "
        "yang adaptif dan tangguh pada Sistem Buku Tamu Digital Diskominfosantik Kabupaten Bekasi, guna mewujudkan efisiensi birokrasi dan "
        "peningkatan kualitas layanan publik yang modern."
    )

    # 1.2 Identifikasi dan Batasan Masalah
    p_12 = doc.add_paragraph()
    p_12.paragraph_format.space_before = Pt(8)
    p_12.paragraph_format.space_after = Pt(4)
    r_12 = p_12.add_run("1.2 Identifikasi dan Batasan Masalah")
    r_12.font.name = 'Times New Roman'
    r_12.font.size = Pt(12)
    r_12.font.bold = True

    add_styled_paragraph(doc, "Berdasarkan konteks latar belakang yang telah diuraikan, identifikasi masalah dirumuskan sebagai berikut:")
    id_points = [
        "Ketidaksesuaian Pemilihan Bidang dan Pegawai Tujuan: Tamu luar sering mengalami kesulitan memahami struktur pembagian tugas 6 divisi teknis Diskominfosantik, sehingga formulir pendaftaran kerap salah sasaran.",
        "Keterlambatan Respons Informasi Repetitif: Pertanyaan rutin mengenai status verifikasi tiket, sisa kuota harian, hari libur, dan berkas persyaratan membebani petugas loket front office.",
        "Kekakuan Antarmuka Formulir Web Statis: Pengisian form berbasis dropdown konvensional dirasa kaku dan kurang interaktif dibandingkan komunikasi percakapan alami.",
        "Risiko Bot Failure dan Halusinasi AI: Perlunya kontrol toleransi kesalahan sistem agar percakapan yang ambigu atau di luar kewenangan AI dapat dialihkan dengan aman ke petugas manusia."
    ]
    for pt in id_points:
        p_pt = doc.add_paragraph()
        p_pt.paragraph_format.left_indent = Inches(0.2)
        p_pt.paragraph_format.space_after = Pt(2)
        p_pt.paragraph_format.line_spacing = 1.15
        r_pt = p_pt.add_run(f"• {pt}")
        r_pt.font.name = 'Times New Roman'
        r_pt.font.size = Pt(12)

    add_styled_paragraph(doc, "Adapun batasan masalah dalam penelitian rancangan ini ditetapkan sebagai berikut:", space_before=4)
    bat_points = [
        "Objek penelitian difokuskan pada platform Buku Tamu Digital berbasis Django 5.x, Channels (ASGI Daphne), dan basis data MySQL di Diskominfosantik Kabupaten Bekasi.",
        "Rekomendasi otomatis dibatasi pada 6 divisi kedinasan: Bidang TIK, Bidang E-Government, Bidang Persandian, Bidang IKP, Bidang Statistik, dan Sekretariat Umum.",
        "Domain bahasa menggunakan Bahasa Indonesia dengan taksonomi 7 kategori intent: sapaan, cek_status_kunjungan, jadwal_kuota, info_layanan_dan_pegawai, buat_kunjungan, keluhan_dan_masukan, serta di_luar_konteks.",
        "Arsitektur agen menerapkan sistem hibrida dwi-jalur (n8n webhook orchestrator + mesin inferensi semantik lokal Django berkecepatan tinggi)."
    ]
    for pt in bat_points:
        p_pt = doc.add_paragraph()
        p_pt.paragraph_format.left_indent = Inches(0.2)
        p_pt.paragraph_format.space_after = Pt(2)
        p_pt.paragraph_format.line_spacing = 1.15
        r_pt = p_pt.add_run(f"• {pt}")
        r_pt.font.name = 'Times New Roman'
        r_pt.font.size = Pt(12)

    # 1.3 Rumusan Masalah dan Tujuan Penelitian
    p_13 = doc.add_paragraph()
    p_13.paragraph_format.space_before = Pt(8)
    p_13.paragraph_format.space_after = Pt(4)
    r_13 = p_13.add_run("1.3 Rumusan Masalah dan Tujuan Penelitian")
    r_13.font.name = 'Times New Roman'
    r_13.font.size = Pt(12)
    r_13.font.bold = True

    add_styled_paragraph(doc, "Rumusan masalah (Research Questions) dan tujuan penelitian (Research Objectives) diselaraskan secara berpasangan pada Tabel 1.1 berikut:")

    # Table 1.1
    t1 = doc.add_table(rows=1, cols=3)
    t1.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t1)

    hdr_cells = t1.rows[0].cells
    hdr_titles = ["Kode", "Rumusan Masalah (Research Questions)", "Tujuan Penelitian (Research Objectives)"]
    widths = [Inches(0.8), Inches(2.7), Inches(2.8)]
    for i, title in enumerate(hdr_titles):
        hdr_cells[i].width = widths[i]
        set_cell_background(hdr_cells[i], "0B2C56")
        set_cell_margins(hdr_cells[i], top=120, bottom=120, left=140, right=140)
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(title)
        r.font.name = 'Times New Roman'
        r.font.size = Pt(10.5)
        r.font.bold = True
        r.font.color.rgb = RGBColor(255, 255, 255)

    rq_rows = [
        ("RQ1", 
         "Bagaimana merancang model NLP (Intent Classification dan Entity Recognition) untuk memetakan keperluan kunjungan tamu ke bidang kedinasan dan pegawai yang tepat di Diskominfosantik Kabupaten Bekasi?",
         "Merancang algoritma NLP hibrida yang mampu mengklasifikasikan intent percakapan dan merekomendasikan divisi kedinasan secara akurat."),
        ("RQ2",
         "Bagaimana mengintegrasikan Agent AI ke dalam alur Conversational Booking pada sistem web Django berbasis WebSocket?",
         "Membangun modul percakapan interaktif multi-turn yang dapat memproses reservasi kunjungan, validasi kuota riil, dan pencatatan tiket langsung ke basis data secara real-time."),
        ("RQ3",
         "Bagaimana mekanisme hybrid human-handoff (aturan 3-strike toleransi kesalahan) dirancang untuk menangani kegagalan inferensi AI atau eskalasi komplain?",
         "Mengembangkan kontrol peralihan otomatis sesi chat dari bot ke admin manusia guna menjamin kepuasan layanan dan mitigasi kesalahan AI."),
        ("RQ4",
         "Bagaimana performa akurasi, waktu respons (latency), dan tingkat penerimaan pengguna terhadap sistem buku tamu ber-AI tersebut?",
         "Mengevaluasi kinerja komputasi melalui confusion matrix, analisis latensi transmisi WebSocket, serta pengujian kegunaan dengan System Usability Scale (SUS).")
    ]
    for kode, rq, ro in rq_rows:
        row_cells = t1.add_row().cells
        for idx, (cell, text) in enumerate(zip(row_cells, [kode, rq, ro])):
            cell.width = widths[idx]
            set_cell_margins(cell, top=100, bottom=100, left=140, right=140)
            p = cell.paragraphs[0]
            p.paragraph_format.line_spacing = 1.15
            p.paragraph_format.space_after = Pt(2)
            if idx == 0:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = p.add_run(text)
                r.font.bold = True
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                r = p.add_run(text)
            r.font.name = 'Times New Roman'
            r.font.size = Pt(10)

    # 1.4 Manfaat dan Kontribusi
    p_14 = doc.add_paragraph()
    p_14.paragraph_format.space_before = Pt(8)
    p_14.paragraph_format.space_after = Pt(4)
    r_14 = p_14.add_run("1.4 Manfaat dan Kontribusi yang Diharapkan")
    r_14.font.name = 'Times New Roman'
    r_14.font.size = Pt(12)
    r_14.font.bold = True

    add_styled_paragraph(doc,
        "Manfaat Teoritis (Akademis): Memberikan rujukan ilmiah mengenai implementasi arsitektur dwi-jalur "
        "(dual-engine) pada conversational agent pemerintahan daerah, yang menggabungkan otomasi alur kerja tingkat lanjut "
        "dengan mesin inferensi semantik lokal berlatensi rendah untuk menjamin ketersediaan sistem yang tinggi (high availability)."
    )
    add_styled_paragraph(doc,
        "Manfaat Praktis: Memberikan kemudahan bagi masyarakat dan tamu dinas dalam memesan kunjungan secara santai dan fleksibel "
        "melalui antarmuka obrolan, mengeliminasi kesalahan disposisi surat/kunjungan di 6 bidang kerja Diskominfosantik, "
        "serta meringankan beban administratif staf loket melalui otomatisasi layanan informasi rutin 24/7."
    )

    doc.add_page_break()

    # ═════════════════════════════════════════════════════════════════════════
    # 5. BAB II LANDASAN TEORI DAN KAJIAN PUSTAKA
    # ═════════════════════════════════════════════════════════════════════════
    p_b2 = doc.add_paragraph()
    p_b2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_b2.paragraph_format.space_before = Pt(0)
    p_b2.paragraph_format.space_after = Pt(12)
    p_b2.paragraph_format.line_spacing = 1.15
    r_b2 = p_b2.add_run("BAB II\nLANDASAN TEORI DAN KAJIAN PUSTAKA")
    r_b2.font.name = 'Times New Roman'
    r_b2.font.size = Pt(14)
    r_b2.font.bold = True

    # 2.1 Penelusuran dan Pemilihan Pustaka
    p_21 = doc.add_paragraph()
    p_21.paragraph_format.space_before = Pt(6)
    p_21.paragraph_format.space_after = Pt(4)
    r_21 = p_21.add_run("2.1 Penelusuran dan Pemilihan Pustaka")
    r_21.font.name = 'Times New Roman'
    r_21.font.size = Pt(12)
    r_21.font.bold = True

    add_styled_paragraph(doc,
        "Penelusuran pustaka dilakukan secara terstruktur pada pangkalan data ilmiah bereputasi, antara lain IEEE Xplore, "
        "ScienceDirect, ACM Digital Library, Google Scholar, dan Portal SINTA. Kata kunci dan strategi pencarian yang digunakan "
        "adalah: (\"Agent AI\" OR \"Conversational Agent\" OR \"Chatbot\") AND (\"Natural Language Processing\" OR \"Intent Classification\") "
        "AND (\"Guest Book\" OR \"Public Service Administration\")."
    )
    add_styled_paragraph(doc,
        "Pencarian dibatasi pada rentang tahun 2021 hingga 2026 guna memastikan kemutakhiran kajian. "
        "Kriteria inklusi mencakup artikel ilmiah yang mengkaji pemrosesan bahasa alami bahasa Indonesia, integrasi chatbot web real-time, "
        "dan arsitektur transaksional database. Kriteria eksklusi mencakup artikel yang tidak memiliki rincian metodologi komputasi "
        "atau hanya membahas antarmuka visual tanpa model NLP."
    )

    # 2.2 Tinjauan Penelitian Terkait
    p_22 = doc.add_paragraph()
    p_22.paragraph_format.space_before = Pt(8)
    p_22.paragraph_format.space_after = Pt(4)
    r_22 = p_22.add_run("2.2 Tinjauan Penelitian Terkait")
    r_22.font.name = 'Times New Roman'
    r_22.font.size = Pt(12)
    r_22.font.bold = True

    add_styled_paragraph(doc, "Tinjauan terhadap empat penelitian mutakhir yang mendasari rancangan ini dirangkum pada Tabel 2.1:")

    # Table 2.1
    t2 = doc.add_table(rows=1, cols=3)
    t2.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t2)

    hdr_cells2 = t2.rows[0].cells
    hdr_titles2 = ["Sumber & Penulis", "Masalah, Metode, dan Hasil", "Keterbatasan & Relevansi"]
    widths2 = [Inches(1.5), Inches(2.5), Inches(2.3)]
    for i, title in enumerate(hdr_titles2):
        hdr_cells2[i].width = widths2[i]
        set_cell_background(hdr_cells2[i], "0B2C56")
        set_cell_margins(hdr_cells2[i], top=120, bottom=120, left=140, right=140)
        p = hdr_cells2[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(title)
        r.font.name = 'Times New Roman'
        r.font.size = Pt(10.5)
        r.font.bold = True
        r.font.color.rgb = RGBColor(255, 255, 255)

    lit_rows = [
        ("Pratama & Wibowo (2023)\nJurnal RESTI, Vol. 7(2).",
         "Masalah: Lambatnya respons FAQ loket dinas sosial.\nMetode: Support Vector Machine (SVM) + TF-IDF.\nHasil: Akurasi klasifikasi 89,4% untuk 5 kelas FAQ.",
         "Keterbatasan: Chatbot hanya bersifat FAQ satu arah tanpa aksi ke database.\nRelevansi: Dasar klasifikasi intent teks bahasa Indonesia."),
        ("Suryanto et al. (2024)\nJurnal Rekayasa Sistem dan Tek. Inf., Vol. 8(1).",
         "Masalah: Buku tamu fisik rawan tercecer dan tanpa notifikasi.\nMetode: Web Django dan Webhook notifikasi.\nHasil: Rekapitulasi digital real-time dan tracking.",
         "Keterbatasan: Formulir dropdown manual tanpa asisten cerdas pemetaan bidang.\nRelevansi: Dasar skema database relasi buku tamu digital."),
        ("Zhang & Chen (2024)\nIEEE Access, Vol. 12.",
         "Masalah: Frustrasi pengguna akibat pengulangan bot saat gagal memahami konteks.\nMetode: Handoff bertingkat berbasis strike counter.\nHasil: Penurunan churn rate pengguna sebesar 41%.",
         "Keterbatasan: Diuji pada sistem e-commerce berbahasa Inggris.\nRelevansi: Landasan teoritis perancangan aturan 3-strike fault-tolerance handoff."),
        ("Nugroho & Santoso (2025)\nSNASTIK 2025.",
         "Masalah: Mahalnya server komputasi LLM mandiri di lingkungan Pemda.\nMetode: Orkestrasi workflow webhook n8n.\nHasil: Integrasi modular dan latensi rata-rata < 2 detik.",
         "Keterbatasan: Ketergantungan penuh pada server eksternal tanpa mesin fallback lokal.\nRelevansi: Mendasari arsitektur dwi-jalur webhook n8n + local engine.")
    ]
    for sbr, mth, rel in lit_rows:
        row_cells = t2.add_row().cells
        for idx, (cell, text) in enumerate(zip(row_cells, [sbr, mth, rel])):
            cell.width = widths2[idx]
            set_cell_margins(cell, top=100, bottom=100, left=140, right=140)
            p = cell.paragraphs[0]
            p.paragraph_format.line_spacing = 1.15
            p.paragraph_format.space_after = Pt(2)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            r = p.add_run(text)
            r.font.name = 'Times New Roman'
            r.font.size = Pt(9.5)

    # 2.3 Sintesis dan Celah Penelitian
    p_23 = doc.add_paragraph()
    p_23.paragraph_format.space_before = Pt(8)
    p_23.paragraph_format.space_after = Pt(4)
    r_23 = p_23.add_run("2.3 Sintesis dan Celah Penelitian (Research Gap)")
    r_23.font.name = 'Times New Roman'
    r_23.font.size = Pt(12)
    r_23.font.bold = True

    add_styled_paragraph(doc,
        "Analisis komparatif terhadap penelitian terdahulu menunjukkan bahwa sebagian besar penelitian buku tamu digital "
        "hanya berfokus pada digitalisasi formulir web konvensional tanpa adanya kecerdasan buatan untuk memandu disposisi kedinasan. "
        "Sementara itu, riset chatbot pelayanan publik umumnya berhenti pada tataran Information Retrieval (FAQ statis) "
        "tanpa terintegrasi langsung dengan mutasi transaksi basis data secara otonom (pemesanan tiket, pengurangan kuota riil, dan disposisi pegawai)."
    )
    add_styled_paragraph(doc,
        "Celah penelitian (research gap) yang diselesaikan dalam penelitian ini adalah: (1) Menghubungkan pemrosesan bahasa alami "
        "secara langsung dengan aksi transaksional basis data (conversational booking) berbasis multi-turn stateful cache; "
        "(2) Merancang arsitektur dwi-jalur (dual-engine) yang menjamin ketersediaan tinggi melalui mesin lokal berlatensi rendah (< 150 ms) "
        "apabila server orkestrasi eksternal mengalami gangguan; dan (3) Mengimplementasikan mekanisme pengalihan bertingkat (3-strike human handoff) "
        "melalui protokol real-time WebSocket tanpa memutuskan sesi percakapan pengguna."
    )

    # 2.4 Teori dan Kerangka Pemikiran
    p_24 = doc.add_paragraph()
    p_24.paragraph_format.space_before = Pt(8)
    p_24.paragraph_format.space_after = Pt(4)
    r_24 = p_24.add_run("2.4 Teori dan Kerangka Pemikiran")
    r_24.font.name = 'Times New Roman'
    r_24.font.size = Pt(12)
    r_24.font.bold = True

    add_styled_paragraph(doc,
        "Landasan konseptual mencakup teori Agent AI (Russell & Norvig, 2021) sebagai agen cerdas rasional berorientasi tujuan, "
        "Natural Language Processing (Jurafsky & Martin, 2024) untuk klasifikasi maksud dan ekstraksi entitas berbasis pola kata kunci, "
        "serta protokol asinkron Django Channels berbasis ASGI Daphne untuk komunikasi dupleks real-time. "
        "Hubungan logis antarbagian penelitian dipetakan dalam kerangka pemikiran pada Tabel 2.2:"
    )

    # Table 2.2
    t_frame = doc.add_table(rows=1, cols=2)
    t_frame.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t_frame)

    hdr_f = t_frame.rows[0].cells
    hdr_f_titles = ["Komponen Kerangka", "Deskripsi Penerapan pada Penelitian"]
    w_f = [Inches(1.8), Inches(4.5)]
    for i, title in enumerate(hdr_f_titles):
        hdr_f[i].width = w_f[i]
        set_cell_background(hdr_f[i], "0B2C56")
        set_cell_margins(hdr_f[i], top=120, bottom=120, left=140, right=140)
        p = hdr_f[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(title)
        r.font.name = 'Times New Roman'
        r.font.size = Pt(10.5)
        r.font.bold = True
        r.font.color.rgb = RGBColor(255, 255, 255)

    f_rows = [
        ("Masalah Operasional & Riset", "Tamu bingung memilih bidang dinas; pertanyaan berulang menumpuk di front desk; antarmuka form kaku; risiko kebuntuan bot AI saat menangani pesan ambigu."),
        ("Landasan Teori & Teknologi", "Agent AI Decision Systems, Natural Language Processing (Intent & Entity Extraction), Framework Django 5 Channels (ASGI WebSocket), dan Fault-Tolerant Human-in-the-Loop."),
        ("Pendekatan Solusi / Metode", "Arsitektur dwi-jalur (n8n AI Webhook + Local Semantic Engine Fallback), pemetaan semantik 6 bidang Diskominfosantik, multi-turn conversational booking, dan 3-strike auto handoff."),
        ("Metode Evaluasi Hasil", "Confusion Matrix (Accuracy, Precision, Recall, F1-Score), uji latensi WebSocket bolak-balik, pengujian fungsional Black Box, dan evaluasi kepuasan System Usability Scale (SUS).")
    ]
    for comp, desc in f_rows:
        row_cells = t_frame.add_row().cells
        for idx, (cell, text) in enumerate(zip(row_cells, [comp, desc])):
            cell.width = w_f[idx]
            set_cell_margins(cell, top=100, bottom=100, left=140, right=140)
            p = cell.paragraphs[0]
            p.paragraph_format.line_spacing = 1.15
            p.paragraph_format.space_after = Pt(2)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            r = p.add_run(text)
            r.font.name = 'Times New Roman'
            r.font.size = Pt(10)
            if idx == 0:
                r.font.bold = True

    doc.add_page_break()

    # ═════════════════════════════════════════════════════════════════════════
    # 6. BAB III METODE DAN TAHAPAN PENELITIAN
    # ═════════════════════════════════════════════════════════════════════════
    p_b3 = doc.add_paragraph()
    p_b3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_b3.paragraph_format.space_before = Pt(0)
    p_b3.paragraph_format.space_after = Pt(12)
    p_b3.paragraph_format.line_spacing = 1.15
    r_b3 = p_b3.add_run("BAB III\nMETODE DAN TAHAPAN PENELITIAN")
    r_b3.font.name = 'Times New Roman'
    r_b3.font.size = Pt(14)
    r_b3.font.bold = True

    # 3.1 Desain Penelitian
    p_31 = doc.add_paragraph()
    p_31.paragraph_format.space_before = Pt(6)
    p_31.paragraph_format.space_after = Pt(4)
    r_31 = p_31.add_run("3.1 Desain Penelitian dan Dasar Berpikir Ilmiah")
    r_31.font.name = 'Times New Roman'
    r_31.font.size = Pt(12)
    r_31.font.bold = True

    add_styled_paragraph(doc,
        "Penelitian ini menerapkan Design Science Research Methodology (DSRM) yang berorientasi pada perancangan dan evaluasi "
        "artefak teknologi komputasi guna memecahkan masalah praktis pada instansi pelayanan publik. "
        "Unit pengamatan meliputi teks percakapan masukan tamu, waktu respons transmisi sistem, serta status transaksi pada basis data. "
        "Asumsi penelitian mengasumsikan masukan teks menggunakan bahasa Indonesia yang lazim serta ketersediaan koneksi database MySQL lokal yang stabil."
    )

    # 3.2 Pengumpulan Data
    p_32 = doc.add_paragraph()
    p_32.paragraph_format.space_before = Pt(8)
    p_32.paragraph_format.space_after = Pt(4)
    r_32 = p_32.add_run("3.2 Pengumpulan dan Pengolahan Awal Data")
    r_32.font.name = 'Times New Roman'
    r_32.font.size = Pt(12)
    r_32.font.bold = True

    add_styled_paragraph(doc,
        "Data primer diperoleh dari struktur organisasi resmi Diskominfosantik Kabupaten Bekasi (tupoksi 6 bidang, daftar pejabat/pegawai aktif, "
        "dan konfigurasi kuota operasional kalender), serta korpus uji 210 kalimat percakapan tamu. "
        "Tahapan prapemrosesan teks mencakup: (1) Case folding menjadi huruf kecil; (2) Trimming dan pembersihan spasi/tanda baca berlebih; "
        "dan (3) Ekstraksi pola entitas waktu/tanggal menggunakan RegEx. "
        "Untuk kepatuhan terhadap UU No. 27 Tahun 2022 tentang Pelindungan Data Pribadi, identitas pribadi tamu (NIK dan nomor telepon) "
        "disamarkan (masked) dalam catatan log cache sesi."
    )

    # 3.3 Metode atau Model yang Diusulkan
    p_33 = doc.add_paragraph()
    p_33.paragraph_format.space_before = Pt(8)
    p_33.paragraph_format.space_after = Pt(4)
    r_33 = p_33.add_run("3.3 Metode atau Model yang Diusulkan")
    r_33.font.name = 'Times New Roman'
    r_33.font.size = Pt(12)
    r_33.font.bold = True

    add_styled_paragraph(doc, "Arsitektur Agent AI yang diusulkan terdiri dari 4 subsistem yang saling terintegrasi:")
    arch_points = [
        "Dual-Engine Coordinator: Setiap pesan chat tamu yang masuk melalui ChatConsumer WebSocket dikirimkan ke webhook n8n AI orkestrator (dengan batas waktu tunggu 5 detik). Jika webhook mengalami kegagalan, timeout, atau offline, sistem secara otomatis mengeksekusi mesin inferensi lokal _detect_user_intent_locally tanpa gangguan pada antarmuka tamu.",
        "Topic & Entity Routing (6 Bidang): Fungsi recommend_pegawai_by_purpose menganalisis semantik keperluan tamu dan memetakan ke bidang dinas yang relevan: Bidang TIK (jaringan/server/wifi), Bidang E-Government (aplikasi/web/SPBE), Bidang Persandian (keamanan siber/TTE), Bidang IKP (humas/media/liputan), Bidang Statistik (data sektoral/survei), dan Sekretariat (magang/surat/arsip).",
        "Multi-turn Conversational Booking: Melalui fungsi _try_create_kunjungan_from_chat, AI menangkap entitas tanggal dan jam, memvalidasi kuota harian, menyimpan draf percakapan di cache sesi, dan secara otomatis menerbitkan tiket kunjungan resmi ke database.",
        "Mekanisme 3-Strike Auto Handoff: Apabila masukan berada di luar konteks atau pengguna menyampaikan komplain ketidakpuasan, nilai ai_strike_count bertambah. Jika mencapai 3 strike, sesi dialihkan ke admin manusia (set_session_handoff_to_admin(True)) dan notifikasi alert dikirimkan ke dashboard admin."
    ]
    for pt in arch_points:
        p_pt = doc.add_paragraph()
        p_pt.paragraph_format.left_indent = Inches(0.2)
        p_pt.paragraph_format.space_after = Pt(3)
        p_pt.paragraph_format.line_spacing = 1.15
        r_pt = p_pt.add_run(f"• {pt}")
        r_pt.font.name = 'Times New Roman'
        r_pt.font.size = Pt(12)

    # 3.4 Rencana Pengujian
    p_34 = doc.add_paragraph()
    p_34.paragraph_format.space_before = Pt(8)
    p_34.paragraph_format.space_after = Pt(4)
    r_34 = p_34.add_run("3.4 Rencana Pengujian, Evaluasi, dan Validasi")
    r_34.font.name = 'Times New Roman'
    r_34.font.size = Pt(12)
    r_34.font.bold = True

    add_styled_paragraph(doc,
        "Rencana evaluasi sistem mencakup empat metode pengujian: (1) Pengujian akurasi klasifikasi intent dengan Confusion Matrix "
        "(Accuracy, Precision, Recall, F1-Score); (2) Uji waktu respons bolak-balik (round-trip latency) melalui protokol WebSocket "
        "dengan target < 150 ms (lokal) dan < 2.000 ms (webhook); (3) Uji fungsional Black Box untuk validasi skenario reservasi dan hari libur; "
        "serta (4) Pengujian penerimaan pengguna menggunakan instrumen baku System Usability Scale (SUS) kepada 20 responden dengan target skor >= 75."
    )

    add_styled_paragraph(doc, "Alur tahapan pelaksanaan penelitian dirangkum pada Tabel 3.1 berikut:")

    # Table 3.1
    t_stages = doc.add_table(rows=1, cols=3)
    t_stages.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t_stages)

    hdr_s = t_stages.rows[0].cells
    hdr_s_titles = ["Tahap", "Aktivitas Penelitian", "Target / Luaran Capaian"]
    w_s = [Inches(0.7), Inches(2.8), Inches(2.8)]
    for i, title in enumerate(hdr_s_titles):
        hdr_s[i].width = w_s[i]
        set_cell_background(hdr_s[i], "0B2C56")
        set_cell_margins(hdr_s[i], top=120, bottom=120, left=140, right=140)
        p = hdr_s[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(title)
        r.font.name = 'Times New Roman'
        r.font.size = Pt(10.5)
        r.font.bold = True
        r.font.color.rgb = RGBColor(255, 255, 255)

    stages_data = [
        ("1", "Identifikasi Masalah & Studi Kasus Diskominfosantik", "Rumusan masalah RQ1–RQ4 dan batasan riset terdefinisi jelas."),
        ("2", "Kajian Pustaka & Penentuan Research Gap", "Kompilasi pustaka ilmiah terindeks dan penegasan celah riset."),
        ("3", "Pengumpulan Data Tupoksi & Korpus Uji", "Dataset 6 divisi kedinasan dan 210 kalimat percakapan uji."),
        ("4", "Perancangan Arsitektur Agent AI & Model NLP", "Bagan alur dual-engine, aturan routing, dan logika booking cerdas."),
        ("5", "Implementasi Sistem pada Django & Channels", "Integrasi kode consumers.py, utils.py, dan konfigurasi webhook n8n."),
        ("6", "Pengujian Fungsional, Akurasi & Latensi", "Data matriks konfusi intent, log latensi WebSocket, hasil black box."),
        ("7", "Evaluasi Penerimaan Pengguna (SUS)", "Skor kegunaan (usability score) dari 20 responden pengguna."),
        ("8", "Sintesis Pembahasan & Penyusunan Laporan", "Laporan penelitian ilmiah utuh beserta rekomendasi lanjutan.")
    ]
    for no, act, out in stages_data:
        row_cells = t_stages.add_row().cells
        for idx, (cell, text) in enumerate(zip(row_cells, [no, act, out])):
            cell.width = w_s[idx]
            set_cell_margins(cell, top=100, bottom=100, left=140, right=140)
            p = cell.paragraphs[0]
            p.paragraph_format.line_spacing = 1.15
            p.paragraph_format.space_after = Pt(2)
            if idx == 0:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = p.add_run(text)
                r.font.bold = True
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                r = p.add_run(text)
            r.font.name = 'Times New Roman'
            r.font.size = Pt(10)

    doc.add_page_break()

    # ═════════════════════════════════════════════════════════════════════════
    # 7. KERANGKA HASIL PEMBAHASAN DAN PENUTUP
    # ═════════════════════════════════════════════════════════════════════════
    p_b4 = doc.add_paragraph()
    p_b4.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_b4.paragraph_format.space_before = Pt(0)
    p_b4.paragraph_format.space_after = Pt(12)
    p_b4.paragraph_format.line_spacing = 1.15
    r_b4 = p_b4.add_run("KERANGKA HASIL PEMBAHASAN DAN PENUTUP")
    r_b4.font.name = 'Times New Roman'
    r_b4.font.size = Pt(14)
    r_b4.font.bold = True

    # Rencana Bab IV
    p_41 = doc.add_paragraph()
    p_41.paragraph_format.space_before = Pt(6)
    p_41.paragraph_format.space_after = Pt(4)
    r_41 = p_41.add_run("Rencana Bab IV Hasil dan Pembahasan")
    r_41.font.name = 'Times New Roman'
    r_41.font.size = Pt(12)
    r_41.font.bold = True

    add_styled_paragraph(doc,
        "Hasil: Rencana keluaran yang akan disajikan meliputi tabel Confusion Matrix 7 kelas intent, "
        "tabel persentase akurasi pemetaan 6 bidang kerja Diskominfosantik, grafik perbandingan latensi waktu respons "
        "(Local Engine vs N8N Webhook), rekaman log transaksional penerbitan tiket via obrolan, bukti transisi 3-strike handoff, "
        "serta skor rata-rata kuesioner System Usability Scale (SUS)."
    )
    add_styled_paragraph(doc,
        "Pembahasan: Data hasil pengujian akan dianalisis untuk menjawab rumusan masalah secara objektif, "
        "menjelaskan faktor penyebab misklasifikasi pada kalimat ambigu, membandingkan performa latensi terhadap baku mutu interaksi web, "
        "serta mengevaluasi keterbatasan arsitektur saat dioperasikan pada beban puncak pengguna."
    )

    add_styled_paragraph(doc, "Rencana pemetaan bukti dan pembahasan terhadap pertanyaan penelitian ditunjukkan pada Tabel 4.1:")

    # Table 4.1
    t_rq4 = doc.add_table(rows=1, cols=3)
    t_rq4.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t_rq4)

    hdr_4 = t_rq4.rows[0].cells
    hdr_4_titles = ["Pertanyaan Penelitian", "Bukti yang Diperlukan", "Cara Menilai atau Membahas"]
    w_4 = [Inches(1.5), Inches(2.4), Inches(2.4)]
    for i, title in enumerate(hdr_4_titles):
        hdr_4[i].width = w_4[i]
        set_cell_background(hdr_4[i], "0B2C56")
        set_cell_margins(hdr_4[i], top=120, bottom=120, left=140, right=140)
        p = hdr_4[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(title)
        r.font.name = 'Times New Roman'
        r.font.size = Pt(10.5)
        r.font.bold = True
        r.font.color.rgb = RGBColor(255, 255, 255)

    rq4_data = [
        ("RQ1: Akurasi NLP & Routing Bidang", "Data matriks konfusi intent dan tabel ketepatan rekomendasi 6 bidang kerja.", "Menghitung F1-score tiap kelas; menganalisis penyebab misklasifikasi pada kalimat ambigu; membandingkan capaian terhadap target minimal 85%."),
        ("RQ2: Conversational Booking WebSocket", "Log transaksi tabel Kunjungan dan waktu pemotongan kuota real-time.", "Memverifikasi integritas slot-filling (tanggal, jam, keperluan) dan memastikan tidak ada race condition pada kuota harian."),
        ("RQ3: Keandalan 3-Strike Auto Handoff", "Log penambahan nilai counter ai_strike_count dan status ai_handoff_active.", "Menguji ketepatan pengalihan pada strike ke-3; mengevaluasi waktu respons admin manusia dalam mengambil alih percakapan."),
        ("RQ4: Latensi Respons & Usability (SUS)", "Data latensi transmisi (ms) dan rekapitulasi kuesioner SUS dari 20 responden.", "Membandingkan latensi terhadap standar responsif web (< 1 detik); mengonversi skor rata-rata SUS ke persentil acceptability.")
    ]
    for q, b, c in rq4_data:
        row_cells = t_rq4.add_row().cells
        for idx, (cell, text) in enumerate(zip(row_cells, [q, b, c])):
            cell.width = w_4[idx]
            set_cell_margins(cell, top=100, bottom=100, left=140, right=140)
            p = cell.paragraphs[0]
            p.paragraph_format.line_spacing = 1.15
            p.paragraph_format.space_after = Pt(2)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            r = p.add_run(text)
            r.font.name = 'Times New Roman'
            r.font.size = Pt(10)
            if idx == 0:
                r.font.bold = True

    # Rencana Bab V
    p_51 = doc.add_paragraph()
    p_51.paragraph_format.space_before = Pt(8)
    p_51.paragraph_format.space_after = Pt(4)
    r_51 = p_51.add_run("Rencana Bab V Kesimpulan dan Saran")
    r_51.font.name = 'Times New Roman'
    r_51.font.size = Pt(12)
    r_51.font.bold = True

    add_styled_paragraph(doc,
        "Kesimpulan: Kesimpulan nantinya akan ditarik secara tegas untuk menjawab rumusan masalah dan tujuan: "
        "(1) Sejauh mana model NLP mampu memetakan keperluan pengunjung ke divisi teknis Diskominfosantik; "
        "(2) Keterandalan fitur conversational booking dalam menerbitkan tiket kunjungan mandiri; "
        "(3) Keberhasilan mekanisme toleransi kesalahan 3-strike dalam mencegah kebuntuan bot; dan "
        "(4) Pencapaian metrik komputasi latensi dan tingkat kepuasan pengguna akhir."
    )
    add_styled_paragraph(doc,
        "Saran: Saran tindak lanjut diarahkan pada: (1) Integrasi model Large Language Model (LLM) on-premise (seperti Llama-3 lokal) "
        "guna menjamin kedaulatan data pemerintahan tanpa bergantung pada API eksternal; (2) Penerapan fitur Optical Character Recognition (OCR) "
        "untuk pembacaan foto KTP otomatis via chat; dan (3) Penambahan modul Speech-to-Text untuk aksesibilitas anjungan tamu mandiri."
    )

    # Pemeriksaan Konsistensi
    p_kons = doc.add_paragraph()
    p_kons.paragraph_format.space_before = Pt(8)
    p_kons.paragraph_format.space_after = Pt(4)
    r_kons = p_kons.add_run("Pemeriksaan Konsistensi Penelitian")
    r_kons.font.name = 'Times New Roman'
    r_kons.font.size = Pt(12)
    r_kons.font.bold = True

    add_styled_paragraph(doc,
        "Verifikasi konsistensi telah dipastikan: Objek penelitian pada judul konsisten dengan latar belakang dan fokus studi kasus di Diskominfosantik Kabupaten Bekasi; "
        "seluruh rumusan masalah (RQ1–RQ4) terhubung tepat dengan tujuan penelitian, tahapan metode di Bab III, serta rencana pembuktian di Bab IV."
    )

    doc.add_page_break()

    # ═════════════════════════════════════════════════════════════════════════
    # 8. DAFTAR PUSTAKA
    # ═════════════════════════════════════════════════════════════════════════
    p_dp = doc.add_paragraph()
    p_dp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_dp.paragraph_format.space_before = Pt(0)
    p_dp.paragraph_format.space_after = Pt(12)
    p_dp.paragraph_format.line_spacing = 1.15
    r_dp = p_dp.add_run("DAFTAR PUSTAKA")
    r_dp.font.name = 'Times New Roman'
    r_dp.font.size = Pt(14)
    r_dp.font.bold = True

    references = [
        "Brooke, J. (1996). SUS: A 'quick and dirty' usability scale. Usability Evaluation in Industry, 189(194), 4–7.",
        "Jurafsky, D., & Martin, J. H. (2024). Speech and Language Processing: An Introduction to Natural Language Processing, Computational Linguistics, and Speech Recognition (3rd ed. draft). Stanford University.",
        "Kementerian Komunikasi dan Informatika Republik Indonesia. (2022). Peraturan Presiden Nomor 95 Tahun 2018 tentang Sistem Pemerintahan Berbasis Elektronik (SPBE). Lembaran Negara RI.",
        "Nugroho, K., & Santoso, B. (2025). Penerapan Workflow Automation n8n dan LLM untuk Layanan Aduan Masyarakat Berbasis Real-time Messaging. Seminar Nasional Teknologi Informasi dan Komunikasi (SNASTIK 2025), 112–120.",
        "Pratama, R., & Wibowo, A. (2023). Implementasi Chatbot Layanan Informasi Publik Berbasis NLP Menggunakan Algoritma Support Vector Machine. Jurnal RESTI (Rekayasa Sistem dan Teknologi Informasi), 7(2), 312–319. https://doi.org/10.29207/resti.v7i2.4851",
        "Republik Indonesia. (2022). Undang-Undang Republik Indonesia Nomor 27 Tahun 2022 tentang Pelindungan Data Pribadi. Lembaran Negara RI Tahun 2022 Nomor 196.",
        "Russell, S., & Norvig, P. (2021). Artificial Intelligence: A Modern Approach (4th ed.). Pearson Education.",
        "Suryanto, E., Hidayat, T., & Nugroho, A. (2024). Sistem Informasi Buku Tamu Digital Berbasis Web Terintegrasi Notifikasi Real-time pada Instansi Pemerintahan. Jurnal Rekayasa Sistem dan Teknologi Informasi, 8(1), 45–53.",
        "Zhang, L., & Chen, H. (2024). Design of Hybrid Conversational Agent Architecture with Seamless Human-in-the-Loop Handoff. IEEE Access, 12, 14205–14217. https://doi.org/10.1109/ACCESS.2024.3359012"
    ]
    for ref in references:
        p_ref = doc.add_paragraph()
        p_ref.paragraph_format.left_indent = Inches(0.4)
        p_ref.paragraph_format.first_line_indent = Inches(-0.4)
        p_ref.paragraph_format.space_after = Pt(4)
        p_ref.paragraph_format.line_spacing = 1.15
        p_ref.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        r_ref = p_ref.add_run(ref)
        r_ref.font.name = 'Times New Roman'
        r_ref.font.size = Pt(11)

    doc.add_page_break()

    # ═════════════════════════════════════════════════════════════════════════
    # 9. LAMPIRAN
    # ═════════════════════════════════════════════════════════════════════════
    p_lp = doc.add_paragraph()
    p_lp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_lp.paragraph_format.space_before = Pt(0)
    p_lp.paragraph_format.space_after = Pt(12)
    p_lp.paragraph_format.line_spacing = 1.15
    r_lp = p_lp.add_run("LAMPIRAN")
    r_lp.font.name = 'Times New Roman'
    r_lp.font.size = Pt(14)
    r_lp.font.bold = True

    # Lampiran A
    p_la = doc.add_paragraph()
    p_la.paragraph_format.space_before = Pt(6)
    p_la.paragraph_format.space_after = Pt(4)
    r_la = p_la.add_run("Lampiran A: Taksonomi Intent dan Matriks Routing 6 Bidang Diskominfosantik")
    r_la.font.name = 'Times New Roman'
    r_la.font.size = Pt(12)
    r_la.font.bold = True

    t_la = doc.add_table(rows=1, cols=4)
    t_la.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t_la)

    hdr_la = t_la.rows[0].cells
    hdr_la_t = ["Kode", "Bidang Kedinasan", "Kata Kunci Pemetaan Semantik (NLP)", "Rekomendasi Jabatan"]
    w_la = [Inches(0.6), Inches(1.8), Inches(2.2), Inches(1.7)]
    for i, title in enumerate(hdr_la_t):
        hdr_la[i].width = w_la[i]
        set_cell_background(hdr_la[i], "0B2C56")
        set_cell_margins(hdr_la[i], top=100, bottom=100, left=120, right=120)
        p = hdr_la[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(title)
        r.font.name = 'Times New Roman'
        r.font.size = Pt(10)
        r.font.bold = True
        r.font.color.rgb = RGBColor(255, 255, 255)

    la_rows = [
        ("TIK", "Teknologi Informasi & Komunikasi", "Jaringan, internet, wifi, fo, fiber optik, server, router, cctv, lan.", "Administrator Jaringan, Teknisi Infrastruktur."),
        ("E-GOV", "Penyelenggaraan E-Government", "Aplikasi, website, web, spbe, software, database, domain, api, superapp.", "Kepala Bidang E-Gov, Analis Sistem Informasi."),
        ("SANDI", "Persandian & Keamanan Informasi", "Persandian, sandi, keamanan siber, cyber, enkripsi, tte, sertifikat elektronik, csirt.", "Analis Keamanan Siber, Kepala Bidang Persandian."),
        ("IKP", "Informasi & Komunikasi Publik", "Berita, liputan, media, pers, wartawan, humas, publikasi, ppid, rilis.", "Pengelola Informasi Publik, Penyusun Konten Media."),
        ("STAT", "Statistik Sektoral", "Statistik, data, survei, sensus, satu data, sdi, metadata, data sektoral.", "Statistisi Ahli Pertama, Pengolah Data Statistik."),
        ("SEKRE", "Sekretariat Umum", "Magang, pkl, penelitian, skripsi, surat disposisi, kepegawaian, berkas arsip.", "Pengadministrasi Umum, Pengelola Kepegawaian.")
    ]
    for c1, c2, c3, c4 in la_rows:
        row_cells = t_la.add_row().cells
        for idx, (cell, text) in enumerate(zip(row_cells, [c1, c2, c3, c4])):
            cell.width = w_la[idx]
            set_cell_margins(cell, top=80, bottom=80, left=120, right=120)
            p = cell.paragraphs[0]
            p.paragraph_format.line_spacing = 1.15
            p.paragraph_format.space_after = Pt(2)
            if idx == 0:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = p.add_run(text)
                r.font.bold = True
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                r = p.add_run(text)
            r.font.name = 'Times New Roman'
            r.font.size = Pt(9.5)

    # Lampiran B
    p_lb = doc.add_paragraph()
    p_lb.paragraph_format.space_before = Pt(10)
    p_lb.paragraph_format.space_after = Pt(4)
    r_lb = p_lb.add_run("Lampiran B: Matriks Skenario Pengujian Fungsional Black Box Agent AI")
    r_lb.font.name = 'Times New Roman'
    r_lb.font.size = Pt(12)
    r_lb.font.bold = True

    t_lb = doc.add_table(rows=1, cols=4)
    t_lb.alignment = WD_TABLE_ALIGNMENT.CENTER
    set_table_borders(t_lb)

    hdr_lb = t_lb.rows[0].cells
    hdr_lb_t = ["ID Uji", "Skenario Pengujian", "Masukan Uji (Input Utterance)", "Hasil yang Diharapkan"]
    w_lb = [Inches(0.7), Inches(1.8), Inches(1.8), Inches(2.0)]
    for i, title in enumerate(hdr_lb_t):
        hdr_lb[i].width = w_lb[i]
        set_cell_background(hdr_lb[i], "0B2C56")
        set_cell_margins(hdr_lb[i], top=100, bottom=100, left=120, right=120)
        p = hdr_lb[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        r = p.add_run(title)
        r.font.name = 'Times New Roman'
        r.font.size = Pt(10)
        r.font.bold = True
        r.font.color.rgb = RGBColor(255, 255, 255)

    lb_rows = [
        ("TC-01", "Deteksi Sapaan Ramah", "Halo selamat pagi kak", "Balasan ramah & penawaran menu bantuan tanpa menambah strike counter."),
        ("TC-02", "Rekomendasi Bidang Persandian (TTE)", "Saya mau konsultasi aktivasi Tanda Tangan Elektronik (TTE)", "Rekomendasi diarahkan ke Bidang Persandian & jabatan Analis Keamanan Siber."),
        ("TC-03", "Validasi Hari Libur Akhir Pekan", "Apakah hari Sabtu besok kantor buka?", "Informasi bahwa Sabtu/Minggu tutup; jadwal kerja resmi Senin–Jumat 08:00–16:00 WIB."),
        ("TC-04", "Conversational Booking Multi-turn", "Daftarkan kunjungan besok -> Jam 10 koordinasi SPBE", "AI menyimpan draf tanggal di cache, validasi kuota, dan menerbitkan kode tiket resmi."),
        ("TC-05", "3-Strike Auto Handoff ke Admin", "3x masukan di luar konteks berturut-turut (resep kue, lagi apa, tidak jelas)", "Sistem mencatat strike ke-3, mengunci bot, dan mengalihkan sesi chat langsung ke admin manusia.")
    ]
    for c1, c2, c3, c4 in lb_rows:
        row_cells = t_lb.add_row().cells
        for idx, (cell, text) in enumerate(zip(row_cells, [c1, c2, c3, c4])):
            cell.width = w_lb[idx]
            set_cell_margins(cell, top=80, bottom=80, left=120, right=120)
            p = cell.paragraphs[0]
            p.paragraph_format.line_spacing = 1.15
            p.paragraph_format.space_after = Pt(2)
            if idx == 0:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
                r = p.add_run(text)
                r.font.bold = True
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                r = p.add_run(text)
            r.font.name = 'Times New Roman'
            r.font.size = Pt(9.5)

    doc.save(output_filename)
    print(f"SUCCESS: DOCX generated successfully at '{output_filename}'")

if __name__ == "__main__":
    create_docx_report()

