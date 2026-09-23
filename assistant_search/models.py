from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .units import unit_matches_property


class SpecificationFields(models.Model):
    """Technische Eigenschaft mit nachvollziehbarer Quelle."""

    class SourceKind(models.TextChoices):
        MANUFACTURER = "manufacturer", "Hersteller"
        DEALER = "dealer", "Händler"
        DOCUMENT = "document", "Inventardokument"

    item = models.ForeignKey("inventory.Item", on_delete=models.CASCADE)
    property_name = models.CharField("Eigenschaft", max_length=100)
    value_text = models.CharField("Originalangabe", max_length=200)
    min_value = models.DecimalField("Minimum", max_digits=18, decimal_places=8, null=True, blank=True)
    max_value = models.DecimalField("Maximum", max_digits=18, decimal_places=8, null=True, blank=True)
    unit = models.CharField("Einheit", max_length=40, blank=True)
    source_url = models.URLField("Quellenlink", max_length=500)
    source_title = models.CharField("Quellentitel", max_length=200, blank=True)
    source_kind = models.CharField("Quellenart", max_length=20, choices=SourceKind.choices)
    created_at = models.DateTimeField("Erfasst am", auto_now_add=True)

    class Meta:
        abstract = True

    def clean(self):
        if self.min_value is not None and self.max_value is not None and self.min_value > self.max_value:
            raise ValidationError({"max_value": "Das Maximum darf nicht kleiner als das Minimum sein."})
        if (self.min_value is not None or self.max_value is not None) and not self.unit:
            raise ValidationError({"unit": "Für Zahlenwerte ist eine Einheit erforderlich."})
        if self.unit and not unit_matches_property(self.property_name, self.unit):
            raise ValidationError({"unit": "Die Einheit passt nicht zur angegebenen Messgröße."})


class ItemSpecification(SpecificationFields):
    item = models.ForeignKey("inventory.Item", on_delete=models.CASCADE, related_name="specifications")
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    verified_at = models.DateTimeField("Geprüft am", auto_now_add=True)

    class Meta:
        ordering = ["property_name", "pk"]
        verbose_name = "Geprüfter Kennwert"
        verbose_name_plural = "Geprüfte Kennwerte"

    def __str__(self):
        return f"{self.item}: {self.property_name} – {self.value_text}"


class SpecificationProposal(SpecificationFields):
    class Status(models.TextChoices):
        PENDING = "pending", "Zur Prüfung"
        APPROVED = "approved", "Übernommen"
        REJECTED = "rejected", "Verworfen"

    item = models.ForeignKey(
        "inventory.Item", on_delete=models.CASCADE, related_name="specification_proposals"
    )
    status = models.CharField("Status", max_length=20, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    reviewed_at = models.DateTimeField("Geprüft am", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Kennwertvorschlag"
        verbose_name_plural = "Kennwertvorschläge"

    def __str__(self):
        return f"{self.item}: {self.property_name} – {self.value_text} ({self.get_status_display()})"
