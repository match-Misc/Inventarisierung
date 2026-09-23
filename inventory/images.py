"""Verarbeitung hochgeladener Fotos: Drehung korrigieren, verkleinern, Vorschaubild erzeugen.

Alle Fotos werden als JPEG neu gespeichert. Dabei gehen auch EXIF-Metadaten wie GPS-Koordinaten verloren.
"""

from io import BytesIO

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

from .models import ItemDocument, ItemPhoto

MAX_EDGE = 2560
THUMB_EDGE = 480


def _to_rgb(img):
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.getchannel("A"))
        return background
    return img.convert("RGB")


def _encode(img, quality):
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=quality, optimize=True)
    return ContentFile(buffer.getvalue())


def process_photo(uploaded_file):
    """Gibt (Foto, Vorschaubild) als JPEG-Dateien zurück."""
    uploaded_file.seek(0)
    with Image.open(uploaded_file) as original:
        img = _to_rgb(ImageOps.exif_transpose(original))
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    thumb = img.copy()
    thumb.thumbnail((THUMB_EDGE, THUMB_EDGE))
    return _encode(img, 85), _encode(thumb, 80)


def add_photo(item, uploaded_file, user):
    image, thumbnail = process_photo(uploaded_file)
    photo = ItemPhoto(item=item, uploaded_by=user, is_primary=not item.photos.exists())
    photo.image.save("foto.jpg", image, save=False)
    photo.thumbnail.save("vorschau.jpg", thumbnail, save=False)
    photo.save()
    return photo


def copy_files(source, target, user):
    """Kopiert Fotos und Dokumente (z. B. beim Duplizieren baugleicher Geräte)."""
    for photo in source.photos.all():
        copy = ItemPhoto(item=target, caption=photo.caption, is_primary=photo.is_primary, uploaded_by=user)
        with photo.image.open("rb") as f:
            copy.image.save("foto.jpg", f, save=False)
        if photo.thumbnail:
            with photo.thumbnail.open("rb") as f:
                copy.thumbnail.save("vorschau.jpg", f, save=False)
        copy.save()
    for document in source.documents.all():
        copy = ItemDocument(
            item=target, title=document.title, doc_type=document.doc_type, url=document.url, uploaded_by=user
        )
        if document.file:
            with document.file.open("rb") as f:
                copy.file.save(document.filename, f, save=False)
        copy.save()
