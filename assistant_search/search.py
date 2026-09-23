import logging
import re
from decimal import Decimal, InvalidOperation

from django.db.models import Prefetch, Q
from django.utils import timezone

from inventory.models import Item
from loans.models import Booking

from .models import SpecificationProposal
from .provider import ProviderUnavailable, infer_intent, research_specification
from .units import comparable_range, normalize_property

logger = logging.getLogger(__name__)

STOPWORDS = {
    "ich",
    "möchte",
    "moechte",
    "eine",
    "einen",
    "einem",
    "haben",
    "brauche",
    "für",
    "fuer",
    "mit",
    "der",
    "die",
    "das",
    "und",
    "oder",
    "bei",
    "von",
    "bis",
    "im",
    "in",
    "den",
    "dem",
    "messen",
    "messung",
    "bereich",
    "gerät",
    "geraet",
    "suche",
    "welcher",
    "welche",
    "kann",
}
SYNONYMS = {
    "force": ("kraft", "kraftsensor", "kraftaufnehmer", "wägezelle", "waegezelle", "load cell"),
    "pressure": ("druck", "drucksensor", "manometer"),
    "temperature": ("temperatur", "thermometer", "temperatursensor"),
    "torque": ("drehmoment", "drehmomentsensor"),
    "voltage": ("spannung", "voltmeter"),
    "current": ("strom", "amperemeter"),
    "length": ("weg", "abstand", "länge", "laenge"),
    "mass": ("masse", "waage", "gewicht"),
}
VALUE_PATTERN = re.compile(
    r"(?P<value>\d+(?:[.,]\d+)?)\s*(?P<unit>kN|mN|N|kPa|MPa|Pa|°C|K|mV|V|mA|A|Nm|mm|cm|m|kg|g)\b",
    re.IGNORECASE,
)


def fallback_intent(question):
    lowered = question.casefold()
    match = VALUE_PATTERN.search(question)
    property_name = next(
        (name for name, words in SYNONYMS.items() if any(word in lowered for word in words)), ""
    )
    if not property_name and match:
        unit = match.group("unit").casefold()
        property_name = next(
            (
                name
                for name, units in {
                    "force": ("n", "kn", "mn"),
                    "pressure": ("pa", "kpa", "mpa"),
                    "voltage": ("v", "mv"),
                    "current": ("a", "ma"),
                    "temperature": ("°c", "k"),
                    "torque": ("nm",),
                    "length": ("mm", "cm", "m"),
                    "mass": ("kg", "g"),
                }.items()
                if unit in units
            ),
            "",
        )
    keywords = [
        word
        for word in re.findall(r"[\wäöüÄÖÜß-]{3,}", lowered)
        if word not in STOPWORDS and not word.isdigit()
    ]
    return {
        "keywords": keywords[:6],
        "property_name": property_name,
        "target_value": float(match.group("value").replace(",", ".")) if match else None,
        "target_unit": match.group("unit") if match else "",
        "category": "",
        "interpretation": "",
        "clarifying_question": "",
    }


def _safe_intent(question, history):
    fallback = fallback_intent(question)
    try:
        model_intent = infer_intent(question, history)
    except ProviderUnavailable:
        return fallback, True
    if not isinstance(model_intent, dict):
        return fallback, True
    result = {**fallback, **model_intent}
    result["property_name"] = normalize_property(str(result.get("property_name", "")))
    result["keywords"] = [str(word)[:40] for word in result.get("keywords", [])[:6] if isinstance(word, str)]
    try:
        if result["target_value"] is not None:
            result["target_value"] = Decimal(str(result["target_value"]))
            if result["target_value"] <= 0 or result["target_value"] > 10**12:
                result["target_value"] = None
    except (InvalidOperation, ValueError, TypeError):
        result["target_value"] = None
    result["target_unit"] = str(result.get("target_unit", ""))[:30]
    result["category"] = str(result.get("category", ""))[:40]
    return result, False


def _candidate_items(intent):
    property_name = intent["property_name"]
    terms = set(word.casefold() for word in intent["keywords"] if len(word) >= 3)
    terms.update(SYNONYMS.get(property_name, ()))
    query = Q()
    for term in list(terms)[:15]:
        query |= (
            Q(name__icontains=term)
            | Q(description__icontains=term)
            | Q(category__path__icontains=term)
            | Q(manufacturer__icontains=term)
            | Q(model_number__icontains=term)
        )
    if intent["category"]:
        query |= Q(category__path__icontains=intent["category"])
    items = (
        Item.objects.exclude(condition=Item.Condition.RETIRED)
        .select_related("category", "location", "responsible")
        .prefetch_related(
            "specifications",
            "specification_proposals",
            Prefetch(
                "bookings",
                queryset=Booking.objects.filter(status__in=Booking.BLOCKING),
                to_attr="open_bookings",
            ),
        )
    )
    if query:
        items = items.filter(query).distinct()
    return list(items[:80]), terms


def _store_proposal(item, property_name):
    if item.specification_proposals.filter(
        status=SpecificationProposal.Status.PENDING,
        property_name=property_name,
    ).exists():
        return
    try:
        result = research_specification(item, property_name)
        if not result or normalize_property(result["property_name"]) != property_name:
            return
        proposal = SpecificationProposal(
            item=item,
            property_name=property_name,
            value_text=str(result["value_text"])[:200],
            min_value=result.get("min_value"),
            max_value=result.get("max_value"),
            unit=str(result.get("unit") or "")[:40],
            source_url=result["source_url"],
            source_title=str(result.get("source_title") or "")[:200],
            source_kind=result["source_kind"],
        )
        proposal.full_clean()
        proposal.save()
        item._prefetched_objects_cache.pop("specification_proposals", None)
    except (ProviderUnavailable, ValueError, TypeError, InvalidOperation) as exc:
        logger.info("Kein belastbarer Kennwertvorschlag für Gerät %s: %s", item.pk, type(exc).__name__)


def search_inventory(question, history=()):
    intent, local_only = _safe_intent(question, history)
    if not intent["keywords"] and not intent["property_name"] and not intent["category"]:
        return {
            "answer": "Welche Aufgabe soll das Gerät erfüllen? Nenne gern eine Messgröße oder einen Gerätetyp.",
            "cards": [],
        }
    items, terms = _candidate_items(intent)
    property_name = intent["property_name"]
    target = intent["target_value"]
    unit = intent["target_unit"]
    if target is not None and unit and property_name:
        researched = 0
        for item in items:
            has_spec = any(
                normalize_property(spec.property_name) == property_name for spec in item.specifications.all()
            )
            if has_spec or not item.manufacturer or not item.model_number:
                continue
            if researched >= 2:
                break
            _store_proposal(item, property_name)
            researched += 1
    cards = []
    for item in items:
        text = " ".join(
            (item.name, item.description, item.category.path, item.manufacturer, item.model_number)
        ).casefold()
        lexical = sum(1 for term in terms if term in text)
        specs = [
            spec
            for spec in item.specifications.all()
            if normalize_property(spec.property_name) == property_name
        ]
        fit = None
        matching_spec = None
        if target is not None and unit and property_name:
            comparisons = [
                (spec, comparable_range(spec.min_value, spec.max_value, spec.unit, target, unit))
                for spec in specs
            ]
            matching = [(spec, check) for spec, check in comparisons if check and check["fits"]]
            if matching:
                matching_spec, fit = matching[0]
            elif any(check is not None for _, check in comparisons):
                continue
        active = next(
            (booking for booking in item.open_bookings if booking.status == Booking.Status.ACTIVE), None
        )
        reserved_today = next(
            (
                booking
                for booking in item.open_bookings
                if booking.status == Booking.Status.RESERVED
                and booking.start_date <= timezone.localdate() <= booking.end_date
            ),
            None,
        )
        pending = next(
            (
                proposal
                for proposal in item.specification_proposals.all()
                if proposal.status == "pending"
                and normalize_property(proposal.property_name) == property_name
            ),
            None,
        )
        suitability = (
            "Passender Messbereich, geprüft" if fit else "Eignung anhand der Kennwerte noch unbestätigt"
        )
        if fit and fit["at_limit"]:
            suitability += " – Zielwert liegt am Bereichsende"
        if target is None:
            suitability = "Passender Suchbegriff; technische Eignung bitte prüfen"
        status = (
            "Ausgeliehen"
            if active
            else "Heute reserviert"
            if reserved_today
            else item.get_condition_display()
        )
        if active:
            status += (
                f" bis {active.end_date:%d.%m.%Y}"
                if active.end_date >= timezone.localdate()
                else f" (überfällig seit {active.end_date:%d.%m.%Y})"
            )
        score = lexical * 2 + (100 if fit else 0) + (0 if active or reserved_today else 5)
        if fit and fit["margin"] is not None and fit["margin"] >= 0:
            score += 30 / (1 + fit["margin"])
        cards.append(
            {
                "id": item.pk,
                "name": item.name,
                "category": item.category.path,
                "status": status,
                "suitability": suitability,
                "detail_url": item.get_absolute_url(),
                "booking_url": f"/ausleihen/neu/{item.pk}/",
                "bookable": item.is_bookable,
                "specification": (
                    {
                        "value": matching_spec.value_text,
                        "source_url": matching_spec.source_url,
                        "source_kind": matching_spec.get_source_kind_display(),
                    }
                    if matching_spec
                    else None
                ),
                "proposal": (
                    {
                        "value": pending.value_text,
                        "source_url": pending.source_url,
                        "source_kind": pending.get_source_kind_display(),
                    }
                    if pending
                    else None
                ),
                "score": score,
            }
        )
    cards.sort(key=lambda card: (-card["score"], card["name"].casefold()))
    cards = cards[:10]
    if cards:
        answer = f"Ich habe {len(cards)} mögliche Geräte gefunden. Geprüfte Messbereiche sind besonders gekennzeichnet."
    else:
        answer = "Ich habe im Inventar keinen belegbar passenden Treffer gefunden. Beschreibe die Aufgabe bitte genauer."
    if local_only:
        answer += " Die KI ist derzeit nicht verfügbar; ich habe die lokale Suche verwendet."
    if intent.get("clarifying_question") and not cards:
        answer += " " + str(intent["clarifying_question"])[:200]
    return {"answer": answer, "cards": cards}
