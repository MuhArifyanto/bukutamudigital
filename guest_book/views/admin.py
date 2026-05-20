# Dummy comment to trigger server reload
import csv, json as _json, calendar as _cal
from datetime import datetime, timedelta, time
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponse
from django.db.models import Count, Q, Max
from django.core.paginator import Paginator

from .base import admin_login_required, get_admin_context
from ..models import (
    Tamu, Kunjungan, Pegawai, Message, Instansi, Departemen, 
    Notification, CalendarSettings
)

@admin_login_required
def admin_kunjungan_detail_view(request, pk):
    """View untuk detail kunjungan di sisi Admin"""
    kunjungan = get_object_or_404(Kunjungan, pk=pk)
    status_history = kunjungan.status_history.order_by('changed_at')
    notes_list = kunjungan.notes_history.order_by('created_at')

    ctx = get_admin_context(request)
    ctx.update({
        'kunjungan': kunjungan,
        'status_history': status_history,
        'notes_list': notes_list,
        'active_page': 'kunjungan',
    })
    return render(request, 'guest_book/admin_kunjungan_detail.html', ctx)

@admin_login_required
def admin_cetak_kartu_view(request, pk):
    """View untuk mencetak kartu pengunjung"""
    kunjungan = get_object_or_404(Kunjungan, pk=pk)
    
    # Hitung nomor urut untuk hari tersebut
    from django.db.models import Q
    
    arrival_date = kunjungan.arrival_time.date()
    start_of_day = timezone.make_aware(datetime.combine(arrival_date, time.min))
    end_of_day = timezone.make_aware(datetime.combine(arrival_date, time.max))
    
    count = Kunjungan.objects.filter(
        arrival_time__range=(start_of_day, end_of_day)
    ).filter(
        Q(arrival_time__lt=kunjungan.arrival_time) | Q(arrival_time=kunjungan.arrival_time, id__lt=kunjungan.id)
    ).count() + 1
    
    nomor_urut = f"{count:02d}"
    nomor_unik = str(kunjungan.id)[:8].upper()
    
    from ..models import Instansi
    instansi = Instansi.objects.first()
    
    context = get_admin_context(request)
    context.update({
        'kunjungan': kunjungan,
        'nomor_urut': nomor_urut,
        'nomor_unik': nomor_unik,
        'instansi': instansi,
    })
    return render(request, 'guest_book/admin_cetak_kartu.html', context)

@admin_login_required
def admin_dashboard_view(request):
    """View untuk Dashboard Utama Admin"""
    now = timezone.localtime(timezone.now())
    today = now.date()

    # Statistik Dasar
    total_tamu          = Tamu.objects.count()
    
    start_of_today = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    end_of_today = timezone.make_aware(datetime.combine(today, datetime.max.time()))
    
    kunjungan_hari_ini  = Kunjungan.objects.filter(arrival_time__range=(start_of_today, end_of_today)).count()
    menunggu_verifikasi = Kunjungan.objects.filter(status='pending').count()

    # Growth: hari ini vs kemarin
    kemarin = today - timedelta(days=1)
    start_of_kemarin = timezone.make_aware(datetime.combine(kemarin, datetime.min.time()))
    end_of_kemarin = timezone.make_aware(datetime.combine(kemarin, datetime.max.time()))
    kunjungan_kemarin = Kunjungan.objects.filter(arrival_time__range=(start_of_kemarin, end_of_kemarin)).count()
    
    growth_pct = 0
    if kunjungan_kemarin > 0:
        growth_pct = round(((kunjungan_hari_ini - kunjungan_kemarin) / kunjungan_kemarin) * 100)
    elif kunjungan_hari_ini > 0:
        growth_pct = 100
        
    # Permintaan user: jika -100% ubah menjadi 0%
    if growth_pct == -100:
        growth_pct = 0

    # Riwayat Terbaru
    k_status = request.GET.get('k_status', 'all')
    k_sort   = request.GET.get('k_sort', '-arrival_time')
    riwayat_query = Kunjungan.objects.select_related('tamu', 'pegawai')
    if k_status != 'all':
        riwayat_query = riwayat_query.filter(status=k_status)
    riwayat_terbaru = riwayat_query.order_by(k_sort)[:10]

    # Chart Data
    chart_range = request.GET.get('range', '7')
    labels, values, prev_values, visitor_values = [], [], [], []

    if chart_range == '30':
        for i in range(29, -1, -1):
            day = now - timedelta(days=i)
            day_date = day.date()
            prev_day_date = day_date - timedelta(days=30)
            
            s_day = timezone.make_aware(datetime.combine(day_date, datetime.min.time()))
            e_day = timezone.make_aware(datetime.combine(day_date, datetime.max.time()))
            
            s_prev = timezone.make_aware(datetime.combine(prev_day_date, datetime.min.time()))
            e_prev = timezone.make_aware(datetime.combine(prev_day_date, datetime.max.time()))
            
            labels.append(day.strftime('%d %b') if i % 5 == 0 else '')
            
            count = Kunjungan.objects.filter(arrival_time__range=(s_day, e_day)).count()
            values.append(count)
            visitor_values.append(count * 3 + 5) # Simulated visitor data
            
            prev_values.append(Kunjungan.objects.filter(arrival_time__range=(s_prev, e_prev)).count())
        chart_title = "Tren Kunjungan 30 Hari Terakhir"
    elif chart_range == '365':
        import calendar
        for i in range(11, -1, -1):
            target_month = today.month - i
            target_year = today.year
            while target_month <= 0:
                target_month += 12
                target_year -= 1
                
            labels.append(calendar.month_abbr[target_month])
            
            import calendar as cal
            _, last_day = cal.monthrange(target_year, target_month)
            s_month = timezone.make_aware(datetime(target_year, target_month, 1, 0, 0, 0))
            e_month = timezone.make_aware(datetime(target_year, target_month, last_day, 23, 59, 59))
            
            count = Kunjungan.objects.filter(arrival_time__range=(s_month, e_month)).count()
            values.append(count)
            visitor_values.append(count * 3 + 20) # Simulated visitor data
            
            s_month_prev = timezone.make_aware(datetime(target_year - 1, target_month, 1, 0, 0, 0))
            e_month_prev = timezone.make_aware(datetime(target_year - 1, target_month, last_day, 23, 59, 59))
            
            prev_values.append(Kunjungan.objects.filter(arrival_time__range=(s_month_prev, e_month_prev)).count())
            
        chart_title = "Tren Kunjungan 12 Bulan Terakhir"
    else: # Default 7 days
        for i in range(6, -1, -1):
            day = now - timedelta(days=i)
            day_date = day.date()
            prev_day_date = day_date - timedelta(days=7)
            
            s_day = timezone.make_aware(datetime.combine(day_date, datetime.min.time()))
            e_day = timezone.make_aware(datetime.combine(day_date, datetime.max.time()))
            
            s_prev = timezone.make_aware(datetime.combine(prev_day_date, datetime.min.time()))
            e_prev = timezone.make_aware(datetime.combine(prev_day_date, datetime.max.time()))
            
            labels.append(day.strftime('%a'))
            
            count = Kunjungan.objects.filter(arrival_time__range=(s_day, e_day)).count()
            values.append(count)
            visitor_values.append(count * 3 + 5) # Simulated visitor data
            
            prev_values.append(Kunjungan.objects.filter(arrival_time__range=(s_prev, e_prev)).count())
        chart_title = "Tren Kunjungan 7 Hari Terakhir"

    context = get_admin_context(request)
    context.update({
        'total_tamu': total_tamu,
        'kunjungan_hari_ini': kunjungan_hari_ini,
        'menunggu_verifikasi': menunggu_verifikasi,
        'growth_pct': growth_pct,
        'riwayat_terbaru': riwayat_terbaru,
        'k_status': k_status,
        'k_sort': k_sort,
        'chart_data': {
            'labels': labels,
            'values': values,
            'prev_values': prev_values,
            'visitor_values': visitor_values,
            'title': chart_title,
            'current_range': chart_range
        },
        'active_page': 'dashboard',
    })
    return render(request, 'guest_book/admin_dashboard.html', context)

@admin_login_required
def admin_statistik_view(request):
    """View untuk Statistik & Jadwal (Upgraded Version)"""
    now = timezone.localtime(timezone.now())
    today = now.date()
    start_of_week = today - timedelta(days=now.weekday())
    
    inst = Instansi.objects.first()
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_pegawai':
            name = request.POST.get('name')
            email = request.POST.get('email')
            phone = request.POST.get('phone')
            department_id = request.POST.get('department')
            
            # Buat pegawai baru
            from ..models import Pegawai
            Pegawai.objects.create(
                name=name,
                email=email,
                phone=phone,
                department_rel_id=department_id,
                password='password123' # Default password
            )
            messages.success(request, f"Pegawai {name} berhasil ditambahkan.")
            return redirect('tamu:admin_statistik')
    
    # 1. Statistik Dasar
    total_tamu = Tamu.objects.count()
    
    # Kunjungan minggu ini (dari Senin jam 00:00)
    start_of_this_week = timezone.make_aware(datetime.combine(start_of_week, datetime.min.time()))
    kunjungan_minggu_ini = Kunjungan.objects.filter(arrival_time__gte=start_of_this_week).count()
    
    # Kunjungan minggu lalu
    start_of_last_week = start_of_this_week - timedelta(days=7)
    kunjungan_minggu_lalu = Kunjungan.objects.filter(
        arrival_time__gte=start_of_last_week,
        arrival_time__lt=start_of_this_week
    ).count()
    
    growth = 0
    if kunjungan_minggu_lalu > 0:
        growth = round(((kunjungan_minggu_ini - kunjungan_minggu_lalu) / kunjungan_minggu_lalu) * 100)
    elif kunjungan_minggu_ini > 0:
        growth = 100
        
    kapasitas_maks = inst.kapasitas_maksimal if inst else 50
    
    # Kapasitas sekarang (hari ini)
    start_of_today = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    end_of_today = timezone.make_aware(datetime.combine(today, datetime.max.time()))
    kapasitas_sekarang = Kunjungan.objects.filter(arrival_time__range=(start_of_today, end_of_today), status='in_progress').count()
    
    kapasitas_persen = round((kapasitas_sekarang / kapasitas_maks) * 100) if kapasitas_maks > 0 else 0
    
    stats = {
        'total_tamu': total_tamu,
        'kunjungan_minggu_ini': kunjungan_minggu_ini,
        'growth': growth,
        'pending': Kunjungan.objects.filter(status='pending').count(),
        'kapasitas_persen': kapasitas_persen,
        'kapasitas_label': 'Penuh' if kapasitas_persen >= 90 else ('Padat' if kapasitas_persen >= 70 else 'Normal')
    }
    
    # 2. Riwayat Jadwal
    jadwal_terkini = Kunjungan.objects.select_related('tamu', 'pegawai').order_by('-arrival_time')[:10]
    
    # 3. Chart Data
    chart_range = request.GET.get('range', '7')
    labels, values, prev_values = [], [], []
    
    if chart_range == '30':
        for i in range(29, -1, -1):
            d = today - timedelta(days=i)
            
            s_day = timezone.make_aware(datetime.combine(d, datetime.min.time()))
            e_day = timezone.make_aware(datetime.combine(d, datetime.max.time()))
            
            prev_d = d - timedelta(days=30)
            s_prev = timezone.make_aware(datetime.combine(prev_d, datetime.min.time()))
            e_prev = timezone.make_aware(datetime.combine(prev_d, datetime.max.time()))
            
            labels.append(d.strftime('%d %b') if i % 5 == 0 else '')
            values.append(Kunjungan.objects.filter(arrival_time__range=(s_day, e_day)).count())
            prev_values.append(Kunjungan.objects.filter(arrival_time__range=(s_prev, e_prev)).count())
        chart_title = "Tren Kunjungan 1 Bulan Terakhir"
    elif chart_range == '365':
        import calendar
        for i in range(11, -1, -1):
            target_month = today.month - i
            target_year = today.year
            while target_month <= 0:
                target_month += 12
                target_year -= 1
                
            labels.append(calendar.month_abbr[target_month])
            
            # Use range for the month to be safe with timezones
            import calendar as cal
            _, last_day = cal.monthrange(target_year, target_month)
            s_month = timezone.make_aware(datetime(target_year, target_month, 1, 0, 0, 0))
            e_month = timezone.make_aware(datetime(target_year, target_month, last_day, 23, 59, 59))
            
            values.append(Kunjungan.objects.filter(arrival_time__range=(s_month, e_month)).count())
            
            # Prev year month
            s_month_prev = timezone.make_aware(datetime(target_year - 1, target_month, 1, 0, 0, 0))
            e_month_prev = timezone.make_aware(datetime(target_year - 1, target_month, last_day, 23, 59, 59))
            
            prev_values.append(Kunjungan.objects.filter(arrival_time__range=(s_month_prev, e_month_prev)).count())
            
        chart_title = "Tren Kunjungan 1 Tahun Terakhir"
    else:
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            
            s_day = timezone.make_aware(datetime.combine(d, datetime.min.time()))
            e_day = timezone.make_aware(datetime.combine(d, datetime.max.time()))
            
            prev_d = d - timedelta(days=7)
            s_prev = timezone.make_aware(datetime.combine(prev_d, datetime.min.time()))
            e_prev = timezone.make_aware(datetime.combine(prev_d, datetime.max.time()))
            
            labels.append(d.strftime('%a'))
            values.append(Kunjungan.objects.filter(arrival_time__range=(s_day, e_day)).count())
            prev_values.append(Kunjungan.objects.filter(arrival_time__range=(s_prev, e_prev)).count())
        chart_title = "Tren Kunjungan 7 Hari Terakhir"
        
    chart_data = {
        'labels': labels,
        'values': values,
        'prev_values': prev_values,
        'title': chart_title,
        'current_range': chart_range
    }

    # 4. Konfigurasi Hari Kerja
    days_config = []
    hari_kerja_raw = inst.hari_kerja if inst and hasattr(inst, 'hari_kerja') else '0,1,2,3,4'
    active_days = [int(x) for x in hari_kerja_raw.split(',') if x.isdigit()]
    
    day_labels = ['S','S','R','K','J','S','M']
    day_full   = ['Senin','Selasa','Rabu','Kamis','Jumat','Sabtu','Minggu']
    for i in range(7):
        days_config.append({
            'index': i,
            'label': day_labels[i],
            'full': day_full[i],
            'active': i in active_days
        })

    context = get_admin_context(request)
    context.update({
        'instansi': inst,
        'stats': stats,
        'departemen_all': Departemen.objects.all().order_by('nama'),
        'jadwal_terkini': jadwal_terkini,
        'chart_data': chart_data,
        'days_config': days_config,
        'operasional': {
            'jam_mulai': inst.jam_buka.strftime('%H:%M') if inst and inst.jam_buka else '08:00',
            'jam_selesai': inst.jam_tutup.strftime('%H:%M') if inst and inst.jam_tutup else '17:00',
            'hari_kerja': hari_kerja_raw
        },
        'active_page': 'statistik',
    })
    return render(request, 'guest_book/admin_statistik.html', context)

@admin_login_required
def admin_kunjungan_list_view(request):
    """Daftar Semua Kunjungan untuk Admin (Enhanced with Filters)"""
    status = request.GET.get('status', 'all')
    q = request.GET.get('q', '').strip()
    date_range = request.GET.get('range', 'all')
    dept_id = request.GET.get('dept', 'all')
    
    qs = Kunjungan.objects.select_related('tamu', 'pegawai', 'pegawai__department_rel').order_by('-arrival_time')
    
    # 1. Filter Status
    if status != 'all':
        qs = qs.filter(status=status)
        
    # 2. Filter Search
    if q:
        qs = qs.filter(Q(tamu__name__icontains=q) | Q(purpose__icontains=q) | Q(tamu__instansi__icontains=q))
        
    # 3. Filter Rentang Tanggal
    now = timezone.now()
    local_now = timezone.localtime(now)
    if date_range == 'today':
        start_of_today = timezone.make_aware(datetime.combine(local_now.date(), datetime.min.time()))
        end_of_today = timezone.make_aware(datetime.combine(local_now.date(), datetime.max.time()))
        qs = qs.filter(arrival_time__range=(start_of_today, end_of_today))
    elif date_range == 'week':
        start_of_week = (local_now - timedelta(days=local_now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        qs = qs.filter(arrival_time__gte=start_of_week)
    elif date_range == 'month':
        import calendar as cal
        _, last_day = cal.monthrange(local_now.year, local_now.month)
        start_of_month = timezone.make_aware(datetime(local_now.year, local_now.month, 1, 0, 0, 0))
        end_of_month = timezone.make_aware(datetime(local_now.year, local_now.month, last_day, 23, 59, 59))
        qs = qs.filter(arrival_time__range=(start_of_month, end_of_month))
        
    # 4. Filter Departemen
    if dept_id != 'all':
        qs = qs.filter(pegawai__department_rel_id=dept_id)

    # Statistik untuk UI (opsional tapi membantu)
    stats = {
        'total': Kunjungan.objects.count(),
        'pending': Kunjungan.objects.filter(status='pending').count(),
        'completed': Kunjungan.objects.filter(status='completed').count(),
        'cancelled': Kunjungan.objects.filter(status='cancelled').count(),
    }
        
    paginator = Paginator(qs, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Hitung nomor urut & nomor unik untuk setiap kunjungan di halaman ini
    from django.db.models import Q
    
    for k in page_obj:
        arrival_date = k.arrival_time.date()
        start_of_day = timezone.make_aware(datetime.combine(arrival_date, time.min))
        end_of_day = timezone.make_aware(datetime.combine(arrival_date, time.max))
        
        count = Kunjungan.objects.filter(
            arrival_time__range=(start_of_day, end_of_day)
        ).filter(
            Q(arrival_time__lt=k.arrival_time) | Q(arrival_time=k.arrival_time, id__lt=k.id)
        ).count() + 1
        
        k.nomor_urut = f"{count:02d}"
        k.nomor_unik = str(k.id)[:8].upper()
    
    context = get_admin_context(request)
    context.update({
        'kunjungan': page_obj,
        'status_filter': status,
        'search_query': q,
        'range_filter': date_range,
        'dept_filter': dept_id,
        'departemen_list': Departemen.objects.all().order_by('nama'),
        'pegawai_list': Pegawai.objects.filter(account_status='active').order_by('name'),
        'stats': stats,
        'active_page': 'kunjungan',
    })
    return render(request, 'guest_book/admin_kunjungan_list.html', context)

@admin_login_required
def admin_kunjungan_manual_create(request):
    """View untuk Admin membuat kunjungan secara manual (Pop-up Modal)"""
    import hashlib
    from ..utils import send_notification
    
    if request.method == 'POST':
        name = request.POST.get('name')
        nik = request.POST.get('nik')
        phone = request.POST.get('phone')
        email = request.POST.get('email')
        instansi = request.POST.get('instansi')
        
        pegawai_id = request.POST.get('pegawai')
        purpose = request.POST.get('purpose')
        
        # 1. Create or Find Tamu
        tamu = None
        if email:
            tamu = Tamu.objects.filter(email=email).first()
            
        if not tamu and nik:
            tamu = Tamu.objects.filter(nik=nik).first()
            
        if not tamu:
            # Buat tamu baru
            dummy_password = hashlib.sha256(b'manual_login_dummy').hexdigest()
            
            # Generate unique email if empty
            if not email:
                import uuid
                email = f"tamu_{uuid.uuid4().hex[:8]}@manual.local"
                
            tamu = Tamu.objects.create(
                name=name,
                nik=nik,
                phone=phone,
                email=email,
                instansi=instansi,
                password=dummy_password,
                registration_type='manual',
                account_status='active'
            )
            
        # 2. Create Kunjungan
        pegawai = None
        if pegawai_id:
            pegawai = Pegawai.objects.filter(pk=pegawai_id).first()
            
        kunjungan = Kunjungan.objects.create(
            tamu=tamu,
            pegawai=pegawai,
            purpose=purpose,
            arrival_time=timezone.now(),
            status='in_progress', # Langsung aktif karena orangnya sudah di tempat
        )
        
        # Notifikasi
        send_notification(
            recipient_id='admin',
            recipient_type='admin',
            notification_type='visit_registered',
            title='Kunjungan Manual Dicatat',
            message=f'Admin telah mencatat kunjungan manual untuk {tamu.name}.',
            related_object_id=str(kunjungan.id)
        )
        
        messages.success(request, f"Kunjungan manual untuk {tamu.name} berhasil dicatat!")
        
    return redirect('tamu:admin_kunjungan_list')

@admin_login_required
def admin_kalender_view(request):
    """View untuk Manajemen Kalender Kunjungan"""
    now = timezone.now()
    year = int(request.GET.get('year', now.year))
    month = int(request.GET.get('month', now.month))
    
    first_day = datetime(year, month, 1)
    if month == 12:
        next_month_date = datetime(year + 1, 1, 1)
        next_month, next_year = 1, year + 1
    else:
        next_month_date = datetime(year, month + 1, 1)
        next_month, next_year = month + 1, year
        
    if month == 1:
        prev_month, prev_year = 12, year - 1
    else:
        prev_month, prev_year = month - 1, year
        
    last_day = next_month_date - timedelta(days=1)
    days_in_month = last_day.day
    blank_start = first_day.weekday() # 0=Monday
    
    # Settings dari DB
    settings_qs = CalendarSettings.objects.filter(date__year=year, date__month=month)
    settings_dict = {s.date.day: s for s in settings_qs}
    
    # Optimized Count: Ambil semua jumlah kunjungan dalam bulan ini sekaligus
    kunjungan_month = Kunjungan.objects.filter(
        arrival_time__year=year,
        arrival_time__month=month
    )
    from collections import defaultdict
    counts_dict = defaultdict(int)
    for k in kunjungan_month:
        if k.arrival_time:
            counts_dict[k.arrival_time.day] += 1
    
    days = []
    full_slot_days = 0
    total_booked = 0
    work_days_count = 0
    
    # 6. Get holidays (Real Google API with Mock Fallback)
    from ..utils import get_google_calendar_holidays
    
    # Ambil data dari Google API
    year_holidays = get_google_calendar_holidays(year)
    
    # Fallback jika API gagal atau library tidak ada
    if not year_holidays:
        year_holidays = [
            {'date': f'{year}-01-01', 'name': 'Tahun Baru Masehi'},
            {'date': f'{year}-05-01', 'name': 'Hari Buruh Internasional'},
            {'date': f'{year}-06-01', 'name': 'Hari Lahir Pancasila'},
            {'date': f'{year}-08-17', 'name': 'Hari Kemerdekaan RI'},
            {'date': f'{year}-12-25', 'name': 'Hari Raya Natal'},
        ]
    
    # Buat dict untuk lookup cepat di loop days
    holidays_dict = {h['date']: h['name'] for h in year_holidays}
    
    days = []
    full_slot_days = 0
    total_booked = 0
    work_days_count = 0
    
    for d in range(1, days_in_month + 1):
        curr_date = datetime(year, month, d).date()
        date_iso = curr_date.isoformat()
        is_weekend = curr_date.weekday() >= 5
        s = settings_dict.get(d)
        
        booked = counts_dict.get(d, 0)
        quota = s.daily_quota if s else 50
        is_full = booked >= quota
        
        # Cek apakah tanggal ini libur (dari Google atau Settings DB)
        is_google_holiday = date_iso in holidays_dict
        holiday_name = holidays_dict.get(date_iso) or (s.holiday_name if s else '')
        is_holiday = is_google_holiday or (s.is_holiday if s else False)
        
        days.append({
            'day': d,
            'date': date_iso,
            'is_today': curr_date == now.date(),
            'is_weekend': is_weekend,
            'is_holiday': is_holiday,
            'holiday_name': holiday_name,
            'quota': quota,
            'booked': booked,
            'is_full': is_full,
            'percentage': round((booked / quota) * 100) if quota > 0 else 0,
            'is_past': curr_date < now.date()
        })
        
        if not is_weekend and not is_holiday:
            work_days_count += 1
            total_booked += booked
            if is_full:
                full_slot_days += 1
                
    avg_per_day = round(total_booked / work_days_count, 1) if work_days_count > 0 else 0.0
    
    # --- HITUNG PERTUMBUHAN (REAL DATA) ---
    # Ambil rata-rata bulan lalu untuk perbandingan
    prev_month_qs = Kunjungan.objects.filter(arrival_time__year=prev_year, arrival_time__month=prev_month)
    prev_total_booked = prev_month_qs.count()
    
    # Hitung hari kerja bulan lalu (estimasi sederhana)
    prev_days_in_month = _cal.monthrange(prev_year, prev_month)[1]
    prev_work_days = 0
    for d in range(1, prev_days_in_month + 1):
        if datetime(prev_year, prev_month, d).weekday() < 5:
            prev_work_days += 1
            
    avg_prev_month = round(prev_total_booked / prev_work_days) if prev_work_days > 0 else 0
    
    growth_pct = 0
    if avg_prev_month > 0:
        growth_pct = round(((avg_per_day - avg_prev_month) / avg_prev_month) * 100)
    elif avg_per_day > 0:
        growth_pct = 100
    
    # Filter only for current month for the list
    month_holidays = [h for h in year_holidays if h['date'].startswith(f"{year}-{month:02d}")]
    
    context = get_admin_context(request)
    months_id = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
    
    context.update({
        'year': year, 'month': month,
        'current_month_str': months_id[month],
        'prev_year': prev_year, 'prev_month': prev_month,
        'next_year': next_year, 'next_month': next_month,
        'blank_start': range(blank_start),
        'days': days,
        'avg_per_day': avg_per_day,
        'avg_growth': growth_pct,
        'full_slot_days': full_slot_days,
        'year_holidays': year_holidays,
        'month_holidays': month_holidays,
        'active_page': 'kalender',
    })
    return render(request, 'guest_book/admin_kalender.html', context)

@admin_login_required
def admin_chat_view(request):
    """Manajemen Chat Admin (WA Style)"""
    from ..models import ChatMessage, Tamu
    
    # 1. Ambil semua session_id unik yang pernah ada chat
    sessions = ChatMessage.objects.values('session_id').annotate(
        last_msg=Max('created_at')
    ).order_by('-last_msg')
    
    active_guest_id = request.GET.get('guest')
    
    # Tandai pesan sebagai terbaca jika admin membuka chat spesifik
    if active_guest_id:
        ChatMessage.objects.filter(session_id=active_guest_id, sender_type='tamu', is_read=False).update(is_read=True)
        
    conversations = []
    active_conversation = None
    
    for s in sessions:
        sid = s['session_id']
        try:
            guest = Tamu.objects.get(id=sid)
            last_message = ChatMessage.objects.filter(session_id=sid).latest('created_at')
            unread_count = ChatMessage.objects.filter(session_id=sid, is_read=False, sender_type='tamu').count()
            
            conv_data = {
                'guest': guest,
                'last_message': last_message,
                'unread_count': unread_count,
                'messages': ChatMessage.objects.filter(session_id=sid).order_by('created_at')
            }
            
            if active_guest_id and str(guest.id) == active_guest_id:
                active_conversation = conv_data
            else:
                conversations.append(conv_data)
        except Tamu.DoesNotExist:
            continue

    # Jika ada active_guest_id tetapi tidak ada di sessions (belum pernah chat)
    if active_guest_id and not active_conversation:
        try:
            guest = Tamu.objects.get(id=active_guest_id)
            active_conversation = {
                'guest': guest,
                'last_message': None,
                'unread_count': 0,
                'messages': []
            }
        except Tamu.DoesNotExist:
            pass

    if active_conversation:
        conversations.insert(0, active_conversation)

    context = get_admin_context(request)
    context.update({
        'conversations': conversations,
        'active_page': 'chat',
    })
    return render(request, 'guest_book/admin_chat.html', context)

@admin_login_required
def admin_profil_view(request):
    """Profil Administrator"""
    from ..models import AuditLog, LoginAttempt, Kunjungan
    context = get_admin_context(request)
    context['active_page'] = 'profil'
    
    admin_user = context.get('admin_user')
    if admin_user:
        # Hitung Total Login
        total_login = LoginAttempt.objects.filter(email=admin_user.email, success=True).count()
        context['total_login'] = total_login
        
        # Ambil Log Aktivitas Terakhir
        logs = AuditLog.objects.filter(user_id=str(admin_user.id)).order_by('-timestamp')[:5]
        context['activity_logs'] = logs
        
        # Data Export (Gunakan jumlah kunjungan selesai sebagai representasi data terproses)
        context['data_export'] = Kunjungan.objects.filter(status='completed').count()
        
        # Uptime Rate (Rasio login sukses vs total percobaan login)
        total_attempts = LoginAttempt.objects.filter(email=admin_user.email).count()
        context['uptime'] = round((total_login / total_attempts) * 100) if total_attempts > 0 else 100
        
        # Baca preferensi notifikasi dari file
        import json
        import os
        pref_path = os.path.join(os.path.dirname(__file__), '../admin_preferences.json')
        if os.path.exists(pref_path):
            try:
                with open(pref_path, 'r') as f:
                    prefs = json.load(f)
            except:
                prefs = {}
        else:
            prefs = {}
            
        context['email_notif_enabled'] = prefs.get('email_notif_enabled', True)
        context['push_notif_enabled'] = prefs.get('push_notif_enabled', False)
        
    return render(request, 'guest_book/admin_profil.html', context)

@admin_login_required
def admin_instansi_view(request):
    """Manajemen Instansi dan Departemen"""
    instansi = Instansi.objects.first()
    departemen_all = Departemen.objects.all().order_by('nama')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_instansi':
            if not instansi: instansi = Instansi()
            instansi.nama = request.POST.get('nama')
            instansi.slogan = request.POST.get('slogan')
            instansi.status_operasional = request.POST.get('status_operasional')
            instansi.jumlah_petugas = int(request.POST.get('jumlah_petugas', 0))
            instansi.kapasitas_maksimal = int(request.POST.get('kapasitas_maksimal', 100))
            instansi.jam_buka = request.POST.get('jam_buka', '08:00')
            instansi.jam_tutup = request.POST.get('jam_tutup', '16:00')
            instansi.alamat = request.POST.get('alamat')
            
            # Hari Kerja (jika dikirim dari statistik portal)
            hari_kerja = request.POST.get('hari_kerja')
            if hari_kerja:
                instansi.hari_kerja = hari_kerja
                
            instansi.save()
            messages.success(request, "Data instansi berhasil diperbarui.")
            return redirect(request.META.get('HTTP_REFERER', 'tamu:admin_instansi'))
        
        elif action == 'add_departemen':
            nama = request.POST.get('nama')
            kode = request.POST.get('kode')
            Departemen.objects.create(nama=nama, kode=kode)
            messages.success(request, f"Departemen {nama} berhasil ditambahkan.")
            return redirect('tamu:admin_instansi')

    context = get_admin_context(request)
    context.update({
        'instansi': instansi,
        'departemen_all': departemen_all,
        'active_page': 'instansi',
    })
    return render(request, 'guest_book/admin_instansi.html', context)

@admin_login_required
def admin_notifications_view(request):
    """Daftar Notifikasi untuk Admin"""
    notifications = Notification.objects.filter(
        recipient_id='admin', recipient_type='admin'
    ).order_by('-created_at')
    
    # Mark read
    notifications.filter(status='unread').update(status='read', read_at=timezone.now())
    
    context = get_admin_context(request)
    context.update({
        'notifications': notifications,
        'active_page': 'notifications'
    })
    return render(request, 'guest_book/admin_notifications.html', context)

# Export views... (export_excel, cetak_pdf)
@admin_login_required
def admin_kunjungan_export_excel(request):
    from openpyxl import Workbook
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Laporan Kunjungan"
    
    # Header
    ws.append(['No', 'Nama Tamu', 'Instansi Tamu', 'Tujuan Kunjungan', 'Menemui', 'Bidang', 'Waktu Masuk', 'Waktu Keluar', 'Status'])
    
    kunjungan = Kunjungan.objects.select_related('tamu', 'pegawai', 'pegawai__department_rel').all().order_by('-arrival_time')
    
    for i, k in enumerate(kunjungan, 1):
        ws.append([
            i,
            k.tamu.name,
            k.tamu.instansi or 'Personal',
            k.purpose,
            k.pegawai.name if k.pegawai else 'Umum',
            k.pegawai.department_rel.nama if k.pegawai and k.pegawai.department_rel else 'Umum',
            k.arrival_time.strftime("%d/%m/%Y %H:%M") if k.arrival_time else '-',
            k.departure_time.strftime("%d/%m/%Y %H:%M") if k.departure_time else '-',
            k.get_status_display()
        ])
        
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="laporan_kunjungan_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx"'
    
    wb.save(response)
    return response

@admin_login_required
def admin_kunjungan_cetak_pdf(request):
    kunjungan_all = Kunjungan.objects.all().order_by('-arrival_time')
    context = get_admin_context(request)
    context.update({
        'kunjungan_all': kunjungan_all,
    })
    return render(request, 'guest_book/admin_kunjungan_cetak_pdf.html', context)
@admin_login_required
def admin_kalender_download_template(request):
    """View untuk mengunduh template Excel jadwal kalender dengan data 365 hari"""
    from openpyxl import Workbook
    from django.http import HttpResponse
    from datetime import date, timedelta
    
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="template_jadwal_tahunan.xlsx"'
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Template Jadwal"
    
    # Header dengan instruksi
    ws.append(['PENTING: JANGAN HAPUS HEADER DI BAWAH INI. Isi kolom Libur dengan "Ya" atau "Tidak"'])
    ws.append(['Bulan', 'Tanggal', 'Kuota', 'Libur', 'Keterangan Libur'])
    
    # Generate data untuk 1 tahun ke depan (mulai dari hari ini)
    start_date = date.today()
    months_name = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']
    
    for i in range(365):
        curr = start_date + timedelta(days=i)
        ws.append([
            months_name[curr.month],
            curr.strftime('%Y-%m-%d'),
            50,
            'Tidak',
            ''
        ])
        
    wb.save(response)
    return response
