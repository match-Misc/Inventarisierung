import json
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from inventory.models import Category, Item, ItemDocument, Location
from inventory.recognition import prepare_photo, research_item


def test_photo_is_resized_and_metadata_is_removed():
    image = Image.new("RGB", (1800, 1200), "white")
    exif = Image.Exif()
    exif[270] = "internal label"
    data = BytesIO()
    image.save(data, format="JPEG", exif=exif)
    upload = SimpleUploadedFile("label.jpg", data.getvalue(), content_type="image/jpeg")

    result = prepare_photo(upload)

    with Image.open(BytesIO(result)) as cleaned:
        assert max(cleaned.size) == 1600
        assert not cleaned.getexif()


def test_research_accepts_only_cited_source_and_sends_model_only(monkeypatch, settings):
    settings.ITEM_RECOGNITION_MODELS = {"medium": "openai/gpt-4.1-mini"}
    captured = {}

    def fake_request(messages, **kwargs):
        captured["messages"] = messages
        captured["options"] = kwargs
        return {
            "content": json.dumps(
                {"model_match": True, "summary": "Kraftaufnehmer", "source_url": "https://example.org/type"}
            ),
            "annotations": [{"url": "https://example.org/type"}],
        }

    monkeypatch.setattr("inventory.recognition._request", fake_request)
    assert research_item("Demo", "T-1", difficulty="medium")["summary"] == "Kraftaufnehmer"
    assert captured["options"]["web"] is True
    assert "Demo T-1" in json.dumps(captured["messages"])
    assert "serial" not in json.dumps(captured["messages"])
    assert research_item("Demo", "T-1", difficulty="easy") is None

    def uncited(messages, **kwargs):
        result = fake_request(messages, **kwargs)
        result["annotations"] = []
        return result

    monkeypatch.setattr("inventory.recognition._request", uncited)
    assert research_item("Demo", "T-1", difficulty="medium") is None


@pytest.mark.django_db
def test_identification_requires_review_and_saves_edited_values(client, people, monkeypatch, settings):
    owner, _, stranger = people
    client.force_login(owner)
    settings.OPENROUTER_API_KEY = "test-key"
    settings.MEDIA_ROOT = settings.MEDIA_ROOT / "identification-test"
    seen = {}

    def fake_recognition(name, photo, *, difficulty):
        seen["name"] = name
        seen["photo"] = photo
        seen["difficulty"] = difficulty
        return {
            "name": "Kraftsensor",
            "category": "Sensoren",
            "manufacturer": "Demo Instruments",
            "model_number": "T-1",
            "serial_number": "S-123",
            "inventory_number": "",
            "description": "Kraftsensor",
            "uncertainty": "Typvariante prüfen.",
        }

    monkeypatch.setattr("inventory.views.recognize_item", fake_recognition)
    data = BytesIO()
    Image.new("RGB", (80, 60), "blue").save(data, format="JPEG")
    response = client.post(
        reverse("inventory:identify"),
        {
            "name_hint": "T-1",
            "difficulty": "easy",
            "photo": SimpleUploadedFile("label.jpg", data.getvalue(), content_type="image/jpeg"),
        },
    )
    assert response.status_code == 200
    assert b"Typvariante" in response.content
    assert seen["name"] == "T-1"
    assert seen["difficulty"] == "easy"
    assert seen["photo"].startswith(b"\xff\xd8")
    assert Item.objects.count() == 0
    token = client.session["item_recognition_draft"]["token"]
    photo_url = reverse("inventory:identified_photo", args=[token])
    assert client.get(photo_url).status_code == 200

    other_client = client_class()
    other_client.force_login(stranger)
    assert other_client.get(photo_url).status_code == 404
    assert other_client.get(f"/medien/.recognition-drafts/{token}.jpg").status_code == 404

    location = Location.objects.create(name="Prüflabor")
    response = client.post(
        reverse("inventory:identify_save"),
        {
            "draft": token,
            "name": "Bearbeiteter Kraftsensor",
            "category": response.context["form"]["category"].value(),
            "manufacturer": "Demo Instruments",
            "model_number": "T-1",
            "serial_number": "S-123",
            "inventory_number": "INV-1",
            "description": "Geprüfter Text",
            "location": location.pk,
            "location_note": "Schrank 2",
            "loan_policy": Item.LoanPolicy.APPROVAL,
            "condition": Item.Condition.OK,
        },
    )
    assert response.status_code == 302
    item = Item.objects.get()
    assert item.name == "Bearbeiteter Kraftsensor"
    assert item.responsible == owner and item.created_by == owner
    assert item.photos.count() == 1
    assert client.get(photo_url).status_code == 404
    assert client.post(reverse("inventory:identify_save"), {"draft": token}).status_code == 302
    assert Item.objects.count() == 1


def client_class():
    from django.test import Client

    return Client()


@pytest.mark.django_db
def test_manual_fallback_when_no_key(client, people, settings):
    owner, _, _ = people
    client.force_login(owner)
    settings.OPENROUTER_API_KEY = ""
    response = client.post(
        reverse("inventory:identify"), {"name_hint": "Drehmomentsensor", "difficulty": "easy"}
    )
    assert response.status_code == 200
    assert response.context["form"]["name"].value() == "Drehmomentsensor"
    assert Item.objects.count() == 0


@pytest.mark.django_db
def test_medium_mode_researches_only_public_model_data(client, people, settings, monkeypatch):
    owner, _, _ = people
    client.force_login(owner)
    settings.OPENROUTER_API_KEY = "test-key"
    seen = {}

    def fake_recognition(name, photo, *, difficulty):
        seen["recognition"] = difficulty
        return {"name": "Sensor", "manufacturer": "Demo Instruments", "model_number": "T-1"}

    def fake_research(manufacturer, model_number, *, difficulty):
        seen["research"] = (manufacturer, model_number, difficulty)
        return {"summary": "Öffentliches Datenblatt", "source_url": "https://example.org/t-1"}

    monkeypatch.setattr("inventory.views.recognize_item", fake_recognition)
    monkeypatch.setattr("inventory.views.research_item", fake_research)
    response = client.post(
        reverse("inventory:identify"), {"name_hint": "Interne Aufschrift", "difficulty": "medium"}
    )
    assert response.status_code == 200
    assert seen["recognition"] == "medium"
    assert seen["research"] == ("Demo Instruments", "T-1", "medium")
    assert response.context["form"]["description"].value() == "Öffentliches Datenblatt"
    token = client.session["item_recognition_draft"]["token"]
    location = Location.objects.create(name="Recherchetest")
    saved = client.post(
        reverse("inventory:identify_save"),
        {
            "draft": token,
            "name": "Sensor",
            "category": Category.objects.get(path="Sensoren").pk,
            "manufacturer": "Demo Instruments",
            "model_number": "T-1",
            "description": "Öffentliches Datenblatt",
            "location": location.pk,
            "loan_policy": Item.LoanPolicy.FREE,
            "condition": Item.Condition.OK,
        },
    )
    assert saved.status_code == 302
    assert ItemDocument.objects.get(item=Item.objects.get()).url == "https://example.org/t-1"
