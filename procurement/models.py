from django.db import models


class PurchaseOrder(models.Model):
    """Eine Bestellung aus dem Ordner `01_Bestellungen`. Wird monatlich per Sync eingelesen.

    `manually_verified` schützt handgepflegte Angaben: Der Sync überschreibt dann nur noch
    `last_seen`, nicht die Fachfelder.
    """

    class ToolType(models.TextChoices):
        SENSOR = "sensor", "Sensor"
        ACTUATOR = "actuator", "Aktor"
        TOOL = "tool", "Werkzeug"
        IT = "it", "IT / Elektronik"
        FURNITURE = "furniture", "Möbel"
        OTHER = "other", "Sonstiges"

    name = models.CharField("Bezeichnung", max_length=255)
    company = models.CharField("Firma", max_length=255, blank=True)
    price = models.DecimalField("Preis (€)", max_digits=10, decimal_places=2, null=True, blank=True)
    tool_type = models.CharField(
        "Typ", max_length=20, choices=ToolType.choices, default=ToolType.OTHER, blank=True
    )
    key_specs = models.TextField(
        "Kurzbeschreibung / Kenndaten",
        blank=True,
        help_text="Kurze Stichpunktliste, z. B. aus dem Datenblatt.",
    )
    purchase_date = models.DateField("Kaufdatum", null=True, blank=True)
    project = models.CharField("Projekt", max_length=200, blank=True)

    source_folder = models.CharField(
        "Quellordner",
        max_length=500,
        unique=True,
        help_text="Pfad relativ zum Basisordner, dient als eindeutiger Schlüssel für den Sync.",
    )
    datasheet_path = models.CharField(
        "Datenblatt", max_length=500, blank=True, help_text="Pfad relativ zum Basisordner."
    )

    manually_verified = models.BooleanField(
        "Manuell geprüft",
        default=False,
        help_text="Wenn gesetzt, überschreibt der monatliche Sync die Fachfelder nicht mehr.",
    )
    is_missing = models.BooleanField(
        "Ordner fehlt",
        default=False,
        help_text="Der Quellordner wurde beim letzten Sync nicht mehr gefunden.",
    )

    created_at = models.DateTimeField("Erstellt am", auto_now_add=True)
    last_synced = models.DateTimeField("Zuletzt synchronisiert", null=True, blank=True)

    class Meta:
        ordering = ["-purchase_date", "name"]
        verbose_name = "Bestellung"
        verbose_name_plural = "Bestellungen"

    def __str__(self):
        return self.name
