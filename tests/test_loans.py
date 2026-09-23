from datetime import timedelta

import pytest
from django.core import mail
from django.core.exceptions import PermissionDenied
from django.urls import reverse
from django.utils import timezone

from inventory.models import Item
from loans import services
from loans.models import Booking
from loans.services import BookingError

from .factories import ItemFactory, UserFactory

Status = Booking.Status
TODAY = timezone.localdate()


def days(n):
    return TODAY + timedelta(days=n)


@pytest.fixture
def owner(db):
    return UserFactory(first_name="Olga")


@pytest.fixture
def free_item(owner):
    return ItemFactory(responsible=owner, loan_policy=Item.LoanPolicy.FREE)


@pytest.fixture
def approval_item(owner):
    return ItemFactory(responsible=owner, loan_policy=Item.LoanPolicy.APPROVAL)


def book(item, user, start, end, **kwargs):
    return services.create_booking(item=item, user=user, start_date=start, end_date=end, **kwargs)


# ---------- Buchen ----------


def test_free_item_today_is_lent_immediately(free_item, user):
    booking = book(free_item, user, TODAY, days(3))
    assert booking.status == Status.ACTIVE and booking.checked_out_at
    assert free_item.current_booking == booking


def test_free_item_future_is_reserved(free_item, user):
    assert book(free_item, user, days(2), days(4)).status == Status.RESERVED


def test_approval_item_creates_request_and_mails_owner(
    approval_item, user, owner, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        booking = book(approval_item, user, TODAY, days(2), message="Bitte!")
    assert booking.status == Status.REQUESTED
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == [owner.email]
    assert "Bitte!" in mail.outbox[0].body


def test_owner_books_own_approval_item_directly(approval_item, owner):
    assert book(approval_item, owner, TODAY, days(1)).status == Status.ACTIVE


@pytest.mark.parametrize(
    ("start", "end", "conflict"),
    [
        (5, 7, True),  # gleicher Zeitraum
        (3, 5, True),  # überlappt am Anfang
        (7, 9, True),  # letzter Tag zählt mit
        (8, 9, False),  # direkt danach
        (2, 4, False),  # direkt davor
        (4, 8, True),  # umschließend
    ],
)
def test_conflicts_with_reservation(free_item, user, start, end, conflict):
    book(free_item, user, days(5), days(7))
    other = UserFactory()
    if conflict:
        with pytest.raises(BookingError, match="belegt"):
            book(free_item, other, days(start), days(end))
    else:
        book(free_item, other, days(start), days(end))


def test_overdue_loan_blocks_until_returned(free_item, user):
    Booking.objects.create(
        item=free_item, borrower=user, start_date=days(-5), end_date=days(-1), status=Status.ACTIVE
    )
    with pytest.raises(BookingError, match="fällig"):
        book(free_item, UserFactory(), TODAY, days(2))


def test_open_request_does_not_block(approval_item, user):
    book(approval_item, user, days(1), days(3))
    other = UserFactory()
    assert book(approval_item, other, days(1), days(3)).status == Status.REQUESTED


def test_invalid_bookings(free_item, user):
    with pytest.raises(BookingError, match="Vergangenheit"):
        book(free_item, user, days(-1), days(1))
    free_item.condition = Item.Condition.DEFECT
    free_item.save()
    with pytest.raises(BookingError, match="Defekt"):
        book(free_item, user, TODAY, days(1))


def test_only_manager_books_for_others(free_item, user, owner):
    other = UserFactory()
    with pytest.raises(PermissionDenied):
        book(free_item, user, TODAY, days(1), borrower=other)
    assert book(free_item, owner, TODAY, days(1), borrower=other).borrower == other


# ---------- Genehmigen, Entnehmen, Zurückgeben ----------


def test_approve_then_checkout_and_return(approval_item, user, owner, django_capture_on_commit_callbacks):
    booking = book(approval_item, user, TODAY, days(2))
    with pytest.raises(PermissionDenied):
        services.approve(booking, user)
    with django_capture_on_commit_callbacks(execute=True):
        services.approve(booking, owner, "Viel Erfolg")
    booking.refresh_from_db()
    assert booking.status == Status.RESERVED
    assert mail.outbox[-1].to == [user.email] and "genehmigt" in mail.outbox[-1].subject

    services.check_out(booking, user)
    booking.refresh_from_db()
    assert booking.status == Status.ACTIVE
    with django_capture_on_commit_callbacks(execute=True):
        services.return_booking(booking, user, "Kabel fehlt")
    booking.refresh_from_db()
    assert booking.status == Status.RETURNED and booking.returned_by == user
    assert "Kabel fehlt" in mail.outbox[-1].body


def test_approve_fails_on_conflict(approval_item, user, owner):
    request = book(approval_item, user, days(1), days(3))
    book(approval_item, owner, days(2), days(2))  # Verantwortliche/r reserviert selbst
    with pytest.raises(BookingError, match="belegt"):
        services.approve(request, owner)


def test_reject(approval_item, user, owner):
    booking = services.reject(book(approval_item, user, days(1), days(2)), owner, "Wird gewartet")
    assert booking.status == Status.REJECTED and booking.decision_comment == "Wird gewartet"
    with pytest.raises(BookingError, match="bereits bearbeitet"):
        services.approve(booking, owner)


def test_checkout_rules(free_item, user):
    future = book(free_item, user, days(2), days(3))
    with pytest.raises(BookingError, match="erst ab"):
        services.check_out(future, user)
    reserved = book(free_item, user, TODAY + timedelta(days=5), days(6))
    Booking.objects.filter(pk=reserved.pk).update(start_date=TODAY)
    Booking.objects.create(
        item=free_item, borrower=UserFactory(), start_date=days(-3), end_date=days(-1), status=Status.ACTIVE
    )
    with pytest.raises(BookingError, match="noch an"):
        services.check_out(reserved, user)


def test_strangers_cannot_return_or_cancel(free_item, user):
    booking = book(free_item, user, TODAY, days(1))
    stranger = UserFactory()
    with pytest.raises(PermissionDenied):
        services.return_booking(booking, stranger)
    reservation = book(free_item, user, days(3), days(4))
    with pytest.raises(PermissionDenied):
        services.cancel(reservation, stranger)
    assert services.cancel(reservation, user).status == Status.CANCELLED


# ---------- Verlängern ----------


def test_extend_free_item_directly(free_item, user):
    booking = book(free_item, user, TODAY, days(2))
    booking = services.extend(booking, user, days(5))
    assert booking.end_date == days(5) and booking.requested_end_date is None


def test_extend_blocked_by_following_reservation(free_item, user):
    booking = book(free_item, user, TODAY, days(2))
    book(free_item, UserFactory(), days(4), days(6))
    with pytest.raises(BookingError, match="belegt"):
        services.extend(booking, user, days(5))


def test_extend_approval_item_needs_approval(approval_item, user, owner):
    booking = book(approval_item, user, TODAY, days(2))
    booking = services.approve(booking, owner)
    booking = services.extend(booking, user, days(6))
    assert booking.end_date == days(2) and booking.requested_end_date == days(6)
    booking = services.approve_extension(booking, owner)
    assert booking.end_date == days(6) and booking.requested_end_date is None


def test_expire_stale(approval_item, user):
    booking = book(approval_item, user, TODAY, days(1))
    assert services.expire_stale(days(2)) == 1
    booking.refresh_from_db()
    assert booking.status == Status.EXPIRED


# ---------- Seiten ----------


def test_booking_page_flow(client, approval_item, user, owner):
    client.force_login(user)
    detail = client.get(approval_item.get_absolute_url())
    assert "Ausleihe anfragen" in detail.content.decode()

    url = reverse("loans:book", args=[approval_item.pk])
    response = client.post(url, {"start_date": days(1), "end_date": days(3), "message": "Hallo"})
    assert response.status_code == 302
    booking = Booking.objects.get()
    assert booking.status == Status.REQUESTED

    client.force_login(owner)
    dashboard = client.get(reverse("dashboard"))
    assert (
        "Anfragen an mich" in dashboard.content.decode() and user.display_name in dashboard.content.decode()
    )
    client.post(reverse("loans:approve", args=[booking.pk]), {"comment": "ok"})
    booking.refresh_from_db()
    assert booking.status == Status.RESERVED


def test_booking_page_shows_conflict(client, free_item, user):
    book(free_item, UserFactory(), TODAY, days(3))
    client.force_login(user)
    response = client.post(
        reverse("loans:book", args=[free_item.pk]), {"start_date": TODAY, "end_date": days(1)}
    )
    assert response.status_code == 200
    assert "belegt" in response.content.decode()


def test_stranger_gets_403_on_actions(client, approval_item, user, owner):
    booking = book(approval_item, user, days(1), days(2))
    client.force_login(UserFactory())
    assert client.post(reverse("loans:approve", args=[booking.pk])).status_code == 403
    assert client.get(reverse("loans:return", args=[booking.pk])).status_code == 403


def test_item_list_filters(client, free_item, user):
    lent = ItemFactory(name="Oszilloskop")
    unverified = ItemFactory(name="Importgerät", condition=Item.Condition.UNVERIFIED)
    book(lent, user, TODAY, days(1))
    client.force_login(user)
    response = client.get(reverse("inventory:item_list"), {"status": "ausgeliehen"})
    names = [item.name for item in response.context["page"]]
    assert names == ["Oszilloskop"]
    response = client.get(reverse("inventory:item_list"), {"q": "oszi"})
    assert [item.name for item in response.context["page"]] == ["Oszilloskop"]
    response = client.get(reverse("inventory:item_list"), {"status": "ungeprueft"})
    assert [item.name for item in response.context["page"]] == [unverified.name]
