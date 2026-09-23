from django.conf import settings
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = f"{settings.SITE_NAME} – Verwaltung"
admin.site.site_title = settings.SITE_NAME
admin.site.index_title = "Verwaltung"

urlpatterns = [
    path("konto/", include("accounts.urls")),
    path("konto/", include("django.contrib.auth.urls")),
    path("bestellungen/", include("procurement.urls")),
    path("admin/", admin.site.urls),
]
