import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Prefetch, Q
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.text import get_valid_filename

from .validators import validate_document_file


class TreeNode(models.Model):
    """Basis für hierarchische Stammdaten. `path` speichert den vollen Pfad, z. B. „Geb. A › Raum 1“."""

    SEPARATOR = " › "

    name = models.CharField("Name", max_length=100)
    parent = models.ForeignKey(
        "self",
        verbose_name="Übergeordnet",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
    )
    path = models.CharField("Pfad", max_length=500, unique=True, editable=False)

    class Meta:
        abstract = True
        ordering = ["path"]

    def __str__(self):
        return self.path or self.name

    def save(self, *args, **kwargs):
        self.path = self.build_path()
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = {*kwargs["update_fields"], "path"}
        super().save(*args, **kwargs)
        for child in self.children.all():
            child.save()

    def build_path(self):
        return f"{self.parent.path}{self.SEPARATOR}{self.name}" if self.parent else self.name

    def clean(self):
        node = self.parent
        while node is not None:
            if self.pk and node.pk == self.pk:
                raise ValidationError(
                    {"parent": "Ein Eintrag kann nicht in sich selbst oder einem Untereintrag liegen."}
                )
            node = node.parent
        if type(self).objects.filter(path=self.build_path()).exclude(pk=self.pk).exists():
            raise ValidationError(
                {"name": "An dieser Stelle gibt es bereits einen Eintrag mit diesem Namen."}
            )

    def subtree_q(self, field):
        """Q-Objekt für „`field` ist dieser Eintrag oder liegt darunter“."""
        return Q(**{field: self}) | Q(**{f"{field}__path__startswith": self.path + self.SEPARATOR})


class Category(TreeNode):
    class Meta(TreeNode.Meta):
        verbose_name = "Kategorie"
        verbose_name_plural = "Kategorien"


class Location(TreeNode):
    description = models.CharField("Beschreibung", max_length=255, blank=True)

    class Meta(TreeNode.Meta):
        verbose_name = "Ort"
        verbose_name_plural = "Orte"


class ItemQuerySet(models.QuerySet):
    def with_status(self):
        """Lädt alles, was Listen für Foto und Ausleihstatus brauchen, ohne Folgeabfragen."""
        from loans.models import Booking

        active = Booking.objects.filter(status=Booking.Status.ACTIVE).select_related("borrower")
        return self.select_related("category", "location", "responsible").prefetch_related(
            "photos", Prefetch("bookings", queryset=active, to_attr="active_bookings")
        )


class Item(models.Model):
    class LoanPolicy(models.TextChoices):
        FREE = "free", "Frei entnehmbar"
        APPROVAL = "approval", "Nur mit Genehmigung"

    class Condition(models.TextChoices):
        OK = "ok", "Einsatzbereit"
        DEFECT = "defect", "Defekt"
        REPAIR = "repair", "In Reparatur / Kalibrierung"
        RETIRED = "retired", "Ausgemustert"

    name = models.CharField("Bezeichnung", max_length=200)
    category = models.ForeignKey(
        Category, verbose_name="Kategorie", on_delete=models.PROTECT, related_name="items"
    )
    manufacturer = models.CharField("Hersteller", max_length=100, blank=True)
    model_number = models.CharField("Modell / Typ", max_length=100, blank=True)
    serial_number = models.CharField("Seriennummer", max_length=100, blank=True)
    inventory_number = models.CharField(
        "Inventarnummer", max_length=50, blank=True, help_text="Offizielle Inventarnummer, falls vorhanden."
    )
    description = models.TextField("Beschreibung", blank=True)
    location = models.ForeignKey(
        Location, verbose_name="Ablageort", on_delete=models.PROTECT, related_name="items"
    )
    location_note = models.CharField(
        "Ablagehinweis", max_length=200, blank=True, help_text="z. B. „oberstes Fach, blaue Kiste“"
    )
    responsible = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Verantwortlich",
        on_delete=models.PROTECT,
        related_name="responsible_items",
    )
    loan_policy = models.CharField(
        "Ausleihregel",
        max_length=20,
        choices=LoanPolicy.choices,
        default=LoanPolicy.FREE,
        help_text="„Nur mit Genehmigung“: Andere müssen die Ausleihe anfragen und Sie entscheiden.",
    )
    condition = models.CharField("Zustand", max_length=20, choices=Condition.choices, default=Condition.OK)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Angelegt von",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField("Angelegt am", auto_now_add=True)
    updated_at = models.DateTimeField("Geändert am", auto_now=True)

    objects = ItemQuerySet.as_manager()

    class Meta:
        ordering = ["name", "pk"]
        verbose_name = "Gerät"
        verbose_name_plural = "Geräte"
        constraints = [
            models.UniqueConstraint(
                fields=["inventory_number"],
                condition=~Q(inventory_number=""),
                name="unique_inventory_number",
                violation_error_message="Diese Inventarnummer ist bereits vergeben.",
            )
        ]

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("inventory:item_detail", args=[self.pk])

    def can_manage(self, user):
        """Verantwortliche/r oder Admin: darf bearbeiten, genehmigen, Rückgaben buchen."""
        return bool(user and user.is_authenticated and (user.is_staff or user.pk == self.responsible_id))

    @property
    def is_bookable(self):
        return self.condition == self.Condition.OK

    @cached_property
    def current_booking(self):
        """Laufende Ausleihe oder None (nutzt die Daten aus `with_status()`, falls geladen)."""
        if hasattr(self, "active_bookings"):
            return self.active_bookings[0] if self.active_bookings else None
        from loans.models import Booking

        return self.bookings.filter(status=Booking.Status.ACTIVE).select_related("borrower").first()

    @cached_property
    def primary_photo(self):
        photos = list(self.photos.all())
        return next((p for p in photos if p.is_primary), photos[0] if photos else None)


def _item_file_path(instance, folder, filename):
    name = get_valid_filename(Path(filename).name)
    stem, suffix = Path(name).stem[:80], Path(name).suffix.lower()[:10]
    return f"items/{instance.item_id}/{folder}/{uuid.uuid4().hex[:12]}/{stem}{suffix}"


def photo_upload_to(instance, filename):
    return _item_file_path(instance, "fotos", filename)


def document_upload_to(instance, filename):
    return _item_file_path(instance, "dokumente", filename)


class ItemPhoto(models.Model):
    item = models.ForeignKey(Item, verbose_name="Gerät", on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField("Foto", upload_to=photo_upload_to, max_length=255)
    thumbnail = models.ImageField("Vorschaubild", upload_to=photo_upload_to, max_length=255, blank=True)
    caption = models.CharField("Bildunterschrift", max_length=200, blank=True)
    is_primary = models.BooleanField("Hauptfoto", default=False)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    uploaded_at = models.DateTimeField("Hochgeladen am", auto_now_add=True)

    class Meta:
        ordering = ["-is_primary", "uploaded_at", "pk"]
        verbose_name = "Foto"
        verbose_name_plural = "Fotos"

    def __str__(self):
        return self.caption or f"Foto {self.pk}"

    @property
    def thumb_url(self):
        return (self.thumbnail or self.image).url


class ItemDocument(models.Model):
    class DocType(models.TextChoices):
        MANUAL = "manual", "Handbuch"
        DATASHEET = "datasheet", "Datenblatt"
        CALIBRATION = "calibration", "Kalibrierschein"
        SOFTWARE = "software", "Software"
        OTHER = "other", "Sonstiges"

    item = models.ForeignKey(Item, verbose_name="Gerät", on_delete=models.CASCADE, related_name="documents")
    title = models.CharField("Titel", max_length=200)
    doc_type = models.CharField("Art", max_length=20, choices=DocType.choices, default=DocType.MANUAL)
    file = models.FileField(
        "Datei",
        upload_to=document_upload_to,
        max_length=255,
        blank=True,
        validators=[validate_document_file],
    )
    url = models.URLField("Link", max_length=500, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    uploaded_at = models.DateTimeField("Hochgeladen am", auto_now_add=True)

    class Meta:
        ordering = ["doc_type", "title", "pk"]
        verbose_name = "Dokument"
        verbose_name_plural = "Dokumente"
        constraints = [
            models.CheckConstraint(condition=~Q(file="") | ~Q(url=""), name="document_has_file_or_url")
        ]

    def __str__(self):
        return self.title

    def clean(self):
        if not self.file and not self.url:
            raise ValidationError({"file": "Bitte eine Datei hochladen oder einen Link angeben."})
        if self.file and self.url:
            raise ValidationError({"url": "Bitte entweder eine Datei oder einen Link angeben, nicht beides."})

    @property
    def href(self):
        return self.file.url if self.file else self.url

    @property
    def filename(self):
        return Path(self.file.name).name if self.file else ""


class Accessory(models.Model):
    item = models.ForeignKey(Item, verbose_name="Gerät", on_delete=models.CASCADE, related_name="accessories")
    name = models.CharField("Bezeichnung", max_length=200)
    quantity = models.PositiveSmallIntegerField("Anzahl", default=1)
    note = models.CharField("Hinweis", max_length=200, blank=True)

    class Meta:
        ordering = ["pk"]
        verbose_name = "Zubehörteil"
        verbose_name_plural = "Zubehör"

    def __str__(self):
        return f"{self.quantity} × {self.name}" if self.quantity != 1 else self.name
