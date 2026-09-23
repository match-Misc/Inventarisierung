"""Fachlogik der Ausleihe. Alle Statuswechsel einer Buchung laufen über diese Funktionen.

Blockierend sind Reservierungen und laufende Ausleihen. Eine überfällige Ausleihe blockiert bis zur
Rückgabe (effektives Ende = später von Enddatum und heute). Offene Anfragen blockieren nicht; beim
Genehmigen wird erneut geprüft.
"""

from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from inventory.models import Item

from . import notifications
from .models import Booking

Status = Booking.Status


class BookingError(Exception):
    """Fachlicher Fehler. Die Meldung wird Nutzer:innen so angezeigt."""


def booking_mode(item, user):
    """'direct', wenn ohne Genehmigung gebucht werden darf, sonst 'request'."""
    if item.loan_policy == Item.LoanPolicy.FREE or item.can_manage(user):
        return "direct"
    return "request"


def conflicting_bookings(item, start, end, *, exclude=None, today=None):
    """Buchungen, die den Zeitraum [start, end] (inklusive) belegen."""
    today = today or timezone.localdate()
    active = Q(status=Status.ACTIVE, start_date__lte=end)
    if start > today:
        active &= Q(end_date__gte=start)
    reserved = Q(status=Status.RESERVED, start_date__lte=end, end_date__gte=start)
    qs = Booking.objects.filter(item=item).filter(active | reserved).select_related("borrower")
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs


def _ensure_free(item, start, end, *, exclude=None, today=None):
    conflict = conflicting_bookings(item, start, end, exclude=exclude, today=today).first()
    if conflict:
        if conflict.status == Status.ACTIVE:
            what = f"ausgeliehen an {conflict.borrower.display_name}"
            if conflict.is_overdue:
                what += f" (Rückgabe war am {conflict.end_date:%d.%m.%Y} fällig)"
            else:
                what += f" bis {conflict.end_date:%d.%m.%Y}"
        else:
            what = (
                f"reserviert für {conflict.borrower.display_name} "
                f"vom {conflict.start_date:%d.%m.%Y} bis {conflict.end_date:%d.%m.%Y}"
            )
        raise BookingError(f"Das Gerät ist in diesem Zeitraum belegt: {what}.")


def _ensure_bookable(item):
    if not item.is_bookable:
        raise BookingError(
            f"Das Gerät kann derzeit nicht ausgeliehen werden (Zustand: {item.get_condition_display()})."
        )


def _lock_item(item):
    """Sperrt das Gerät bis zum Ende der Transaktion und verhindert so Doppelbuchungen."""
    return Item.objects.select_for_update().get(pk=item.pk)


def _reload(booking):
    item = _lock_item(booking.item)
    booking = Booking.objects.select_for_update(of=("self",)).select_related("borrower").get(pk=booking.pk)
    booking.item = item
    return booking


def _check_actor(booking, user, *, manager_only=False):
    is_manager = booking.item.can_manage(user)
    if not is_manager and (manager_only or booking.borrower_id != user.pk):
        raise PermissionDenied


def _notify(func, *args):
    transaction.on_commit(lambda: func(*args))


@transaction.atomic
def create_booking(
    *, item, user, start_date, end_date, borrower=None, purpose="", usage_location="", message=""
):
    """Bucht ein Gerät: sofort ausgeliehen, reserviert oder angefragt – je nach Regel und Startdatum."""
    item = _lock_item(item)
    borrower = borrower or user
    if borrower.pk != user.pk and not item.can_manage(user):
        raise PermissionDenied("Nur Verantwortliche können für andere Personen buchen.")
    today = timezone.localdate()
    _ensure_bookable(item)
    if start_date < today:
        raise BookingError("Der Zeitraum darf nicht in der Vergangenheit beginnen.")
    if end_date < start_date:
        raise BookingError("Das Enddatum darf nicht vor dem Startdatum liegen.")
    _ensure_free(item, start_date, end_date, today=today)

    if booking_mode(item, user) == "direct":
        status = Status.ACTIVE if start_date == today else Status.RESERVED
    else:
        status = Status.REQUESTED
    booking = Booking.objects.create(
        item=item,
        borrower=borrower,
        created_by=user,
        start_date=start_date,
        end_date=end_date,
        status=status,
        purpose=purpose,
        usage_location=usage_location,
        request_message=message,
        checked_out_at=timezone.now() if status == Status.ACTIVE else None,
    )
    if status == Status.REQUESTED:
        _notify(notifications.request_created, booking)
    elif borrower.pk != user.pk:
        _notify(notifications.booking_created_for_borrower, booking)
    return booking


def _decide(booking, user, comment):
    booking.decided_by = user
    booking.decided_at = timezone.now()
    booking.decision_comment = comment
    booking.save()


@transaction.atomic
def approve(booking, user, comment=""):
    booking = _reload(booking)
    _check_actor(booking, user, manager_only=True)
    if booking.status != Status.REQUESTED:
        raise BookingError("Diese Anfrage wurde bereits bearbeitet.")
    today = timezone.localdate()
    if booking.end_date < today:
        raise BookingError("Der angefragte Zeitraum ist bereits vorbei.")
    _ensure_bookable(booking.item)
    _ensure_free(booking.item, max(booking.start_date, today), booking.end_date, exclude=booking, today=today)
    booking.status = Status.RESERVED
    _decide(booking, user, comment)
    _notify(notifications.request_decided, booking)
    return booking


@transaction.atomic
def reject(booking, user, comment=""):
    booking = _reload(booking)
    _check_actor(booking, user, manager_only=True)
    if booking.status != Status.REQUESTED:
        raise BookingError("Diese Anfrage wurde bereits bearbeitet.")
    booking.status = Status.REJECTED
    _decide(booking, user, comment)
    _notify(notifications.request_decided, booking)
    return booking


@transaction.atomic
def cancel(booking, user):
    booking = _reload(booking)
    _check_actor(booking, user)
    if booking.status not in (Status.REQUESTED, Status.RESERVED):
        raise BookingError("Nur offene Anfragen und Reservierungen können storniert werden.")
    booking.status = Status.CANCELLED
    booking.save()
    _notify(notifications.booking_cancelled, booking, user)
    return booking


@transaction.atomic
def check_out(booking, user):
    """Reservierung abholen: Das Gerät gilt ab jetzt als ausgeliehen."""
    booking = _reload(booking)
    _check_actor(booking, user)
    if booking.status != Status.RESERVED:
        raise BookingError("Nur reservierte Buchungen können entnommen werden.")
    today = timezone.localdate()
    if booking.start_date > today:
        raise BookingError(f"Die Entnahme ist erst ab dem {booking.start_date:%d.%m.%Y} möglich.")
    if booking.end_date < today:
        raise BookingError("Der Reservierungszeitraum ist bereits vorbei.")
    _ensure_bookable(booking.item)
    other = (
        Booking.objects.filter(item=booking.item, status=Status.ACTIVE)
        .exclude(pk=booking.pk)
        .select_related("borrower")
        .first()
    )
    if other:
        contact = ", ".join(filter(None, [other.borrower.email, other.borrower.phone]))
        raise BookingError(
            f"Das Gerät ist noch an {other.borrower.display_name} ausgeliehen"
            f"{f' ({contact})' if contact else ''}. Bitte zuerst die Rückgabe klären."
        )
    booking.status = Status.ACTIVE
    booking.checked_out_at = timezone.now()
    booking.save()
    return booking


@transaction.atomic
def return_booking(booking, user, note=""):
    booking = _reload(booking)
    _check_actor(booking, user)
    if booking.status != Status.ACTIVE:
        raise BookingError("Das Gerät ist nicht (mehr) ausgeliehen.")
    booking.status = Status.RETURNED
    booking.returned_at = timezone.now()
    booking.returned_by = user
    booking.return_note = note
    booking.requested_end_date = None
    booking.save()
    _notify(notifications.item_returned, booking)
    return booking


@transaction.atomic
def extend(booking, user, new_end_date):
    """Verlängert direkt oder stellt eine Verlängerungsanfrage (genehmigungspflichtige Geräte)."""
    booking = _reload(booking)
    _check_actor(booking, user)
    if booking.status not in Booking.BLOCKING:
        raise BookingError("Nur Reservierungen und laufende Ausleihen können verlängert werden.")
    today = timezone.localdate()
    if new_end_date <= booking.end_date:
        raise BookingError("Das neue Enddatum muss nach dem bisherigen liegen.")
    if new_end_date < today:
        raise BookingError("Das neue Enddatum darf nicht in der Vergangenheit liegen.")
    _ensure_free(
        booking.item, booking.end_date + timedelta(days=1), new_end_date, exclude=booking, today=today
    )
    if booking_mode(booking.item, user) == "direct":
        booking.end_date = new_end_date
        booking.requested_end_date = None
        booking.save()
    else:
        booking.requested_end_date = new_end_date
        booking.save()
        _notify(notifications.extension_requested, booking)
    return booking


@transaction.atomic
def approve_extension(booking, user):
    booking = _reload(booking)
    _check_actor(booking, user, manager_only=True)
    if not booking.requested_end_date or booking.status not in Booking.BLOCKING:
        raise BookingError("Es liegt keine offene Verlängerungsanfrage vor.")
    _ensure_free(
        booking.item, booking.end_date + timedelta(days=1), booking.requested_end_date, exclude=booking
    )
    booking.end_date = booking.requested_end_date
    booking.requested_end_date = None
    booking.save()
    _notify(notifications.extension_decided, booking, True)
    return booking


@transaction.atomic
def reject_extension(booking, user, comment=""):
    booking = _reload(booking)
    _check_actor(booking, user, manager_only=True)
    if not booking.requested_end_date:
        raise BookingError("Es liegt keine offene Verlängerungsanfrage vor.")
    requested = booking.requested_end_date
    booking.requested_end_date = None
    booking.save()
    _notify(notifications.extension_decided, booking, False, requested, comment)
    return booking


def expire_stale(today=None):
    """Verstrichene Anfragen und nicht abgeholte Reservierungen auf „verfallen“ setzen."""
    today = today or timezone.localdate()
    return Booking.objects.filter(status__in=[Status.REQUESTED, Status.RESERVED], end_date__lt=today).update(
        status=Status.EXPIRED, updated_at=timezone.now()
    )
