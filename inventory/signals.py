from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import ItemDocument, ItemPhoto


def _delete_files_on_commit(*files):
    """Löscht Dateien erst, wenn das Löschen in der Datenbank wirklich durchgeht."""
    targets = [(f.storage, f.name) for f in files if f]
    transaction.on_commit(lambda: [storage.delete(name) for storage, name in targets])


@receiver(post_delete, sender=ItemPhoto)
def delete_photo_files(sender, instance, **kwargs):
    _delete_files_on_commit(instance.image, instance.thumbnail)


@receiver(post_delete, sender=ItemDocument)
def delete_document_file(sender, instance, **kwargs):
    _delete_files_on_commit(instance.file)
