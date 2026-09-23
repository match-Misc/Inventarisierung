"""E-Mails zur Ausleihe. Ein Versandfehler wird nur geloggt und blockiert nichts."""

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.urls import reverse

from inventory.models import Item

logger = logging.getLogger(__name__)


def _url(path):
    return f"{settings.SITE_URL}{path}"


def send(subject, template, context, to, cc=()):
    """Schickt eine Text-Mail an Nutzer (nicht Adressen). Gibt True zurück, wenn verschickt."""
    to_addresses = [u.email for u in to if u and u.email]
    cc_addresses = [u.email for u in cc if u and u.email and u.email not in to_addresses]
    if not to_addresses and not cc_addresses:
        return False
    body = render_to_string(
        f"email/{template}.txt",
        {"site_name": settings.SITE_NAME, "site_url": settings.SITE_URL, **context},
    )
    message = EmailMessage(
        f"[{settings.SITE_NAME}] {subject}",
        body,
        to=to_addresses or cc_addresses,
        cc=cc_addresses if to_addresses else [],
    )
    try:
        message.send()
    except Exception:
        logger.exception("E-Mail „%s“ an %s konnte nicht verschickt werden", subject, to_addresses)
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


def request_created(booking):
    return send(
        f"Ausleihanfrage: {booking.item}", "request_created", _context(booking), [booking.item.responsible]
    )


def extension_requested(booking):
    return send(
        f"Verlängerungsanfrage: {booking.item}",
        "extension_requested",
        _context(booking),
        [booking.item.responsible],
    )


def request_decided(booking):
    approved = booking.status == booking.Status.RESERVED
    return send(
        f"Anfrage {'genehmigt' if approved else 'abgelehnt'}: {booking.item}",
        "request_decided",
        _context(booking, approved=approved),
        [booking.borrower],
    )


def extension_decided(booking, approved, requested_end_date=None, comment=""):
    return send(
        f"Verlängerung {'genehmigt' if approved else 'abgelehnt'}: {booking.item}",
        "extension_decided",
        _context(booking, approved=approved, requested_end_date=requested_end_date, comment=comment),
        [booking.borrower],
    )


def booking_cancelled(booking, by_user):
    if by_user.pk == booking.borrower_id:
        responsible = booking.item.responsible
        if booking.item.loan_policy != Item.LoanPolicy.APPROVAL or responsible.pk == by_user.pk:
            return False
        recipient = responsible
    else:
        recipient = booking.borrower
    return send(
        f"Storniert: {booking.item}", "booking_cancelled", _context(booking, by_user=by_user), [recipient]
    )


def item_returned(booking):
    responsible = booking.item.responsible
    if responsible.pk == booking.returned_by_id:
        return False
    if booking.item.loan_policy != Item.LoanPolicy.APPROVAL and not booking.return_note:
        return False
    return send(f"Zurückgegeben: {booking.item}", "item_returned", _context(booking), [responsible])


def booking_created_for_borrower(booking):
    return send(
        f"Ausleihe eingetragen: {booking.item}",
        "booking_created_for_you",
        _context(booking),
        [booking.borrower],
    )
