import weasyprint
import json
from django.conf import settings
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from django.template.loader import render_to_string
from .models import GuestRegistration, AuditLog
from django.views.decorators.http import require_POST
from django.urls import reverse
from django_ratelimit.decorators import ratelimit
from django.utils import timezone
from datetime import timedelta

# ROOM DATA CONFIGURATION
ROOM_DATA = {
    '1st Floor': [
        {'id': '1A', 'price': 2350},
        {'id': '1B', 'price': 2050},
        {'id': '1C', 'price': 2450},
        {'id': '1D', 'price': 1750},
    ],
    '2nd Floor': [
        {'id': '2A', 'price': 1115},
        {'id': '2B', 'price': 1115},
        {'id': '2C', 'price': 1115},
        {'id': '2D', 'price': 1115},
        {'id': '2E', 'price': 1115},
        {'id': '2F', 'price': 1115},
        {'id': '2G', 'price': 2250},
        {'id': '2H', 'price': 1450},
    ],
    '3rd Floor': [
        {'id': '3A', 'price': 1115},
        {'id': '3B', 'price': 1115},
        {'id': '3C', 'price': 1115},
        {'id': '3D', 'price': 1115},
        {'id': '3E', 'price': 1115},
        {'id': '3F', 'price': 1115},
        {'id': '3G', 'price': 2350},
        {'id': '3H', 'price': 1450},
    ]
}

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

from django.db.models import Sum, Count, F
from django.db.models.functions import TruncMonth, TruncDate

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
        guest.room_rate = float(request.POST.get('room_rate') or 0)
        
        # Financials
        guest.discount_percent = float(request.POST.get('discount_percent') or 0)
        guest.security_deposit = request.POST.get('security_deposit') or 0
        
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
        discount_amount = room_total * (guest.discount_percent / 100)
        guest.total_amount = room_total - discount_amount + requests_total

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

    return render(request, 'management/update_guest.html', {
        'guest': guest, 
        'room_data': ROOM_DATA,
        'current_requests': current_requests
    })

def analytics_dashboard(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
        
    # Summary Stats
    total_revenue = GuestRegistration.objects.aggregate(Sum('total_amount'))['total_amount__sum'] or 0
    total_guests = GuestRegistration.objects.count()
    
    # Source Breakdown
    source_query = GuestRegistration.objects.values('source').annotate(count=Count('id'))
    source_data = list(source_query)
    
    # Daily Revenue (Last 31 days)
    last_month = timezone.now() - timedelta(days=31)
    daily_query = GuestRegistration.objects.filter(
        created_at__gte=last_month
    ).annotate(
        date=TruncDate('created_at')
    ).values('date').annotate(
        revenue=Sum('total_amount')
    ).order_by('date')
    
    daily_data = list(daily_query)
    
    # Calculate Max Revenue for Chart Scaling
    max_revenue = 0
    if daily_data:
        max_revenue = max((d['revenue'] or 0) for d in daily_data)

    return render(request, 'management/analytics.html', {
        'total_revenue': total_revenue,
        'total_guests': total_guests,
        'source_data': source_data,
        'daily_revenue': daily_data,
        'max_revenue': max_revenue,
    })

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
    
    discount_percent = float(guest.discount_percent or 0)
    discount_amount = room_total * (discount_percent / 100)
    
    requests_total = sum(float(r.get('price', 0)) for r in requests_list)
    
    grand_total = room_total - discount_amount + requests_total

    html_string = render_to_string('pdf/guest_registration.html', {
        'guest': guest,
        'base_dir': settings.BASE_DIR,
        'requests_list': requests_list,
        'room_total': room_total,
        'discount_amount': discount_amount,
        'requests_total': requests_total,
        'grand_total': grand_total,
        'now': timezone.now()
    })
    
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="guest_{guest.id}.pdf"'
    weasyprint.HTML(string=html_string, base_url=str(settings.BASE_DIR)).write_pdf(response)
    
    return response