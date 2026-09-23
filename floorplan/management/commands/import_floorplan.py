from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from floorplan.models import FloorPlan
from floorplan.pptx_import import read_elements
from floorplan.services import PlanError, save_plan
from inventory.models import Location


class Command(BaseCommand):
    help = "Übernimmt eine PowerPoint-Skizze (erste Folie) als Hallenplan."

    def add_arguments(self, parser):
        parser.add_argument("pptx", help="Pfad zur .pptx-Datei")
        parser.add_argument("--name", default="Versuchsfeld", help="Name des Plans und des Orts")
        parser.add_argument("--scale", type=float, default=1.0, help="Meter pro Zentimeter auf der Folie")
        parser.add_argument(
            "--replace", action="store_true", help="Vorhandene Objekte des gleichnamigen Plans ersetzen"
        )

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            width, height, elements = read_elements(options["pptx"], options["scale"])
        except Exception as error:
            raise CommandError(f"Datei konnte nicht gelesen werden: {error}") from error

        name = options["name"]
        location = Location.objects.filter(parent=None, name=name).first() or Location.objects.create(
            name=name
        )
        plan, created = FloorPlan.objects.get_or_create(
            location=location, defaults={"name": name, "width": width, "height": height}
        )
        if not created and plan.elements.exists() and not options["replace"]:
            raise CommandError(f"Plan „{name}“ hat schon Objekte. Mit --replace ersetzen.")
        plan.width, plan.height = width, height
        plan.save()
        try:
            save_plan(plan, elements, deleted_ids=list(plan.elements.values_list("pk", flat=True)))
        except PlanError as error:
            raise CommandError(str(error)) from error

        holding = plan.elements.filter(location__isnull=False).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"Plan „{plan}“ ({width} × {height} m): {len(elements)} Objekte übernommen, "
                f"davon {holding} als Ablageorte."
            )
        )
