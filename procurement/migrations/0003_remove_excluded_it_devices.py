from django.db import migrations

EXCLUDED_IT_DEVICE_NAMES = {
    "Alternate_Hiwi-Rechner",
    "Alternate_Mini-PC-MiR",
    "Alternate_Notebook-Klingeberg",
    "Alternate_Razer-Blade",
    "Amazon_Surface_Pro",
    "Apple_iPad-Pro-Raatz",
    "CSL_Studi-Rechner-MLL",
    "Computer-Versuchsfeld",
    "Cyberport_iPad-PM",
    "Dell_Server",
    "Dell_Notebook-Binnemann",
    "Dell_Notebook-Lurz",
    "Dell_Notebook-Terei",
    "Laptop Peters",
    "Notebook Ince",
    "Notebook Kleinschmidt",
    "Notebook Raatz",
    "Notebook Sourkounis",
    "Notebook Wendorff",
    "Notebook Westermann",
    "Notebook-Gerland",
    "Notebooksbilliger_Notebook-Annika",
    "Notebooksbilliger_Notebook-Ditzia",
    "Notebooksbilliger_Notebook-Lachmayer",
    "Notebooksbilliger_Notebook-Richard",
    "ROS-Simulations-PC",
    "Raatz Iphone",
    "Raatz Surface",
    "Raatz_Apple_Diensthandy-Annika",
    "Source-IT_ROS-PC",
    "VisaRaatz_Apple_IPadPro",
    "Workstation Tschöke",
    "iPhone SE",
}

IMPORTED_DESCRIPTION = (
    "Aus dem Bestellbestand übernommen. Technische Angaben, "
    "Ablageort und Verantwortlichkeit müssen geprüft werden."
)


def remove_general_computers(apps, schema_editor):
    Item = apps.get_model("inventory", "Item")
    PurchaseOrder = apps.get_model("procurement", "PurchaseOrder")

    orders = PurchaseOrder.objects.filter(
        name__in=EXCLUDED_IT_DEVICE_NAMES,
        inventory_item__isnull=False,
    )
    item_ids = set(orders.values_list("inventory_item_id", flat=True))
    orders.update(inventory_item=None)

    for item in Item.objects.filter(
        pk__in=item_ids,
        condition="unverified",
        description=IMPORTED_DESCRIPTION,
        location__path="Noch nicht zugeordnet",
    ):
        if not item.purchase_orders.exists() and not item.bookings.exists():
            item.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("loans", "0002_reminder_kinds"),
        ("procurement", "0002_purchaseorder_inventory_item_and_more"),
    ]

    operations = [
        migrations.RunPython(remove_general_computers, migrations.RunPython.noop),
    ]
