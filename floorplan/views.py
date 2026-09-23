import json

from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from inventory.models import Item, Location

from .models import FloorPlan, PlanElement, element_for_location
from .services import PlanError, save_plan


def plan_list(request):
    plans = list(FloorPlan.objects.all())
    if len(plans) == 1:
        return redirect(plans[0])
    return render(request, "floorplan/plan_list.html", {"plans": plans})


def _items_on_plan(plan):
    """Geräte (ohne ausgemusterte) unterhalb des Hallen-Orts."""
    return Item.objects.exclude(condition=Item.Condition.RETIRED).filter(plan.location.subtree_q("location"))


def _element_item_counts(plan, elements):
    by_path = {e.location.path: e.pk for e in elements if e.location_id}
    counts = dict.fromkeys(by_path.values(), 0)
    for path in _items_on_plan(plan).values_list("location__path", flat=True):
        # Gerät liegt im Planobjekt selbst oder in einem Unterort (z. B. Fach im Schrank)
        while path:
            if path in by_path:
                counts[by_path[path]] += 1
                break
            path = path.rpartition(Location.SEPARATOR)[0]
    return counts


def _highlight(request):
    location = None
    if request.GET.get("ort", "").isdigit():
        location = Location.objects.filter(pk=request.GET["ort"]).first()
    elif request.GET.get("geraet", "").isdigit():
        item = Item.objects.filter(pk=request.GET["geraet"]).select_related("location").first()
        location = item.location if item else None
    return element_for_location(location) if location else None


def plan_detail(request, pk, edit=False):
    plan = get_object_or_404(FloorPlan.objects.select_related("location"), pk=pk)
    if edit and not request.user.is_staff:
        raise PermissionDenied
    elements = list(plan.elements.select_related("location"))
    counts = _element_item_counts(plan, elements)
    highlight = _highlight(request)
    data = {
        "plan": {"id": plan.pk, "name": plan.name, "width": plan.width, "height": plan.height},
        "elements": [{**e.as_dict(), "items": counts.get(e.pk, 0)} for e in elements],
        "kinds": dict(PlanElement.Kind.choices),
        "holdingKinds": sorted(PlanElement.HOLDING_KINDS),
        "editable": edit,
        "highlight": highlight.pk if highlight and highlight.plan_id == plan.pk else None,
    }
    return render(
        request,
        "floorplan/plan_detail.html",
        {"plan": plan, "plan_data": data, "edit": edit, "highlight": highlight},
    )


@require_POST
def plan_save(request, pk):
    if not request.user.is_staff:
        raise PermissionDenied
    plan = get_object_or_404(FloorPlan, pk=pk)
    try:
        payload = json.loads(request.body)
        size = payload.get("plan") or {}
        if size:
            plan.width = max(float(size["width"]), 1)
            plan.height = max(float(size["height"]), 1)
            plan.save(update_fields=["width", "height"])
        save_plan(plan, payload.get("elements", []), payload.get("deleted", []))
    except PlanError as error:
        return JsonResponse({"error": str(error)}, status=400)
    except (ValueError, KeyError, TypeError, AttributeError):
        return JsonResponse({"error": "Ungültige Daten."}, status=400)
    elements = list(plan.elements.select_related("location"))
    counts = _element_item_counts(plan, elements)
    return JsonResponse({"elements": [{**e.as_dict(), "items": counts.get(e.pk, 0)} for e in elements]})


def element_panel(request, pk):
    element = get_object_or_404(PlanElement.objects.select_related("location", "plan"), pk=pk)
    items = []
    if element.location_id:
        items = (
            Item.objects.with_status()
            .exclude(condition=Item.Condition.RETIRED)
            .filter(element.location.subtree_q("location"))
        )
    return render(request, "floorplan/partials/element_panel.html", {"element": element, "items": items})


def item_search(request, pk):
    plan = get_object_or_404(FloorPlan, pk=pk)
    query = request.GET.get("q", "").strip()
    results = []
    if len(query) >= 2:
        words = Q()
        for word in query.split():
            words &= (
                Q(name__icontains=word)
                | Q(manufacturer__icontains=word)
                | Q(model_number__icontains=word)
                | Q(inventory_number__icontains=word)
            )
        for item in Item.objects.with_status().exclude(condition=Item.Condition.RETIRED).filter(words)[:20]:
            element = element_for_location(item.location)
            on_plan = element is not None and element.plan_id == plan.pk
            results.append({"item": item, "element": element if on_plan else None})
    return render(request, "floorplan/partials/search_results.html", {"results": results, "query": query})
