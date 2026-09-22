from datetime import date, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from inventory.models import Item

from . import services
from .forms import BookingForm
from .models import Booking


@login_required
def booking_list(request):
    bookings = (
        Booking.objects.filter(borrower=request.user).select_related("item").order_by("-created_at")[:100]
    )
    return render(request, "loans/list.html", {"bookings": bookings})


@login_required
def pending_requests(request):
    bookings = Booking.objects.select_related("item", "borrower").filter(
        Q(status=Booking.Status.REQUESTED) | Q(requested_end_date__isnull=False)
    )
    if not request.user.is_staff:
        bookings = bookings.filter(item__responsible=request.user)
    return render(request, "loans/pending.html", {"bookings": bookings})


@login_required
def booking_create(request, item_id):
    item = get_object_or_404(Item.objects.select_related("responsible"), pk=item_id)
    today = timezone.localdate()
    initial = {"start_date": today, "end_date": today + timedelta(days=settings.DEFAULT_LOAN_DAYS - 1)}
    form = BookingForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            booking = services.create_booking(
                user=request.user,
                item_id=item.pk,
                **form.cleaned_data,
            )
        except services.BookingError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(
                request,
                "Buchung angelegt." if booking.status != Booking.Status.REQUESTED else "Anfrage gesendet.",
            )
            return redirect("loans:detail", pk=booking.pk)
    return render(request, "loans/form.html", {"form": form, "item": item})


@login_required
def booking_detail(request, pk):
    booking = get_object_or_404(Booking.objects.select_related("item__responsible", "borrower"), pk=pk)
    if booking.borrower_id != request.user.pk and not booking.item.can_manage(request.user):
        raise PermissionDenied
    return render(
        request,
        "loans/detail.html",
        {"booking": booking, "can_manage": booking.item.can_manage(request.user)},
    )


@login_required
def booking_action(request, pk, action):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    get_object_or_404(Booking, pk=pk)
    handlers = {
        "genehmigen": lambda: services.approve_booking(
            booking_id=pk, user=request.user, comment=request.POST.get("comment", "")
        ),
        "ablehnen": lambda: services.reject_booking(
            booking_id=pk, user=request.user, comment=request.POST.get("comment", "")
        ),
        "stornieren": lambda: services.cancel_booking(booking_id=pk, user=request.user),
        "entnehmen": lambda: services.checkout_booking(booking_id=pk, user=request.user),
        "zurueckgeben": lambda: services.return_booking(
            booking_id=pk, user=request.user, note=request.POST.get("note", "")
        ),
        "verlaengern": lambda: services.extend_booking(
            booking_id=pk,
            user=request.user,
            new_end_date=date.fromisoformat(request.POST.get("end_date", "")),
        ),
        "verlaengerung-genehmigen": lambda: services.decide_extension(
            booking_id=pk, user=request.user, approve=True
        ),
        "verlaengerung-ablehnen": lambda: services.decide_extension(
            booking_id=pk, user=request.user, approve=False
        ),
    }
    if action not in handlers:
        raise PermissionDenied
    try:
        handlers[action]()
    except (services.BookingError, ValueError) as exc:
        messages.error(request, str(exc) if isinstance(exc, services.BookingError) else "Ungültiges Datum.")
    else:
        messages.success(request, "Buchung aktualisiert.")
    return redirect("loans:detail", pk=pk)
