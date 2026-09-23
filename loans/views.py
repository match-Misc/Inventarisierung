from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from inventory.models import Category, Item, Location

from . import services
from .forms import BookingForm, CalendarBookingForm, ExtendForm, ReturnForm
from .models import Booking
from .services import BookingError

Status = Booking.Status


def _redirect_back(request, fallback):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(target)
    return redirect(fallback)


def dashboard(request):
    user = request.user
    mine = Booking.objects.filter(borrower=user).select_related("item", "item__location", "item__responsible")
    to_decide = Booking.objects.filter(item__responsible=user).select_related("item", "borrower")
    context = {
        "active": mine.filter(status=Status.ACTIVE).order_by("end_date"),
        "upcoming": mine.filter(status__in=[Status.RESERVED, Status.REQUESTED]).order_by("start_date"),
        "requests": to_decide.filter(status=Status.REQUESTED).order_by("start_date"),
        "extensions": to_decide.filter(
            status__in=Booking.BLOCKING, requested_end_date__isnull=False
        ).order_by("end_date"),
        "my_items": Item.objects.with_status()
        .filter(responsible=user)
        .exclude(condition=Item.Condition.RETIRED),
        "today": timezone.localdate(),
    }
    return render(request, "loans/dashboard.html", context)


def _success_message(booking, user):
    item, end = booking.item, f"{booking.end_date:%d.%m.%Y}"
    if booking.borrower_id != user.pk:
        return f"Buchung für {booking.borrower.display_name} eingetragen ({booking.get_status_display()})."
    if booking.status == Status.ACTIVE:
        return f"„{item}“ ist jetzt an dich ausgeliehen. Bitte bis {end} zurückgeben."
    if booking.status == Status.RESERVED:
        return (
            f"„{item}“ ist für dich vom {booking.start_date:%d.%m.%Y} bis {end} reserviert. "
            "Bitte bestätige am Starttag die Entnahme."
        )
    return (
        f"Deine Anfrage wurde an {item.responsible.display_name} geschickt. "
        "Du bekommst eine E-Mail, sobald entschieden ist."
    )


def book_item(request, pk):
    item = get_object_or_404(Item.objects.select_related("responsible", "location"), pk=pk)
    initial = {}
    for key, field in (("von", "start_date"), ("bis", "end_date")):
        if value := parse_date(request.GET.get(key, "")):
            initial[field] = value
    form = BookingForm(request.POST or None, item=item, user=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            booking = services.create_booking(item=item, user=request.user, **form.booking_kwargs())
        except BookingError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, _success_message(booking, request.user))
            return redirect(item)
    upcoming = (
        item.bookings.filter(Q(status=Status.ACTIVE) | Q(status__in=[Status.RESERVED, Status.REQUESTED]))
        .filter(Q(status=Status.ACTIVE) | Q(end_date__gte=timezone.localdate()))
        .select_related("borrower")
        .order_by("start_date")
    )
    return render(
        request,
        "loans/booking_form.html",
        {"item": item, "form": form, "mode": form.mode, "upcoming": upcoming, "today": timezone.localdate()},
    )


ACTIONS = {
    "approve": (lambda b, u, c: services.approve(b, u, c), "Anfrage genehmigt."),
    "reject": (lambda b, u, c: services.reject(b, u, c), "Anfrage abgelehnt."),
    "cancel": (lambda b, u, c: services.cancel(b, u), "Buchung storniert."),
    "checkout": (
        lambda b, u, c: services.check_out(b, u),
        "Entnahme bestätigt – das Gerät ist jetzt ausgeliehen.",
    ),
    "approve_extension": (lambda b, u, c: services.approve_extension(b, u), "Verlängerung genehmigt."),
    "reject_extension": (lambda b, u, c: services.reject_extension(b, u, c), "Verlängerung abgelehnt."),
}


@require_POST
def booking_action(request, pk, action):
    booking = get_object_or_404(Booking.objects.select_related("item", "borrower"), pk=pk)
    func, success = ACTIONS[action]
    try:
        func(booking, request.user, request.POST.get("comment", "").strip())
    except BookingError as error:
        messages.error(request, str(error))
    else:
        messages.success(request, success)
    return _redirect_back(request, booking.item)


def _get_own_or_managed(request, pk):
    booking = get_object_or_404(Booking.objects.select_related("item", "borrower"), pk=pk)
    if booking.borrower_id != request.user.pk and not booking.item.can_manage(request.user):
        raise PermissionDenied
    return booking


def return_booking(request, pk):
    booking = _get_own_or_managed(request, pk)
    form = ReturnForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.return_booking(booking, request.user, form.cleaned_data["note"])
        except BookingError as error:
            messages.error(request, str(error))
        else:
            messages.success(request, f"„{booking.item}“ wurde zurückgegeben. Danke!")
        return _redirect_back(request, booking.item)
    return render(
        request,
        "loans/return_form.html",
        {"booking": booking, "form": form, "accessories": booking.item.accessories.all()},
    )


def extend_booking(request, pk):
    booking = _get_own_or_managed(request, pk)
    form = ExtendForm(request.POST or None, initial={"new_end_date": booking.end_date + timedelta(days=7)})
    if request.method == "POST" and form.is_valid():
        try:
            booking = services.extend(booking, request.user, form.cleaned_data["new_end_date"])
        except BookingError as error:
            form.add_error("new_end_date", str(error))
        else:
            if booking.requested_end_date:
                messages.success(
                    request,
                    f"Verlängerungsanfrage an {booking.item.responsible.display_name} geschickt.",
                )
            else:
                messages.success(request, f"Verlängert bis {booking.end_date:%d.%m.%Y}.")
            return _redirect_back(request, booking.item)
    return render(
        request,
        "loans/extend_form.html",
        {"booking": booking, "form": form, "mode": services.booking_mode(booking.item, request.user)},
    )


# ---------- Buchungskalender (Karina, #5) ----------

STATUS_COLORS = {
    Booking.Status.ACTIVE: "#0d6efd",
    Booking.Status.RESERVED: "#20c997",
    Booking.Status.REQUESTED: "#ffc107",
}
OVERDUE_COLOR = "#dc3545"


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
        form = CalendarBookingForm(request.POST, initial_item=initial_item)
        if form.is_valid():
            try:
                booking = services.create_booking(
                    item=form.cleaned_data["item"],
                    user=request.user,
                    start_date=form.cleaned_data["start_date"],
                    end_date=form.cleaned_data["end_date"],
                    purpose=form.cleaned_data["purpose"],
                    usage_location=form.cleaned_data["usage_location"],
                    message=form.cleaned_data["request_message"],
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
        form = CalendarBookingForm(initial=initial, initial_item=initial_item)
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
