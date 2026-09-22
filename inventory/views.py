from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render

from .models import Item


@login_required
def dashboard(request):
    query = request.GET.get("q", "").strip()[:100]
    items = Item.objects.with_status().exclude(condition=Item.Condition.RETIRED)
    if query:
        items = items.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(manufacturer__icontains=query)
            | Q(model_number__icontains=query)
            | Q(category__path__icontains=query)
        )
    return render(request, "inventory/dashboard.html", {"items": items[:100], "query": query})


@login_required
def item_detail(request, pk):
    item = get_object_or_404(
        Item.objects.select_related("category", "location", "responsible").prefetch_related(
            "accessories", "photos", "documents", "specifications", "bookings"
        ),
        pk=pk,
    )
    active_booking = next((booking for booking in item.bookings.all() if booking.status == "active"), None)
    return render(
        request,
        "inventory/item_detail.html",
        {"item": item, "active_booking": active_booking, "can_manage": item.can_manage(request.user)},
    )


@login_required
def serve_media(request, path):
    root = Path(settings.MEDIA_ROOT).resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root) or not target.is_file():
        raise Http404
    return FileResponse(target.open("rb"))
