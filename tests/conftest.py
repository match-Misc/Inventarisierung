import pytest

from .factories import UserFactory


@pytest.fixture(autouse=True)
def _test_settings(settings, tmp_path):
    # Tests laufen mit DEBUG=False: kein Manifest (collectstatic) nötig, kein HTTPS-Redirect
    settings.STORAGES = {
        **settings.STORAGES,
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
    settings.SECURE_SSL_REDIRECT = False
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def user(db):
    return UserFactory()


@pytest.fixture
def staff(db):
    return UserFactory(is_staff=True)
