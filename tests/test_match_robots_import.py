from django.core.management import call_command
from PIL import Image

from accounts.models import User
from assistant_search.models import ItemSpecification, SpecificationProposal
from inventory.models import Category, Item, Location
from procurement.models import PurchaseOrder


def test_match_robot_import_preserves_origin_and_is_repeatable(db, tmp_path, client):
    tobias = User.objects.create_user(username="tobias")
    original_creator = User.objects.create_user(username="importer")
    category, _ = Category.objects.get_or_create(name="Roboter", parent=None)
    location, _ = Location.objects.get_or_create(name="Noch nicht zugeordnet", parent=None)
    item = Item.objects.create(
        name="Stäubli TX200",
        category=category,
        location=location,
        responsible=original_creator,
        created_by=original_creator,
        model_number="TX200",
        description="Eigene Notiz zum Gerät.",
        condition=Item.Condition.UNVERIFIED,
    )
    order = PurchaseOrder.objects.create(
        name="Stäubli_TX200",
        source_folder="2014/2014-07_Stäubli_TX200",
        inventory_item=item,
        research_data={"model_number": "TX2-200"},
    )
    wrong_proposal = SpecificationProposal.objects.create(
        item=item,
        property_name="Traglast",
        value_text="170 kg",
        unit="kg",
        source_url="https://www.staubli.com/global/en/robotics/products/industrial-robots/6-axis/tx2-200.html",
        source_kind="manufacturer",
    )
    photo_dir = tmp_path / "photos"
    photo_dir.mkdir()
    Image.new("RGB", (8, 8), "white").save(photo_dir / "abb.jpg")

    call_command("import_match_robots", photo_dir=photo_dir)
    call_command("import_match_robots", photo_dir=photo_dir)

    item.refresh_from_db()
    assert item.created_by == original_creator
    assert item.responsible == tobias
    assert item.model_number == "TX200"
    assert "Eigene Notiz" in item.description
    assert "TX2-200" in item.description
    assert item.specification_proposals.count() == 4
    wrong_proposal.refresh_from_db()
    assert wrong_proposal.status == SpecificationProposal.Status.REJECTED
    order.refresh_from_db()
    assert order.research_data["model_number"] == "TX200"
    assert ItemSpecification.objects.filter(item=item).count() == 0
    assert Item.objects.filter(name="ABB FlexPicker IRB 360").count() == 1
    abb = Item.objects.get(name="ABB FlexPicker IRB 360")
    assert abb.created_by == tobias
    assert abb.condition == Item.Condition.UNVERIFIED
    assert abb.photos.count() == 1
    assert SpecificationProposal.objects.filter(item=abb).count() == 2
    client.force_login(tobias)
    response = client.get(abb.get_absolute_url())
    assert response.status_code == 200
    assert abb.photos.first().thumb_url in response.content.decode()
