from django.conf import settings
from django.db import models
from django.db.models import F, Q
from django.utils import timezone


class Booking(models.Model):
    """Eine Ausleihe, Reservierung oder Anfrage. Statuswechsel nur über loans.services."""

    class Status(models.TextChoices):
        REQUESTED = "requested", "Angefragt"
        RESERVED = "reserved", "Reserviert"
        ACTIVE = "active", "Ausgeliehen"
        RETURNED = "returned", "Zurückgegeben"
        REJECTED = "rejected", "Abgelehnt"
        CANCELLED = "cancelled", "Storniert"
        EXPIRED = "expired", "Verfallen"

    # Diese Status belegen einen Zeitraum.
    BLOCKING = (Status.RESERVED, Status.ACTIVE)
    OPEN = (Status.REQUESTED, Status.RESERVED, Status.ACTIVE)

    item = models.ForeignKey(
        "inventory.Item", verbose_name="Gerät", on_delete=models.PROTECT, related_name="bookings"
    )
    borrower = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Ausleiher/in",
        on_delete=models.PROTECT,
        related_name="bookings",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Eingetragen von",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    start_date = models.DateField("Von")
    end_date = models.DateField("Bis (voraussichtliche Rückgabe)")
    status = models.CharField("Status", max_length=20, choices=Status.choices, db_index=True)
    purpose = models.CharField("Zweck / Projekt", max_length=200, blank=True)
    usage_location = models.CharField("Einsatzort", max_length=200, blank=True)
    request_message = models.TextField("Nachricht an Verantwortliche/n", blank=True)
    decision_comment = models.TextField("Kommentar zur Entscheidung", blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Entschieden von",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    decided_at = models.DateTimeField("Entschieden am", null=True, blank=True)
    requested_end_date = models.DateField("Beantragtes neues Enddatum", null=True, blank=True)
    checked_out_at = models.DateTimeField("Entnommen am", null=True, blank=True)
    returned_at = models.DateTimeField("Zurückgegeben am", null=True, blank=True)
    returned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Rückgabe gebucht von",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    return_note = models.TextField("Rückgabenotiz", blank=True)
    created_at = models.DateTimeField("Erstellt am", auto_now_add=True)
    updated_at = models.DateTimeField("Geändert am", auto_now=True)

    class Meta:
        ordering = ["start_date", "pk"]
        verbose_name = "Buchung"
        verbose_name_plural = "Buchungen"
        constraints = [
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")), name="booking_end_not_before_start"
            )
        ]
        indexes = [models.Index(fields=["item", "status", "start_date", "end_date"])]

    def __str__(self):
        return f"{self.item} – {self.borrower} ({self.start_date:%d.%m.%Y}–{self.end_date:%d.%m.%Y})"

    @property
    def is_overdue(self):
        return self.status == self.Status.ACTIVE and self.end_date < timezone.localdate()


class ReminderLog(models.Model):
    """Versandprotokoll der täglichen Erinnerungen (verhindert doppelte Mails)."""

    class Kind(models.TextChoices):
        STARTS_SOON = "starts_soon", "Reservierung beginnt"
        DUE_SOON = "due_soon", "Rückgabe fällig"
        OVERDUE = "overdue", "Überfällig (an Ausleiher/in)"
        OWNER_OVERDUE = "owner_overdue", "Überfällig (an Verantwortliche/n)"
        PENDING_REQUEST = "pending_request", "Unbeantwortete Anfrage"

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name="reminders")
    kind = models.CharField("Art", max_length=20, choices=Kind.choices)
    sent_on = models.DateField("Versendet am")

    class Meta:
        verbose_name = "Erinnerung"
        verbose_name_plural = "Erinnerungen"
        constraints = [
            models.UniqueConstraint(fields=["booking", "kind", "sent_on"], name="unique_reminder_per_day")
        ]

    def __str__(self):
        return f"{self.get_kind_display()} – {self.booking} ({self.sent_on:%d.%m.%Y})"
