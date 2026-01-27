from django.urls import path
from . import views

app_name = 'payslip'

urlpatterns = [
    path('', views.index, name='index'),
    path('add/', views.add_employee, name='add_employee'),
    path('remove/<uuid:employee_id>/', views.remove_employee, name='remove_employee'),
    path('generate/<uuid:employee_id>/', views.generate_payslip, name='generate'),
    path('preview/', views.save_and_preview, name='preview'),
    path('save/', views.save_payslip, name='save'),
    path('print-all/', views.print_all_employees, name='print_all'),
]