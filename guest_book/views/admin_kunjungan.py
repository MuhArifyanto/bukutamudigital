"""
Views Admin — Modul Kunjungan
Berisi: detail, cetak kartu, list, manual create, export Excel, cetak PDF
"""
import csv
import logging
from datetime import datetime, timedelta, time

logger = logging.getLogger(__name__)

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from django.http import HttpResponse
from django.db.models import Count, Q
from django.core.paginator import Paginator

from .base import admin_login_required, get_admin_context
from ..models import Kunjungan, Tamu, Pegawai, Departemen, Instansi


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
def admin_kunjungan_list_view(request):
    """Daftar Semua Kunjungan untuk Admin (Enhanced with Filters)"""
    status = request.GET.get('status', 'all')
    q = request.GET.get('q', '').strip()
    date_range = request.GET.get('range', 'all')
    dept_id = request.GET.get('dept', 'all')

    qs = Kunjungan.objects.select_related('tamu', 'pegawai', 'pegawai__department_rel').order_by('-arrival_time')

    if status != 'all':
        qs = qs.filter(status=status)

    if q:
        qs = qs.filter(Q(tamu__name__icontains=q) | Q(purpose__icontains=q) | Q(tamu__instansi__icontains=q))

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

    if dept_id != 'all':
        qs = qs.filter(pegawai__department_rel_id=dept_id)

    stats = Kunjungan.objects.aggregate(
        total=Count('id'),
        pending=Count('id', filter=Q(status__in=Kunjungan.Status.PENDING_VERIFICATION)),
        completed=Count('id', filter=Q(status='completed')),
        cancelled=Count('id', filter=Q(status='cancelled')),
    )

    paginator = Paginator(qs, 100)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    page_items = list(page_obj)
    unique_dates = {k.arrival_time.date() for k in page_items}

    nomor_map = {}
    if unique_dates:
        combined_filter = Q(arrival_time__date=unique_dates.pop())
        for d in unique_dates:
            combined_filter |= Q(arrival_time__date=d)

        all_day_kunjungan = list(
            Kunjungan.objects
            .filter(combined_filter)
            .only('id', 'arrival_time')
            .order_by('arrival_time', 'id')
        )

        day_counter = {}
        for item in all_day_kunjungan:
            d = item.arrival_time.date()
            day_counter[d] = day_counter.get(d, 0) + 1
            nomor_map[item.id] = day_counter[d]

    for k in page_items:
        k.nomor_urut = f"{nomor_map.get(k.id, 1):02d}"
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
        pegawai_id = request.POST.get('pegawai') or request.POST.get('pegawai_id')
        purpose = request.POST.get('purpose')

        tamu = None
        if email:
            tamu = Tamu.objects.filter(email=email).first()
        if not tamu and nik:
            tamu = Tamu.objects.filter(nik=nik).first()
        if not tamu:
            from django.contrib.auth.hashers import make_password
            dummy_password = make_password('manual_login_dummy')
            if not email:
                import uuid
                email = f"tamu_{uuid.uuid4().hex[:8]}@manual.local"
            tamu = Tamu.objects.create(
                name=name, nik=nik, phone=phone, email=email,
                instansi=instansi, password=dummy_password,
                registration_type='manual', account_status='active'
            )

        pegawai = None
        if pegawai_id:
            pegawai = Pegawai.objects.filter(pk=pegawai_id).first()

        arrival_now = timezone.now()
        from ..validators import validate_kunjungan_schedule
        from django.core.exceptions import ValidationError as DjangoValidationError
        try:
            validate_kunjungan_schedule(
                arrival_time=arrival_now,
                is_admin=True,
                is_import=False
            )
        except DjangoValidationError as e:
            err_msg = e.message if hasattr(e, 'message') else str(e)
            messages.error(request, f"Gagal mencatat kunjungan manual: {err_msg}")
            return redirect('tamu:admin_kunjungan_list')

        kunjungan = Kunjungan.objects.create(
            tamu=tamu, pegawai=pegawai, purpose=purpose,
            arrival_time=arrival_now, status='in_progress',
        )

        if pegawai:
            try:
                send_notification(
                    recipient_id=str(pegawai.id), recipient_type='pegawai',
                    notification_type='visit_registered',
                    title='Kunjungan Baru untuk Anda',
                    message=f'Tamu {tamu.name} telah tiba dan dicatat untuk bertemu Anda.',
                    related_object_id=str(kunjungan.id)
                )
            except Exception as notif_err:
                logger.warning("Gagal mengirim notifikasi kunjungan manual ke pegawai: %s", notif_err)

        messages.success(request, f"Kunjungan manual untuk {tamu.name} berhasil dicatat!")

    return redirect('tamu:admin_kunjungan_list')


@admin_login_required
def admin_kunjungan_export_excel(request):
    """Export semua kunjungan ke file Excel"""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Laporan Kunjungan"
    ws.append(['No', 'Nama Tamu', 'Instansi Tamu', 'Tujuan Kunjungan', 'Menemui', 'Bidang', 'Waktu Masuk', 'Waktu Keluar', 'Status'])

    kunjungan = Kunjungan.objects.select_related('tamu', 'pegawai', 'pegawai__department_rel').all().order_by('-arrival_time')

    def sanitize_cell(val):
        """Mencegah formula injection (CSV/Excel DDE attack) jika data diawali =, +, -, @, dll"""
        if isinstance(val, str) and val and val[0] in ('=', '+', '-', '@', '\t', '\r'):
            return "'" + val
        return val

    for i, k in enumerate(kunjungan, 1):
        ws.append([
            i,
            sanitize_cell(k.tamu.name if k.tamu else '-'),
            sanitize_cell(k.tamu.instansi if k.tamu and k.tamu.instansi else 'Personal'),
            sanitize_cell(k.purpose),
            sanitize_cell(k.pegawai.name if k.pegawai else 'Umum'),
            sanitize_cell(k.pegawai.department_rel.nama if k.pegawai and k.pegawai.department_rel else 'Umum'),
            k.arrival_time.strftime("%d/%m/%Y %H:%M") if k.arrival_time else '-',
            k.departure_time.strftime("%d/%m/%Y %H:%M") if k.departure_time else '-',
            sanitize_cell(k.get_status_display())
        ])

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="laporan_kunjungan_{timezone.now().strftime("%Y%m%d_%H%M")}.xlsx"'
    wb.save(response)
    return response


@admin_login_required
def admin_kunjungan_cetak_pdf(request):
    """Cetak semua kunjungan sebagai PDF"""
    kunjungan_all = Kunjungan.objects.all().order_by('-arrival_time')
    context = get_admin_context(request)
    context.update({'kunjungan_all': kunjungan_all})
    return render(request, 'guest_book/admin_kunjungan_cetak_pdf.html', context)
