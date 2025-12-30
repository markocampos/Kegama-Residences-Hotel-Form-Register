import uuid
from django.db import models

class AuditLog(models.Model):
    ACTION_CHOICES = [
        ('LOGIN', 'Admin Login'),
        ('VIEW_GUEST', 'Viewed Guest'),
        ('UPDATE_GUEST', 'Updated Guest'),
        ('PRINT_PDF', 'Generated PDF'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    details = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp}] {self.action}: {self.details} ({self.ip_address})"

class GuestRegistration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    SOURCE_CHOICES = [
        ('OYO', 'OYO'),
        ('AIRBNB', 'Airbnb'),
        ('WALKIN', 'Page/Walk-in'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('PRINTED', 'Printed'),
        ('CHECKED_IN', 'Checked-in'),
    ]

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default='WALKIN')
    booking_id = models.CharField(max_length=50, blank=True, help_text="Auto-generated if empty")
    security_deposit = models.DecimalField(max_digits=10, decimal_places=2, default=1000, blank=True, null=True)

    last_name = models.CharField(max_length=100)
    first_name = models.CharField(max_length=100)
    address = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    email = models.EmailField()
    birth_date = models.DateField(blank=True, null=True)
    gender = models.CharField(max_length=20, blank=True)

    pax = models.IntegerField(default=1)
    nights = models.IntegerField(default=1)
    room_number = models.CharField(max_length=20, blank=True)
    room_rate = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    additional_requests = models.TextField(blank=True, default='[]', help_text="JSON list of requests")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Final calculated amount")

    check_in_date = models.DateField(blank=True, null=True)
    check_in_time = models.TimeField(blank=True, null=True)
    check_out_date = models.DateField(blank=True, null=True)
    check_out_time = models.TimeField(blank=True, null=True)

    notes = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if not self.booking_id:
            import uuid
            self.booking_id = str(uuid.uuid4())[:8].upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.room_number}"

class AdminSettings(models.Model):
    pin_code = models.CharField(max_length=10, default='12345', help_text="PIN for Management Access")
    maintenance_mode = models.BooleanField(default=False, help_text="Disable guest form")
    form_access_code = models.CharField(max_length=20, blank=True, help_text="Optional code required to view form")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Admin Settings"
        verbose_name_plural = "Admin Settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super(AdminSettings, self).save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return f"System Settings (PIN: {self.pin_code})"