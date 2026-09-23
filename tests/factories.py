import factory

from accounts.models import User
from inventory.models import Category, Item, Location


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"nutzer{n}")
    first_name = "Test"
    last_name = factory.Sequence(lambda n: f"Person {n}")
    email = factory.LazyAttribute(lambda u: f"{u.username}@example.org")
    password = factory.django.Password("geheim123")


class CategoryFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Category

    name = factory.Sequence(lambda n: f"Kategorie {n}")


class LocationFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Location

    name = factory.Sequence(lambda n: f"Ort {n}")


class ItemFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Item

    name = factory.Sequence(lambda n: f"Gerät {n}")
    category = factory.SubFactory(CategoryFactory)
    location = factory.SubFactory(LocationFactory)
    responsible = factory.SubFactory(UserFactory)
