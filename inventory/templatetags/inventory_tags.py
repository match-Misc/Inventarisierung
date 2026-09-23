from django import template
from django.utils import timezone

from inventory.models import Item

register = template.Library()

BOOKING_BADGES = {
    "requested": "text-bg-secondary",
    "reserved": "text-bg-primary",
    "active": "text-bg-success",
    "returned": "text-bg-light border",
    "rejected": "text-bg-danger",
    "cancelled": "text-bg-light border",
    "expired": "text-bg-light border",
}


@register.inclusion_tag("inventory/partials/item_status.html")
def item_status(item, detailed=True):
    """Status-Badge: verfügbar / ausgeliehen an … bis … / überfällig / Zustand."""
    booking = item.current_booking
    if item.condition != Item.Condition.OK:
        state = "condition"
    elif booking:
        state = "overdue" if booking.end_date < timezone.localdate() else "lent"
    else:
        state = "available"
    return {"item": item, "booking": booking, "state": state, "detailed": detailed}


@register.inclusion_tag("inventory/partials/booking_badge.html")
def booking_badge(booking):
    overdue = booking.is_overdue
    return {
        "label": "Überfällig" if overdue else booking.get_status_display(),
        "css": "text-bg-danger" if overdue else BOOKING_BADGES.get(booking.status, "text-bg-secondary"),
        "extension": bool(booking.requested_end_date),
    }


@register.inclusion_tag("inventory/partials/policy_icon.html")
def policy_icon(item):
    return {"approval": item.loan_policy == Item.LoanPolicy.APPROVAL}


@register.filter
def can_manage(item, user):
    return item.can_manage(user)
