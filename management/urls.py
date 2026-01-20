from django.urls import path
from . import views
import os

MGMT_PREFIX = os.environ.get('MANAGEMENT_URL_PREFIX', 'mgmt').strip('/') + '/'

urlpatterns = [
    # Guest Routes
    path('', views.intro, name='intro'), # Landing Page
    path('register/', views.guest_form_page, name='guest_form_page'),
    path('submit/', views.submit_guest_form, name='submit_guest_form'),
    
    # Management Routes
    path(f'{MGMT_PREFIX}login/', views.admin_login, name='admin_login'),
    path(f'{MGMT_PREFIX}dashboard/', views.dashboard, name='dashboard'),
    path(f'{MGMT_PREFIX}rooms/', views.room_rack, name='room_rack'),
    path(f'{MGMT_PREFIX}rooms/manage/', views.room_management, name='room_management'),
    path(f'{MGMT_PREFIX}analytics/', views.analytics_dashboard, name='analytics_dashboard'),
    path(f'{MGMT_PREFIX}analytics/print/', views.print_analytics, name='print_analytics'),
    path(f'{MGMT_PREFIX}settings/', views.settings_page, name='settings_page'),
    path(f'{MGMT_PREFIX}calendar/', views.calendar_view, name='calendar_view'),
    path(f'{MGMT_PREFIX}calendar/print/', views.print_timeline, name='print_timeline'),
    path(f'{MGMT_PREFIX}booking/new/', views.new_booking, name='new_booking'),
    path(f'{MGMT_PREFIX}update/<uuid:guest_id>/', views.update_guest, name='update_guest'),
    path(f'{MGMT_PREFIX}delete/<uuid:guest_id>/', views.delete_guest, name='delete_guest'),
    path(f'{MGMT_PREFIX}pdf/<uuid:guest_id>/', views.generate_guest_pdf, name='generate_guest_pdf'),

]
