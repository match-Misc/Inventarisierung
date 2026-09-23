"""Tests für den Bestellungen-Import (procurement.importer und der Sync-Command)."""

import json
from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command

from assistant_search.models import SpecificationProposal
from inventory.models import Item
from procurement.importer import (
    detect_project,
    extract_price_from_pdf_text,
    guess_company_from_filename,
    guess_datasheet,
    guess_tool_type,
    parse_folder_name,
    scan_base_dir,
    scan_order_folder,
)
from procurement.models import PurchaseOrder
from procurement.research import _allowed_product_source, research_device


class TestParseFolderName:
    def test_valid_name(self):
        purchase_date, name = parse_folder_name("2025-07 SPP 2433 Drohne")
        assert purchase_date == date(2025, 7, 1)
        assert name == "SPP 2433 Drohne"

    def test_underscore_separator(self):
        purchase_date, name = parse_folder_name("2025-04_Labortische_und_Schränke")
        assert purchase_date == date(2025, 4, 1)
        assert name == "Labortische_und_Schränke"

    def test_invalid_name_has_no_date(self):
        purchase_date, name = parse_folder_name("Sonstiges ohne Datum")
        assert purchase_date is None
        assert name == "Sonstiges ohne Datum"

    def test_invalid_month_has_no_date(self):
        purchase_date, name = parse_folder_name("2025-13 Kaputtes Datum")
        assert purchase_date is None


class TestDetectProject:
    def test_spp_number(self):
        assert detect_project("2025-08 SPP 2100 Kamerasystem") == "SPP 2100"

    def test_dfg(self):
        assert "DFG" in detect_project("2024-01 DFG Gerät")

    def test_no_project(self):
        assert detect_project("2025-02 Laptop Peters") == ""


class TestGuessToolType:
    def test_it_keyword(self):
        assert guess_tool_type("Laptop Peters") == "it"

    def test_furniture_keyword(self):
        assert guess_tool_type("Labortische und Schränke") == "furniture"

    def test_no_match(self):
        assert guess_tool_type("Unbekanntes Gerät XY") == ""


class TestGuessCompanyFromFilename:
    def test_simple_offer(self):
        assert guess_company_from_filename("Angebot_FlyingMachines.pdf") == "FlyingMachines"

    def test_offer_with_trailing_number(self):
        assert guess_company_from_filename("Angebot_Premium_Modellbau_1.pdf") == "Premium Modellbau"

    def test_non_offer_file(self):
        assert guess_company_from_filename("Invoice RE-2025-13126.pdf") == ""


class TestGuessDatasheet:
    def test_prefers_datasheet_keyword(self):
        files = ["Angebot_X.pdf", "Datenblatt_Sensor.pdf", "Invoice.pdf"]
        assert guess_datasheet(files) == "Datenblatt_Sensor.pdf"

    def test_falls_back_to_angebot(self):
        files = ["Angebot_X.pdf", "Invoice.pdf"]
        assert guess_datasheet(files) == "Angebot_X.pdf"

    def test_no_candidate(self):
        assert guess_datasheet(["Invoice.pdf", "Vertrag.docx"]) == ""


class TestExtractPriceFromPdfText:
    def test_german_format_with_keyword(self):
        text = "Position 1\nGesamtbetrag: 1.234,56 €\nDanke"
        assert extract_price_from_pdf_text(text) == "1234.56"

    def test_fallback_without_keyword(self):
        text = "Zwischensumme 999,00 € inkl. MwSt."
        assert extract_price_from_pdf_text(text) == "999.00"

    def test_no_price_found(self):
        assert extract_price_from_pdf_text("Kein Betrag hier.") is None


@pytest.fixture
def order_folder(tmp_path):
    """Legt einen minimalen Bestellordner ohne echte PDFs an (Textextraktion liefert dann nichts)."""
    year_dir = tmp_path / "2025"
    order_dir = year_dir / "2025-07 SPP 2433 Drohne"
    order_dir.mkdir(parents=True)
    (order_dir / "Angebot_FlyingMachines.pdf").write_text("kein echtes PDF")
    (order_dir / "Thumbs.db").write_text("ignorieren")
    (order_dir / "~$Sachkonten.xlsx").write_text("ignorieren")
    return tmp_path, order_dir


class TestScanOrderFolder:
    def test_scans_files_and_ignores_junk(self, order_folder):
        _, order_dir = order_folder
        data = scan_order_folder(order_dir)
        assert data.name == "SPP 2433 Drohne"
        assert data.purchase_date == date(2025, 7, 1)
        assert data.project == "SPP 2433"
        assert data.company == "FlyingMachines"
        assert "Thumbs.db" not in data.files
        assert "~$Sachkonten.xlsx" not in data.files
        assert "Angebot_FlyingMachines.pdf" in data.files


class TestScanBaseDir:
    def test_finds_orders_under_year_folders(self, order_folder):
        base_dir, _ = order_folder
        results = scan_base_dir(base_dir)
        assert len(results) == 1
        assert results[0].source_folder == "2025/2025-07 SPP 2433 Drohne"

    def test_missing_base_dir_returns_empty(self, tmp_path):
        assert scan_base_dir(tmp_path / "nicht_vorhanden") == []

    def test_ignores_non_year_folders(self, tmp_path):
        (tmp_path / "Vorlagen").mkdir()
        assert scan_base_dir(tmp_path) == []


@pytest.mark.django_db
class TestSyncBestellungenCommand:
    def test_creates_new_order(self, order_folder, capsys):
        base_dir, _ = order_folder
        call_command("sync_bestellungen", base_dir=str(base_dir))

        order = PurchaseOrder.objects.get(source_folder="2025/2025-07 SPP 2433 Drohne")
        assert order.name == "SPP 2433 Drohne"
        assert order.purchase_date == date(2025, 7, 1)
        assert order.manually_verified is False
        assert order.is_missing is False

    def test_does_not_overwrite_manually_verified_orders(self, order_folder):
        base_dir, _ = order_folder
        PurchaseOrder.objects.create(
            source_folder="2025/2025-07 SPP 2433 Drohne",
            name="Von Hand korrigiert",
            manually_verified=True,
        )

        call_command("sync_bestellungen", base_dir=str(base_dir))

        order = PurchaseOrder.objects.get(source_folder="2025/2025-07 SPP 2433 Drohne")
        assert order.name == "Von Hand korrigiert"
        assert order.last_synced is not None

    def test_marks_disappeared_orders_as_missing(self, tmp_path):
        PurchaseOrder.objects.create(source_folder="2020/2020-01 Altes Gerät", name="Altes Gerät")
        empty_base = tmp_path / "leer"
        empty_base.mkdir()

        call_command("sync_bestellungen", base_dir=str(empty_base))

        order = PurchaseOrder.objects.get(source_folder="2020/2020-01 Altes Gerät")
        assert order.is_missing is True

    def test_dry_run_does_not_write(self, order_folder):
        base_dir, _ = order_folder
        call_command("sync_bestellungen", base_dir=str(base_dir), dry_run=True)
        assert not PurchaseOrder.objects.exists()

    def test_price_decimal_conversion(self, tmp_path):
        year_dir = tmp_path / "2025"
        order_dir = year_dir / "2025-01 Testgerät"
        order_dir.mkdir(parents=True)
        (order_dir / "Invoice.pdf").write_bytes(b"%PDF-1.4 kein echtes PDF")

        call_command("sync_bestellungen", base_dir=str(tmp_path))

        order = PurchaseOrder.objects.get(source_folder="2025/2025-01 Testgerät")
        assert order.price is None or isinstance(order.price, Decimal)


@pytest.mark.django_db
class TestPurchaseOrderList:
    def test_requires_login(self, client):
        response = client.get("/bestellungen/")

        assert response.status_code == 302
        assert response.url.startswith("/konto/login/")

    def test_shows_orders_in_application_layout(self, client, user):
        PurchaseOrder.objects.create(
            source_folder="2025/2025-09 Kraftsensor",
            name="Kraftsensor 500 N",
            company="Beispiel Messtechnik",
            tool_type=PurchaseOrder.ToolType.SENSOR,
        )
        client.force_login(user)

        response = client.get("/bestellungen/")

        assert response.status_code == 200
        assert response.context["orders"].count() == 1
        assert b"Kraftsensor 500 N" in response.content
        assert b"navbar" in response.content


@pytest.mark.django_db
class TestImportPurchaseDevicesCommand:
    def test_creates_unverified_device_and_is_idempotent(self, staff, client):
        order = PurchaseOrder.objects.create(
            source_folder="2014/2014-07 CalPlus_Handmultimeter",
            name="CalPlus_Handmultimeter",
            tool_type=PurchaseOrder.ToolType.OTHER,
        )

        call_command("import_purchase_devices", responsible=staff.username)
        call_command("import_purchase_devices", responsible=staff.username)

        order.refresh_from_db()
        assert Item.objects.count() == 1
        assert order.inventory_item.condition == Item.Condition.UNVERIFIED
        assert order.inventory_item.location.path == "Noch nicht zugeordnet"
        assert order.inventory_item.responsible == staff
        assert order.inventory_item.category.path == "Mess- und Prüfgeräte"
        assert order.inventory_item.loan_policy == Item.LoanPolicy.APPROVAL

        client.force_login(staff)
        response = client.get(order.inventory_item.get_absolute_url())
        assert response.status_code == 200
        assert "Bestellinformationen" in response.content.decode()
        assert order.source_folder in response.content.decode()

    def test_research_creates_pending_sourced_specifications(self, staff, client, monkeypatch):
        order = PurchaseOrder.objects.create(
            source_folder="2026/2026-05 Beckhoff IPC C6043 ML BiBaZu",
            name="Beckhoff IPC C6043 ML BiBaZu",
            tool_type=PurchaseOrder.ToolType.IT,
        )
        monkeypatch.setattr(
            "procurement.management.commands.import_purchase_devices.research_device",
            lambda hint: {
                "model_match": True,
                "product_name": "C6043",
                "manufacturer": "Beckhoff",
                "model_number": "C6043",
                "category": "Industrie-PC",
                "summary": "Kompakter Industrie-PC.",
                "source_url": "https://example.org/c6043",
                "source_title": "C6043",
                "source_kind": "manufacturer",
                "uncertainty": "",
                "specifications": [{"property_name": "Versorgungsspannung", "value_text": "24 V DC"}],
            },
        )

        call_command("import_purchase_devices", responsible=staff.username, research=True)

        order.refresh_from_db()
        assert order.research_status == PurchaseOrder.ResearchStatus.RESEARCHED
        assert order.inventory_item.manufacturer == "Beckhoff"
        assert SpecificationProposal.objects.filter(
            item=order.inventory_item,
            status=SpecificationProposal.Status.PENDING,
            source_url="https://example.org/c6043",
        ).exists()
        client.force_login(staff)
        response = client.get(order.inventory_item.get_absolute_url())
        assert "Herstellerquelle" in response.content.decode()

    def test_missing_exact_type_is_marked_ambiguous_without_web_request(self, staff, monkeypatch):
        order = PurchaseOrder.objects.create(
            source_folder="2014/2014-07 CalPlus Handmultimeter",
            name="CalPlus_Handmultimeter",
        )
        called = False

        def unexpected_request(hint):
            nonlocal called
            called = True

        monkeypatch.setattr(
            "procurement.management.commands.import_purchase_devices.research_device",
            unexpected_request,
        )

        call_command("import_purchase_devices", responsible=staff.username, research=True)

        order.refresh_from_db()
        assert order.research_status == PurchaseOrder.ResearchStatus.AMBIGUOUS
        assert called is False


def test_device_research_structures_cited_web_evidence(monkeypatch):
    source_url = "https://manufacturer.example/products/c6043"
    calls = []

    def fake_request(messages, *, schema=None, web=False, model=None, max_tokens=550):
        calls.append({"schema": schema, "web": web})
        if web:
            return {
                "content": "Der C6043 ist ein Industrie-PC mit 24-V-Versorgung.",
                "annotations": [
                    {
                        "type": "url_citation",
                        "url_citation": {
                            "url": source_url,
                            "title": "C6043",
                            "content": "Versorgungsspannung 24 V DC",
                        },
                    }
                ],
            }
        return {
            "content": json.dumps(
                {
                    "model_match": True,
                    "product_name": "C6043",
                    "manufacturer": "Beckhoff",
                    "model_number": "C6043",
                    "category": "Industrie-PC",
                    "summary": "Kompakter Industrie-PC.",
                    "source_url": source_url,
                    "source_title": "C6043",
                    "source_kind": "manufacturer",
                    "uncertainty": "",
                    "specifications": [{"property_name": "Versorgungsspannung", "value_text": "24 V DC"}],
                }
            )
        }

    monkeypatch.setattr("procurement.research._request", fake_request)

    result = research_device("Beckhoff C6043 industrial PC")

    assert result["source_url"] == source_url
    assert result["specifications"][0]["value_text"] == "24 V DC"
    assert calls[0] == {"schema": None, "web": True}
    assert calls[1]["schema"] is not None
    assert calls[1]["web"] is False


def test_device_research_rejects_general_reference_sites():
    assert not _allowed_product_source("https://de.wikipedia.org/wiki/Beispiel")
    assert not _allowed_product_source("https://www.engineering.com/example")
    assert _allowed_product_source("https://www.beckhoff.com/products/c6043")
