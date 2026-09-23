from django.db import migrations

INITIAL_CATEGORIES = ["Sensoren", "Aktoren", "Werkzeuge", "Sonstiges"]


def create_categories(apps, schema_editor):
    Category = apps.get_model("inventory", "Category")
    for name in INITIAL_CATEGORIES:
        # Historische Modelle kennen das eigene save() nicht, deshalb `path` direkt setzen.
        Category.objects.get_or_create(path=name, defaults={"name": name})


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]

    operations = [migrations.RunPython(create_categories, migrations.RunPython.noop)]
