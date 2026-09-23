import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_brand_name_uses_site_setting_on_login_and_dashboard(client, people, settings):
    settings.SITE_NAME = "MATCH Labor"
    login = client.get(reverse("login"))
    assert login.status_code == 200
    assert "MATCH Labor" in login.content.decode()

    client.force_login(people[0])
    dashboard = client.get(reverse("dashboard"))
    assert dashboard.status_code == 200
    assert "MATCH Labor" in dashboard.content.decode()
