from datetime import timedelta

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from inventory.models import Item

from . import services
from .forms import BookingForm, ExtendForm, ReturnForm
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
