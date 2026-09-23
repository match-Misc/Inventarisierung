"""Kurzlebige, nur für den jeweiligen Nutzer abrufbare Erkennungsfotos."""

import time
import uuid
from pathlib import Path

from django.conf import settings

DRAFT_LIFETIME = 24 * 60 * 60


def draft_directory():
    directory = Path(settings.MEDIA_ROOT) / ".recognition-drafts"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def clear_old_drafts():
    cutoff = time.time() - DRAFT_LIFETIME
    for path in draft_directory().glob("*.jpg"):
        if path.stat().st_mtime < cutoff:
            path.unlink(missing_ok=True)


def create_draft(photo_bytes):
    token = uuid.uuid4().hex
    if photo_bytes:
        (draft_directory() / f"{token}.jpg").write_bytes(photo_bytes)
    return token


def draft_photo(token):
    if len(token) != 32 or any(ch not in "0123456789abcdef" for ch in token):
        return None
    path = draft_directory() / f"{token}.jpg"
    return path if path.is_file() else None


def delete_draft(token):
    path = draft_photo(token)
    if path:
        path.unlink(missing_ok=True)
