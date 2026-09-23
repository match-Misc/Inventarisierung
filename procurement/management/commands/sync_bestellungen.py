"""Liest den Bestellungen-Ordner ein und aktualisiert die Bestellungen-Datenbank.

Läuft monatlich (siehe README-Abschnitt zur Aufgabenplanung). Manuell geprüfte Einträge
(`manually_verified=True`) werden inhaltlich nicht mehr verändert, nur `last_synced` aktualisiert.
"""

from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from procurement.importer import scan_base_dir
from procurement.models import PurchaseOrder


class Command(BaseCommand):
    help = "Synchronisiert die Bestellungen-Datenbank mit dem Ordner 01_Bestellungen."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-dir",
            default=None,
            help="Basisordner der Bestellungen. Ohne Angabe wird settings.BESTELLUNGEN_DIR verwendet.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Zeigt nur an, was geändert würde, ohne die Datenbank zu ändern.",
        )

    def handle(self, *args, base_dir, dry_run, **options):
        base_path = Path(base_dir) if base_dir else Path(settings.BESTELLUNGEN_DIR)
        if not base_path.exists():
            self.stderr.write(self.style.ERROR(f"Basisordner nicht gefunden: {base_path}"))
            return

        found = scan_base_dir(base_path)
        found_keys = {data.source_folder for data in found}
        now = timezone.now()
        created = updated = skipped = missing = 0

        for data in found:
            try:
                order = PurchaseOrder.objects.get(source_folder=data.source_folder)
            except PurchaseOrder.DoesNotExist:
                order = PurchaseOrder(source_folder=data.source_folder)
                is_new = True
            else:
                is_new = False

            if order.manually_verified:
                skipped += 1
                if not dry_run:
                    order.is_missing = False
                    order.last_synced = now
                    order.save(update_fields=["is_missing", "last_synced"])
                continue

            order.name = data.name
            order.company = data.company
            order.price = self._to_decimal(data.price)
            order.tool_type = data.tool_type or order.tool_type
            order.key_specs = data.key_specs
            order.purchase_date = data.purchase_date
            order.project = data.project
            order.datasheet_path = data.datasheet_path
            order.is_missing = False
            order.last_synced = now

            if not dry_run:
                order.save()
            created += int(is_new)
            updated += int(not is_new)

        missing_qs = PurchaseOrder.objects.exclude(source_folder__in=found_keys).filter(is_missing=False)
        missing = missing_qs.count()
        if not dry_run:
            missing_qs.update(is_missing=True, last_synced=now)

        prefix = "[Testlauf] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Neu: {created}, aktualisiert: {updated}, "
                f"übersprungen (geprüft): {skipped}, fehlend: {missing}."
            )
        )

    @staticmethod
    def _to_decimal(value):
        if value is None:
            return None
        try:
            return Decimal(value)
        except (InvalidOperation, TypeError):
            return None
