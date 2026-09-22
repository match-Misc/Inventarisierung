from django.core.management.base import BaseCommand

from loans.services import expire_stale_bookings


class Command(BaseCommand):
    help = "Markiert abgelaufene Anfragen und Reservierungen als verfallen."

    def handle(self, *args, **options):
        count = expire_stale_bookings()
        self.stdout.write(f"{count} Buchung(en) verfallen.")
