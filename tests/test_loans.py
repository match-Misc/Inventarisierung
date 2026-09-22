from datetime import timedelta

import pytest
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from inventory.models import Item
from loans.models import Booking
from loans.services import (
    BookingError,
    approve_booking,
    cancel_booking,
    checkout_booking,
    create_booking,
    return_booking,
)


@pytest.mark.django_db
def test_free_booking_blocks_overlap_and_can_be_returned(people, inventory):
    _, borrower, stranger = people
    item = inventory("Freier Kraftsensor")
    today = timezone.localdate()
    booking = create_booking(
        user=borrower, item_id=item.pk, start_date=today, end_date=today + timedelta(days=2)
    )
    assert booking.status == Booking.Status.ACTIVE
    with pytest.raises(BookingError, match="bereits gebucht"):
        create_booking(
            user=stranger,
            item_id=item.pk,
            start_date=today + timedelta(days=1),
            end_date=today + timedelta(days=3),
        )
    with pytest.raises(PermissionDenied):
        return_booking(booking_id=booking.pk, user=stranger)
    assert return_booking(booking_id=booking.pk, user=borrower).status == Booking.Status.RETURNED


@pytest.mark.django_db
def test_approval_rechecks_conflicts_and_permissions(people, inventory):
    owner, borrower, stranger = people
    item = inventory("Freigabepflichtig", policy=Item.LoanPolicy.APPROVAL)
    today = timezone.localdate()
    request = create_booking(
        user=borrower, item_id=item.pk, start_date=today, end_date=today + timedelta(days=1)
    )
    assert request.status == Booking.Status.REQUESTED
    assert (
        create_booking(user=stranger, item_id=item.pk, start_date=today, end_date=today).status
        == Booking.Status.REQUESTED
    )
    with pytest.raises(PermissionDenied):
        approve_booking(booking_id=request.pk, user=stranger)
    assert approve_booking(booking_id=request.pk, user=owner).status == Booking.Status.RESERVED
    other = Booking.objects.get(borrower=stranger)
    with pytest.raises(BookingError, match="bereits gebucht"):
        approve_booking(booking_id=other.pk, user=owner)
    assert checkout_booking(booking_id=request.pk, user=borrower).status == Booking.Status.ACTIVE


@pytest.mark.django_db
def test_future_reservation_can_be_cancelled(people, inventory):
    _, borrower, _ = people
    item = inventory("Reservierbarer Sensor")
    tomorrow = timezone.localdate() + timedelta(days=1)
    booking = create_booking(user=borrower, item_id=item.pk, start_date=tomorrow, end_date=tomorrow)
    assert booking.status == Booking.Status.RESERVED
    assert cancel_booking(booking_id=booking.pk, user=borrower).status == Booking.Status.CANCELLED
