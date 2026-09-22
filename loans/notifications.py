import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


def send_booking_notice(booking_id, template_name, recipient):
    if not recipient:
        return
    from .models import Booking

    try:
        booking = Booking.objects.select_related("item", "borrower").get(pk=booking_id)
        body = render_to_string(
            f"email/{template_name}.txt", {"booking": booking, "site_url": settings.SITE_URL}
        )
        send_mail(
            "Geräteinventar: Buchung", body, settings.DEFAULT_FROM_EMAIL, [recipient], fail_silently=False
        )
    except Exception:
        logger.exception("Buchungsbenachrichtigung konnte nicht versendet werden (Buchung %s).", booking_id)
