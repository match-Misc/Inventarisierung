import pytest

from accounts.models import User
from inventory.models import Category, Item, Location


@pytest.fixture(autouse=True)
def local_test_settings(settings):
    settings.DEBUG = False
    settings.SECURE_SSL_REDIRECT = False
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    settings.OPENROUTER_API_KEY = ""


@pytest.fixture
def people(db):
    owner = User.objects.create_user(
        username="owner", password="safe-demo-password", email="owner@example.invalid"
    )
    borrower = User.objects.create_user(
        username="borrower", password="safe-demo-password", email="borrower@example.invalid"
    )
    stranger = User.objects.create_user(username="stranger", password="safe-demo-password")
    return owner, borrower, stranger


@pytest.fixture
def inventory(people):
    owner, _, _ = people
    category = Category.objects.get(path="Sensoren")
    location = Location.objects.create(name="Testlabor")

    def make_item(name, *, policy=Item.LoanPolicy.FREE, model="T-1", max_range=None):
        item = Item.objects.create(
            name=name,
            category=category,
            location=location,
            responsible=owner,
            manufacturer="Demo Instruments",
            model_number=model,
            loan_policy=policy,
        )
        if max_range is not None:
            from assistant_search.models import ItemSpecification

            ItemSpecification.objects.create(
                item=item,
                property_name="force",
                value_text=f"0–{max_range} N",
                min_value=0,
                max_value=max_range,
                unit="N",
                source_url="https://example.org/datasheet",
                source_kind="manufacturer",
                verified_by=owner,
            )
        return item

    return make_item
