"""
Views Admin — Modul Dashboard & Statistik
Berisi: dashboard utama, statistik, kalender, download template kalender
"""
import calendar as _cal
from datetime import datetime, timedelta, time, date

from django.shortcuts import render, redirect
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q
from django.db.models.functions import TruncDate, TruncMonth

from .base import admin_login_required, get_admin_context
from ..models import Kunjungan, Tamu, Instansi, Departemen, CalendarSettings


@admin_login_required
def admin_dashboard_view(request):
    """View untuk Dashboard Utama Admin"""
    now = timezone.localtime(timezone.now())
    today = now.date()

    total_tamu = Tamu.objects.count()

    start_of_today = timezone.make_aware(datetime.combine(today, datetime.min.time()))
    end_of_today = timezone.make_aware(datetime.combine(today, datetime.max.time()))
    kunjungan_hari_ini = Kunjungan.objects.filter(arrival_time__range=(start_of_today, end_of_today)).count()
    menunggu_verifikasi = Kunjungan.objects.filter(
        status__in=Kunjungan.Status.PENDING_VERIFICATION
    ).count()

    kemarin = today - timedelta(days=1)
    start_of_kemarin = timezone.make_aware(datetime.combine(kemarin, datetime.min.time()))
    end_of_kemarin = timezone.make_aware(datetime.combine(kemarin, datetime.max.time()))
    kunjungan_kemarin = Kunjungan.objects.filter(arrival_time__range=(start_of_kemarin, end_of_kemarin)).count()

    growth_pct = 0
    if kunjungan_kemarin > 0:
        growth_pct = round(((kunjungan_hari_ini - kunjungan_kemarin) / kunjungan_kemarin) * 100)
    elif kunjungan_hari_ini > 0:
        growth_pct = 100
    if growth_pct == -100:
        growth_pct = 0

    k_status = request.GET.get('k_status', 'all')
    k_sort = request.GET.get('k_sort', '-arrival_time')
    riwayat_query = Kunjungan.objects.select_related('tamu', 'pegawai')
    if k_status != 'all':
        riwayat_query = riwayat_query.filter(status=k_status)
    riwayat_terbaru = riwayat_query.order_by(k_sort)[:10]

    chart_range = request.GET.get('range', '7')
    labels, values, prev_values, visitor_values = [], [], [], []

    if chart_range == '30':
        num_days = 30
        period_start = timezone.make_aware(datetime.combine(today - timedelta(days=num_days - 1), time.min))
        period_end = timezone.make_aware(datetime.combine(today, time.max))
        prev_start = timezone.make_aware(datetime.combine(today - timedelta(days=num_days * 2 - 1), time.min))
        prev_end = timezone.make_aware(datetime.combine(today - timedelta(days=num_days), time.max))

        current_map = {row['day']: row['total'] for row in Kunjungan.objects.filter(arrival_time__range=(period_start, period_end)).annotate(day=TruncDate('arrival_time')).values('day').annotate(total=Count('id'))}
        prev_map = {row['day']: row['total'] for row in Kunjungan.objects.filter(arrival_time__range=(prev_start, prev_end)).annotate(day=TruncDate('arrival_time')).values('day').annotate(total=Count('id'))}

        for i in range(num_days - 1, -1, -1):
            day_date = today - timedelta(days=i)
            prev_day_date = day_date - timedelta(days=num_days)
            labels.append(day_date.strftime('%d %b') if i % 5 == 0 else '')
            count = current_map.get(day_date, 0)
            values.append(count)
            visitor_values.append(count * 3 + 5)
            prev_values.append(prev_map.get(prev_day_date, 0))
        chart_title = "Tren Kunjungan 30 Hari Terakhir"

    elif chart_range == '365':
        month_list = []
        for i in range(11, -1, -1):
            m = today.month - i
            y = today.year
            while m <= 0:
                m += 12
                y -= 1
            month_list.append((y, m))

        first_year, first_month = month_list[0]
        last_year, last_month = month_list[-1]
        _, last_day_of_last = _cal.monthrange(last_year, last_month)

        period_start = timezone.make_aware(datetime(first_year, first_month, 1, 0, 0, 0))
        period_end = timezone.make_aware(datetime(last_year, last_month, last_day_of_last, 23, 59, 59))
        prev_period_start = timezone.make_aware(datetime(first_year - 1, first_month, 1, 0, 0, 0))
        prev_period_end = timezone.make_aware(datetime(last_year - 1, last_month, last_day_of_last, 23, 59, 59))

        current_map = {(row['month'].year, row['month'].month): row['total'] for row in Kunjungan.objects.filter(arrival_time__range=(period_start, period_end)).annotate(month=TruncMonth('arrival_time')).values('month').annotate(total=Count('id'))}
        prev_map = {(row['month'].year, row['month'].month): row['total'] for row in Kunjungan.objects.filter(arrival_time__range=(prev_period_start, prev_period_end)).annotate(month=TruncMonth('arrival_time')).values('month').annotate(total=Count('id'))}

        for (y, m) in month_list:
            labels.append(_cal.month_abbr[m])
            count = current_map.get((y, m), 0)
            values.append(count)
            visitor_values.append(count * 3 + 20)
            prev_values.append(prev_map.get((y - 1, m), 0))
        chart_title = "Tren Kunjungan 12 Bulan Terakhir"

    else:
        num_days = 7
        period_start = timezone.make_aware(datetime.combine(today - timedelta(days=num_days - 1), time.min))
        period_end = timezone.make_aware(datetime.combine(today, time.max))
        prev_start = timezone.make_aware(datetime.combine(today - timedelta(days=num_days * 2 - 1), time.min))
        prev_end = timezone.make_aware(datetime.combine(today - timedelta(days=num_days), time.max))

        current_map = {row['day']: row['total'] for row in Kunjungan.objects.filter(arrival_time__range=(period_start, period_end)).annotate(day=TruncDate('arrival_time')).values('day').annotate(total=Count('id'))}
        prev_map = {row['day']: row['total'] for row in Kunjungan.objects.filter(arrival_time__range=(prev_start, prev_end)).annotate(day=TruncDate('arrival_time')).values('day').annotate(total=Count('id'))}

        for i in range(num_days - 1, -1, -1):
            day_date = today - timedelta(days=i)
            prev_day_date = day_date - timedelta(days=num_days)
            labels.append(day_date.strftime('%a'))
            count = current_map.get(day_date, 0)
            values.append(count)
            visitor_values.append(count * 3 + 5)
            prev_values.append(prev_map.get(prev_day_date, 0))
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
    """View untuk Statistik & Jadwal"""
    now = timezone.localtime(timezone.now())
    today = now.date()
    start_of_week = today - timedelta(days=now.weekday())

    inst = Instansi.objects.first()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_pegawai':
            from ..models import Pegawai
            name = request.POST.get('name')
            email = request.POST.get('email')
            phone = request.POST.get('phone')
            department_id = request.POST.get('department')
            Pegawai.objects.create(
                name=name, email=email, phone=phone,
                department_rel_id=department_id, password='password123'
            )
            messages.success(request, f"Pegawai {name} berhasil ditambahkan.")
            return redirect('tamu:admin_statistik')

    start_of_this_week = timezone.make_aware(datetime.combine(start_of_week, datetime.min.time()))
    start_of_last_week = start_of_this_week - timedelta(days=7)
    start_of_today = timezone.make_aware(datetime.combine(today, time.min))
    end_of_today = timezone.make_aware(datetime.combine(today, time.max))

    kunjungan_agg = Kunjungan.objects.aggregate(
        minggu_ini=Count('id', filter=Q(arrival_time__gte=start_of_this_week)),
        minggu_lalu=Count('id', filter=Q(arrival_time__gte=start_of_last_week, arrival_time__lt=start_of_this_week)),
        pending=Count('id', filter=Q(status__in=Kunjungan.Status.PENDING_VERIFICATION)),
        kapasitas_sekarang=Count('id', filter=Q(arrival_time__range=(start_of_today, end_of_today), status='in_progress')),
    )

    total_tamu = Tamu.objects.count()
    kunjungan_minggu_ini = kunjungan_agg['minggu_ini']
    kunjungan_minggu_lalu = kunjungan_agg['minggu_lalu']
    kapasitas_maks = inst.kapasitas_maksimal if inst else 50
    kapasitas_sekarang = kunjungan_agg['kapasitas_sekarang']

    growth = 0
    if kunjungan_minggu_lalu > 0:
        growth = round(((kunjungan_minggu_ini - kunjungan_minggu_lalu) / kunjungan_minggu_lalu) * 100)
    elif kunjungan_minggu_ini > 0:
        growth = 100

    kapasitas_persen = round((kapasitas_sekarang / kapasitas_maks) * 100) if kapasitas_maks > 0 else 0
    stats = {
        'total_tamu': total_tamu,
        'kunjungan_minggu_ini': kunjungan_minggu_ini,
        'growth': growth,
        'pending': kunjungan_agg['pending'],
        'kapasitas_persen': kapasitas_persen,
        'kapasitas_label': 'Penuh' if kapasitas_persen >= 90 else ('Padat' if kapasitas_persen >= 70 else 'Normal'),
    }

    jadwal_terkini = Kunjungan.objects.select_related('tamu', 'pegawai').order_by('-arrival_time')[:10]

    chart_range = request.GET.get('range', '7')
    labels, values, prev_values = [], [], []

    if chart_range == '30':
        num_days = 30
        period_start = timezone.make_aware(datetime.combine(today - timedelta(days=num_days - 1), time.min))
        period_end = timezone.make_aware(datetime.combine(today, time.max))
        prev_start = timezone.make_aware(datetime.combine(today - timedelta(days=num_days * 2 - 1), time.min))
        prev_end = timezone.make_aware(datetime.combine(today - timedelta(days=num_days), time.max))

        current_map = {row['day']: row['total'] for row in Kunjungan.objects.filter(arrival_time__range=(period_start, period_end)).annotate(day=TruncDate('arrival_time')).values('day').annotate(total=Count('id'))}
        prev_map = {row['day']: row['total'] for row in Kunjungan.objects.filter(arrival_time__range=(prev_start, prev_end)).annotate(day=TruncDate('arrival_time')).values('day').annotate(total=Count('id'))}

        for i in range(num_days - 1, -1, -1):
            d = today - timedelta(days=i)
            prev_d = d - timedelta(days=num_days)
            labels.append(d.strftime('%d %b') if i % 5 == 0 else '')
            values.append(current_map.get(d, 0))
            prev_values.append(prev_map.get(prev_d, 0))
        chart_title = "Tren Kunjungan 1 Bulan Terakhir"

    elif chart_range == '365':
        month_list = []
        for i in range(11, -1, -1):
            m, y = today.month - i, today.year
            while m <= 0:
                m += 12
                y -= 1
            month_list.append((y, m))

        first_year, first_month = month_list[0]
        last_year, last_month = month_list[-1]
        _, last_day_of_last = _cal.monthrange(last_year, last_month)

        period_start = timezone.make_aware(datetime(first_year, first_month, 1, 0, 0, 0))
        period_end = timezone.make_aware(datetime(last_year, last_month, last_day_of_last, 23, 59, 59))
        prev_period_start = timezone.make_aware(datetime(first_year - 1, first_month, 1, 0, 0, 0))
        prev_period_end = timezone.make_aware(datetime(last_year - 1, last_month, last_day_of_last, 23, 59, 59))

        current_map = {(row['month'].year, row['month'].month): row['total'] for row in Kunjungan.objects.filter(arrival_time__range=(period_start, period_end)).annotate(month=TruncMonth('arrival_time')).values('month').annotate(total=Count('id'))}
        prev_map = {(row['month'].year, row['month'].month): row['total'] for row in Kunjungan.objects.filter(arrival_time__range=(prev_period_start, prev_period_end)).annotate(month=TruncMonth('arrival_time')).values('month').annotate(total=Count('id'))}

        for (y, m) in month_list:
            labels.append(_cal.month_abbr[m])
            values.append(current_map.get((y, m), 0))
            prev_values.append(prev_map.get((y - 1, m), 0))
        chart_title = "Tren Kunjungan 1 Tahun Terakhir"

    else:
        num_days = 7
        period_start = timezone.make_aware(datetime.combine(today - timedelta(days=num_days - 1), time.min))
        period_end = timezone.make_aware(datetime.combine(today, time.max))
        prev_start = timezone.make_aware(datetime.combine(today - timedelta(days=num_days * 2 - 1), time.min))
        prev_end = timezone.make_aware(datetime.combine(today - timedelta(days=num_days), time.max))

        current_map = {row['day']: row['total'] for row in Kunjungan.objects.filter(arrival_time__range=(period_start, period_end)).annotate(day=TruncDate('arrival_time')).values('day').annotate(total=Count('id'))}
        prev_map = {row['day']: row['total'] for row in Kunjungan.objects.filter(arrival_time__range=(prev_start, prev_end)).annotate(day=TruncDate('arrival_time')).values('day').annotate(total=Count('id'))}

        for i in range(num_days - 1, -1, -1):
            d = today - timedelta(days=i)
            prev_d = d - timedelta(days=num_days)
            labels.append(d.strftime('%a'))
            values.append(current_map.get(d, 0))
            prev_values.append(prev_map.get(prev_d, 0))
        chart_title = "Tren Kunjungan 7 Hari Terakhir"

    hari_kerja_raw = inst.hari_kerja if inst and hasattr(inst, 'hari_kerja') else '0,1,2,3,4'
    active_days = [int(x) for x in hari_kerja_raw.split(',') if x.isdigit()]
    day_labels = ['S', 'S', 'R', 'K', 'J', 'S', 'M']
    day_full = ['Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu']
    days_config = [{'index': i, 'label': day_labels[i], 'full': day_full[i], 'active': i in active_days} for i in range(7)]

    # Data for Department Chart (Donut Chart)
    dept_stats = Kunjungan.objects.filter(
        arrival_time__range=(period_start, period_end)
    ).values('pegawai__department_rel__nama').annotate(
        total=Count('id')
    ).order_by('-total')

    dept_labels = []
    dept_values = []
    for row in dept_stats:
        nama = row['pegawai__department_rel__nama']
        if not nama:
            nama = "Umum/Personal"
        dept_labels.append(nama)
        dept_values.append(row['total'])

    context = get_admin_context(request)
    context.update({
        'instansi': inst,
        'stats': stats,
        'departemen_all': Departemen.objects.all().order_by('nama'),
        'jadwal_terkini': jadwal_terkini,
        'chart_data': {'labels': labels, 'values': values, 'prev_values': prev_values, 'title': chart_title, 'current_range': chart_range},
        'dept_chart_data': {'labels': dept_labels, 'values': dept_values},
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
def admin_kalender_view(request):
    """View untuk Manajemen Kalender Kunjungan"""
    from django.db.models.functions import TruncDate
    from ..utils import get_google_calendar_holidays

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

    prev_month, prev_year = (12, year - 1) if month == 1 else (month - 1, year)
    last_day = next_month_date - timedelta(days=1)
    days_in_month = last_day.day
    blank_start = first_day.weekday()

    settings_qs = CalendarSettings.objects.filter(date__year=year, date__month=month)
    settings_dict = {s.date.day: s for s in settings_qs}

    from ..validators import get_monthly_quota_usage, ACTIVE_QUOTA_STATUSES, JAKARTA_TZ
    counts_dict = get_monthly_quota_usage(year, month)

    year_holidays = get_google_calendar_holidays(year) or [
        {'date': f'{year}-01-01', 'name': 'Tahun Baru Masehi'},
        {'date': f'{year}-05-01', 'name': 'Hari Buruh Internasional'},
        {'date': f'{year}-06-01', 'name': 'Hari Lahir Pancasila'},
        {'date': f'{year}-08-17', 'name': 'Hari Kemerdekaan RI'},
        {'date': f'{year}-12-25', 'name': 'Hari Raya Natal'},
    ]
    holidays_dict = {h['date']: h['name'] for h in year_holidays}

    days = []
    full_slot_days = total_booked = work_days_count = 0

    for d in range(1, days_in_month + 1):
        curr_date = datetime(year, month, d).date()
        date_iso = curr_date.isoformat()
        is_weekend = curr_date.weekday() >= 5
        s = settings_dict.get(d)
        booked = counts_dict.get(d, 0)
        quota = s.daily_quota if s else 50
        is_full = booked >= quota
        is_google_holiday = date_iso in holidays_dict
        holiday_name = holidays_dict.get(date_iso) or (s.holiday_name if s else '')
        is_holiday = is_google_holiday or (s.is_holiday if s else False)

        days.append({
            'day': d, 'date': date_iso,
            'is_today': curr_date == now.date(),
            'is_weekend': is_weekend, 'is_holiday': is_holiday,
            'holiday_name': holiday_name, 'quota': quota,
            'booked': booked, 'is_full': is_full,
            'percentage': round((booked / quota) * 100) if quota > 0 else 0,
            'is_past': curr_date < now.date()
        })

        if not is_weekend and not is_holiday:
            work_days_count += 1
            total_booked += booked
            if is_full:
                full_slot_days += 1

    avg_per_day = round(total_booked / work_days_count, 1) if work_days_count > 0 else 0.0

    prev_start = datetime(prev_year, prev_month, 1, 0, 0, 0, tzinfo=JAKARTA_TZ)
    if prev_month == 12:
        prev_next = datetime(prev_year + 1, 1, 1, 0, 0, 0, tzinfo=JAKARTA_TZ)
    else:
        prev_next = datetime(prev_year, prev_month + 1, 1, 0, 0, 0, tzinfo=JAKARTA_TZ)
    prev_total_booked = Kunjungan.objects.filter(
        arrival_time__gte=prev_start,
        arrival_time__lt=prev_next,
        status__in=ACTIVE_QUOTA_STATUSES
    ).count()
    prev_days_in_month = _cal.monthrange(prev_year, prev_month)[1]
    first_weekday, _ = _cal.monthrange(prev_year, prev_month)
    prev_work_days = sum(1 for d in range(prev_days_in_month) if (first_weekday + d) % 7 < 5)
    avg_prev_month = round(prev_total_booked / prev_work_days) if prev_work_days > 0 else 0

    growth_pct = 0
    if avg_prev_month > 0:
        growth_pct = round(((avg_per_day - avg_prev_month) / avg_prev_month) * 100)
    elif avg_per_day > 0:
        growth_pct = 100

    month_holidays = [h for h in year_holidays if h['date'].startswith(f"{year}-{month:02d}")]
    months_id = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']

    context = get_admin_context(request)
    context.update({
        'year': year, 'month': month,
        'current_month_str': months_id[month],
        'prev_year': prev_year, 'prev_month': prev_month,
        'next_year': next_year, 'next_month': next_month,
        'blank_start': range(blank_start),
        'days': days, 'avg_per_day': avg_per_day,
        'avg_growth': growth_pct, 'full_slot_days': full_slot_days,
        'year_holidays': year_holidays, 'month_holidays': month_holidays,
        'active_page': 'kalender',
    })
    return render(request, 'guest_book/admin_kalender.html', context)


@admin_login_required
def admin_kalender_download_template(request):
    """Unduh template Excel jadwal kalender (365 hari)"""
    from openpyxl import Workbook
    from django.http import HttpResponse

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="template_jadwal_tahunan.xlsx"'

    wb = Workbook()
    ws = wb.active
    ws.title = "Template Jadwal"
    ws.append(['PENTING: JANGAN HAPUS HEADER DI BAWAH INI. Isi kolom Libur dengan "Ya" atau "Tidak"'])
    ws.append(['Bulan', 'Tanggal', 'Kuota', 'Libur', 'Keterangan Libur'])

    start_date = date.today()
    months_name = ['', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']

    for i in range(365):
        curr = start_date + timedelta(days=i)
        ws.append([months_name[curr.month], curr.strftime('%Y-%m-%d'), 50, 'Tidak', ''])

    wb.save(response)
    return response
