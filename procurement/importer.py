"""Reine Funktionen zum Einlesen der Bestellordner. Kein Datenbankzugriff, gut testbar.

Ordnerstruktur (siehe AGENTS.md-Vorgabe für den Ordner `01_Bestellungen`):
    <Basisordner>/<Jahr>/<YYYY-MM Name>/  -- Angebote, Rechnungen, Datenblätter, ...

`scan_base_dir()` liefert für jeden erkannten Bestellordner einen `PurchaseOrderData`.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover - pypdf ist eine Pflichtabhängigkeit, Fallback nur zur Sicherheit
    PdfReader = None

# Ordner-/Dateinamen, die nie ein Bestellordner bzw. eine relevante Datei sind.
IGNORED_FILE_PATTERNS = (".lnk", ".tmp", ".kdbx")
IGNORED_FILENAMES = {"thumbs.db"}
IGNORED_FILE_PREFIXES = ("~$",)

# "2025-07 SPP 2433 Drohne" -> Jahr 2025, Monat 07, Name "SPP 2433 Drohne"
FOLDER_NAME_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})[ _-]+(?P<name>.+)$")

# Projekt-Kennungen, die häufig in Bestellordnern auftauchen (SPP-Nummern, DFG-Kennzeichen, ...)
PROJECT_PATTERNS = (
    re.compile(r"\bSPP\s?\d{3,4}\b", re.IGNORECASE),
    re.compile(r"\bDFG\b[\w -]*", re.IGNORECASE),
)

# Schlüsselwörter für eine grobe Zuordnung des Gerätetyps (siehe PurchaseOrder.ToolType)
TOOL_TYPE_KEYWORDS = {
    "it": ("laptop", "pc", "computer", "iphone", "drucker", "monitor", "tablet"),
    "furniture": ("tisch", "schrank", "regal", "stuhl", "möbel"),
    "tool": ("werkzeug", "bohrer", "sla-drucker", "3d-drucker"),
    "sensor": ("sensor", "kamera", "kamerasystem", "messgerät"),
    "actuator": ("aktor", "motor", "antrieb", "netzteil"),
}

COMPANY_FILE_RE = re.compile(r"^(?:angebot|offer|quote)[_ -]+(?P<company>.+?)(?:[_ -]\d+)?$", re.IGNORECASE)
INVOICE_FILE_KEYWORDS = ("invoice", "rechnung", "re-", "re_")
DATASHEET_KEYWORDS = ("datenblatt", "datasheet", "spec", "manual", "handbuch")

# Grobe Preis-Erkennung in Rechnungstexten: "1.234,56 €", "1234.56 EUR", "Gesamtbetrag: 999,00"
PRICE_RE = re.compile(
    r"(?:gesamt(?:betrag|summe)?|summe|total|endbetrag)\D{0,15}?"
    r"(?P<amount>\d{1,3}(?:[.,]\d{3})*[.,]\d{2})",
    re.IGNORECASE,
)
FALLBACK_PRICE_RE = re.compile(r"(?P<amount>\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*(?:€|eur)", re.IGNORECASE)


@dataclass
class PurchaseOrderData:
    """Ergebnis der Ordnerauswertung für einen einzelnen Bestellordner."""

    source_folder: str
    name: str
    purchase_date: date | None
    project: str = ""
    company: str = ""
    price: str | None = None
    tool_type: str = ""
    key_specs: str = ""
    datasheet_path: str = ""
    files: list[str] = field(default_factory=list)


def _is_ignored(filename: str) -> bool:
    lower = filename.lower()
    if lower in IGNORED_FILENAMES:
        return True
    if any(lower.startswith(p) for p in IGNORED_FILE_PREFIXES):
        return True
    return any(lower.endswith(p) for p in IGNORED_FILE_PATTERNS)


def parse_folder_name(folder_name: str) -> tuple[date | None, str]:
    """Leitet Kaufdatum (Tag 1) und Gerätename aus einem Ordnernamen ab, z. B. "2025-07 SPP 2433 Drohne"."""
    match = FOLDER_NAME_RE.match(folder_name.strip())
    if not match:
        return None, folder_name.strip()
    year, month, name = int(match["year"]), int(match["month"]), match["name"].strip()
    try:
        return date(year, month, 1), name
    except ValueError:
        return None, name


def detect_project(text: str) -> str:
    """Sucht bekannte Projekt-Kennungen (SPP-Nummern, DFG, ...) in einem Text."""
    for pattern in PROJECT_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(0).strip()
    return ""


def guess_tool_type(name: str) -> str:
    """Ordnet über Schlüsselwörter im Namen grob einen Gerätetyp zu."""
    lower = name.lower()
    for tool_type, keywords in TOOL_TYPE_KEYWORDS.items():
        if any(keyword in lower for keyword in keywords):
            return tool_type
    return ""


def guess_company_from_filename(filename: str) -> str:
    """Erkennt Firmennamen aus Dateinamen wie "Angebot_FlyingMachines.pdf"."""
    stem = Path(filename).stem
    match = COMPANY_FILE_RE.match(stem)
    if not match:
        return ""
    return match["company"].replace("_", " ").strip()


def guess_datasheet(files: list[str]) -> str:
    """Wählt die wahrscheinlichste Datenblatt-/Spezifikationsdatei aus der Dateiliste."""
    for filename in files:
        lower = filename.lower()
        if any(keyword in lower for keyword in DATASHEET_KEYWORDS) and lower.endswith(".pdf"):
            return filename
    # Fallback: irgendein Angebot, das oft Spezifikationen enthält
    for filename in files:
        if filename.lower().startswith("angebot") and filename.lower().endswith(".pdf"):
            return filename
    return ""


def extract_price_from_pdf_text(text: str) -> str | None:
    """Sucht einen Gesamtbetrag im extrahierten PDF-Text. Gibt einen String mit Punkt als Dezimaltrenner zurück."""
    match = PRICE_RE.search(text) or FALLBACK_PRICE_RE.search(text)
    if not match:
        return None
    amount = match["amount"]
    # Deutsches Format "1.234,56" -> "1234.56"; englisches Format "1234.56" bleibt unverändert.
    if "," in amount:
        amount = amount.replace(".", "").replace(",", ".")
    return amount


def read_pdf_text(path: Path) -> str:
    """Extrahiert Text aus einer PDF-Datei. Gibt bei Fehlern (z. B. gescannte Dokumente) einen leeren String zurück."""
    if PdfReader is None:
        return ""
    try:
        reader = PdfReader(str(path))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except Exception:  # noqa: BLE001 - defekte/gescannte PDFs sollen den Sync nicht abbrechen
        return ""


def scan_order_folder(folder: Path) -> PurchaseOrderData:
    """Liest einen einzelnen Bestellordner (z. B. "2025-07 SPP 2433 Drohne") aus."""
    purchase_date, name = parse_folder_name(folder.name)
    files = sorted(f.name for f in folder.iterdir() if f.is_file() and not _is_ignored(f.name))

    project = detect_project(folder.name)
    company = ""
    price = None

    for filename in files:
        if not company:
            company = guess_company_from_filename(filename)
        lower = filename.lower()
        if price is None and (any(k in lower for k in INVOICE_FILE_KEYWORDS) or lower.startswith("angebot")):
            price_candidate = extract_price_from_pdf_text(read_pdf_text(folder / filename))
            if price_candidate:
                price = price_candidate

    datasheet = guess_datasheet(files)
    key_specs = f"Datenblatt: {datasheet}" if datasheet else ""

    return PurchaseOrderData(
        source_folder=folder.name,
        name=name,
        purchase_date=purchase_date,
        project=project,
        company=company,
        price=price,
        tool_type=guess_tool_type(name),
        key_specs=key_specs,
        datasheet_path=datasheet,
        files=files,
    )


def scan_base_dir(base_dir: Path) -> list[PurchaseOrderData]:
    """Durchläuft `<base_dir>/<Jahr>/<Bestellordner>` und liefert alle erkannten Bestellungen."""
    results: list[PurchaseOrderData] = []
    if not base_dir.exists():
        return results

    for year_dir in sorted(base_dir.iterdir()):
        if not year_dir.is_dir() or not re.fullmatch(r"\d{4}", year_dir.name):
            continue
        for order_dir in sorted(year_dir.iterdir()):
            if not order_dir.is_dir():
                continue
            data = scan_order_folder(order_dir)
            data.source_folder = f"{year_dir.name}/{order_dir.name}"
            results.append(data)
    return results
