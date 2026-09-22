import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ProposalReviewForm
from .models import ItemSpecification, SpecificationProposal
from .search import search_inventory


@login_required
def chat(request):
    return render(request, "assistant_search/chat.html")


@login_required
def message(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Ungültige Anfrage."}, status=400)
    question = data.get("question", "")
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        return JsonResponse({"error": "Bitte eine Frage mit höchstens 2000 Zeichen eingeben."}, status=400)
    history = data.get("history", [])
    if not isinstance(history, list):
        history = []
    history = history[-4:]
    if settings.OPENROUTER_API_KEY:
        cache_key = f"assistant-hourly-{request.user.pk}"
        request_count = 1 if cache.add(cache_key, 1, timeout=60 * 60) else cache.incr(cache_key)
        if request_count > settings.ASSISTANT_REQUESTS_PER_HOUR:
            return JsonResponse(
                {
                    "error": "Das persönliche Stundenlimit für KI-Anfragen ist erreicht. Bitte später erneut versuchen."
                },
                status=429,
            )
    return JsonResponse(search_inventory(question.strip(), history))


@login_required
def proposal_list(request):
    proposals = SpecificationProposal.objects.filter(
        status=SpecificationProposal.Status.PENDING
    ).select_related("item", "item__responsible")
    if not request.user.is_staff:
        proposals = proposals.filter(item__responsible=request.user)
    return render(request, "assistant_search/proposals.html", {"proposals": proposals})


@login_required
def review_proposal(request, pk):
    proposal = get_object_or_404(SpecificationProposal.objects.select_related("item__responsible"), pk=pk)
    if not proposal.item.can_manage(request.user):
        raise PermissionDenied
    if proposal.status != SpecificationProposal.Status.PENDING:
        messages.info(request, "Dieser Vorschlag wurde bereits bearbeitet.")
        return redirect("assistant_search:proposals")
    form = ProposalReviewForm(request.POST or None, instance=proposal)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "reject":
            with transaction.atomic():
                locked = SpecificationProposal.objects.select_for_update().get(pk=pk)
                if locked.status == SpecificationProposal.Status.PENDING:
                    locked.status = SpecificationProposal.Status.REJECTED
                    locked.reviewed_by = request.user
                    locked.reviewed_at = timezone.now()
                    locked.save(update_fields=["status", "reviewed_by", "reviewed_at"])
            messages.success(request, "Vorschlag verworfen.")
            return redirect("assistant_search:proposals")
        if action == "approve" and form.is_valid():
            with transaction.atomic():
                locked = SpecificationProposal.objects.select_for_update().get(pk=pk)
                if locked.status != SpecificationProposal.Status.PENDING:
                    messages.error(request, "Der Vorschlag wurde inzwischen bearbeitet.")
                    return redirect("assistant_search:proposals")
                data = form.cleaned_data
                specification = ItemSpecification(
                    item=locked.item,
                    verified_by=request.user,
                    **{field: data[field] for field in form.Meta.fields},
                )
                specification.full_clean()
                specification.save()
                locked.status = SpecificationProposal.Status.APPROVED
                locked.reviewed_by = request.user
                locked.reviewed_at = timezone.now()
                locked.save(update_fields=["status", "reviewed_by", "reviewed_at"])
            messages.success(request, "Geprüfter Kennwert übernommen.")
            return redirect("inventory:item_detail", pk=proposal.item_id)
    return render(request, "assistant_search/review.html", {"proposal": proposal, "form": form})
