from django.core.management.base import BaseCommand

from loans.reminders import run


class Command(BaseCommand):
    help = (
        "Verschickt die täglichen Erinnerungen (Reservierung beginnt, Rückgabe fällig/überfällig, "
        "unbeantwortete Anfragen) und setzt verstrichene Buchungen auf „verfallen“. Einmal täglich starten."
    )

    def handle(self, *args, **options):
        stats = run()
        self.stdout.write(self.style.SUCCESS(", ".join(f"{key}: {value}" for key, value in stats.items())))
