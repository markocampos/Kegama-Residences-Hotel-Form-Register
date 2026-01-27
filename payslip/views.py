from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.utils import timezone
from .models import Employee, Payslip

def index(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    if not request.session.get('is_owner'):
        return redirect('dashboard')
    employees = Employee.objects.all()
    return render(request, 'payslip/employee_list.html', {'employees': employees})

def add_employee(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    if not request.session.get('is_owner'):
        return redirect('dashboard')
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        position = request.POST.get('position')
        
        if first_name and last_name:
            Employee.objects.create(
                first_name=first_name,
                last_name=last_name,
                position=position
            )
            messages.success(request, 'Employee added successfully.')
        else:
            messages.error(request, 'Please fill in all fields.')
            
    return redirect('payslip:index')

def remove_employee(request, employee_id):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    if not request.session.get('is_owner'):
        return redirect('dashboard')
    if request.method == 'POST':
        employee = get_object_or_404(Employee, id=employee_id)
        employee.delete()
        messages.success(request, 'Employee removed successfully.')
    return redirect('payslip:index')

def generate_payslip(request, employee_id):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    if not request.session.get('is_owner'):
        return redirect('dashboard')
    employee = get_object_or_404(Employee, id=employee_id)
    last_payslip = Payslip.objects.filter(employee=employee).order_by('-pay_date').first()
    return render(request, 'payslip/generate.html', {
        'employee': employee,
        'payslip': last_payslip
    })

def save_payslip(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    if not request.session.get('is_owner'):
        return redirect('dashboard')
    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        employee = get_object_or_404(Employee, id=employee_id)
        
        def get_float(key):
            try:
                val = request.POST.get(key, '0').replace(',', '')
                return float(val or 0)
            except ValueError:
                return 0.0

        pay_period = request.POST.get('pay_period')
        pay_date = request.POST.get('pay_date') or timezone.now().date()

        # Handle duplicates: find all matches, update the first/latest, delete others
        existing_slips = Payslip.objects.filter(
            employee=employee,
            pay_period=pay_period,
            pay_date=pay_date
        )
        
        defaults = {
            'earning_regular': get_float('earning_regular'),
            'earning_holiday': get_float('earning_holiday'),
            'earning_overtime': get_float('earning_overtime'),
            'earning_allowances': get_float('earning_allowances'),
            'earning_13th': get_float('earning_13th'),
            'earning_other': get_float('earning_other'),
            'deduction_sss': get_float('deduction_sss'),
            'deduction_philhealth': get_float('deduction_philhealth'),
            'deduction_pagibig': get_float('deduction_pagibig'),
            'deduction_tax': get_float('deduction_tax'),
            'deduction_cashadv': get_float('deduction_cashadv'),
            'deduction_other': get_float('deduction_other'),
        }

        if existing_slips.exists():
            # Update the first one
            payslip = existing_slips.first()
            for key, value in defaults.items():
                setattr(payslip, key, value)
            payslip.save()
            
            # Delete duplicates if any
            if existing_slips.count() > 1:
                existing_slips.exclude(id=payslip.id).delete()
        else:
            # Create new
            Payslip.objects.create(
                employee=employee,
                pay_period=pay_period,
                pay_date=pay_date,
                **defaults
            )

        messages.success(request, f'Payslip for {employee.first_name} saved successfully.')
        
    # Redirect back to the employee list
    return redirect('payslip:index')

def save_and_preview(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    if not request.session.get('is_owner'):
        return redirect('dashboard')
    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        employee = get_object_or_404(Employee, id=employee_id)
        
        def get_float(key):
            try:
                val = request.POST.get(key, '0').replace(',', '')
                return float(val or 0)
            except ValueError:
                return 0.0

        pay_period = request.POST.get('pay_period')
        pay_date = request.POST.get('pay_date') or timezone.now().date()

        payslip = Payslip.objects.create(
            employee=employee,
            pay_period=pay_period,
            pay_date=pay_date,
            earning_regular=get_float('earning_regular'),
            earning_holiday=get_float('earning_holiday'),
            earning_overtime=get_float('earning_overtime'),
            earning_allowances=get_float('earning_allowances'),
            earning_13th=get_float('earning_13th'),
            earning_other=get_float('earning_other'),
            deduction_sss=get_float('deduction_sss'),
            deduction_philhealth=get_float('deduction_philhealth'),
            deduction_pagibig=get_float('deduction_pagibig'),
            deduction_tax=get_float('deduction_tax'),
            deduction_cashadv=get_float('deduction_cashadv'),
            deduction_other=get_float('deduction_other'),
        )
        
        context = {
            'employee_id': str(employee.id),
            'employee_name': f"{employee.last_name}, {employee.first_name}",
            'position': employee.position,
            'period': payslip.pay_period,
            'date': payslip.pay_date,
            'earnings': {
                'Regular': payslip.earning_regular,
                'Holiday': payslip.earning_holiday,
                'Overtime': payslip.earning_overtime,
                'Allowances': payslip.earning_allowances,
                '13th Mo.': payslip.earning_13th,
                'Other': payslip.earning_other,
            },
            'deductions': {
                'SSS': payslip.deduction_sss,
                'PhilHealth': payslip.deduction_philhealth,
                'Pag-IBIG': payslip.deduction_pagibig,
                'Tax': payslip.deduction_tax,
                'Cash Adv.': payslip.deduction_cashadv,
                'Other': payslip.deduction_other,
            },
            'total_earnings': payslip.total_earnings,
            'total_deductions': payslip.total_deductions,
            'net_pay': payslip.net_pay,
        }
        return render(request, 'payslip/print_view.html', context)
    return redirect('payslip:index')

def print_all_employees(request):
    if not request.session.get('is_manager'):
        return redirect('admin_login')
    if not request.session.get('is_owner'):
        return redirect('dashboard')
    employees = Employee.objects.all()
    
    # Get all unique pay periods for the filter dropdown
    available_periods = Payslip.objects.values_list('pay_period', flat=True).distinct().order_by('-created_at')
    # Remove duplicates (distinct on values_list can be tricky with order_by depending on DB)
    available_periods = list(dict.fromkeys(available_periods)) 

    selected_period = request.GET.get('period')
    
    employee_data = []
    grand_total = 0
    for emp in employees:
        if selected_period:
            # If a period is selected, try to find the specific slip for that period
            payslip = Payslip.objects.filter(employee=emp, pay_period=selected_period).first()
        else:
            # Default to the absolute latest one if no filter is applied
            payslip = Payslip.objects.filter(employee=emp).order_by('-pay_date').first()
            
        if payslip:
            grand_total += float(payslip.net_pay)

        employee_data.append({
            'employee': emp,
            'payslip': payslip
        })
        
    return render(request, 'payslip/print_all.html', {
        'employee_data': employee_data,
        'available_periods': available_periods,
        'selected_period': selected_period,
        'grand_total': grand_total
    })
