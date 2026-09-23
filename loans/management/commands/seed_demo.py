from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from inventory.models import Accessory, Category, Item, Location
from loans.models import Booking

PASSWORD = "demo1234"
USERS = ["Torge", "Tobias", "Dasha", "Karina", "Robert"]

# name, Kategorie, Hersteller, Modell, Verantwortlich, Regel, bevorzugter Ort (Hallenplan), Zubehör
ITEMS = [
    (
        "KUKA KR6",
        "Aktoren",
        "KUKA",
        "KR 6 R900 sixx",
        "torge",
        Item.LoanPolicy.APPROVAL,
        "Labortisch KR6 / Keyence",
        ["Steuerung KR C4 compact", "smartPAD (Teach-Pendant)", "Not-Halt-Taster"],
        "Sechsachs-Industrieroboter, 6 kg Traglast. Nur nach Sicherheitsunterweisung benutzen.",
    ),
    (
        "UR16",
        "Aktoren",
        "Universal Robots",
        "UR16e",
        "tobias",
        Item.LoanPolicy.APPROVAL,
        "Labortisch ROMO",
        ["Control Box", "Teach-Pendant", "Montageplatte"],
        "Kollaborierender Roboter, 16 kg Traglast, 900 mm Reichweite.",
    ),
    (
        "Schweißgerät",
        "Werkzeuge",
        "Fronius",
        "TransSteel 2200",
        "robert",
        Item.LoanPolicy.FREE,
        "Schweißtisch SoRo I Origami",
        ["Schlauchpaket", "Massekabel", "Schweißhelm"],
        "MIG/MAG- und E-Hand-Schweißgerät.",
    ),
    (
        "Sony Kamera",
        "Sensoren",
        "Sony",
        "Alpha 7 IV",
        "dasha",
        Item.LoanPolicy.FREE,
        "Schrank 5",
        ["Objektiv 24–70 mm", "2 Akkus", "Ladegerät", "SD-Karte 128 GB"],
        "Vollformat-Systemkamera für Versuchsdokumentation und Fotos.",
    ),
]


class Command(BaseCommand):
    help = (
        f"Legt Testnutzer ({', '.join(USERS)}) und Beispielgeräte mit Buchungen an. Nur für die Entwicklung."
    )

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Auch bei DEBUG=False ausführen")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG and not options["force"]:
            raise CommandError("Nur für die Entwicklung (DEBUG=True). Mit --force trotzdem ausführen.")

        users = {}
        for first_name in USERS:
            username = first_name.lower()
            user, created = User.objects.get_or_create(
                username=username, defaults={"first_name": first_name, "email": f"{username}@example.org"}
            )
            if created:
                user.set_password(PASSWORD)
                user.save()
            users[username] = user

        fallback, _ = Location.objects.get_or_create(path="Demo-Lager", defaults={"name": "Demo-Lager"})
        items = {}
        for name, category, maker, model, owner, policy, place, accessories, text in ITEMS:
            location = Location.objects.filter(name=place).first() or fallback
            item, created = Item.objects.get_or_create(
                name=name,
                defaults={
                    "category": Category.objects.get_or_create(path=category, defaults={"name": category})[0],
                    "manufacturer": maker,
                    "model_number": model,
                    "description": text,
                    "location": location,
                    "responsible": users[owner],
                    "loan_policy": policy,
                    "created_by": users[owner],
                },
            )
            if created:
                Accessory.objects.bulk_create(Accessory(item=item, name=a) for a in accessories)
            items[name] = item

        today = timezone.localdate()
        if not Booking.objects.filter(item__in=items.values()).exists():
            Booking.objects.create(
                item=items["Sony Kamera"],
                borrower=users["karina"],
                created_by=users["karina"],
                start_date=today - timedelta(days=2),
                end_date=today + timedelta(days=5),
                status=Booking.Status.ACTIVE,
                checked_out_at=timezone.now() - timedelta(days=2),
                purpose="Fotos Versuchsaufbau",
                usage_location="Versuchsfeld, Labortisch Sandra",
            )
            Booking.objects.create(
                item=items["KUKA KR6"],
                borrower=users["robert"],
                created_by=users["robert"],
                start_date=today + timedelta(days=3),
                end_date=today + timedelta(days=10),
                status=Booking.Status.REQUESTED,
                purpose="Schweißversuche",
                request_message="Brauche den Roboter für eine Versuchsreihe, Einweisung habe ich.",
            )
            Booking.objects.create(
                item=items["Schweißgerät"],
                borrower=users["tobias"],
                created_by=users["tobias"],
                start_date=today + timedelta(days=7),
                end_date=today + timedelta(days=9),
                status=Booking.Status.RESERVED,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Testnutzer: {', '.join(users)} (Passwort: {PASSWORD}); "
                f"Geräte: {', '.join(items)}; Beispielbuchungen angelegt."
            )
        )
