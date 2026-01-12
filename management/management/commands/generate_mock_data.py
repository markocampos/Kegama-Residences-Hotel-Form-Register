import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from management.models import GuestRegistration

class Command(BaseCommand):
    help = 'Generates mock data for the last 365 days'

    def handle(self, *args, **options):
        # Clear existing data if you want, but better to just append
        # GuestRegistration.objects.all().delete()
        
        sources = ['OYO', 'AIRBNB', 'WALKIN']
        first_names = ['Juan', 'Maria', 'Jose', 'Elena', 'Ricardo', 'Beatriz', 'Antonio', 'Teresa']
        last_names = ['Dela Cruz', 'Santos', 'Reyes', 'Garcia', 'Mendoza', 'Bautista', 'Aquino']
        rooms = ['101', '102', '103', '201', '202', '301', '302', '401']
        payment_modes = ['CASH', 'GCASH', 'MAYA', 'BANK_TRANSFER']

        end_date = timezone.now()
        start_date = end_date - timedelta(days=365)
        
        current_date = start_date
        total_created = 0

        self.stdout.write(self.style.SUCCESS(f'Generating mock data from {start_date.date()} to {end_date.date()}...'))

        while current_date <= end_date:
            # Random number of guests per day (1 to 5)
            num_guests = random.randint(1, 5)
            
            for _ in range(num_guests):
                first_name = random.choice(first_names)
                last_name = random.choice(last_names)
                nights = random.randint(1, 3)
                rate = random.choice([1500, 1800, 2500, 3500])
                
                # Create guest
                guest = GuestRegistration.objects.create(
                    first_name=first_name.upper(),
                    last_name=last_name.upper(),
                    address="SAMPLE ADDRESS, PHILIPPINES",
                    phone=f"09{random.randint(10,99)} {random.randint(100,999)} {random.randint(1000,9999)}",
                    email=f"{first_name.lower()}@example.com",
                    source=random.choice(sources),
                    room_number=random.choice(rooms),
                    room_rate=rate,
                    nights=nights,
                    pax=random.randint(1, 2),
                    mode_of_payment=random.choice(payment_modes),
                    security_deposit=1000,
                    total_amount=rate * nights,
                    status='CHECKED_IN',
                )
                
                # Override auto-now fields to simulate historical data
                GuestRegistration.objects.filter(id=guest.id).update(created_at=current_date)
                total_created += 1
            
            current_date += timedelta(days=1)

        self.stdout.write(self.style.SUCCESS(f'Successfully created {total_created} mock guest records!'))
