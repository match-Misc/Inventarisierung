"""E-Mails zur Ausleihe.

Jede E-Mail-Art ist an eine Einstellung in accounts.NotificationPreferences gebunden (`setting`).
`setting=None` heißt Pflicht-Mail (z. B. Mahnung bei Überfälligkeit). Versandfehler werden nur geloggt.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from inventory.models import Item

logger = logging.getLogger(__name__)

# Wie viele Tage vor Beginn einer Reservierung „Gerät ist wieder da“ verschickt wird
AVAILABLE_NOTICE_DAYS = 3


def _url(path):
    return f"{settings.SITE_URL}{path}"


def wants(user, setting):
    if user is None or not user.is_active or not user.email:
        return False
    return setting is None or user.notification_settings.wants(setting)


def send(user, setting, subject, template, context):
    """Schickt eine Text-Mail an `user`, falls gewünscht. Gibt True zurück, wenn verschickt."""
    if not wants(user, setting):
        return False
    body = render_to_string(
        f"email/{template}.txt",
        {
            "site_name": settings.SITE_NAME,
            "site_url": settings.SITE_URL,
            "settings_url": _url(reverse("accounts:notifications")),
            "recipient": user,
            **context,
        },
    )
    message = EmailMessage(f"[{settings.SITE_NAME}] {subject}", body, to=[user.email])
    try:
        message.send()
    except Exception:
        logger.exception("E-Mail „%s“ an %s konnte nicht verschickt werden", subject, user.email)
        return False
    return True


def _context(booking, **extra):
    return {
        "booking": booking,
        "item": booking.item,
        "item_url": _url(booking.item.get_absolute_url()),
        "dashboard_url": _url(reverse("dashboard")),
        **extra,
    }


def _owner_setting(item):
    """Aktivität an Geräten: genehmigungspflichtig und frei entnehmbar getrennt einstellbar."""
    return "owner_returns" if item.loan_policy == Item.LoanPolicy.APPROVAL else "owner_activity"


# ---------- Sofort (aus loans.services) ----------


def request_created(booking):
    return send(
        booking.item.responsible,
        "new_requests",
        f"Ausleihanfrage: {booking.item}",
        "request_created",
        _context(booking),
    )


def extension_requested(booking):
    return send(
        booking.item.responsible,
        "new_requests",
        f"Verlängerungsanfrage: {booking.item}",
        "extension_requested",
        _context(booking),
    )


def request_decided(booking):
    approved = booking.status == booking.Status.RESERVED
    return send(
        booking.borrower,
        "booking_updates",
        f"Anfrage {'genehmigt' if approved else 'abgelehnt'}: {booking.item}",
        "request_decided",
        _context(booking, approved=approved),
    )


def extension_decided(booking, approved, requested_end_date=None, comment=""):
    return send(
        booking.borrower,
        "booking_updates",
        f"Verlängerung {'genehmigt' if approved else 'abgelehnt'}: {booking.item}",
        "extension_decided",
        _context(booking, approved=approved, requested_end_date=requested_end_date, comment=comment),
    )


def booking_created(booking):
    """Direkte Buchung (ausgeliehen/reserviert): Ausleiher/in, falls für sie eingetragen; Verantwortliche/r."""
    creator, borrower, owner = booking.created_by, booking.borrower, booking.item.responsible
    if creator and creator.pk != borrower.pk:
        send(
            borrower,
            "booking_updates",
            f"Buchung für dich eingetragen: {booking.item}",
            "booking_created_for_you",
            _context(booking),
        )
    if owner.pk not in {borrower.pk, getattr(creator, "pk", None)}:
        send(
            owner,
            _owner_setting(booking.item),
            f"{booking.get_status_display()}: {booking.item}",
            "owner_activity",
            _context(booking),
        )


def booking_cancelled(booking, by_user):
    owner, borrower = booking.item.responsible, booking.borrower
    if by_user.pk == borrower.pk:
        if owner.pk == by_user.pk:
            return False
        return send(
            owner,
            _owner_setting(booking.item),
            f"Storniert: {booking.item}",
            "booking_cancelled",
            _context(booking, by_user=by_user),
        )
    return send(
        borrower,
        "booking_updates",
        f"Deine Buchung wurde storniert: {booking.item}",
        "booking_cancelled",
        _context(booking, by_user=by_user),
    )


def item_returned(booking):
    owner = booking.item.responsible
    if owner.pk != booking.returned_by_id:
        # Rückgaben mit Hinweis sind wichtig und kommen immer (nur der Hauptschalter zählt)
        setting = "enabled" if booking.return_note else _owner_setting(booking.item)
        send(owner, setting, f"Zurückgegeben: {booking.item}", "item_returned", _context(booking))
    notify_waiting_reservations(booking)


def notify_waiting_reservations(returned):
    """Wer das Gerät bald reserviert hat, erfährt, dass es wieder da ist."""
    from .models import Booking

    today = timezone.localdate()
    waiting = (
        Booking.objects.filter(
            item=returned.item,
            status=Booking.Status.RESERVED,
            start_date__lte=today + timedelta(days=AVAILABLE_NOTICE_DAYS),
            end_date__gte=today,
        )
        .exclude(borrower=returned.borrower)
        .select_related("borrower", "item__location")
    )
    for booking in waiting:
        send(
            booking.borrower,
            "item_available",
            f"Wieder verfügbar: {booking.item}",
            "item_available",
            _context(booking),
        )


def booking_expired(booking):
    return send(
        booking.borrower,
        "booking_updates",
        f"{'Anfrage' if booking.decided_at is None else 'Reservierung'} verfallen: {booking.item}",
        "booking_expired",
        _context(booking),
    )


# ---------- Erinnerungen (aus loans.reminders, täglich) ----------


def reminder_starts(booking):
    return send(
        booking.borrower,
        "start_reminder",
        f"Reservierung beginnt {_when(booking.start_date)}: {booking.item}",
        "reminder_starts",
        _context(booking, when=_when(booking.start_date)),
    )


def reminder_due(booking):
    return send(
        booking.borrower,
        "due_reminder",
        f"Rückgabe {_when(booking.end_date)} fällig: {booking.item}",
        "reminder_due",
        _context(booking, when=_when(booking.end_date)),
    )


def reminder_overdue(booking):
    days = (timezone.localdate() - booking.end_date).days
    return send(
        booking.borrower,
        None,
        f"Rückgabe überfällig: {booking.item}",
        "reminder_overdue",
        _context(booking, days_overdue=days),
    )


def owner_overdue(booking):
    days = (timezone.localdate() - booking.end_date).days
    return send(
        booking.item.responsible,
        "owner_overdue",
        f"Dein Gerät ist überfällig: {booking.item}",
        "owner_overdue",
        _context(booking, days_overdue=days),
    )


def pending_digest(user, bookings):
    return send(
        user,
        "pending_digest",
        f"{len(bookings)} unbeantwortete Anfrage(n)",
        "pending_digest",
        {"bookings": bookings, "dashboard_url": _url(reverse("dashboard"))},
    )


def test_mail(user):
    return send(user, None, "Testmail", "test_mail", {"dashboard_url": _url(reverse("dashboard"))})


def _when(day):
    delta = (day - timezone.localdate()).days
    return {0: "heute", 1: "morgen", 2: "übermorgen"}.get(delta, f"am {day:%d.%m.%Y}")
