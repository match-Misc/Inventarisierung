from datetime import timedelta

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from accounts.models import OFF
from inventory.models import Item
from loans import reminders, services
from loans.models import Booking

from .factories import ItemFactory, UserFactory

Status = Booking.Status
TODAY = timezone.localdate()


def days(n):
    return TODAY + timedelta(days=n)


def set_prefs(user, **values):
    prefs = user.notification_settings
    for key, value in values.items():
        setattr(prefs, key, value)
    prefs.save()


def recipients():
    return [(m.to[0], m.subject) for m in mail.outbox]


@pytest.fixture
def owner(db):
    return UserFactory(first_name="Olga")


@pytest.fixture
def borrower(db):
    return UserFactory(first_name="Bea")


@pytest.fixture
def free_item(owner):
    return ItemFactory(name="Oszilloskop", responsible=owner, loan_policy=Item.LoanPolicy.FREE)


@pytest.fixture
def approval_item(owner):
    return ItemFactory(name="Roboter", responsible=owner, loan_policy=Item.LoanPolicy.APPROVAL)


@pytest.fixture
def on_commit(django_capture_on_commit_callbacks):
    return lambda: django_capture_on_commit_callbacks(execute=True)


def booking(item, user, start, end, status):
    return Booking.objects.create(item=item, borrower=user, start_date=start, end_date=end, status=status)


# ---------- Einstellungen ----------


def test_defaults_are_created_lazily(borrower):
    prefs = borrower.notification_settings
    assert prefs.pk and prefs.enabled and prefs.due_reminder == 1 and not prefs.owner_activity


def test_request_mail_respects_setting(approval_item, owner, borrower, on_commit):
    set_prefs(owner, new_requests=False)
    with on_commit():
        services.create_booking(item=approval_item, user=borrower, start_date=TODAY, end_date=days(1))
    assert mail.outbox == []


def test_master_switch_blocks_decisions(approval_item, owner, borrower, on_commit):
    set_prefs(borrower, enabled=False)
    request = services.create_booking(item=approval_item, user=borrower, start_date=TODAY, end_date=days(1))
    with on_commit():
        services.approve(request, owner)
    assert borrower.email not in [m.to[0] for m in mail.outbox]


def test_owner_activity_for_free_items_is_opt_in(free_item, owner, borrower, on_commit):
    with on_commit():
        services.create_booking(item=free_item, user=borrower, start_date=TODAY, end_date=days(1))
    assert mail.outbox == []
    set_prefs(owner, owner_activity=True)
    with on_commit():
        services.create_booking(item=free_item, user=borrower, start_date=days(3), end_date=days(4))
    assert recipients() == [(owner.email, "[Geräteinventar] Reserviert: Oszilloskop")]


def test_borrower_cancel_informs_owner_of_approval_item(approval_item, owner, borrower, on_commit):
    reservation = booking(approval_item, borrower, days(2), days(3), Status.RESERVED)
    with on_commit():
        services.cancel(reservation, borrower)
    assert recipients() == [(owner.email, "[Geräteinventar] Storniert: Roboter")]


def test_owner_cancel_informs_borrower(free_item, owner, borrower, on_commit):
    reservation = booking(free_item, borrower, days(2), days(3), Status.RESERVED)
    with on_commit():
        services.cancel(reservation, owner)
    assert recipients() == [(borrower.email, "[Geräteinventar] Deine Buchung wurde storniert: Oszilloskop")]


def test_return_note_always_reaches_owner_and_waiting_reservation_is_informed(
    free_item, owner, borrower, on_commit
):
    loan = booking(free_item, borrower, days(-3), days(1), Status.ACTIVE)
    next_person = UserFactory()
    booking(free_item, next_person, days(2), days(4), Status.RESERVED)
    with on_commit():
        services.return_booking(loan, borrower, "Tastkopf fehlt")
    assert (owner.email, "[Geräteinventar] Zurückgegeben: Oszilloskop") in recipients()
    assert (next_person.email, "[Geräteinventar] Wieder verfügbar: Oszilloskop") in recipients()
    assert "Tastkopf fehlt" in mail.outbox[0].body


def test_expired_request_is_announced(approval_item, borrower):
    booking(approval_item, borrower, days(-3), days(-1), Status.REQUESTED)
    assert services.expire_stale() == 1
    assert recipients() == [(borrower.email, "[Geräteinventar] Anfrage verfallen: Roboter")]


def test_every_mail_links_to_settings(approval_item, borrower, on_commit):
    with on_commit():
        services.create_booking(item=approval_item, user=borrower, start_date=TODAY, end_date=days(1))
    assert "/konto/benachrichtigungen/" in mail.outbox[0].body


# ---------- Täglicher Erinnerungslauf ----------


def test_start_reminder_day_before_and_only_once(free_item, borrower):
    booking(free_item, borrower, days(1), days(3), Status.RESERVED)
    reminders.run()
    reminders.run()  # zweiter Lauf am selben Tag verschickt nichts doppelt
    assert recipients() == [(borrower.email, "[Geräteinventar] Reservierung beginnt morgen: Oszilloskop")]


def test_start_reminder_respects_setting(free_item, borrower):
    set_prefs(borrower, start_reminder=0)
    booking(free_item, borrower, days(1), days(3), Status.RESERVED)
    reminders.run()
    assert mail.outbox == []
    set_prefs(borrower, start_reminder=OFF)
    booking(ItemFactory(), borrower, TODAY, days(3), Status.RESERVED)
    reminders.run()
    assert mail.outbox == []


@pytest.mark.parametrize(
    ("setting", "end", "expected"), [(1, 1, True), (2, 2, True), (0, 0, True), (1, 2, False)]
)
def test_due_reminder(free_item, borrower, setting, end, expected):
    set_prefs(borrower, due_reminder=setting)
    booking(free_item, borrower, days(-2), days(end), Status.ACTIVE)
    reminders.run()
    assert bool(mail.outbox) is expected


def test_overdue_reminders_follow_interval_and_cannot_be_disabled(free_item, owner, borrower):
    set_prefs(borrower, enabled=False, overdue_interval=2)
    loan = booking(free_item, borrower, days(-5), days(-1), Status.ACTIVE)
    reminders.run()
    assert sorted(recipients()) == sorted(
        [
            (borrower.email, "[Geräteinventar] Rückgabe überfällig: Oszilloskop"),
            (owner.email, "[Geräteinventar] Dein Gerät ist überfällig: Oszilloskop"),
        ]
    )
    assert "seit 1 Tag " in mail.outbox[0].body or "seit 1 Tag " in mail.outbox[1].body

    mail.outbox.clear()
    loan.reminders.update(sent_on=days(-1))  # gestern verschickt: Abstand 2 Tage noch nicht erreicht
    reminders.run()
    assert mail.outbox == []
    loan.reminders.update(sent_on=days(-2))  # vor 2 Tagen: Ausleiher/in wieder, Verantwortliche/r erst nach 7
    reminders.run()
    assert recipients() == [(borrower.email, "[Geräteinventar] Rückgabe überfällig: Oszilloskop")]


def test_pending_digest(approval_item, owner, borrower):
    request = booking(approval_item, borrower, days(3), days(4), Status.REQUESTED)
    reminders.run()
    assert mail.outbox == []  # noch zu frisch
    Booking.objects.filter(pk=request.pk).update(updated_at=timezone.now() - timedelta(days=2))
    reminders.run()
    reminders.run()
    assert recipients() == [(owner.email, "[Geräteinventar] 1 unbeantwortete Anfrage(n)")]
    assert "Roboter" in mail.outbox[0].body


# ---------- Seiten ----------


def test_settings_page(client, borrower):
    client.force_login(borrower)
    url = reverse("accounts:notifications")
    assert client.get(url).status_code == 200
    data = {
        "enabled": "on",
        "booking_updates": "on",
        "start_reminder": 0,
        "due_reminder": 2,
        "overdue_interval": 7,
        "new_requests": "on",
        "pending_digest": OFF,
    }
    assert client.post(url, data).status_code == 302
    borrower.refresh_from_db()
    prefs = type(borrower.notification_settings).objects.get(user=borrower)
    assert (prefs.due_reminder, prefs.overdue_interval, prefs.item_available) == (2, 7, False)


def test_test_mail(client, borrower):
    client.force_login(borrower)
    client.post(reverse("accounts:test_mail"))
    assert recipients() == [(borrower.email, "[Geräteinventar] Testmail")]
