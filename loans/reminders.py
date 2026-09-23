"""Täglicher Erinnerungslauf (manage.py send_reminders).

Jede verschickte Erinnerung wird im ReminderLog festgehalten. Dadurch schadet es nicht, den Lauf
mehrmals am Tag zu starten: Nichts wird doppelt verschickt.
"""

from collections import defaultdict
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from accounts.models import OFF

from . import notifications, services
from .models import Booking, ReminderLog

Kind = ReminderLog.Kind
Status = Booking.Status
OWNER_OVERDUE_INTERVAL = 7


def _last_sent(booking, kind):
    return booking.reminders.filter(kind=kind).order_by("-sent_on").values_list("sent_on", flat=True).first()


def _log(booking, kind, today):
    ReminderLog.objects.get_or_create(booking=booking, kind=kind, sent_on=today)


def _due_today(last, today, interval):
    return last is None or (today - last).days >= max(interval, 1)


def run(today=None):
    """Verschickt alle fälligen Erinnerungen. Gibt die Anzahl je Art zurück."""
    today = today or timezone.localdate()
    stats = {"verfallen": services.expire_stale(today)}
    bookings = Booking.objects.select_related("item__responsible", "item__location", "borrower")

    # Reservierung beginnt (0 = am Starttag, 1 = Vortag – je nach Einstellung)
    sent = 0
    for booking in bookings.filter(
        status=Status.RESERVED, start_date__range=(today, today + timedelta(days=1))
    ):
        days_before = booking.borrower.notification_settings.start_reminder
        if (
            days_before != OFF
            and (booking.start_date - today).days == days_before
            and _last_sent(booking, Kind.STARTS_SOON) is None
            and notifications.reminder_starts(booking)
        ):
            _log(booking, Kind.STARTS_SOON, today)
            sent += 1
    stats["reservierung_beginnt"] = sent

    # Rückgabe fällig (0–2 Tage vorher, je nach Einstellung). Nach einer Verlängerung erneut.
    sent = 0
    for booking in bookings.filter(status=Status.ACTIVE, end_date__range=(today, today + timedelta(days=2))):
        days_before = booking.borrower.notification_settings.due_reminder
        if days_before != OFF and (booking.end_date - today).days == days_before:
            last = _last_sent(booking, Kind.DUE_SOON)
            if (last is None or last < booking.end_date - timedelta(days=2)) and notifications.reminder_due(
                booking
            ):
                _log(booking, Kind.DUE_SOON, today)
                sent += 1
    stats["rueckgabe_faellig"] = sent

    # Überfällig: Ausleiher/in im gewählten Abstand, Verantwortliche/r am ersten Tag und dann wöchentlich
    sent_borrower = sent_owner = 0
    for booking in bookings.filter(status=Status.ACTIVE, end_date__lt=today):
        interval = booking.borrower.notification_settings.overdue_interval
        if _due_today(_last_sent(booking, Kind.OVERDUE), today, interval) and notifications.reminder_overdue(
            booking
        ):
            _log(booking, Kind.OVERDUE, today)
            sent_borrower += 1
        owner = booking.item.responsible
        if (
            owner.pk != booking.borrower_id
            and _due_today(_last_sent(booking, Kind.OWNER_OVERDUE), today, OWNER_OVERDUE_INTERVAL)
            and notifications.owner_overdue(booking)
        ):
            _log(booking, Kind.OWNER_OVERDUE, today)
            sent_owner += 1
    stats["ueberfaellig"] = sent_borrower
    stats["ueberfaellig_verantwortliche"] = sent_owner

    # Unbeantwortete Anfragen: Sammelmail an Verantwortliche nach 1–3 Tagen (Einstellung), dann im selben Abstand
    waiting = bookings.filter(
        Q(status=Status.REQUESTED) | Q(status__in=Booking.BLOCKING, requested_end_date__isnull=False)
    )
    per_owner = defaultdict(list)
    for booking in waiting:
        owner = booking.item.responsible
        after = owner.notification_settings.pending_digest
        if after == OFF:
            continue
        waiting_since = timezone.localdate(booking.updated_at)
        if (today - waiting_since).days >= after and _due_today(
            _last_sent(booking, Kind.PENDING_REQUEST), today, after
        ):
            per_owner[owner].append(booking)
    sent = 0
    for owner, owner_bookings in per_owner.items():
        if notifications.pending_digest(owner, owner_bookings):
            for booking in owner_bookings:
                _log(booking, Kind.PENDING_REQUEST, today)
            sent += 1
    stats["offene_anfragen"] = sent
    return stats
