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
    path(f'{MGMT_PREFIX}analytics/', views.analytics_dashboard, name='analytics_dashboard'),
    path(f'{MGMT_PREFIX}settings/', views.settings_page, name='settings_page'),
    path(f'{MGMT_PREFIX}update/<uuid:guest_id>/', views.update_guest, name='update_guest'),
    path(f'{MGMT_PREFIX}pdf/<uuid:guest_id>/', views.generate_guest_pdf, name='generate_guest_pdf'),
]
