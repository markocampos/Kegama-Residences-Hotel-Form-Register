import os
from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.conf import settings

ADMIN_URL = os.environ.get('ADMIN_URL', 'admin/').strip('/') + '/'

def service_worker(request):
    sw_path = os.path.join(settings.BASE_DIR, 'static/sw.js')
    try:
        with open(sw_path, 'r') as f:
            content = f.read()
        return HttpResponse(content, content_type='application/javascript')
    except FileNotFoundError:
        return HttpResponse("Service Worker not found", status=404)


PAYSLIP_URL = os.environ.get('PAYSLIP_URL', 'payslip/').strip('/') + '/'

urlpatterns = [
    path('sw.js', service_worker, name='service_worker'),
    path(ADMIN_URL, admin.site.urls),
    path(PAYSLIP_URL, include('payslip.urls')),
    path('', include('management.urls')),
]
