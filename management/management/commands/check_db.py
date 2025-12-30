from django.core.management.base import BaseCommand
from django.db import connections
from django.db.utils import OperationalError

class Command(BaseCommand):
    help = "Validates the database connection"

    def handle(self, *args, **options):
        self.stdout.write("Checking database connection...")
        
        db_conn = connections['default']
        try:
            db_conn.cursor()
            self.stdout.write(self.style.SUCCESS("SUCCESS: Database connection established!"))
        except OperationalError as e:
            self.stdout.write(self.style.ERROR(f"ERROR: Database connection failed. Details: {e}"))
            exit(1)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"ERROR: An unexpected error occurred. Details: {e}"))
            exit(1)
