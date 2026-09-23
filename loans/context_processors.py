from django.conf import settings
from django.db.models import Q

from .models import Booking


def navigation(request):
    """Seitenname und Zahl offener Anfragen (Badge in der Navigationsleiste)."""
    context = {"site_name": settings.SITE_NAME}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        context["pending_approvals_count"] = (
            Booking.objects.filter(item__responsible=user)
            .filter(
                Q(status=Booking.Status.REQUESTED)
                | Q(status__in=Booking.BLOCKING, requested_end_date__isnull=False)
            )
            .count()
        )
    return context
