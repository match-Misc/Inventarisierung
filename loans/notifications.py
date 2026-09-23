"""E-Mail-Benachrichtigungen zur Ausleihe. Versandfehler werden nur geloggt (siehe AGENTS.md)."""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def _send(subject, template, context, to):
    if not to:
        return
    body = render_to_string(
        template, {**context, "site_name": settings.SITE_NAME, "site_url": settings.SITE_URL}
    )
    try:
        send_mail(f"[{settings.SITE_NAME}] {subject}", body, None, to)
    except Exception:
        logger.exception("E-Mail „%s“ an %s konnte nicht verschickt werden", subject, to)


def send_booking_requested(booking):
    """An die/den Verantwortliche/n: Es liegt eine neue Ausleihanfrage vor."""
    item = booking.item
    if not item.responsible.email:
        return
    _send(
        "Neue Ausleihanfrage",
        "email/booking_requested.txt",
        {"booking": booking, "item": item},
        [item.responsible.email],
    )
