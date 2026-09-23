from datetime import timedelta

import pytest
from django.utils import timezone

from inventory.models import Item
from loans.models import Booking
from loans.services import BookingError, create_booking

from .factories import BookingFactory, ItemFactory, UserFactory

pytestmark = pytest.mark.django_db


def _today():
    return timezone.localdate()


def test_direct_booking_active_when_starts_today():
    item = ItemFactory(loan_policy=Item.LoanPolicy.FREE)
    user = UserFactory()
    booking = create_booking(
        item=item, borrower=user, start_date=_today(), end_date=_today() + timedelta(days=2)
    )
    assert booking.status == Booking.Status.ACTIVE
    assert booking.checked_out_at is not None


def test_direct_booking_reserved_when_starts_later():
    item = ItemFactory(loan_policy=Item.LoanPolicy.FREE)
    user = UserFactory()
    start = _today() + timedelta(days=3)
    booking = create_booking(item=item, borrower=user, start_date=start, end_date=start + timedelta(days=1))
    assert booking.status == Booking.Status.RESERVED
    assert booking.checked_out_at is None


def test_requires_approval_creates_request():
    item = ItemFactory(loan_policy=Item.LoanPolicy.APPROVAL)
    user = UserFactory()
    booking = create_booking(item=item, borrower=user, start_date=_today(), end_date=_today())
    assert booking.status == Booking.Status.REQUESTED


def test_responsible_books_directly_despite_approval_policy():
    responsible = UserFactory()
    item = ItemFactory(loan_policy=Item.LoanPolicy.APPROVAL, responsible=responsible)
    booking = create_booking(item=item, borrower=responsible, start_date=_today(), end_date=_today())
    assert booking.status == Booking.Status.ACTIVE


def test_conflict_blocks_direct_booking():
    item = ItemFactory(loan_policy=Item.LoanPolicy.FREE)
    BookingFactory(
        item=item,
        status=Booking.Status.RESERVED,
        start_date=_today(),
        end_date=_today() + timedelta(days=5),
    )
    other = UserFactory()
    with pytest.raises(BookingError):
        create_booking(
            item=item,
            borrower=other,
            start_date=_today() + timedelta(days=2),
            end_date=_today() + timedelta(days=3),
        )


def test_request_ignores_existing_blocking_bookings():
    item = ItemFactory(loan_policy=Item.LoanPolicy.APPROVAL)
    BookingFactory(
        item=item,
        status=Booking.Status.ACTIVE,
        start_date=_today(),
        end_date=_today() + timedelta(days=5),
    )
    other = UserFactory()
    booking = create_booking(
        item=item,
        borrower=other,
        start_date=_today() + timedelta(days=1),
        end_date=_today() + timedelta(days=2),
    )
    assert booking.status == Booking.Status.REQUESTED


def test_defect_item_cannot_be_booked():
    item = ItemFactory(condition=Item.Condition.DEFECT)
    user = UserFactory()
    with pytest.raises(BookingError, match="nicht verfügbar"):
        create_booking(item=item, borrower=user, start_date=_today(), end_date=_today())


def test_start_in_past_rejected():
    item = ItemFactory()
    user = UserFactory()
    with pytest.raises(BookingError):
        create_booking(item=item, borrower=user, start_date=_today() - timedelta(days=1), end_date=_today())


def test_overdue_active_booking_still_blocks():
    item = ItemFactory(loan_policy=Item.LoanPolicy.FREE)
    BookingFactory(
        item=item,
        status=Booking.Status.ACTIVE,
        start_date=_today() - timedelta(days=5),
        end_date=_today() - timedelta(days=1),
    )
    other = UserFactory()
    with pytest.raises(BookingError):
        create_booking(
            item=item, borrower=other, start_date=_today(), end_date=_today() + timedelta(days=1)
        )


def test_email_sent_on_request(django_capture_on_commit_callbacks, mailoutbox):
    responsible = UserFactory(email="chef@example.org")
    item = ItemFactory(loan_policy=Item.LoanPolicy.APPROVAL, responsible=responsible)
    borrower = UserFactory()
    with django_capture_on_commit_callbacks(execute=True):
        create_booking(item=item, borrower=borrower, start_date=_today(), end_date=_today())
    assert len(mailoutbox) == 1
    assert responsible.email in mailoutbox[0].to


def test_no_email_on_direct_booking(django_capture_on_commit_callbacks, mailoutbox):
    item = ItemFactory(loan_policy=Item.LoanPolicy.FREE)
    user = UserFactory()
    with django_capture_on_commit_callbacks(execute=True):
        create_booking(item=item, borrower=user, start_date=_today(), end_date=_today())
    assert not mailoutbox
