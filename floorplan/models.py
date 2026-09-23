from django.db import models
from django.urls import reverse

from inventory.models import Location


class FloorPlan(models.Model):
    """Grundriss einer Halle bzw. eines Versuchsfelds. Alle Maße in Metern."""

    name = models.CharField("Name", max_length=100)
    location = models.OneToOneField(
        Location,
        verbose_name="Ort",
        on_delete=models.PROTECT,
        related_name="floor_plan",
        help_text="Ort, unter dem die Planobjekte als Unterorte angelegt werden.",
    )
    width = models.FloatField("Breite (m)")
    height = models.FloatField("Länge (m)")

    class Meta:
        ordering = ["name"]
        verbose_name = "Hallenplan"
        verbose_name_plural = "Hallenpläne"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("floorplan:detail", args=[self.pk])


class PlanElement(models.Model):
    """Objekt auf dem Plan (Schrank, Versuchsstand, Bereich …). x/y ist die linke obere Ecke."""

    class Kind(models.TextChoices):
        AREA = "area", "Bereich / Raum"
        CABINET = "cabinet", "Schrank / Regal"
        WORKSTATION = "workstation", "Tisch / Arbeitsplatz"
        TEST_RIG = "test_rig", "Versuchsstand / Anlage"
        MARKING = "marking", "Markierung / Weg"
        OTHER = "other", "Sonstiges"

    # In diesen Objekten können Geräte liegen, sie bekommen einen eigenen Ort.
    HOLDING_KINDS = {Kind.AREA, Kind.CABINET, Kind.WORKSTATION, Kind.TEST_RIG}

    plan = models.ForeignKey(
        FloorPlan, verbose_name="Hallenplan", on_delete=models.CASCADE, related_name="elements"
    )
    kind = models.CharField("Art", max_length=20, choices=Kind.choices, default=Kind.OTHER)
    label = models.CharField("Beschriftung", max_length=200, blank=True)
    x = models.FloatField("x (m)")
    y = models.FloatField("y (m)")
    width = models.FloatField("Breite (m)")
    height = models.FloatField("Tiefe (m)")
    rotation = models.FloatField("Drehung (°)", default=0)
    color = models.CharField("Farbe", max_length=7, blank=True, help_text="z. B. #ffffff")
    z = models.IntegerField("Ebene", default=0)
    location = models.OneToOneField(
        Location,
        verbose_name="Ort",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="plan_element",
    )

    class Meta:
        ordering = ["z", "pk"]
        verbose_name = "Planobjekt"
        verbose_name_plural = "Planobjekte"

    def __str__(self):
        return self.label.replace("\n", " ") or f"{self.get_kind_display()} {self.pk}"

    @property
    def holds_items(self):
        return self.kind in self.HOLDING_KINDS and bool(self.label.strip())

    def as_dict(self):
        return {
            "id": self.pk,
            "kind": self.kind,
            "label": self.label,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "color": self.color,
            "z": self.z,
            "location": self.location_id,
        }


def element_for_location(location):
    """Planobjekt, zu dem ein Ort gehört – auch wenn der Ort darunter liegt (z. B. Fach im Schrank)."""
    node = location
    while node is not None:
        element = PlanElement.objects.filter(location=node).select_related("plan").first()
        if element:
            return element
        node = node.parent
    return None
