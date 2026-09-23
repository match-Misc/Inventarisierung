"""Fachlogik für Buchungen. Alle Statuswechsel laufen über diese Funktionen (siehe AGENTS.md).

Bisher ist nur das Anlegen einer Buchung umgesetzt (Grundlage für den Kalender). Genehmigen,
ablehnen, entnehmen, zurückgeben und verlängern folgen mit dem Rest von Schritt 3.
"""

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from inventory.models import Item

from .models import Booking


class BookingError(Exception):
    """Fachlicher Fehler bei einer Buchung. Die Meldung wird Nutzer:innen angezeigt."""


def effective_end_date(booking):
    """Tatsächliches Ende eines blockierenden Zeitraums: Bei Überfälligkeit bis heute."""
    today = timezone.localdate()
    if booking.status == Booking.Status.ACTIVE and booking.end_date < today:
        return today
    return booking.end_date


def find_conflicts(item, start_date, end_date, exclude_pk=None):
    """Buchungen, die den Zeitraum blockieren. Nur `reserved`/`active` blockieren (siehe AGENTS.md)."""
    qs = item.bookings.filter(status__in=Booking.BLOCKING, start_date__lte=end_date).select_related("borrower")
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return [booking for booking in qs if effective_end_date(booking) >= start_date]


def can_book_directly(item, user):
    """Frei entnehmbar, oder die buchende Person ist verantwortlich bzw. Admin."""
    return item.loan_policy == Item.LoanPolicy.FREE or item.can_manage(user)


@transaction.atomic
def create_booking(
    *,
    item,
    borrower,
    start_date,
    end_date,
    purpose="",
    usage_location="",
    request_message="",
    created_by=None,
):
    """Legt eine Buchung an: direkt (`reserved`/`active`) oder als Anfrage (`requested`).

    Sperrt das Gerät mit `select_for_update()` gegen gleichzeitige Buchungen.
    """
    if borrower is None or not borrower.is_authenticated:
        raise PermissionDenied
    item = Item.objects.select_for_update().get(pk=item.pk)
    if not item.is_bookable:
        raise BookingError(f"„{item}“ ist derzeit nicht verfügbar ({item.get_condition_display()}).")
    if end_date < start_date:
        raise BookingError("Das Enddatum darf nicht vor dem Startdatum liegen.")
    today = timezone.localdate()
    if start_date < today:
        raise BookingError("Der Beginn darf nicht in der Vergangenheit liegen.")

    direct = can_book_directly(item, borrower)
    if direct:
        conflicts = find_conflicts(item, start_date, end_date)
        if conflicts:
            other = conflicts[0]
            raise BookingError(
                f"„{item}“ ist im gewählten Zeitraum bereits an {other.borrower.short_name} vergeben "
                f"({other.start_date:%d.%m.%Y}–{other.end_date:%d.%m.%Y})."
            )
        status = Booking.Status.ACTIVE if start_date == today else Booking.Status.RESERVED
    else:
        status = Booking.Status.REQUESTED

    booking = Booking.objects.create(
        item=item,
        borrower=borrower,
        created_by=created_by or borrower,
        start_date=start_date,
        end_date=end_date,
        status=status,
        purpose=purpose,
        usage_location=usage_location,
        request_message=request_message,
        checked_out_at=timezone.now() if status == Booking.Status.ACTIVE else None,
    )

    if status == Booking.Status.REQUESTED:
        from . import notifications

        transaction.on_commit(lambda: notifications.send_booking_requested(booking))

    return booking
