import json
import calendar as py_calendar
from datetime import date, datetime, timedelta

import weasyprint
from django.conf import settings
from django.db.models import Sum, Count, F, Q
from django.db.models.functions import TruncMonth, TruncDate, TruncWeek, TruncYear
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit

from .models import GuestRegistration, AuditLog, Room, AdminSettings

def log_action(request, action, details):
    ip = request.META.get('HTTP_X_FORWARDED_FOR')
    if ip:
        ip = ip.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
        
    AuditLog.objects.create(
        action=action,
        details=details,
        ip_address=ip
    )

def cleanup_expired_registrations():
    expiration_time = timezone.now() - timedelta(hours=1)
    GuestRegistration.objects.filter(status='PENDING', created_at__lt=expiration_time).delete()

def intro(request):
    try:
        guest_id = request.get_signed_cookie('kegama_guest_id')
    except (KeyError, Exception):
        guest_id = None
    
    if guest_id:
        try:
            guest = GuestRegistration.objects.get(id=guest_id)
            if guest.status == 'PENDING':
                return render(request, 'management/status_pending.html', {
                    'guest_name': f"{guest.first_name} {guest.last_name}",
                    'guest_id': guest.id
                })
        except (GuestRegistration.DoesNotExist, ValueError):
            pass

    return render(request, 'management/intro.html')

def guest_form_page(request):
    settings_obj = AdminSettings.load()

    if settings_obj.maintenance_mode:
        return render(request, 'management/maintenance.html')

    if settings_obj.form_access_code:
        if not request.session.get('form_authorized'):
            if request.method == 'POST':
                entered_code = request.POST.get('access_code')
                if entered_code == settings_obj.form_access_code:
                    request.session['form_authorized'] = True
                    return redirect('guest_form_page')
                else:
                    return render(request, 'management/enter_code.html', {'error': 'Invalid Access Code'})
            return render(request, 'management/enter_code.html')

    try:
        guest_id = request.get_signed_cookie('kegama_guest_id')
    except (KeyError, Exception):
        guest_id = None
        
    if guest_id:
        try:
            guest = GuestRegistration.objects.get(id=guest_id)
            if guest.status == 'PENDING':
                return redirect('intro')
        except (GuestRegistration.DoesNotExist, ValueError):
            pass

    return render(request, 'management/guest_form.html')

@require_POST
def submit_guest_form(request):
    if AdminSettings.load().maintenance_mode:
        return HttpResponse("System is under maintenance.", status=503)

    data = request.POST
    
    if data.get('nickname'):
        return HttpResponse("Spam detected", status=400)

    required_fields = ['last_name', 'first_name', 'address', 'phone', 'birth_date', 'gender']
    
    missing_fields = [field for field in required_fields if not data.get(field)]
    if missing_fields:
        return HttpResponse(f"Missing required fields: {', '.join(missing_fields)}", status=400)

    guest = GuestRegistration.objects.create(
        source=data.get('source', 'WALKIN'),
        last_name=data.get('last_name').upper(),
        first_name=data.get('first_name').upper(),
        address=data.get('address').upper(),
        phone=data.get('phone'),
        email=data.get('email'),
        car_plate=data.get('car_plate', '').upper() if data.get('car_plate') else None,
        birth_date=data.get('birth_date') or None,
        gender=data.get('gender'),
        security_deposit=1000,
        pax=1,
        nights=1,
        room_number='',
        check_in_date=None,
        check_in_time=None,
        check_out_date=None,
        check_out_time=None,
        notes=data.get('notes', '')
    )
    
    if request.headers.get('HX-Request'):
        response = render(request, 'management/partials/success_page_content.html')
    else:
        response = render(request, 'management/submission_success.html')
    
    response.set_signed_cookie('kegama_guest_id', str(guest.id), max_age=60*60*24*90) 
    return response

@ratelimit(key='ip', rate='5/10m', block=False)
def admin_login(request):
    was_limited = getattr(request, 'limited', False)
    if was_limited:
         return render(request, 'management/admin_login.html', {'error': 'Too many failed attempts. Please try again in 10 minutes.'})

    if request.method == 'POST':
        pin = request.POST.get('pin')
        settings_obj = AdminSettings.load()
        if pin == settings_obj.pin_code: 
            request.session['is_manager'] = True
            log_action(request, 'LOGIN', 'Admin logged in successfully')
            return redirect('dashboard')
        else:
            return render(request, 'management/admin_login.html', {'error': 'Invalid PIN'})
            
    return render(request, 'management/admin_login.html')

def dashboard(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    
    cleanup_expired_registrations()
    
    guests_query = GuestRegistration.objects.all().order_by('-created_at')
    
    query = request.GET.get('q')
    if query:
        guests_query = guests_query.filter(
            Q(first_name__icontains=query) | 
            Q(last_name__icontains=query) | 
            Q(room_number__icontains=query) |
            Q(booking_id__icontains=query)
        )

    today = timezone.now().date()
    
    stats = {
        'total': GuestRegistration.objects.count(),
        'active': GuestRegistration.objects.filter(status='PRINTED', check_out_date__gte=today).count(),
        'pending': GuestRegistration.objects.filter(status='PENDING').count(),
        'today_checkins': GuestRegistration.objects.filter(check_in_date=today).count(),
    }

    grouped_guests = {}
    for guest in guests_query:
        month_year = guest.created_at.strftime('%B %Y')
        if month_year not in grouped_guests:
            grouped_guests[month_year] = []
        grouped_guests[month_year].append(guest)
        
    audit_logs = AuditLog.objects.all().order_by('-timestamp')[:8]
    
    context = {
        'grouped_guests': grouped_guests, 
        'audit_logs': audit_logs,
        'search_query': query,
        'stats': stats
    }
    
    if request.headers.get('HX-Request'):
        return render(request, 'management/partials/guest_list.html', context)
        
    return render(request, 'management/dashboard.html', context)

def update_guest(request, guest_id):
    if not request.session.get('is_manager'):
        return redirect('admin_login')

    guest = get_object_or_404(GuestRegistration, id=guest_id)
    old_room_number = guest.room_number
    error = None

    if request.method == 'POST':
        guest.source = request.POST.get('source', 'WALKIN')
        guest.first_name = request.POST.get('first_name', '').upper()
        guest.last_name = request.POST.get('last_name', '').upper()
        guest.address = request.POST.get('address', '').upper()
        guest.phone = request.POST.get('phone')
        guest.email = request.POST.get('email')
        guest.car_plate = request.POST.get('car_plate', '').upper() if request.POST.get('car_plate') else None
        guest.birth_date = request.POST.get('birth_date') or None
        guest.gender = request.POST.get('gender')

        guest.pax = request.POST.get('pax', 1)
        guest.nights = request.POST.get('nights', 1)
        guest.stay_duration = request.POST.get('stay_duration', '')
        
        new_room_number = request.POST.get('room_number', '')
        guest.room_number = new_room_number
        room_rate_raw = request.POST.get('room_rate', '0').replace(',', '')
        guest.room_rate = float(room_rate_raw or 0)
        
        guest.mode_of_payment = request.POST.get('mode_of_payment', 'CASH')
        security_deposit_raw = request.POST.get('security_deposit', '0').replace(',', '')
        guest.security_deposit = float(security_deposit_raw or 0)
        
        req_items = request.POST.getlist('request_item[]')
        req_prices = request.POST.getlist('request_price[]')
        requests_list = []
        requests_total = 0
        for i, item in enumerate(req_items):
            if item.strip():
                try:
                    price_str = req_prices[i].replace(',', '') if i < len(req_prices) and req_prices[i] else '0'
                    price = float(price_str)
                except ValueError:
                    price = 0
                requests_list.append({'item': item.strip(), 'price': price})
                requests_total += price
        
        guest.additional_requests = json.dumps(requests_list)
        room_total = guest.room_rate * int(guest.nights or 1)
        guest.total_amount = room_total + requests_total
        
        cid = request.POST.get('check_in_date')
        if cid:
            try:
                guest.check_in_date = datetime.strptime(cid, '%Y-%m-%d').date()
            except ValueError:
                guest.check_in_date = None
        else:
            guest.check_in_date = None

        guest.check_in_time = request.POST.get('check_in_time') or None
        
        if guest.check_in_date:
            try:
                nights = int(guest.nights or 0)
                guest.check_out_date = guest.check_in_date + timedelta(days=nights)
            except (ValueError, TypeError):
                guest.check_out_date = guest.check_in_date
        
        guest.notes = request.POST.get('notes', '')
        
        required_fields = ['first_name', 'last_name', 'address', 'phone', 'birth_date', 'gender']
        missing = [f for f in required_fields if not getattr(guest, f)]
        
        if missing:
            error = "Please fill in all required fields: " + ", ".join([f.replace('_', ' ').title() for f in missing])
        else:
            if isinstance(guest.birth_date, str):
                try:
                    bdate = datetime.strptime(guest.birth_date, '%Y-%m-%d').date()
                    guest.birth_date = bdate
                except:
                    error = "Invalid birth date format."
            
            if not error and guest.birth_date:
                today = timezone.now().date()
                age = today.year - guest.birth_date.year - ((today.month, today.day) < (guest.birth_date.month, guest.birth_date.day))
                if age < 18:
                    error = f"Guest must be at least 18 years old. (Current Age: {age})"

        if not error:
            action = request.POST.get('action')
            is_activating = action == 'save_and_print'
            is_checking_out = action == 'checkout'
            
            if is_activating:
                guest.status = 'PRINTED'
            elif is_checking_out:
                guest.status = 'CHECKED_OUT'
            
            guest.save()

            if old_room_number and old_room_number != new_room_number:
                Room.objects.filter(number=old_room_number).update(status='AVAILABLE')
            
            if new_room_number:
                if guest.status == 'PRINTED':
                    today = timezone.now().date()
                    if guest.check_in_date and guest.check_out_date and guest.check_in_date <= today and guest.check_out_date > today:
                        Room.objects.filter(number=new_room_number).update(status='OCCUPIED')
                    else:
                        Room.objects.filter(number=new_room_number).update(status='AVAILABLE')
                elif guest.status == 'CHECKED_OUT':
                    Room.objects.filter(number=new_room_number).update(status='DIRTY')

            log_action(request, 'UPDATE_GUEST', f"Updated info for {guest.first_name} {guest.last_name} ({guest.status})")

            if is_activating:
                return redirect('generate_guest_pdf', guest_id=guest.id)
            
            return redirect('dashboard')

    try:
        current_requests = json.loads(guest.additional_requests)
    except:
        current_requests = []

    now = timezone.now()
    if not guest.check_in_date:
        guest.check_in_date = now.date()
    if not guest.check_in_time:
        guest.check_in_time = "14:00"
    if not guest.check_out_date:
        guest.check_out_date = (now + timedelta(days=1)).date()
    if not guest.check_out_time:
        guest.check_out_time = "12:00"

    today = timezone.now().date()
    occupied_today_rooms = GuestRegistration.objects.filter(
        status='PRINTED',
        check_in_date__lte=today,
        check_out_date__gt=today
    ).exclude(id=guest.id).values_list('room_number', flat=True)

    db_rooms = Room.objects.filter(
        ~Q(status='MAINTENANCE')
    ).exclude(
        Q(number__in=occupied_today_rooms) & ~Q(number=guest.room_number)
    ).order_by('floor', 'number')
    
    room_data = {}
    for room in db_rooms:
        if room.floor not in room_data:
            room_data[room.floor] = []
        room_data[room.floor].append({
            'id': room.number,
            'price': room.price,
            'price_6hr': room.price_6hr,
            'price_10hr': room.price_10hr,
            'capacity': room.capacity
        })

    conflict_warning = None
    if guest.room_number and guest.check_in_date and guest.check_out_date:
        overlapping_guests = GuestRegistration.objects.filter(
            room_number=guest.room_number,
            check_in_date__lt=guest.check_out_date,
            check_out_date__gt=guest.check_in_date
        ).exclude(id=guest.id).exclude(status='CHECKED_OUT')

        if overlapping_guests.exists():
            conflicts = [f"{g.first_name} {g.last_name} ({g.check_in_date} to {g.check_out_date})" for g in overlapping_guests]
            conflict_warning = f"Warning: Room {guest.room_number} has overlapping booking(s): {', '.join(conflicts)}"

    return render(request, 'management/update_guest.html', {
        'guest': guest, 
        'room_data': room_data,
        'current_requests': current_requests,
        'error': error,
        'conflict_warning': conflict_warning
    })

def delete_guest(request, guest_id):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    
    guest = get_object_or_404(GuestRegistration, id=guest_id)
    room_number = guest.room_number
    guest_name = f"{guest.first_name} {guest.last_name}"
    
    if room_number:
        Room.objects.filter(number=room_number).update(status='AVAILABLE')
    
    guest.delete()
    log_action(request, 'DELETE_GUEST', f"Deleted registration for {guest_name}")
    return redirect('dashboard')

def analytics_dashboard(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
        
    total_revenue = GuestRegistration.objects.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_guests = GuestRegistration.objects.count()
    
    today = timezone.now().date()
    guests_today = GuestRegistration.objects.filter(check_in_date=today).count()
    
    source_query = GuestRegistration.objects.values('source').annotate(count=Count('id'))
    source_data = list(source_query)
    
    filter_type = request.GET.get('filter', 'daily')
    chart_data = []
    
    if filter_type == 'weekly':
        start_date = timezone.now() - timedelta(weeks=52)
        chart_query = GuestRegistration.objects.filter(created_at__gte=start_date).annotate(
            date=TruncWeek('created_at')
        ).values('date').annotate(revenue=Sum('total_amount')).order_by('date')
        
    elif filter_type == 'monthly':
        start_date = timezone.now() - timedelta(days=365)
        chart_query = GuestRegistration.objects.filter(created_at__gte=start_date).annotate(
            date=TruncMonth('created_at')
        ).values('date').annotate(revenue=Sum('total_amount')).order_by('date')
        
    elif filter_type == 'yearly':
        start_date = timezone.now() - timedelta(days=365*5)
        chart_query = GuestRegistration.objects.filter(created_at__gte=start_date).annotate(
            date=TruncYear('created_at')
        ).values('date').annotate(revenue=Sum('total_amount')).order_by('date')
        
    else:
        start_date = timezone.now() - timedelta(days=30)
        chart_query = GuestRegistration.objects.filter(created_at__gte=start_date).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(revenue=Sum('total_amount')).order_by('date')
    
    chart_data = list(chart_query)
    
    max_revenue = 0
    if chart_data:
        max_revenue = max((d['revenue'] or 0) for d in chart_data)

    return render(request, 'management/analytics.html', {
        'total_revenue': total_revenue,
        'total_guests': total_guests,
        'guests_today': guests_today,
        'source_data': source_data,
        'daily_revenue': chart_data,
        'max_revenue': max_revenue,
        'current_filter': filter_type,
    })

def print_analytics(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    
    total_revenue = GuestRegistration.objects.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_guests = GuestRegistration.objects.count()
    
    last_year = timezone.now() - timedelta(days=365)
    monthly_query = GuestRegistration.objects.filter(
        created_at__gte=last_year
    ).annotate(
        month=TruncMonth('created_at')
    ).values('month').annotate(
        revenue=Sum('total_amount'),
        guests=Count('id')
    ).order_by('month')
    
    monthly_data = list(monthly_query)

    html_string = render_to_string('pdf/analytics_report.html', {
        'total_revenue': total_revenue,
        'total_guests': total_guests,
        'monthly_data': monthly_data,
        'generated_at': timezone.now(),
        'base_dir': settings.BASE_DIR,
    })
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="revenue_report_{timezone.now().date()}.pdf"'
    weasyprint.HTML(string=html_string, base_url=str(settings.BASE_DIR)).write_pdf(response)
    
    return response

def settings_page(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
        
    settings_obj = AdminSettings.load()
    error = None
    success = None
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'update_security':
            old_pin = request.POST.get('old_pin')
            new_pin = request.POST.get('new_pin')
            confirm_pin = request.POST.get('confirm_pin')
            
            if old_pin != settings_obj.pin_code:
                error = "Incorrect Old PIN"
            elif new_pin != confirm_pin:
                error = "New PINs do not match"
            elif len(new_pin) < 4:
                error = "PIN must be at least 4 digits"
            else:
                settings_obj.pin_code = new_pin
                settings_obj.save()
                log_action(request, 'UPDATE_SETTINGS', 'Changed Admin PIN')
                success = "PIN successfully updated!"

        elif action == 'update_config':
            settings_obj.maintenance_mode = request.POST.get('maintenance_mode') == 'on'
            settings_obj.form_access_code = request.POST.get('form_access_code', '').strip()
            settings_obj.save()
            log_action(request, 'UPDATE_SETTINGS', 'Updated Form Configuration')
            success = "Configuration updated!"
            
    return render(request, 'management/settings.html', {
        'error': error,
        'success': success,
        'settings': settings_obj
    })

def room_rack(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    
    active_guests = GuestRegistration.objects.filter(
        status__in=['PENDING', 'PRINTED']
    ).order_by('created_at')
    
    room_map = {guest.room_number: guest for guest in active_guests if guest.room_number}

    db_rooms = Room.objects.all().order_by('floor', 'number')
    rack_data = {}
    
    for room in db_rooms:
        if room.floor not in rack_data:
            rack_data[room.floor] = []
            
        r_id = room.number
        db_status = room.status
        display_status = db_status
        
        guest = room_map.get(r_id)
        guest_name = ''
        guest_id = ''
        
        if guest:
            guest_name = f"{guest.first_name} {guest.last_name}"
            guest_id = guest.id
            
            if guest.status == 'PENDING':
                display_status = 'PENDING'
            elif guest.status == 'PRINTED':
                display_status = 'OCCUPIED'
                today = timezone.now().date()
                if guest.check_in_date <= today and guest.check_out_date > today:
                    if db_status == 'AVAILABLE':
                        room.status = 'OCCUPIED'
                        room.save()
                else:
                    if db_status == 'OCCUPIED':
                        room.status = 'AVAILABLE'
                        room.save()
            
        rack_data[room.floor].append({
            'id': r_id,
            'price': room.price,
            'status': display_status,
            'guest_name': guest_name,
            'guest_id': guest_id,
            'is_advance': (guest.check_in_date > timezone.now().date()) if guest and guest.check_in_date else False
        })

    return render(request, 'management/room_rack.html', {
        'rack_data': rack_data
    })

@require_POST
def mark_room_clean(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
        
    room_id = request.POST.get('room_id')
    try:
        room = Room.objects.get(number=room_id)
        if room.status == 'DIRTY':
            room.status = 'AVAILABLE'
            room.save()
            log_action(request, 'HOUSEKEEPING', f"Marked Room {room_id} as Clean")
    except Room.DoesNotExist:
        pass
        
    return redirect(request.META.get('HTTP_REFERER', 'room_rack'))

def room_management(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    
    if request.method == 'POST':
        rooms = Room.objects.all()
        updated_count = 0
        
        for room in rooms:
            rid = room.number
            if f'price_{rid}' in request.POST:
                try:
                    room.price = float(request.POST.get(f'price_{rid}', '0').replace(',', '') or 0)
                    room.price_6hr = float(request.POST.get(f'price_6hr_{rid}', '0').replace(',', '') or 0)
                    room.price_10hr = float(request.POST.get(f'price_10hr_{rid}', '0').replace(',', '') or 0)
                    room.capacity = int(request.POST.get(f'capacity_{rid}', 1))
                    room.status = request.POST.get(f'status_{rid}', room.status)
                    room.save()
                    updated_count += 1
                except ValueError:
                    continue
        
        if updated_count > 0:
            log_action(request, 'UPDATE_ROOMS', f"Bulk updated {updated_count} rooms")
        
        return redirect('room_management')

    rooms = Room.objects.all().order_by('floor', 'number')
    grouped_rooms = {}
    for room in rooms:
        floor_name = room.floor
        if floor_name not in grouped_rooms:
            grouped_rooms[floor_name] = []
        grouped_rooms[floor_name].append(room)
    
    room_stats = {
        'total': Room.objects.count(),
        'available': Room.objects.filter(status='AVAILABLE').count(),
        'occupied': Room.objects.filter(status='OCCUPIED').count(),
        'maintenance': Room.objects.filter(status='MAINTENANCE').count(),
    }

    return render(request, 'management/manage_rooms.html', {
        'grouped_rooms': grouped_rooms,
        'room_stats': room_stats
    })

def calendar_view(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    
    today = timezone.now().date()
    year = int(request.GET.get('year', today.year))
    month = int(request.GET.get('month', today.month))
    
    num_days = py_calendar.monthrange(year, month)[1]
    first_day = date(year, month, 1)
    last_day = date(year, month, num_days)
    days_range = [date(year, month, d) for d in range(1, num_days + 1)]
    
    rooms = Room.objects.all().order_by('floor', 'number')
    
    guests = GuestRegistration.objects.filter(
        check_in_date__lte=last_day,
        check_out_date__gte=first_day
    ).exclude(status='CHECKED_OUT').exclude(room_number='')

    booking_map = {}
    for guest in guests:
        if guest.room_number not in booking_map:
            booking_map[guest.room_number] = []
        
        is_nightly = '22' in str(guest.stay_duration)
        
        if is_nightly:
            last_night = guest.check_out_date
        else:
            if guest.check_in_date == guest.check_out_date:
                last_night = guest.check_in_date
            else:
                last_night = guest.check_out_date - timedelta(days=1)
        
        guest.start_date = guest.check_in_date
        guest.end_night = last_night
        booking_map[guest.room_number].append(guest)

    for room in rooms:
        room.is_occupied_today = False
        if room.number in booking_map:
            for g in booking_map[room.number]:
                # Room is occupied if today is within the range [check_in, check_out]
                if g.check_in_date <= today and today <= g.end_night:
                    room.is_occupied_today = True
                    break
        
    context = {
        'days_range': days_range,
        'rooms': rooms,
        'current_month': first_day,
        'today': today,
        'booking_map': booking_map,
        'prev_month': (first_day - timedelta(days=1)),
        'next_month': (last_day + timedelta(days=1)),
    }
    
    return render(request, 'management/calendar.html', context)

def print_timeline(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    
    year = int(request.GET.get('year', timezone.now().year))
    month = int(request.GET.get('month', timezone.now().month))
    
    first_day = date(year, month, 1)
    num_days = py_calendar.monthrange(year, month)[1]
    last_day = date(year, month, num_days)
    days_range = [date(year, month, d) for d in range(1, num_days + 1)]
    
    rooms = Room.objects.all().order_by('floor', 'number')
    guests = GuestRegistration.objects.filter(
        check_in_date__lte=last_day,
        check_out_date__gte=first_day
    ).exclude(status='CHECKED_OUT').exclude(room_number='')

    booking_map = {}
    for guest in guests:
        if guest.room_number not in booking_map:
            booking_map[guest.room_number] = []
        
        is_nightly = '22' in str(guest.stay_duration)
        
        if is_nightly:
            last_night = guest.check_out_date
        else:
            if guest.check_in_date == guest.check_out_date:
                last_night = guest.check_in_date
            else:
                last_night = guest.check_out_date - timedelta(days=1)
        
        guest.start_date = guest.check_in_date
        guest.end_night = last_night
        booking_map[guest.room_number].append(guest)

    html_string = render_to_string('pdf/timeline_report.html', {
        'days_range': days_range,
        'rooms': rooms,
        'booking_map': booking_map,
        'current_month': first_day,
        'base_dir': settings.BASE_DIR,
        'generated_at': timezone.now()
    })
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="timeline_{year}_{month}.pdf"'
    weasyprint.HTML(string=html_string, base_url=str(settings.BASE_DIR)).write_pdf(response)
    
    return response

def new_booking(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
        
    pre_room = request.GET.get('room', '')
    pre_date = request.GET.get('date', None)
    
    guest = GuestRegistration.objects.create(
        first_name='NEW',
        last_name='GUEST',
        status='PENDING',
        room_number=pre_room,
        check_in_date=pre_date,
        pax=1,
        nights=1
    )
    return redirect('update_guest', guest_id=guest.id)

def guest_lookup_page(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    return render(request, 'management/guest_lookup.html')

def clone_guest(request, guest_id):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
        
    source_guest = get_object_or_404(GuestRegistration, id=guest_id)
    
    new_guest = GuestRegistration.objects.create(
        first_name=source_guest.first_name,
        last_name=source_guest.last_name,
        address=source_guest.address,
        phone=source_guest.phone,
        email=source_guest.email,
        car_plate=source_guest.car_plate,
        birth_date=source_guest.birth_date,
        gender=source_guest.gender,
        status='PENDING',
        nights=1,
        pax=1
    )
    
    log_action(request, 'CLONE_GUEST', f"Cloned guest {source_guest.first_name} {source_guest.last_name}")
    return redirect('update_guest', guest_id=new_guest.id)

def search_guests(request):
    if not request.session.get('is_manager'):
        return HttpResponse("", status=403)
        
    query = request.GET.get('q', '').strip()
    if len(query) < 2:
        return HttpResponse("")
        
    guests = GuestRegistration.objects.filter(
        Q(first_name__icontains=query) | 
        Q(last_name__icontains=query) |
        Q(phone__icontains=query)
    ).values('id', 'first_name', 'last_name', 'phone', 'address', 'created_at').order_by('-created_at')[:10]
    
    seen = set()
    unique_guests = []
    for g in guests:
        key = (g['first_name'], g['last_name'], g['phone'])
        if key not in seen:
            seen.add(key)
            unique_guests.append(g)
    
    if not unique_guests:
        return HttpResponse('<div class="p-6 text-center text-xs font-bold text-gray-400 uppercase tracking-widest bg-white rounded-xl border border-dashed border-gray-200">No guests found</div>')
        
    html = ""
    for g in unique_guests:
        clone_url = reverse('clone_guest', args=[g['id']])
        html += f"""
        <a href="{clone_url}" class="block bg-white p-4 rounded-xl border border-gray-100 shadow-sm hover:shadow-md hover:border-orange-200 transition-all group">
            <div class="flex justify-between items-center">
                <div>
                    <h3 class="font-black text-sm text-gray-900 uppercase group-hover:text-orange-600 transition-colors">{g['first_name']} {g['last_name']}</h3>
                    <p class="text-[10px] font-bold text-gray-400 mt-1">{g['address']}</p>
                </div>
                <div class="text-right">
                    <div class="text-[10px] font-mono font-bold text-gray-500">{g['phone']}</div>
                    <span class="text-[9px] font-bold text-orange-500 uppercase tracking-wider opacity-0 group-hover:opacity-100 transition-opacity">Select &rarr;</span>
                </div>
            </div>
        </a>
        """
    return HttpResponse(html)

def generate_guest_pdf(request, guest_id):
    if not request.session.get('is_manager'):
        return redirect('admin_login')

    guest = get_object_or_404(GuestRegistration, id=guest_id)
    log_action(request, 'PRINT_PDF', f"Generated PDF for {guest.first_name} {guest.last_name}")
    
    try:
        requests_list = json.loads(guest.additional_requests)
    except:
        requests_list = []

    room_rate = float(guest.room_rate or 0)
    nights = int(guest.nights or 1)
    room_total = room_rate * nights
    requests_total = sum(float(r.get('price', 0)) for r in requests_list)
    grand_total = room_total + requests_total

    settings_obj = AdminSettings.load()

    html_string = render_to_string('pdf/guest_registration.html', {
        'guest': guest,
        'base_dir': settings.BASE_DIR,
        'requests_list': requests_list,
        'room_total': room_total,
        'requests_total': requests_total,
        'grand_total': grand_total,
        'now': timezone.now(),
        'policy_text': settings_obj.policy_text
    })
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="guest_{guest.id}.pdf"'
    weasyprint.HTML(string=html_string, base_url=str(settings.BASE_DIR)).write_pdf(response)
    
    return response