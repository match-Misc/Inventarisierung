from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError

# Dateitypen, die ein Browser als aktive Inhalte ausführen könnte
BLOCKED_DOCUMENT_EXTENSIONS = {".html", ".htm", ".xhtml", ".shtml", ".svg", ".svgz", ".js", ".mjs"}


def _check_size(file, limit_mb):
    if file.size > limit_mb * 1024 * 1024:
        raise ValidationError(f"Die Datei ist zu groß (maximal {limit_mb} MB).")


def validate_photo_size(file):
    _check_size(file, settings.MAX_PHOTO_UPLOAD_MB)


def validate_document_file(file):
    _check_size(file, settings.MAX_DOCUMENT_UPLOAD_MB)
    if Path(file.name).suffix.lower() in BLOCKED_DOCUMENT_EXTENSIONS:
        raise ValidationError(
            "Dieser Dateityp ist aus Sicherheitsgründen nicht erlaubt (HTML, SVG, JavaScript)."
        )
