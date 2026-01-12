import weasyprint
import json
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.template.loader import render_to_string
from .models import GuestRegistration, AuditLog, Room
from django.views.decorators.http import require_POST
from django.urls import reverse
from django_ratelimit.decorators import ratelimit
from django.utils import timezone
from datetime import timedelta
import json

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
    from .models import AdminSettings
    settings_obj = AdminSettings.load()

    # 1. Maintenance Mode Check
    if settings_obj.maintenance_mode:
        return render(request, 'management/maintenance.html')

    # 2. Access Code Check
    if settings_obj.form_access_code:
        # Check if user has already entered the code
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
    # Ensure maintenance mode is respected even on direct POST
    from .models import AdminSettings
    if AdminSettings.load().maintenance_mode:
        return HttpResponse("System is under maintenance.", status=503)

    data = request.POST
    
    # Honeypot Check (Anti-Bot)
    if data.get('nickname'):
        # Log this event if logging was set up
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
    
    response = render(request, 'management/submission_success.html')
    response.set_signed_cookie('kegama_guest_id', str(guest.id), max_age=60*60*24*90) 
    return response

@ratelimit(key='ip', rate='5/10m', block=False)
def admin_login(request):
    was_limited = getattr(request, 'limited', False)
    if was_limited:
         return render(request, 'management/admin_login.html', {'error': 'Too many failed attempts. Please try again in 10 minutes.'})

    from .models import AdminSettings
    if request.method == 'POST':
        pin = request.POST.get('pin')
        settings = AdminSettings.load()
        if pin == settings.pin_code: 
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
    guests = GuestRegistration.objects.all().order_by('-created_at')
    audit_logs = AuditLog.objects.all()[:5]
    
    if request.headers.get('HX-Request'):
        return render(request, 'management/partials/guest_list.html', {'guests': guests})
        
    return render(request, 'management/dashboard.html', {'guests': guests, 'audit_logs': audit_logs})

from django.db.models import Sum, Count, F, Q
from django.db.models.functions import TruncMonth, TruncDate, TruncWeek, TruncYear

def update_guest(request, guest_id):
    if not request.session.get('is_manager'):
        return redirect('admin_login')

    guest = get_object_or_404(GuestRegistration, id=guest_id)

    if request.method == 'POST':
        guest.first_name = request.POST.get('first_name').upper()
        guest.last_name = request.POST.get('last_name').upper()
        guest.address = request.POST.get('address').upper()
        guest.phone = request.POST.get('phone')
        guest.email = request.POST.get('email')

        guest.pax = request.POST.get('pax')
        guest.nights = request.POST.get('nights')
        
        # Room Data
        guest.room_number = request.POST.get('room_number')
        room_rate_raw = request.POST.get('room_rate', '0').replace(',', '')
        guest.room_rate = float(room_rate_raw or 0)
        
        # Financials
        guest.mode_of_payment = request.POST.get('mode_of_payment')
        security_deposit_raw = request.POST.get('security_deposit', '0').replace(',', '')
        guest.security_deposit = float(security_deposit_raw or 0)
        
        # Requests processing
        req_items = request.POST.getlist('request_item[]')
        req_prices = request.POST.getlist('request_price[]')
        requests = []
        requests_total = 0
        for i, item in enumerate(req_items):
            if item.strip():
                try:
                    price = float(req_prices[i]) if i < len(req_prices) and req_prices[i] else 0
                except ValueError:
                    price = 0
                requests.append({'item': item.strip(), 'price': price})
                requests_total += price
        
        guest.additional_requests = json.dumps(requests)
        
        # Calculate Total Amount
        room_total = guest.room_rate * int(guest.nights or 1)
        guest.total_amount = room_total + requests_total

        guest.check_in_date = request.POST.get('check_in_date') or None
        guest.check_in_time = request.POST.get('check_in_time') or None
        guest.check_out_date = request.POST.get('check_out_date') or None
        guest.check_out_time = request.POST.get('check_out_time') or None
        guest.notes = request.POST.get('notes', '')
        
        guest.save()

        log_action(request, 'UPDATE_GUEST', f"Updated info for {guest.first_name} {guest.last_name}")

        if request.POST.get('action') == 'save_and_print':
            guest.status = 'PRINTED'
            guest.save()
            return redirect('generate_guest_pdf', guest_id=guest.id)
        
        return redirect('dashboard')

    # Parse requests for template if needed
    try:
        current_requests = json.loads(guest.additional_requests)
    except:
        current_requests = []

    # POLICY: Auto-fill dates if missing
    now = timezone.now()
    if not guest.check_in_date:
        guest.check_in_date = now.date()
    if not guest.check_in_time:
        guest.check_in_time = "14:00" # Policy 2PM
    if not guest.check_out_date:
        guest.check_out_date = (now + timedelta(days=1)).date()
    if not guest.check_out_time:
        guest.check_out_time = "12:00" # Policy 12NN

    # Fetch Rooms from Database for Dropdown
    # Filter out MAINTENANCE or OCCUPIED rooms unless it is the guest's current room
    db_rooms = Room.objects.filter(
        Q(status='AVAILABLE') | Q(number=guest.room_number)
    ).order_by('floor', 'number')
    
    room_data = {}
    for room in db_rooms:
        if room.floor not in room_data:
            room_data[room.floor] = []
        room_data[room.floor].append({
            'id': room.number,
            'price': room.price,
            'capacity': room.capacity
        })

    return render(request, 'management/update_guest.html', {
        'guest': guest, 
        'room_data': room_data,
        'current_requests': current_requests
    })

def analytics_dashboard(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
        
    # Summary Stats
    total_revenue = GuestRegistration.objects.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_guests = GuestRegistration.objects.count()
    
    # Guests of the Day
    today = timezone.now().date()
    guests_today = GuestRegistration.objects.filter(created_at__date=today).count()
    
    # Source Breakdown
    source_query = GuestRegistration.objects.values('source').annotate(count=Count('id'))
    source_data = list(source_query)
    
    # Chart Data Filtering
    filter_type = request.GET.get('filter', 'daily')
    chart_data = []
    
    if filter_type == 'weekly':
        # Last 52 weeks
        start_date = timezone.now() - timedelta(weeks=52)
        chart_query = GuestRegistration.objects.filter(created_at__gte=start_date).annotate(
            date=TruncWeek('created_at')
        ).values('date').annotate(revenue=Sum('total_amount')).order_by('date')
        
    elif filter_type == 'monthly':
        # Last 12 months
        start_date = timezone.now() - timedelta(days=365)
        chart_query = GuestRegistration.objects.filter(created_at__gte=start_date).annotate(
            date=TruncMonth('created_at')
        ).values('date').annotate(revenue=Sum('total_amount')).order_by('date')
        
    elif filter_type == 'yearly':
        # Last 5 years
        start_date = timezone.now() - timedelta(days=365*5)
        chart_query = GuestRegistration.objects.filter(created_at__gte=start_date).annotate(
            date=TruncYear('created_at')
        ).values('date').annotate(revenue=Sum('total_amount')).order_by('date')
        
    else: # daily (default)
        # Last 30 days only for readability, or use scroll
        start_date = timezone.now() - timedelta(days=30)
        chart_query = GuestRegistration.objects.filter(created_at__gte=start_date).annotate(
            date=TruncDate('created_at')
        ).values('date').annotate(revenue=Sum('total_amount')).order_by('date')
    
    chart_data = list(chart_query)
    
    # Calculate Max Revenue for Chart Scaling
    max_revenue = 0
    if chart_data:
        max_revenue = max((d['revenue'] or 0) for d in chart_data)

    return render(request, 'management/analytics.html', {
        'total_revenue': total_revenue,
        'total_guests': total_guests,
        'guests_today': guests_today,
        'source_data': source_data,
        'daily_revenue': chart_data, # Passed as daily_revenue for compatibility with template
        'max_revenue': max_revenue,
        'current_filter': filter_type,
    })

def print_analytics(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    
    # Yearly Summary Stats
    total_revenue = GuestRegistration.objects.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_guests = GuestRegistration.objects.count()
    
    # Monthly Breakdown (Last 12 Months)
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
        
    from .models import AdminSettings
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
    
    # Fetch all guests
    # In a real scenario, you might filter out 'checked-out' guests if you had that status.
    # For now, we map the latest registration for each room.
    guests = GuestRegistration.objects.all().order_by('created_at')
    
    room_map = {}
    for guest in guests:
        if guest.room_number:
            room_map[guest.room_number] = guest

    # Fetch Rooms from DB
    db_rooms = Room.objects.all().order_by('floor', 'number')
    rack_data = {}
    
    for room in db_rooms:
        if room.floor not in rack_data:
            rack_data[room.floor] = []
            
        r_id = room.number
        status = room.status # AVAILABLE, OCCUPIED, MAINTENANCE
        
        guest = room_map.get(r_id)
        guest_name = ''
        guest_id = ''
        
        if status == 'OCCUPIED' and guest:
             guest_name = f"{guest.first_name} {guest.last_name}"
             guest_id = guest.id
        elif guest and guest.status == 'PENDING':
             status = 'PENDING'
             guest_name = f"{guest.first_name} {guest.last_name}"
             guest_id = guest.id
            
        rack_data[room.floor].append({
            'id': r_id,
            'price': room.price,
            'status': status,
            'guest_name': guest_name,
            'guest_id': guest_id
        })

    return render(request, 'management/room_rack.html', {
        'rack_data': rack_data
    })

def room_management(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    
    from .models import Room

    if request.method == 'POST':
        room_id = request.POST.get('room_id')
        price_raw = request.POST.get('price', '0').replace(',', '')
        price = float(price_raw or 0)
        capacity = request.POST.get('capacity')
        status = request.POST.get('status')
        
        try:
            room = Room.objects.get(number=room_id)
            room.price = price
            room.capacity = capacity
            room.status = status
            room.save()
            log_action(request, 'UPDATE_ROOM', f"Updated Room {room_id}")
        except Room.DoesNotExist:
            pass
        
        return redirect('room_management')

    # Group rooms by floor
    rooms = Room.objects.all().order_by('floor', 'number')
    grouped_rooms = {}
    for room in rooms:
        if room.floor not in grouped_rooms:
            grouped_rooms[room.floor] = []
        grouped_rooms[room.floor].append(room)

    return render(request, 'management/manage_rooms.html', {
        'grouped_rooms': grouped_rooms
    })

def generate_guest_pdf(request, guest_id):
    if not request.session.get('is_manager'):
        return redirect('admin_login')

    guest = get_object_or_404(GuestRegistration, id=guest_id)
    
    log_action(request, 'PRINT_PDF', f"Generated PDF for {guest.first_name} {guest.last_name}")
    
    # Calculate Financials
    try:
        requests_list = json.loads(guest.additional_requests)
    except:
        requests_list = []

    room_rate = float(guest.room_rate or 0)
    nights = int(guest.nights or 1)
    room_total = room_rate * nights
    
    requests_total = sum(float(r.get('price', 0)) for r in requests_list)
    
    grand_total = room_total + requests_total

    html_string = render_to_string('pdf/guest_registration.html', {
        'guest': guest,
        'base_dir': settings.BASE_DIR,
        'requests_list': requests_list,
        'room_total': room_total,
        'requests_total': requests_total,
        'grand_total': grand_total,
        'now': timezone.now()
    })
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="guest_{guest.id}.pdf"'
    weasyprint.HTML(string=html_string, base_url=str(settings.BASE_DIR)).write_pdf(response)
    
    return response