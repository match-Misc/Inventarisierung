from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from inventory.models import Item
from loans.models import Booking

from .factories import BookingFactory, ItemFactory

pytestmark = pytest.mark.django_db


def _today():
    return timezone.localdate()


def test_calendar_requires_login(client):
    response = client.get(reverse("loans:calendar"))
    assert response.status_code == 302 and "/konto/login/" in response["Location"]


def test_events_feed_only_open_statuses(client, user):
    item = ItemFactory()
    open_booking = BookingFactory(
        item=item, status=Booking.Status.RESERVED, start_date=_today(), end_date=_today() + timedelta(days=1)
    )
    BookingFactory(item=item, status=Booking.Status.RETURNED, start_date=_today(), end_date=_today())
    BookingFactory(item=item, status=Booking.Status.REJECTED, start_date=_today(), end_date=_today())
    client.force_login(user)
    response = client.get(
        reverse("loans:calendar_events"),
        {"start": (_today() - timedelta(days=1)).isoformat(), "end": (_today() + timedelta(days=10)).isoformat()},
    )
    assert response.status_code == 200
    assert [e["id"] for e in response.json()] == [open_booking.pk]


def test_events_feed_end_date_is_exclusive(client, user):
    item = ItemFactory()
    booking = BookingFactory(
        item=item, status=Booking.Status.RESERVED, start_date=_today(), end_date=_today() + timedelta(days=2)
    )
    client.force_login(user)
    response = client.get(
        reverse("loans:calendar_events"),
        {"start": _today().isoformat(), "end": (_today() + timedelta(days=10)).isoformat()},
    )
    event = response.json()[0]
    assert event["end"] == (booking.end_date + timedelta(days=1)).isoformat()


def test_events_feed_filters_by_item(client, user):
    item_a, item_b = ItemFactory(), ItemFactory()
    booking_a = BookingFactory(item=item_a, status=Booking.Status.RESERVED, start_date=_today(), end_date=_today())
    BookingFactory(item=item_b, status=Booking.Status.RESERVED, start_date=_today(), end_date=_today())
    client.force_login(user)
    response = client.get(
        reverse("loans:calendar_events"),
        {
            "start": _today().isoformat(),
            "end": (_today() + timedelta(days=1)).isoformat(),
            "geraet": item_a.pk,
        },
    )
    assert [e["id"] for e in response.json()] == [booking_a.pk]


def test_events_feed_filters_by_borrower(client, user):
    mine = BookingFactory(borrower=user, status=Booking.Status.RESERVED, start_date=_today(), end_date=_today())
    BookingFactory(status=Booking.Status.RESERVED, start_date=_today(), end_date=_today())
    client.force_login(user)
    response = client.get(
        reverse("loans:calendar_events"),
        {
            "start": _today().isoformat(),
            "end": (_today() + timedelta(days=1)).isoformat(),
            "nur_meine": "1",
        },
    )
    assert [e["id"] for e in response.json()] == [mine.pk]


def test_booking_create_direct_booking_triggers_htmx_event(client, user, django_capture_on_commit_callbacks, mailoutbox):
    item = ItemFactory(loan_policy=Item.LoanPolicy.FREE)
    client.force_login(user)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("loans:booking_create"),
            {
                "item": item.pk,
                "start_date": _today().isoformat(),
                "end_date": (_today() + timedelta(days=1)).isoformat(),
                "purpose": "",
                "usage_location": "",
                "request_message": "",
            },
        )
    assert response.status_code == 200
    assert response["HX-Trigger"] == "booking-saved"
    booking = Booking.objects.get(item=item, borrower=user)
    assert booking.status == Booking.Status.ACTIVE
    assert not mailoutbox


def test_booking_create_rejects_defect_item(client, user):
    item = ItemFactory(condition=Item.Condition.DEFECT)
    client.force_login(user)
    response = client.post(
        reverse("loans:booking_create"),
        {"item": item.pk, "start_date": _today().isoformat(), "end_date": _today().isoformat()},
    )
    assert response.status_code == 200
    assert "nicht verfügbar" in response.content.decode()
    assert not Booking.objects.filter(item=item).exists()


def test_booking_detail_visible_to_anyone_when_open(client, user):
    booking = BookingFactory(status=Booking.Status.RESERVED)
    client.force_login(user)
    response = client.get(reverse("loans:booking_detail", args=[booking.pk]))
    assert response.status_code == 200


def test_booking_detail_history_hidden_from_others(client, user):
    booking = BookingFactory(status=Booking.Status.RETURNED)
    client.force_login(user)
    response = client.get(reverse("loans:booking_detail", args=[booking.pk]))
    assert response.status_code == 403


def test_booking_detail_history_visible_to_borrower(client):
    booking = BookingFactory(status=Booking.Status.RETURNED)
    client.force_login(booking.borrower)
    response = client.get(reverse("loans:booking_detail", args=[booking.pk]))
    assert response.status_code == 200


def test_booking_detail_history_visible_to_responsible(client):
    booking = BookingFactory(status=Booking.Status.RETURNED)
    client.force_login(booking.item.responsible)
    response = client.get(reverse("loans:booking_detail", args=[booking.pk]))
    assert response.status_code == 200
