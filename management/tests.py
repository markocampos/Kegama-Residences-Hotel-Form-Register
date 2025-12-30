from django.test import TestCase, Client
from django.urls import reverse
from django.core.cache import cache
from .models import GuestRegistration, AdminSettings, AuditLog
import uuid

class GuestRegistrationModelTest(TestCase):
    def test_create_guest(self):
        guest = GuestRegistration.objects.create(
            first_name="John",
            last_name="Doe",
            address="123 Main St",
            phone="1234567890",
            email="john@example.com",
            birth_date="1990-01-01",
            gender="Male"
        )
        self.assertIsInstance(guest.id, uuid.UUID)
        self.assertEqual(guest.status, 'PENDING')
        self.assertTrue(guest.booking_id) # Should be auto-generated

class GeneralTests(TestCase):
    def test_service_worker_served_at_root(self):
        client = Client()
        response = client.get('/sw.js')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/javascript')

class GuestViewsTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.register_url = reverse('guest_form_page')
        self.submit_url = reverse('submit_guest_form')

    def test_guest_form_page(self):
        response = self.client.get(self.register_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'management/guest_form.html')

    def test_submit_valid_form(self):
        data = {
            'first_name': 'Jane',
            'last_name': 'Doe',
            'address': '456 Oak St',
            'phone': '9876543210',
            'email': 'jane@example.com',
            'birth_date': '1992-02-02',
            'gender': 'Female',
            'source': 'WALKIN'
        }
        response = self.client.post(self.submit_url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'management/submission_success.html')
        
        # Check cookie
        self.assertIn('kegama_guest_id', response.cookies)
        
        # Check DB
        self.assertEqual(GuestRegistration.objects.count(), 1)
        guest = GuestRegistration.objects.first()
        self.assertEqual(guest.first_name, 'JANE') # Should be uppercased

    def test_submit_invalid_form(self):
        # Missing required fields
        data = {
            'first_name': 'Jane'
        }
        response = self.client.post(self.submit_url, data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(GuestRegistration.objects.count(), 0)

    def test_honeypot_rejection(self):
        # Bot filling the hidden field
        data = {
            'first_name': 'Bot',
            'last_name': 'Spammer',
            'address': '123 Fake St',
            'phone': '0000000000',
            'email': 'bot@spam.com',
            'birth_date': '2000-01-01',
            'gender': 'Male',
            'nickname': 'I am a bot' # Honeypot filled
        }
        response = self.client.post(self.submit_url, data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(GuestRegistration.objects.count(), 0)

class AdminViewsTest(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.login_url = reverse('admin_login')
        self.dashboard_url = reverse('dashboard')
        self.settings = AdminSettings.objects.create(pin_code='12345')

    def test_admin_login_page(self):
        response = self.client.get(self.login_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'management/admin_login.html')

    def test_admin_login_success(self):
        response = self.client.post(self.login_url, {'pin': '12345'})
        self.assertRedirects(response, self.dashboard_url)
        session = self.client.session
        self.assertTrue(session.get('is_manager'))

    def test_admin_login_failure(self):
        response = self.client.post(self.login_url, {'pin': '00000'})
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'management/admin_login.html')
        self.assertContains(response, 'Invalid PIN')
        
    def test_admin_login_rate_limit(self):
        # 5 failed attempts
        for _ in range(5):
            self.client.post(self.login_url, {'pin': '00000'})
        
        # 6th attempt should be blocked
        response = self.client.post(self.login_url, {'pin': '00000'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Too many failed attempts')

    def test_dashboard_access_denied(self):
        response = self.client.get(self.dashboard_url)
        self.assertRedirects(response, self.login_url)

    def test_dashboard_access_granted(self):
        # Manually set session
        session = self.client.session
        session['is_manager'] = True
        session.save()
        
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'management/dashboard.html')

    def test_audit_logging(self):
        # Perform login
        self.client.post(self.login_url, {'pin': '12345'})
        
        # Check Log
        log = AuditLog.objects.first()
        self.assertIsNotNone(log)
        self.assertEqual(log.action, 'LOGIN')
        self.assertIn('Admin logged in', log.details)