from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from inventory.views import dashboard, serve_media

admin.site.site_header = f"{settings.SITE_NAME} – Verwaltung"
admin.site.site_title = settings.SITE_NAME
admin.site.index_title = "Verwaltung"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("geraete/", include("inventory.urls")),
    path("ausleihen/", include("loans.urls")),
    path("assistent/", include("assistant_search.urls")),
    path("medien/<path:path>", serve_media, name="serve_media"),
    path("konto/", include("accounts.urls")),
    path("konto/", include("django.contrib.auth.urls")),
    path("admin/", admin.site.urls),
]
