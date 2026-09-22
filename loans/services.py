"""Alle Buchungs-Statuswechsel und Konfliktprüfungen liegen an einer Stelle."""

from datetime import date

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from inventory.models import Item

from .models import Booking
from .notifications import send_booking_notice


class BookingError(Exception):
    pass


def _notify(booking, kind):
    if kind == "request":
        recipient = booking.item.responsible.email
        template = "booking_request"
    else:
        recipient = booking.borrower.email
        template = "booking_decision"
    transaction.on_commit(lambda: send_booking_notice(booking.pk, template, recipient))


def _require_user(user):
    if not user or not user.is_authenticated:
        raise PermissionDenied


def _require_manager(item, user):
    if not item.can_manage(user):
        raise PermissionDenied


def _require_participant(booking, user):
    if user.pk != booking.borrower_id and not booking.item.can_manage(user):
        raise PermissionDenied


def _check_dates(start_date, end_date):
    if not isinstance(start_date, date) or not isinstance(end_date, date) or end_date < start_date:
        raise BookingError("Bitte einen gültigen Zeitraum wählen.")
    if end_date < timezone.localdate():
        raise BookingError("Der Zeitraum liegt bereits in der Vergangenheit.")


def _check_conflict(item, start_date, end_date, *, exclude_id=None):
    today = timezone.localdate()
    for other in Booking.objects.filter(item=item, status__in=Booking.BLOCKING).exclude(pk=exclude_id):
        effective_end = (
            max(other.end_date, today) if other.status == Booking.Status.ACTIVE else other.end_date
        )
        if other.start_date <= end_date and effective_end >= start_date:
            raise BookingError("Das Gerät ist in diesem Zeitraum bereits gebucht.")


def _locked_booking(booking_id):
    booking = Booking.objects.select_related("borrower", "item__responsible").get(pk=booking_id)
    Item.objects.select_for_update().get(pk=booking.item_id)
    return (
        Booking.objects.select_for_update().select_related("borrower", "item__responsible").get(pk=booking_id)
    )


@transaction.atomic
def create_booking(*, user, item_id, start_date, end_date, purpose="", usage_location="", request_message=""):
    _require_user(user)
    _check_dates(start_date, end_date)
    if start_date < timezone.localdate():
        raise BookingError("Die Buchung kann nicht vor heute beginnen.")
    item = Item.objects.select_for_update().select_related("responsible").get(pk=item_id)
    if not item.is_bookable:
        raise BookingError("Das Gerät ist derzeit nicht buchbar.")
    direct = item.loan_policy == Item.LoanPolicy.FREE or item.can_manage(user)
    if direct:
        _check_conflict(item, start_date, end_date)
        status = Booking.Status.ACTIVE if start_date == timezone.localdate() else Booking.Status.RESERVED
    else:
        status = Booking.Status.REQUESTED
    booking = Booking.objects.create(
        item=item,
        borrower=user,
        created_by=user,
        start_date=start_date,
        end_date=end_date,
        status=status,
        purpose=purpose[:200],
        usage_location=usage_location[:200],
        request_message=request_message,
        checked_out_at=timezone.now() if status == Booking.Status.ACTIVE else None,
    )
    if status == Booking.Status.REQUESTED:
        _notify(booking, "request")
    return booking


@transaction.atomic
def approve_booking(*, booking_id, user, comment=""):
    _require_user(user)
    booking = _locked_booking(booking_id)
    _require_manager(booking.item, user)
    if booking.status != Booking.Status.REQUESTED:
        raise BookingError("Nur offene Anfragen können genehmigt werden.")
    _check_dates(booking.start_date, booking.end_date)
    _check_conflict(booking.item, booking.start_date, booking.end_date, exclude_id=booking.pk)
    booking.status = Booking.Status.RESERVED
    booking.decided_by = user
    booking.decided_at = timezone.now()
    booking.decision_comment = comment
    booking.save()
    _notify(booking, "decision")
    return booking


@transaction.atomic
def reject_booking(*, booking_id, user, comment=""):
    _require_user(user)
    booking = _locked_booking(booking_id)
    _require_manager(booking.item, user)
    if booking.status != Booking.Status.REQUESTED:
        raise BookingError("Nur offene Anfragen können abgelehnt werden.")
    booking.status = Booking.Status.REJECTED
    booking.decided_by = user
    booking.decided_at = timezone.now()
    booking.decision_comment = comment
    booking.save()
    _notify(booking, "decision")
    return booking


@transaction.atomic
def cancel_booking(*, booking_id, user):
    _require_user(user)
    booking = _locked_booking(booking_id)
    _require_participant(booking, user)
    if booking.status not in {Booking.Status.REQUESTED, Booking.Status.RESERVED}:
        raise BookingError("Diese Buchung kann nicht storniert werden.")
    booking.status = Booking.Status.CANCELLED
    booking.save()
    return booking


@transaction.atomic
def checkout_booking(*, booking_id, user):
    _require_user(user)
    booking = _locked_booking(booking_id)
    _require_participant(booking, user)
    if booking.status != Booking.Status.RESERVED:
        raise BookingError("Nur reservierte Geräte können entnommen werden.")
    today = timezone.localdate()
    if not booking.start_date <= today <= booking.end_date:
        raise BookingError("Das Gerät kann nur im reservierten Zeitraum entnommen werden.")
    booking.status = Booking.Status.ACTIVE
    booking.checked_out_at = timezone.now()
    booking.save()
    return booking


@transaction.atomic
def return_booking(*, booking_id, user, note=""):
    _require_user(user)
    booking = _locked_booking(booking_id)
    _require_participant(booking, user)
    if booking.status != Booking.Status.ACTIVE:
        raise BookingError("Nur ausgeliehene Geräte können zurückgegeben werden.")
    booking.status = Booking.Status.RETURNED
    booking.returned_at = timezone.now()
    booking.returned_by = user
    booking.return_note = note
    booking.save()
    return booking


@transaction.atomic
def extend_booking(*, booking_id, user, new_end_date):
    _require_user(user)
    booking = _locked_booking(booking_id)
    _require_participant(booking, user)
    if booking.status not in Booking.BLOCKING:
        raise BookingError("Nur laufende Buchungen können verlängert werden.")
    if new_end_date <= booking.end_date:
        raise BookingError("Das neue Enddatum muss später liegen.")
    _check_dates(booking.start_date, new_end_date)
    if booking.item.loan_policy == Item.LoanPolicy.APPROVAL and not booking.item.can_manage(user):
        booking.requested_end_date = new_end_date
        booking.save()
        _notify(booking, "request")
    else:
        _check_conflict(booking.item, booking.start_date, new_end_date, exclude_id=booking.pk)
        booking.end_date = new_end_date
        booking.save()
    return booking


@transaction.atomic
def decide_extension(*, booking_id, user, approve, comment=""):
    _require_user(user)
    booking = _locked_booking(booking_id)
    _require_manager(booking.item, user)
    if booking.status not in Booking.BLOCKING or booking.requested_end_date is None:
        raise BookingError("Es liegt keine Verlängerungsanfrage vor.")
    if approve:
        _check_conflict(booking.item, booking.start_date, booking.requested_end_date, exclude_id=booking.pk)
        booking.end_date = booking.requested_end_date
    booking.requested_end_date = None
    booking.decided_by = user
    booking.decided_at = timezone.now()
    booking.decision_comment = comment
    booking.save()
    _notify(booking, "decision")
    return booking


def expire_stale_bookings():
    """Verstrichene Anfragen/Reservierungen freigeben; laufende Ausleihen bleiben aktiv."""
    today = timezone.localdate()
    ids = list(
        Booking.objects.filter(
            status__in=(Booking.Status.REQUESTED, Booking.Status.RESERVED), end_date__lt=today
        ).values_list("pk", flat=True)
    )
    expired = 0
    for booking_id in ids:
        with transaction.atomic():
            booking = _locked_booking(booking_id)
            if (
                booking.status in (Booking.Status.REQUESTED, Booking.Status.RESERVED)
                and booking.end_date < today
            ):
                booking.status = Booking.Status.EXPIRED
                booking.save(update_fields=["status", "updated_at"])
                expired += 1
    return expired
