"""Speichern des Hallenplans und Abgleich der Planobjekte mit den Orten im Inventar."""

from django.db import transaction

from inventory.models import Location

from .models import PlanElement

EDITABLE_FIELDS = ("kind", "label", "x", "y", "width", "height", "rotation", "color", "z")


class PlanError(Exception):
    """Fachlicher Fehler beim Speichern. Die Meldung wird angezeigt."""


def location_name(label):
    return " ".join(label.split())[:100]


def _unique_name(parent, name, exclude_pk=None):
    candidate, number = name, 2
    siblings = Location.objects.filter(parent=parent).exclude(pk=exclude_pk)
    while siblings.filter(name=candidate).exists():
        candidate = f"{name} ({number})"
        number += 1
    return candidate


def sync_location(element):
    """Legt den Ort zum Planobjekt an, benennt ihn um oder entfernt ihn."""
    parent = element.plan.location
    if element.holds_items:
        name = location_name(element.label)
        location = element.location
        if location is None:
            location = Location(parent=parent)
        if location.name != name or location.parent_id != parent.pk:
            location.name = _unique_name(parent, name, exclude_pk=location.pk)
            location.parent = parent
            location.save()
        if element.location_id != location.pk:
            element.location = location
            element.save(update_fields=["location"])
    elif element.location is not None:
        location = element.location
        _ensure_empty(location, element)
        element.location = None
        element.save(update_fields=["location"])
        location.delete()


def _ensure_empty(location, element):
    if location.items.exists() or location.children.exists():
        count = location.items.count()
        raise PlanError(
            f"„{element}“ kann nicht entfernt oder geändert werden: Dort liegen noch {count} Gerät(e) "
            "bzw. Unterorte. Bitte zuerst einen anderen Ablageort zuweisen."
        )


def _clean_values(data):
    try:
        values = {
            "kind": data.get("kind", PlanElement.Kind.OTHER),
            "label": str(data.get("label", ""))[:200],
            "x": round(float(data["x"]), 3),
            "y": round(float(data["y"]), 3),
            "width": round(max(float(data["width"]), 0.05), 3),
            "height": round(max(float(data["height"]), 0.05), 3),
            "rotation": round(float(data.get("rotation") or 0), 1) % 360,
            "color": str(data.get("color") or "")[:7],
            "z": int(data.get("z") or 0),
        }
    except (KeyError, TypeError, ValueError) as error:
        raise PlanError(f"Ungültige Objektdaten: {error}") from error
    if values["kind"] not in PlanElement.Kind.values:
        raise PlanError(f"Unbekannte Objektart: {values['kind']}")
    return values


@transaction.atomic
def save_plan(plan, elements, deleted_ids):
    """Übernimmt den Stand aus dem Editor. `elements` ohne id werden neu angelegt."""
    existing = {e.pk: e for e in plan.elements.select_related("location")}
    for pk in deleted_ids:
        element = existing.pop(int(pk), None)
        if element is None:
            continue
        if element.location is not None:
            _ensure_empty(element.location, element)
        location = element.location
        element.delete()
        if location is not None:
            location.delete()

    for data in elements:
        values = _clean_values(data)
        pk = data.get("id")
        if pk:
            element = existing.get(int(pk))
            if element is None:
                raise PlanError("Ein Objekt wurde inzwischen gelöscht. Bitte Seite neu laden.")
            for field, value in values.items():
                setattr(element, field, value)
            element.save()
        else:
            element = PlanElement.objects.create(plan=plan, **values)
        sync_location(element)
