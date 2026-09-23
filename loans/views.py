from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.dateparse import parse_date, parse_datetime

from inventory.models import Category, Item, Location

from . import services
from .forms import BookingForm
from .models import Booking

STATUS_COLORS = {
    Booking.Status.ACTIVE: "#0d6efd",
    Booking.Status.RESERVED: "#20c997",
    Booking.Status.REQUESTED: "#ffc107",
}
OVERDUE_COLOR = "#dc3545"


def dashboard(request):
    """Vorläufige Startseite. Die richtige Übersicht (meine Ausleihen, Anfragen …) folgt mit Schritt 3."""
    return render(request, "home.html")


def calendar_page(request):
    """Kalenderseite mit Filtern. Die Buchungen selbst liefert calendar_events als JSON."""
    items = list(
        Item.objects.exclude(condition=Item.Condition.RETIRED).select_related("category", "location")
    )
    selected_item = None
    if request.GET.get("geraet", "").isdigit():
        selected_item = next((i for i in items if i.pk == int(request.GET["geraet"])), None)
    context = {
        "available_items": [i for i in items if i.condition == Item.Condition.OK],
        "unavailable_items": [i for i in items if i.condition != Item.Condition.OK],
        "categories": Category.objects.all(),
        "locations": Location.objects.all(),
        "selected_item": selected_item,
    }
    return render(request, "loans/calendar.html", context)


def _parse_day(value):
    """FullCalendar schickt Datum/Zeit als ISO-String, unser Formularfeld nur ein Datum."""
    if not value:
        return None
    dt = parse_datetime(value)
    if dt is not None:
        return dt.date()
    return parse_date(value)


def calendar_events(request):
    """JSON-Feed für FullCalendar. Enddatum ist exklusiv (siehe AGENTS.md)."""
    range_start = _parse_day(request.GET.get("start"))
    range_end = _parse_day(request.GET.get("end"))
    qs = Booking.objects.filter(status__in=Booking.OPEN).select_related("item", "borrower")
    if range_end:
        qs = qs.filter(start_date__lt=range_end)
    if range_start:
        # Überfällige aktive Ausleihen blockieren bis heute weiter, unabhängig vom gespeicherten Enddatum.
        qs = qs.filter(Q(end_date__gte=range_start) | Q(status=Booking.Status.ACTIVE))
    if request.GET.get("geraet", "").isdigit():
        qs = qs.filter(item_id=request.GET["geraet"])
    if request.GET.get("kategorie", "").isdigit():
        category = Category.objects.filter(pk=request.GET["kategorie"]).first()
        if category:
            qs = qs.filter(category.subtree_q("item__category"))
    if request.GET.get("ort", "").isdigit():
        location = Location.objects.filter(pk=request.GET["ort"]).first()
        if location:
            qs = qs.filter(location.subtree_q("item__location"))
    if request.GET.get("nur_meine") == "1" and request.user.is_authenticated:
        qs = qs.filter(borrower=request.user)

    events = []
    for booking in qs:
        end = services.effective_end_date(booking)
        color = OVERDUE_COLOR if booking.is_overdue else STATUS_COLORS.get(booking.status, "#6c757d")
        events.append(
            {
                "id": booking.pk,
                "title": f"{booking.item.name} · {booking.borrower.short_name}",
                "start": booking.start_date.isoformat(),
                "end": (end + timedelta(days=1)).isoformat(),
                "color": color,
                "extendedProps": {
                    "status": booking.status,
                    "statusLabel": booking.get_status_display(),
                    "overdue": booking.is_overdue,
                },
            }
        )
    return JsonResponse(events, safe=False)


def booking_create(request):
    """HTMX-Modal zum Anlegen einer Buchung. Die Statuslogik liegt in loans.services."""
    initial_item = None
    item_id = request.GET.get("geraet") or request.POST.get("item")
    if item_id and str(item_id).isdigit():
        initial_item = Item.objects.filter(pk=item_id).exclude(condition=Item.Condition.RETIRED).first()

    if request.method == "POST":
        form = BookingForm(request.POST, initial_item=initial_item)
        if form.is_valid():
            try:
                booking = services.create_booking(
                    item=form.cleaned_data["item"],
                    borrower=request.user,
                    start_date=form.cleaned_data["start_date"],
                    end_date=form.cleaned_data["end_date"],
                    purpose=form.cleaned_data["purpose"],
                    usage_location=form.cleaned_data["usage_location"],
                    request_message=form.cleaned_data["request_message"],
                    created_by=request.user,
                )
            except services.BookingError as error:
                form.add_error(None, str(error))
            else:
                response = render(request, "loans/partials/booking_success.html", {"booking": booking})
                response["HX-Trigger"] = "booking-saved"
                return response
    else:
        initial = {}
        start = _parse_day(request.GET.get("start"))
        end = _parse_day(request.GET.get("end"))
        if start:
            initial["start_date"] = start
        if end:
            initial["end_date"] = end
        form = BookingForm(initial=initial, initial_item=initial_item)
    return render(request, "loans/partials/booking_form.html", {"form": form})


def booking_detail(request, pk):
    """HTMX-Modal mit den Details einer Buchung.

    Sichtbarkeit: Aktuelle/künftige Buchungen sehen alle. Die Ausleihhistorie (zurückgegeben,
    abgelehnt, storniert, verfallen) sehen nur die/der Verantwortliche, Admins und die/der Ausleiher/in.
    """
    booking = get_object_or_404(
        Booking.objects.select_related("item", "borrower", "item__responsible"), pk=pk
    )
    can_manage = booking.item.can_manage(request.user) or booking.borrower_id == request.user.pk
    if booking.status not in Booking.OPEN and not can_manage:
        raise PermissionDenied
    return render(
        request, "loans/partials/booking_detail.html", {"booking": booking, "can_manage": can_manage}
    )
