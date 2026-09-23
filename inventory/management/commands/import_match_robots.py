"""Kuratierter, wiederholbarer Import der Roboter aus der match-Ausstattungsliste.

Die Institutsseite belegt den Bestand, technische Werte stammen aus den unten
verlinkten Produktunterlagen. Modellkennwerte bleiben bis zur Sichtprüfung des
Typenschilds Vorschläge. Foto-Dateien werden separat über --photo-dir übergeben.
"""

from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from assistant_search.models import SpecificationProposal
from inventory.images import add_photo
from inventory.models import Category, Item, ItemDocument, Location
from procurement.models import PurchaseOrder

MATCH_URL = "https://www.match.uni-hannover.de/kooperationen/ausstattung"
KUKA_KR6 = (
    "https://www.kuka.com/-/media/kuka-downloads/imported/8350ff3ca11642998dbdc81dcc2ed44c/0000205456_en.pdf"
)
KUKA_KR60 = "https://assets.robots.com/robots/KUKA/Medium-Payload/KUKA_KR_60_3_Datasheet.pdf"
KUKA_IIWA = (
    "https://www.kuka.com/-/media/kuka-downloads/imported/8350ff3ca11642998dbdc81dcc2ed44c/0000246833_en.pdf"
)
STAUBLI = "https://assets.staubli.com/Robotics/Partner-Portal-DE/Food_Flash_DE_1802.pdf"
PANDA = "https://www.erm-automatismes.com/d000384-brochure-robot-panda-de-franka.pdf"
ABB = "https://library.e.abb.com/public/582efb4972404f0fbd6cc9a3a8f04ea8/IRB360_ROB0082-RevJ_DataSheet-A4.pdf"
MIR100 = "https://www.rg-group.com/store/images/document/MIR/MiR100-Datasheet.pdf"
MIR200 = "https://www.rg-group.com/store/images/document/MIR/MiR200-Datasheet.pdf"
MIR600 = "https://mobile-industrial-robots.com/products/robots/mir600/specifications"
SPOT = "https://www.bostondynamics.com/sites/default/files/inline-files/spot-specifications.pdf"
SCOUT = "https://global.agilex.ai/products/scout-mini"
ROSBOT = "https://husarion.com/manuals/rosbot/"


def spec(name, value, number, unit, source, source_kind="manufacturer"):
    return (name, value, number, unit, source, source_kind)


# Ein Datensatz pro Modell, aber ein Item pro bereits gekaufter physischer Einheit.
# Die drei Modelle ohne Bestellbezug werden nur angelegt, wenn noch kein passender
# Eintrag existiert. Die Quelle der Fotos ist stets in einem Dokument verlinkt.
ROBOTS = (
    {
        "name": "KUKA KR 6 R900 sixx",
        "manufacturer": "KUKA",
        "model": "KR 6 R900 sixx",
        "section": "Roboter",
        "orders": ("2014/2014-04_KUKA_AgilusKR6", "2017/2017-08_KUKA_Agilus KR6"),
        "anchor": "c240815",
        "summary": "Kompakter 6-Achs-Industrieroboter der KR-AGILUS-Reihe. KUKA nennt 901,5 mm Reichweite und bis zu 6 kg Traglast (3 kg Nennlast für optimale Dynamik). Die match-Seite nennt abweichend 1.611 mm; die Typzuordnung der Bestellung von 2014 ist am Typenschild zu prüfen.",
        "datasheet": KUKA_KR6,
        "photo": "kr6.jpg",
        "photo_url": "https://www.match.uni-hannover.de/fileadmin/_processed_/9/6/csm_Robotergestuetzte_Handhabung_Montage_16x9_ae548eb316.jpg",
        "specs": (
            spec("Maximale Traglast", "bis 6 kg (Nennlast 3 kg)", 6, "kg", KUKA_KR6),
            spec("Reichweite", "901,5 mm", 901.5, "mm", KUKA_KR6),
            spec("Wiederholgenauigkeit", "±0,03 mm", 0.03, "mm", KUKA_KR6),
        ),
    },
    {
        "name": "KUKA KR 60-3",
        "manufacturer": "KUKA",
        "model": "KR 60-3",
        "section": "Roboter",
        "orders": ("2017/2017-06_KUKA_KR60-3",),
        "anchor": "c240818",
        "summary": "6-Achs-Industrieroboter mit KR-C4-Steuerung, 60 kg Traglast, 2.033 mm Reichweite und ±0,06 mm Wiederholgenauigkeit. Die technischen Werte stammen aus einem Datenblatt des Robotikhändlers; die konkrete Ausführung des Instituts ist am Typenschild zu prüfen.",
        "datasheet": KUKA_KR60,
        "photo": "kr60.jpg",
        "photo_url": "https://revelationmachinery.com/product/kuka-kr-60-3-medium-payload-industrial-robot-2015/",
        "photo_example": True,
        "specs": (
            spec("Traglast", "60 kg", 60, "kg", KUKA_KR60, "dealer"),
            spec("Reichweite", "2.033 mm", 2033, "mm", KUKA_KR60, "dealer"),
            spec("Wiederholgenauigkeit", "±0,06 mm", 0.06, "mm", KUKA_KR60, "dealer"),
        ),
    },
    {
        "name": "KUKA LBR iiwa 14 R820",
        "manufacturer": "KUKA",
        "model": "LBR iiwa 14 R820",
        "section": "Roboter",
        "orders": ("2018/2018-12_KUKA_iiwa",),
        "anchor": "c247384",
        "summary": "Kollaborativer 7-Achs-Leichtbauroboter mit Drehmomentsensoren in allen Achsen, 14 kg Traglast und 820 mm Reichweite. Die Bestellung nennt nur „iiwa“; die vom Institut angegebene Variante 14 R820 ist am Typenschild zu bestätigen.",
        "datasheet": KUKA_IIWA,
        "photo": "iiwa.jpg",
        "photo_url": "https://www.match.uni-hannover.de/fileadmin/_processed_/b/a/csm_iiwa_6eff337c27.jpg",
        "specs": (
            spec("Traglast", "14 kg", 14, "kg", KUKA_IIWA),
            spec("Reichweite", "820 mm", 820, "mm", KUKA_IIWA),
            spec("Achsen", "7", 7, "", KUKA_IIWA),
        ),
    },
    {
        "name": "Stäubli TX200",
        "manufacturer": "Stäubli",
        "model": "TX200",
        "section": "Roboter",
        "orders": ("2014/2014-07_Stäubli_TX200",),
        "anchor": "c240820",
        "summary": "6-Achs-Schwerlastroboter mit externer Beckhoff-Anbindung am match. Für den TX200 gelten 100 kg Nenntraglast, 130 kg maximale Traglast und 2.194 mm Reichweite. Die ältere Bestellrecherche verwechselte TX200 mit TX2-200; die match-Seite nennt im Fließtext 120 kg.",
        "datasheet": STAUBLI,
        "photo": "tx200.jpg",
        "photo_url": "https://www.match.uni-hannover.de/fileadmin/_processed_/f/5/csm_Staubli_tx200_DSC00396_db3a456cb5.jpg",
        "specs": (
            spec("Nenntraglast", "100 kg", 100, "kg", STAUBLI),
            spec("Maximale Traglast", "130 kg", 130, "kg", STAUBLI),
            spec("Reichweite", "2.194 mm", 2194, "mm", STAUBLI),
        ),
    },
    {
        "name": "Franka Emika Panda",
        "manufacturer": "Franka Emika",
        "model": "Panda",
        "section": "Roboter",
        "orders": ("2018/2018-10_Panda", "2021/2021-02_Franka_Emika"),
        "anchor": "c240822",
        "summary": "Kollaborativer 7-Achs-Roboterarm mit Gelenkdrehmomentsensoren, 3 kg Traglast und 855 mm Reichweite. Zwei getrennte Bestellungen sind vorhanden; ob beide aktuell als eigenständige Geräte vorliegen, muss vor Ort bestätigt werden.",
        "datasheet": PANDA,
        "photo": "panda.png",
        "photo_url": "https://www.match.uni-hannover.de/fileadmin/_processed_/0/7/csm_Miranda_Panda_faaccc943b.png",
        "specs": (
            spec("Traglast", "3 kg", 3, "kg", PANDA),
            spec("Reichweite", "855 mm", 855, "mm", PANDA),
            spec("Achsen", "7", 7, "", PANDA),
        ),
    },
    {
        "name": "ABB FlexPicker IRB 360",
        "manufacturer": "ABB",
        "model": "IRB 360-1/1130 (Variante zu prüfen)",
        "section": "Roboter",
        "orders": (),
        "anchor": "c240855",
        "summary": "Delta-Roboter für schnelle Pick-and-Place-Aufgaben. Aus 1 kg Traglast und 1.130 mm Arbeitsdurchmesser auf der match-Seite folgt wahrscheinlich die ABB-Variante IRB 360-1/1130; das Typenschild muss diese Zuordnung bestätigen. ABB nennt 0,1 mm Positionswiederholgenauigkeit, die match-Seite 0,05 mm.",
        "datasheet": ABB,
        "photo": "abb.jpg",
        "photo_url": "https://www.match.uni-hannover.de/fileadmin/_processed_/c/a/csm_ABB_Flexpicker_RoMo_955c3e8ad9.jpg",
        "specs": (
            spec("Traglast", "1 kg (Variante IRB 360-1/1130)", 1, "kg", ABB),
            spec("Arbeitsdurchmesser", "1.130 mm", 1130, "mm", ABB),
        ),
    },
    {
        "name": "MiR100",
        "manufacturer": "Mobile Industrial Robots",
        "model": "MiR100",
        "section": "Autonome Mobile Plattformen",
        "orders": ("2020/2020-07_ICS_MiR-100",),
        "anchor": "c240824",
        "summary": "Autonome Transportplattform; am match unter anderem für kooperativen Objekttransport genutzt. Die Herstellerunterlage nennt bis zu 100 kg Nutzlast, 1,5 m/s und 10 h bzw. 20 km Reichweite. Das Typbild zeigt einen Forschungsaufbau und belegt keine Seriennummer.",
        "datasheet": MIR100,
        "photo": "mir100.png",
        "photo_url": "https://www.match.uni-hannover.de/fileadmin/_processed_/4/3/csm_Miranda_Mir_e62dd47d65.png",
        "specs": (
            spec("Traglast", "bis 100 kg", 100, "kg", MIR100),
            spec("Fahrstrecke", "bis 20 km", 20, "km", MIR100),
            spec("Akkulaufzeit", "bis 10 h", 10, "h", MIR100),
            spec("Geschwindigkeit", "bis 1,5 m/s", 1.5, "m/s", MIR100),
        ),
    },
    {
        "name": "MiR200",
        "manufacturer": "Mobile Industrial Robots",
        "model": "MiR200",
        "section": "Autonome Mobile Plattformen",
        "orders": ("2018/2018-10_MIR-200",),
        "anchor": "c247380",
        "summary": "Autonome Transportplattform. Das MiR-Datenblatt nennt bis zu 200 kg Nutzlast, 1,1 m/s und 10 h bzw. 15 km Reichweite. Das Bild ist eine externe Modellabbildung, kein Foto des Institutsgeräts.",
        "datasheet": MIR200,
        "photo": "mir200.png",
        "photo_url": "https://antonrobots.com/mir200/",
        "photo_example": True,
        "specs": (
            spec("Traglast", "bis 200 kg", 200, "kg", MIR200),
            spec("Fahrstrecke", "bis 15 km", 15, "km", MIR200),
            spec("Akkulaufzeit", "bis 10 h", 10, "h", MIR200),
            spec("Geschwindigkeit", "bis 1,1 m/s", 1.1, "m/s", MIR200),
        ),
    },
    {
        "name": "MiR600",
        "manufacturer": "Mobile Industrial Robots",
        "model": "MiR600",
        "section": "Autonome Mobile Plattformen",
        "orders": (),
        "anchor": "c240826",
        "summary": "Autonome Schwerlastplattform. Aktuelle MiR-Angaben: bis 600 kg Nutzlast, 2,0 m/s, bis 8 h 30 min aktive Betriebszeit bei voller Last. Das match-Foto zeigt einen spezifischen Aufbau mit Roboterarm; die Konfiguration und Generation vor Ort prüfen.",
        "datasheet": MIR600,
        "photo": "mir600.jpg",
        "photo_url": "https://www.match.uni-hannover.de/fileadmin/_processed_/e/8/csm_MUR_610_99dcd2b065.jpg",
        "specs": (
            spec("Traglast", "bis 600 kg", 600, "kg", MIR600),
            spec("Geschwindigkeit", "bis 2,0 m/s", 2, "m/s", MIR600),
            spec("Akkulaufzeit bei voller Last", "bis 8 h 30 min", 8.5, "h", MIR600),
        ),
    },
    {
        "name": "Boston Dynamics Spot (Emma)",
        "manufacturer": "Boston Dynamics",
        "model": "Spot",
        "section": "Autonome Mobile Plattformen",
        "orders": ("2021/2021-05_Generation-Robots_Boston-Dynamics_Spot",),
        "anchor": "c240828",
        "summary": "Vierbeiniger mobiler Inspektionsroboter, am match „Emma“ genannt. Boston Dynamics nennt 14 kg Zusatzlast, 1,6 m/s und etwa 90 min durchschnittliche Laufzeit. Ausstattung und Akkugeneration vor Ort prüfen.",
        "datasheet": SPOT,
        "photo": "spot.jpg",
        "photo_url": "https://www.match.uni-hannover.de/fileadmin/_processed_/4/6/csm_Emma-vor-PZH_d0a0870d80.jpg",
        "specs": (
            spec("Traglast", "bis 14 kg", 14, "kg", SPOT),
            spec("Geschwindigkeit", "bis 1,6 m/s", 1.6, "m/s", SPOT),
            spec("Akkulaufzeit", "ca. 90 min", 90, "min", SPOT),
        ),
    },
    {
        "name": "AgileX SCOUT MINI",
        "manufacturer": "AgileX Robotics",
        "model": "SCOUT MINI (Radvariante zu prüfen)",
        "section": "Autonome Mobile Plattformen",
        "orders": (),
        "anchor": "c240830",
        "summary": "Kompakte 4-Rad-Forschungsplattform. AgileX nennt für das Standardmodell 10 kg Nutzlast und bis 3 h Laufzeit. Die match-Seite beschreibt holonome Mecanum-Räder, kombiniert diese aber mit Daten des Standardmodells. Radvariante, Traglast und Geschwindigkeit am Gerät prüfen. Das Bild zeigt die Standardvariante.",
        "datasheet": SCOUT,
        "photo": "scout.png",
        "photo_url": "https://global.agilex.ai/products/scout-mini",
        "photo_example": True,
        "specs": (
            spec("Traglast Standardmodell", "10 kg (Radvariante prüfen)", 10, "kg", SCOUT),
            spec("Akkulaufzeit Standardmodell", "bis 3 h", 3, "h", SCOUT),
        ),
    },
    {
        "name": "Husarion ROSbot 2 PRO",
        "manufacturer": "Husarion",
        "model": "ROSbot 2 PRO",
        "section": "Autonome Mobile Plattformen",
        "orders": ("2023/2023-08 ROSBot 2 Pro",),
        "anchor": "c247382",
        "summary": "Kleine ROS-Forschungsplattform mit LiDAR, Kamera und IMU. Husarion nennt bis 5 kg Zusatzlast (nicht im Dauerbetrieb), 1,0 m/s und je nach Nutzung 1,5–5 h Akkulaufzeit. Die match-Aufnahme zeigt Mecanum-Räder; die Konfiguration am Gerät prüfen.",
        "datasheet": ROSBOT,
        "photo": "rosbot.jpg",
        "photo_url": "https://www.match.uni-hannover.de/fileadmin/_processed_/1/3/csm_Husarion_39cbebdc77.jpg",
        "specs": (
            spec("Traglast", "bis 5 kg, nicht im Dauerbetrieb", 5, "kg", ROSBOT),
            spec("Geschwindigkeit", "bis 1,0 m/s", 1, "m/s", ROSBOT),
            spec("Akkulaufzeit", "1,5–5 h", 5, "h", ROSBOT),
        ),
    },
)


class Command(BaseCommand):
    help = "Kuratierte Roboter und mobile Plattformen der match-Ausstattung einpflegen"

    def add_arguments(self, parser):
        parser.add_argument("--responsible", default="tobias", help="Kennung der verantwortlichen Person")
        parser.add_argument("--photo-dir", type=Path, help="Ordner mit den kuratierten Bilddateien")

    def handle(self, *args, **options):
        user = get_user_model().objects.filter(username=options["responsible"]).first()
        if user is None:
            raise CommandError(f"Konto {options['responsible']!r} wurde nicht gefunden.")
        photo_dir = options["photo_dir"]
        if photo_dir and not photo_dir.is_dir():
            raise CommandError(f"Bildordner fehlt: {photo_dir}")
        parent = Category.objects.get(path="Roboter")
        location = Location.objects.get(path="Noch nicht zugeordnet")
        categories = {}
        for section in ("Roboter", "Autonome Mobile Plattformen"):
            name = "Industrieroboter" if section == "Roboter" else section
            categories[section], _ = Category.objects.get_or_create(name=name, parent=parent)

        items_seen = set()
        for robot in ROBOTS:
            category = categories[robot["section"]]
            items = []
            for folder in robot["orders"]:
                try:
                    order = PurchaseOrder.objects.select_related("inventory_item").get(source_folder=folder)
                except PurchaseOrder.DoesNotExist:
                    self.stderr.write(self.style.WARNING(f"Bestellung fehlt: {folder}"))
                    continue
                if order.inventory_item is None:
                    self.stderr.write(self.style.WARNING(f"Bestellung ohne Gerät: {folder}"))
                    continue
                items.append(order.inventory_item)
            if not robot["orders"]:
                item, created = Item.objects.get_or_create(
                    name=robot["name"],
                    defaults={
                        "category": category,
                        "manufacturer": robot["manufacturer"],
                        "model_number": robot["model"],
                        "location": location,
                        "responsible": user,
                        "created_by": user,
                        "loan_policy": Item.LoanPolicy.APPROVAL,
                        "condition": Item.Condition.UNVERIFIED,
                    },
                )
                items.append(item)
                if created:
                    self.stdout.write(f"Neu: {item.name} (#{item.pk})")

            for item in items:
                if item.pk in items_seen:
                    continue
                items_seen.add(item.pk)
                self._update_item(item, robot, category, user, photo_dir)
        self.stdout.write(self.style.SUCCESS(f"{len(items_seen)} Geräte bearbeitet."))

    @transaction.atomic
    def _update_item(self, item, robot, category, user, photo_dir):
        item.name = robot["name"]
        item.category = category
        item.manufacturer = robot["manufacturer"]
        # Bei unklarer Zuordnung wird die frühere Modellangabe nicht überschrieben.
        if item.model_number and item.model_number != robot["model"]:
            if item.model_number.casefold() in {
                "panda",
                "lbr iiwa",
                "mir100",
                "mir200",
                "spot",
                "rosbot 2 pro",
                "kr 60-3",
                "tx200",
            }:
                item.model_number = robot["model"]
        elif (
            not item.model_number
            and "zu prüfen" not in robot["model"]
            and robot["name"] != "KUKA KR 6 R900 sixx"
        ):
            item.model_number = robot["model"]
        item.responsible = user
        source_note = f"Bestandsquelle: {MATCH_URL}#{robot['anchor']}"
        if source_note not in item.description:
            existing = item.description.strip()
            if existing.startswith("Aus dem Bestellbestand übernommen."):
                existing = ""
            item.description = "\n\n".join(part for part in (existing, robot["summary"], source_note) if part)
        item.save(
            update_fields=[
                "name",
                "category",
                "manufacturer",
                "model_number",
                "responsible",
                "description",
                "updated_at",
            ]
        )

        ItemDocument.objects.get_or_create(
            item=item,
            doc_type=ItemDocument.DocType.DATASHEET,
            url=robot["datasheet"],
            defaults={"title": f"Technische Unterlage: {robot['model']}"},
        )
        photo_url = robot.get("photo_url")
        if photo_url:
            ItemDocument.objects.get_or_create(
                item=item,
                doc_type=ItemDocument.DocType.OTHER,
                url=photo_url,
                defaults={"title": "Bildquelle und Bildnachweis"},
            )
        for name, value, number, unit, source, kind in robot["specs"]:
            SpecificationProposal.objects.get_or_create(
                item=item,
                property_name=name,
                source_url=source,
                defaults={
                    "value_text": value,
                    "max_value": number if unit else None,
                    "unit": unit,
                    "source_title": f"Technische Unterlage: {robot['model']}"[:200],
                    "source_kind": kind,
                },
            )

        if robot["model"] == "TX200":
            self._correct_tx200_research(item)
        elif robot["model"] == "Panda":
            SpecificationProposal.objects.filter(
                item=item,
                property_name="Reichweite",
                value_text="850 mm",
                status=SpecificationProposal.Status.PENDING,
            ).update(status=SpecificationProposal.Status.REJECTED, reviewed_at=timezone.now())

        if photo_dir and robot.get("photo") and not item.photos.exists():
            path = photo_dir / robot["photo"]
            if path.is_file():
                with path.open("rb") as image:
                    photo = add_photo(item, image, None)
                photo.caption = (
                    "Beispielbild der Modellreihe; nicht das Institutsgerät"
                    if robot.get("photo_example")
                    else "match-Ausstattung; Typbild ohne Einzelidentifikation"
                )
                photo.save(update_fields=["caption"])
            else:
                self.stderr.write(self.style.WARNING(f"Bild fehlt: {path}"))
        self.stdout.write(f"Aktualisiert: {item.name} (#{item.pk})")

    def _correct_tx200_research(self, item):
        wrong_source = (
            "https://www.staubli.com/global/en/robotics/products/industrial-robots/6-axis/tx2-200.html"
        )
        SpecificationProposal.objects.filter(
            item=item,
            source_url=wrong_source,
            status=SpecificationProposal.Status.PENDING,
        ).update(status=SpecificationProposal.Status.REJECTED, reviewed_at=timezone.now())
        for order in item.purchase_orders.filter(research_data__model_number="TX2-200"):
            order.research_status = PurchaseOrder.ResearchStatus.RESEARCHED
            order.research_summary = (
                "Korrektur: Bestellung und match-Ausstattung nennen TX200, nicht TX2-200. "
                "Stäubli nennt für TX200 100 kg Nenntraglast, 130 kg maximale Traglast "
                "und 2.194 mm Reichweite. Die konkrete Konfiguration ist am Gerät zu prüfen."
            )
            order.research_source_url = STAUBLI
            order.research_source_title = "Stäubli TX200 – Herstellerunterlage"
            order.research_data = {
                "model_match": True,
                "product_name": "Stäubli TX200",
                "manufacturer": "Stäubli",
                "model_number": "TX200",
                "source_url": STAUBLI,
                "source_title": order.research_source_title,
                "source_kind": "manufacturer",
                "specifications": [
                    {"property_name": "Nenntraglast", "value_text": "100 kg"},
                    {"property_name": "Maximale Traglast", "value_text": "130 kg"},
                    {"property_name": "Reichweite", "value_text": "2.194 mm"},
                ],
            }
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
