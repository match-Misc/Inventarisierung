import mimetypes
from pathlib import Path

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Exists, OuterRef, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from floorplan.models import element_for_location
from loans.models import Booking
from loans.services import booking_mode

from .models import Category, Item

Status = Booking.Status


def item_list(request):
    """Geräteliste mit Suche und einfachen Filtern (wird mit Issue #2 ausgebaut)."""
    items = Item.objects.with_status()
    query = request.GET.get("q", "").strip()
    for word in query.split():
        items = items.filter(
            Q(name__icontains=word)
            | Q(manufacturer__icontains=word)
            | Q(model_number__icontains=word)
            | Q(serial_number__icontains=word)
            | Q(inventory_number__icontains=word)
        )
    category = Category.objects.filter(pk=request.GET.get("kategorie") or None).first()
    if category:
        items = items.filter(category.subtree_q("category"))
    active = Booking.objects.filter(item=OuterRef("pk"), status=Status.ACTIVE)
    availability = request.GET.get("status", "")
    if availability == "verfuegbar":
        items = items.filter(~Exists(active), condition=Item.Condition.OK)
    elif availability == "ausgeliehen":
        items = items.filter(Exists(active))
    if request.GET.get("meine"):
        items = items.filter(responsible=request.user)
    items = items.exclude(condition=Item.Condition.RETIRED)
    page = Paginator(items, 25).get_page(request.GET.get("page"))
    return render(
        request,
        "inventory/item_list.html",
        {"page": page, "query": query, "categories": Category.objects.all(), "category": category},
    )


def item_detail(request, pk):
    item = get_object_or_404(
        Item.objects.select_related("category", "location", "responsible").prefetch_related("specifications"),
        pk=pk,
    )
    today = timezone.localdate()
    can_manage = item.can_manage(request.user)
    bookings = item.bookings.select_related("borrower").order_by("start_date")
    upcoming = bookings.filter(status__in=[Status.RESERVED, Status.REQUESTED], end_date__gte=today)
    plan_element = element_for_location(item.location)
    context = {
        "item": item,
        "can_manage": can_manage,
        "current": item.current_booking,
        "upcoming": upcoming,
        "mode": booking_mode(item, request.user),
        "accessories": item.accessories.all(),
        "documents": item.documents.all(),
        "photos": item.photos.all(),
        "pending": bookings.filter(status=Status.REQUESTED) if can_manage else None,
        "history": bookings.exclude(status__in=Booking.OPEN).order_by("-start_date")[:20]
        if can_manage
        else None,
        "plan_element": plan_element,
        "today": today,
    }
    return render(request, "inventory/item_detail.html", context)


# Bilder und PDFs zeigt der Browser direkt an, alles andere wird nur heruntergeladen.
INLINE_TYPES = {"application/pdf", "image/jpeg", "image/png", "image/gif", "image/webp", "text/plain"}


def serve_media(request, path):
    """Hochgeladene Dateien nur für angemeldete Nutzer (LoginRequiredMiddleware)."""
    root = Path(settings.MEDIA_ROOT).resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise Http404
    content_type, encoding = mimetypes.guess_type(target.name)
    inline = content_type in INLINE_TYPES and encoding is None
    response = FileResponse(target.open("rb"), as_attachment=not inline, filename=target.name)
    response["X-Content-Type-Options"] = "nosniff"
    return response
