from django.conf import settings
from django.contrib import admin
from django.urls import include, path

from inventory.views import serve_media
from loans.views import dashboard

admin.site.site_header = f"{settings.SITE_NAME} – Verwaltung"
admin.site.site_title = settings.SITE_NAME
admin.site.index_title = "Verwaltung"

urlpatterns = [
    path("", dashboard, name="dashboard"),
    path("geraete/", include("inventory.urls")),
    path("", include("loans.urls")),
    path("hallenplan/", include("floorplan.urls")),
    path("assistent/", include("assistant_search.urls")),
    path("medien/<path:path>", serve_media, name="serve_media"),
    path("konto/", include("accounts.urls")),
    path("konto/", include("django.contrib.auth.urls")),
    path("bestellungen/", include("procurement.urls")),
    path("admin/", admin.site.urls),
]
