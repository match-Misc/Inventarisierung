"""Gemeinsame Testkonfiguration. Tests laufen mit DEBUG=False (siehe AGENTS.md)."""

import pytest


@pytest.fixture(autouse=True)
def _test_settings(settings):
    # Ohne Manifest-Storage braucht es kein collectstatic vor den Tests.
    settings.STORAGES["staticfiles"]["BACKEND"] = "django.contrib.staticfiles.storage.StaticFilesStorage"
    settings.SECURE_SSL_REDIRECT = False
