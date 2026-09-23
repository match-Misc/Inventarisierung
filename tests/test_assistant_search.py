import json

import pytest
from django.urls import reverse

from assistant_search.models import ItemSpecification, SpecificationProposal
from assistant_search.provider import _request, research_specification
from assistant_search.search import search_inventory
from assistant_search.units import comparable_range


@pytest.mark.django_db
def test_force_query_ranks_verified_range_and_excludes_too_small(inventory):
    good = inventory("Wägezelle 250 N", max_range=250)
    inventory("Kraftsensor 100 N", model="T-2", max_range=100)
    wide = inventory("Kraftsensor 2 kN", model="T-3", max_range=2000)

    result = search_inventory("Ich möchte eine Kraft im Bereich von 200 N messen")

    assert [card["id"] for card in result["cards"]] == [good.pk, wide.pk]
    assert result["cards"][0]["specification"]["source_url"] == "https://example.org/datasheet"
    assert "geprüft" in result["cards"][0]["suitability"].lower()


def test_physical_units_are_checked():
    assert comparable_range(0, 0.25, "kN", 200, "N")["fits"]
    assert not comparable_range(0, 100, "N", 200, "N")["fits"]
    assert comparable_range(0, 25, "kg", 200, "N") is None


@pytest.mark.django_db
def test_provisional_value_is_not_treated_as_verified(inventory, monkeypatch):
    item = inventory("Kraftsensor ungeprüft")
    monkeypatch.setattr(
        "assistant_search.search.research_specification",
        lambda item, property_name: {
            "property_name": "force",
            "value_text": "0–250 N",
            "min_value": 0,
            "max_value": 250,
            "unit": "N",
            "source_url": "https://example.org/spec",
            "source_title": "Datenblatt",
            "source_kind": "dealer",
        },
    )

    result = search_inventory("Kraft 200 N messen")

    assert result["cards"][0]["id"] == item.pk
    assert result["cards"][0]["specification"] is None
    assert SpecificationProposal.objects.filter(item=item, status="pending").count() == 1


@pytest.mark.django_db
def test_review_requires_responsible_person(client, people, inventory):
    owner, _, stranger = people
    item = inventory("Wägezelle")
    proposal = SpecificationProposal.objects.create(
        item=item,
        property_name="force",
        value_text="0–250 N",
        min_value=0,
        max_value=250,
        unit="N",
        source_url="https://example.org/spec",
        source_kind="dealer",
    )
    url = reverse("assistant_search:review", args=[proposal.pk])
    client.force_login(stranger)
    assert client.get(url).status_code == 403
    client.force_login(owner)
    assert client.get(url).status_code == 200
    assert (
        client.post(
            url,
            {
                "action": "approve",
                "property_name": "force",
                "value_text": "0–250 N",
                "min_value": "0",
                "max_value": "250",
                "unit": "N",
                "source_url": "https://example.org/spec",
                "source_title": "Datenblatt",
                "source_kind": "dealer",
            },
        ).status_code
        == 302
    )
    assert ItemSpecification.objects.filter(item=item, verified_by=owner).count() == 1
    assert client.post(url, {"action": "approve"}).status_code == 302
    assert ItemSpecification.objects.filter(item=item).count() == 1


def test_research_needs_a_real_citation(monkeypatch, inventory):
    item = inventory("Wägezelle")
    result = {
        "model_match": True,
        "property_name": "force",
        "value_text": "0–250 N",
        "min_value": 0,
        "max_value": 250,
        "unit": "N",
        "source_url": "https://example.org/spec",
        "source_title": "Datenblatt",
        "source_kind": "manufacturer",
    }
    monkeypatch.setattr(
        "assistant_search.provider._request",
        lambda *args, **kwargs: {"content": json.dumps(result), "annotations": []},
    )
    assert research_specification(item, "force") is None
    monkeypatch.setattr(
        "assistant_search.provider._request",
        lambda *args, **kwargs: {
            "content": json.dumps(result),
            "annotations": [{"type": "url_citation", "url": "https://example.org/spec"}],
        },
    )
    assert research_specification(item, "force")["max_value"] == 250


@pytest.mark.django_db
def test_research_sends_only_public_product_data(monkeypatch, inventory, settings):
    item = inventory("Interner Name")
    item.serial_number = "SECRET-SERIAL"
    item.inventory_number = "SECRET-INVENTORY"
    item.location_note = "SECRET-LOCATION"
    item.save()
    captured = {}

    def fake_request(messages, **kwargs):
        captured["messages"] = messages
        return {"content": "{}", "annotations": []}

    settings.ASSISTANT_WEB_SEARCH = True
    monkeypatch.setattr("assistant_search.provider._request", fake_request)
    research_specification(item, "force")
    transmitted = json.dumps(captured["messages"])
    assert "Demo Instruments" in transmitted and "T-1" in transmitted
    assert "SECRET-SERIAL" not in transmitted
    assert "SECRET-INVENTORY" not in transmitted
    assert "SECRET-LOCATION" not in transmitted


def test_provider_enforces_privacy_routing(monkeypatch, settings):
    settings.OPENROUTER_API_KEY = "test-key"
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}]}'

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr("assistant_search.provider.urlopen", fake_urlopen)
    assert _request([{"role": "user", "content": "Kraftsensor"}])["content"] == "ok"
    assert captured["payload"]["provider"] == {
        "zdr": True,
        "data_collection": "deny",
        "require_parameters": True,
    }
    assert "temperature" not in captured["payload"]


def test_provider_retries_an_incomplete_response(monkeypatch, settings):
    settings.OPENROUTER_API_KEY = "test-key"
    responses = iter(
        [
            b'{"error":{"message":"temporary"}}',
            b'{"choices":[{"message":{"content":"ok"}}]}',
        ]
    )
    calls = 0

    class FakeResponse:
        def __init__(self, data):
            self.data = data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self.data

    def fake_urlopen(request, timeout):
        nonlocal calls
        calls += 1
        return FakeResponse(next(responses))

    monkeypatch.setattr("assistant_search.provider.urlopen", fake_urlopen)
    assert _request([{"role": "user", "content": "Kraftsensor"}])["content"] == "ok"
    assert calls == 2


@pytest.mark.django_db
def test_chat_requires_login_and_does_not_store_history(client, people, inventory):
    _, borrower, _ = people
    inventory("Wägezelle", max_range=250)
    url = reverse("assistant_search:message")
    assert client.post(url, data="{}", content_type="application/json").status_code == 302
    client.force_login(borrower)
    response = client.post(
        url, data=json.dumps({"question": "Kraft 200 N", "history": []}), content_type="application/json"
    )
    assert response.status_code == 200
    assert response.json()["cards"]
    assert "history" not in client.session


@pytest.mark.django_db
def test_chat_rate_limit_caps_external_calls(client, people, settings, monkeypatch):
    _, borrower, _ = people
    settings.OPENROUTER_API_KEY = "test-key"
    settings.ASSISTANT_REQUESTS_PER_HOUR = 1
    monkeypatch.setattr(
        "assistant_search.views.search_inventory",
        lambda question, history: {"answer": "ok", "cards": []},
    )
    client.force_login(borrower)
    url = reverse("assistant_search:message")
    payload = json.dumps({"question": "Kraftsensor", "history": []})
    assert client.post(url, data=payload, content_type="application/json").status_code == 200
    assert client.post(url, data=payload, content_type="application/json").status_code == 429
