from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from assistant_search.models import SpecificationProposal
from assistant_search.provider import ProviderUnavailable
from inventory.models import Category, Item, Location
from procurement.device_candidates import (
    CLEAR_DEVICE_NAMES,
    MANUFACTURER_HINTS,
    MODEL_HINTS,
    RESEARCH_HINTS,
    category_name,
    clean_device_name,
)
from procurement.models import PurchaseOrder
from procurement.research import research_device

EXISTING_ITEM_MATCHES = {
    "KUKA_Agilus KR6": {
        "manufacturer__iexact": "KUKA",
        "model_number__iexact": "KR 6 R900 sixx",
    },
    "Sony Alpha 7 iV": {"manufacturer__iexact": "Sony", "model_number__iexact": "Alpha 7 IV"},
    "UR16e": {"manufacturer__iexact": "Universal Robots", "model_number__iexact": "UR16e"},
}


class Command(BaseCommand):
    help = "Legt eindeutig erkannte Einzelgeräte aus der Bestellliste im Inventar an."

    def add_arguments(self, parser):
        parser.add_argument("--responsible", default="admin", help="Kennung der verantwortlichen Person")
        parser.add_argument("--location", default="Noch nicht zugeordnet", help="Vorläufiger Ablageort")
        parser.add_argument("--research", action="store_true", help="Öffentliche Produktdaten recherchieren")
        parser.add_argument(
            "--retry", action="store_true", help="Fehlgeschlagene Recherchen erneut versuchen"
        )
        parser.add_argument("--limit", type=int, help="Höchstens so viele Bestellungen verarbeiten")
        parser.add_argument("--workers", type=int, default=1, help="Parallele Recherchen (1–8)")
        parser.add_argument("--dry-run", action="store_true", help="Nur geplante Änderungen ausgeben")

    def handle(self, *args, **options):
        try:
            responsible = User.objects.get(username=options["responsible"])
        except User.DoesNotExist as exc:
            raise CommandError(f"Konto {options['responsible']!r} wurde nicht gefunden.") from exc

        orders = PurchaseOrder.objects.filter(name__in=CLEAR_DEVICE_NAMES).order_by("purchase_date", "pk")
        if options["limit"]:
            orders = orders[: options["limit"]]

        if options["dry_run"]:
            unlinked = sum(order.inventory_item_id is None for order in orders)
            researchable = sum(order.name in RESEARCH_HINTS for order in orders)
            self.stdout.write(
                f"{len(orders)} eindeutige Bestellungen, {unlinked} ohne Gerät, "
                f"{researchable} mit eindeutiger öffentlicher Typbezeichnung."
            )
            return

        location, _ = Location.objects.get_or_create(
            path=options["location"],
            defaults={"name": options["location"], "description": "Vorläufiger Ort für Bestellimporte"},
        )
        categories = {
            name: Category.objects.get_or_create(path=name, defaults={"name": name})[0]
            for name in {
                "Sensoren",
                "Aktoren",
                "Werkzeuge",
                "IT / Elektronik",
                "Roboter",
                "Mess- und Prüfgeräte",
                "Maschinen und Anlagen",
                "Sonstiges",
            }
        }

        created_count = 0
        linked_count = 0
        researched_count = 0
        ambiguous_count = 0
        failed_count = 0
        research_queue = []

        for order in orders:
            if order.inventory_item_id is None:
                with transaction.atomic():
                    locked_order = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
                    if locked_order.inventory_item_id is None:
                        item = self._find_existing_item(locked_order)
                        if item is None:
                            item = Item.objects.create(
                                name=clean_device_name(locked_order.name)[:200],
                                category=categories[category_name(locked_order.name, locked_order.tool_type)],
                                manufacturer=MANUFACTURER_HINTS.get(locked_order.name, "")[:100],
                                model_number=MODEL_HINTS.get(locked_order.name, "")[:100],
                                description=(
                                    "Aus dem Bestellbestand übernommen. Technische Angaben, "
                                    "Ablageort und Verantwortlichkeit müssen geprüft werden."
                                ),
                                location=location,
                                responsible=responsible,
                                loan_policy=Item.LoanPolicy.APPROVAL,
                                condition=Item.Condition.UNVERIFIED,
                                created_by=responsible,
                            )
                            created_count += 1
                        else:
                            linked_count += 1
                        locked_order.inventory_item = item
                        locked_order.save(update_fields=["inventory_item"])
                        order.inventory_item = item

            if options["research"]:
                status = order.research_status
                should_retry = options["retry"] and status == PurchaseOrder.ResearchStatus.FAILED
                if status == PurchaseOrder.ResearchStatus.NOT_STARTED or should_retry:
                    hint = RESEARCH_HINTS.get(order.name)
                    if hint:
                        research_queue.append((order.pk, hint))
                    else:
                        self._mark_ambiguous(
                            order,
                            "Die Bestellung enthält keine eindeutige öffentliche Hersteller- und "
                            "Typbezeichnung.",
                        )
                        ambiguous_count += 1

        if research_queue:
            workers = max(1, min(options["workers"], 8))
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(research_device, hint): order_id for order_id, hint in research_queue
                }
                for position, future in enumerate(as_completed(futures), start=1):
                    order = PurchaseOrder.objects.select_related("inventory_item").get(pk=futures[future])
                    try:
                        result = future.result()
                    except ProviderUnavailable:
                        self._mark_failed(order)
                        failed_count += 1
                    else:
                        if result is None:
                            self._mark_ambiguous(
                                order,
                                "Für die genaue Typvariante wurde keine belegte Quelle gefunden.",
                            )
                            ambiguous_count += 1
                        else:
                            self._store_research(order, result)
                            researched_count += 1
                    self.stdout.write(f"Recherche {position}/{len(research_queue)} abgeschlossen.")

        self.stdout.write(
            self.style.SUCCESS(
                f"{created_count} Geräte angelegt, {linked_count} vorhandene Geräte verknüpft. "
                f"Recherche: {researched_count} erfolgreich, {ambiguous_count} nicht eindeutig, "
                f"{failed_count} fehlgeschlagen."
            )
        )

    @staticmethod
    def _find_existing_item(order):
        lookup = EXISTING_ITEM_MATCHES.get(order.name)
        return Item.objects.filter(**lookup).first() if lookup else None

    @staticmethod
    def _mark_ambiguous(order, summary):
        order.research_status = PurchaseOrder.ResearchStatus.AMBIGUOUS
        order.research_summary = summary
        order.researched_at = timezone.now()
        order.save(update_fields=["research_status", "research_summary", "researched_at"])

    @staticmethod
    def _mark_failed(order):
        order.research_status = PurchaseOrder.ResearchStatus.FAILED
        order.research_summary = "Der Recherchedienst war nicht verfügbar."
        order.researched_at = timezone.now()
        order.save(update_fields=["research_status", "research_summary", "researched_at"])

    @staticmethod
    def _store_research(order, result):
        source_url = str(result["source_url"])[:500]
        source_title = str(result.get("source_title") or "Produktinformation")[:200]
        order.research_status = PurchaseOrder.ResearchStatus.RESEARCHED
        order.research_summary = str(result.get("summary") or "")[:2000]
        order.research_source_url = source_url
        order.research_source_title = source_title
        order.research_data = result
        order.researched_at = timezone.now()
        order.save(
            update_fields=[
                "research_status",
                "research_summary",
                "research_source_url",
                "research_source_title",
                "research_data",
                "researched_at",
            ]
        )

        item = order.inventory_item
        changed = []
        for field, limit in (("manufacturer", 100), ("model_number", 100)):
            value = str(result.get(field) or "")[:limit]
            if value and not getattr(item, field):
                setattr(item, field, value)
                changed.append(field)
        if changed:
            item.save(update_fields=[*changed, "updated_at"])

        for spec in result.get("specifications", []):
            SpecificationProposal.objects.get_or_create(
                item=item,
                property_name=spec["property_name"],
                value_text=spec["value_text"],
                source_url=source_url,
                defaults={
                    "source_title": source_title,
                    "source_kind": result["source_kind"],
                },
            )
