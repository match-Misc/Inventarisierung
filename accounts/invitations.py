"""Einladungs-E-Mails mit einem Link zum Setzen des Passworts.

Djangos PasswordResetForm überspringt Konten ohne nutzbares Passwort. Neue Konten haben
aber noch keins, deshalb bauen wir den Link hier selbst mit demselben Token-Mechanismus.
Der Link führt auf die normale Seite „Neues Passwort setzen“ (password_reset_confirm).
"""

import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)


def invitation_link(user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    path = reverse("password_reset_confirm", kwargs={"uidb64": uid, "token": token})
    return f"{settings.SITE_URL}{path}"


def send_invitation(user):
    """Verschickt die Einladung. Gibt False zurück, wenn keine Mail verschickt werden konnte."""
    if not user.email:
        return False
    body = render_to_string(
        "email/invitation.txt",
        {
            "user": user,
            "link": invitation_link(user),
            "site_name": settings.SITE_NAME,
            "site_url": settings.SITE_URL,
            "valid_days": settings.PASSWORD_RESET_TIMEOUT // (60 * 60 * 24),
        },
    )
    try:
        send_mail(f"[{settings.SITE_NAME}] Einladung", body, None, [user.email])
    except Exception:
        logger.exception("Einladung an %s konnte nicht verschickt werden", user.email)
        return False
    return True
