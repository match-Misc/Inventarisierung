import mimetypes
import time
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Exists, OuterRef, Q
from django.http import FileResponse, Http404, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from assistant_search.provider import ProviderUnavailable
from floorplan.models import element_for_location
from loans.models import Booking
from loans.services import booking_mode

from .drafts import DRAFT_LIFETIME, clear_old_drafts, create_draft, delete_draft, draft_photo
from .forms import IdentifiedItemForm, RecognitionInputForm
from .images import add_photo
from .models import Category, Item, ItemDocument
from .recognition import prepare_photo, recognize_item, research_item

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
    if not target.is_relative_to(root) or ".recognition-drafts" in target.parts or not target.is_file():
        raise Http404
    content_type, encoding = mimetypes.guess_type(target.name)
    inline = content_type in INLINE_TYPES and encoding is None
    response = FileResponse(target.open("rb"), as_attachment=not inline, filename=target.name)
    response["X-Content-Type-Options"] = "nosniff"
    return response


def _draft_from_session(request):
    draft = request.session.get("item_recognition_draft")
    if not isinstance(draft, dict) or time.time() - draft.get("created", 0) > DRAFT_LIFETIME:
        request.session.pop("item_recognition_draft", None)
        return None
    return draft


def _category_initial(label):
    from .models import Category

    label = label.strip().casefold()
    if not label:
        return None
    for category in Category.objects.all():
        if category.name.casefold() == label or category.path.casefold() == label:
            return category.pk
    return None


def _allow_ai_call(user_id):
    cache_key = f"assistant-hourly-{user_id}"
    count = 1 if cache.add(cache_key, 1, timeout=3600) else cache.incr(cache_key)
    return count <= settings.ASSISTANT_REQUESTS_PER_HOUR


@login_required
def identify_item(request):
    if request.method not in {"GET", "POST"}:
        return HttpResponseNotAllowed(["GET", "POST"])
    if request.method == "GET":
        clear_old_drafts()
        return render(
            request,
            "inventory/identify.html",
            {"form": RecognitionInputForm(), "max_photo_mb": settings.MAX_PHOTO_UPLOAD_MB},
        )
    form = RecognitionInputForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(
            request,
            "inventory/identify.html",
            {"form": form, "max_photo_mb": settings.MAX_PHOTO_UPLOAD_MB},
        )
    old = _draft_from_session(request)
    if old:
        delete_draft(old["token"])
    name_hint = form.cleaned_data["name_hint"].strip()
    photo = form.cleaned_data["photo"]
    difficulty = form.cleaned_data["difficulty"]
    photo_bytes = prepare_photo(photo) if photo else None
    proposal = {"name": name_hint}
    source = None
    if settings.OPENROUTER_API_KEY:
        if _allow_ai_call(request.user.pk):
            try:
                proposal = recognize_item(name_hint, photo_bytes, difficulty=difficulty)
            except ProviderUnavailable:
                messages.warning(
                    request, "Die KI-Erkennung ist gerade nicht verfügbar. Bitte Angaben selbst ausfüllen."
                )
            if (
                difficulty != "easy"
                and proposal.get("manufacturer")
                and proposal.get("model_number")
                and _allow_ai_call(request.user.pk)
            ):
                try:
                    source = research_item(
                        proposal.get("manufacturer", ""),
                        proposal.get("model_number", ""),
                        difficulty=difficulty,
                    )
                    if source:
                        source["manufacturer"] = proposal["manufacturer"]
                        source["model_number"] = proposal["model_number"]
                        proposal["description"] = source["summary"]
                except ProviderUnavailable:
                    messages.info(
                        request, "Die Webrecherche ist gerade nicht verfügbar. Bitte Typdaten prüfen."
                    )
        else:
            messages.warning(
                request, "Das persönliche KI-Stundenlimit ist erreicht. Bitte Angaben selbst ausfüllen."
            )
    else:
        messages.info(request, "Kein KI-Schlüssel eingerichtet. Bitte Angaben selbst ausfüllen.")
    token = create_draft(photo_bytes)
    request.session["item_recognition_draft"] = {"token": token, "created": time.time()}
    initial = {key: proposal.get(key, "") for key in IdentifiedItemForm.Meta.fields}
    initial["category"] = _category_initial(proposal.get("category", ""))
    initial["loan_policy"] = Item.LoanPolicy.FREE
    initial["condition"] = Item.Condition.OK
    request.session["item_recognition_uncertainty"] = proposal.get("uncertainty", "")[:500]
    request.session["item_recognition_source"] = source
    return render(
        request,
        "inventory/identify_review.html",
        {
            "form": IdentifiedItemForm(initial=initial),
            "draft": token,
            "has_photo": bool(photo_bytes),
            "uncertainty": request.session["item_recognition_uncertainty"],
            "source": source,
        },
    )


@login_required
def identified_photo(request, token):
    draft = _draft_from_session(request)
    if not draft or draft["token"] != token:
        raise Http404
    path = draft_photo(token)
    if not path:
        raise Http404
    response = FileResponse(path.open("rb"), content_type="image/jpeg")
    response["Cache-Control"] = "private, no-store"
    return response


@login_required
def save_identified_item(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    draft = _draft_from_session(request)
    if not draft or request.POST.get("draft") != draft["token"]:
        messages.error(request, "Der Entwurf ist abgelaufen. Bitte erneut beginnen.")
        return redirect("inventory:identify")
    form = IdentifiedItemForm(request.POST)
    path = draft_photo(draft["token"])
    if form.is_valid():
        with transaction.atomic():
            item = form.save(commit=False)
            item.responsible = request.user
            item.created_by = request.user
            item.full_clean()
            item.save()
            source = request.session.get("item_recognition_source")
            if (
                source
                and item.manufacturer == source.get("manufacturer")
                and item.model_number == source.get("model_number")
            ):
                ItemDocument.objects.create(
                    item=item,
                    title="Quelle zur Geräteerkennung",
                    doc_type=ItemDocument.DocType.OTHER,
                    url=source["source_url"],
                    uploaded_by=request.user,
                )
            if path:
                add_photo(item, ContentFile(path.read_bytes(), name="erkennung.jpg"), request.user)
        delete_draft(draft["token"])
        request.session.pop("item_recognition_draft", None)
        request.session.pop("item_recognition_uncertainty", None)
        request.session.pop("item_recognition_source", None)
        messages.success(request, "Gerät wurde ins Inventar aufgenommen.")
        return redirect(item)
    return render(
        request,
        "inventory/identify_review.html",
        {
            "form": form,
            "draft": draft["token"],
            "has_photo": bool(path),
            "uncertainty": request.session.get("item_recognition_uncertainty", ""),
            "source": request.session.get("item_recognition_source"),
        },
    )
