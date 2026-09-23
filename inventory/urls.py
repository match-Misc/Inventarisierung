from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("hinzufuegen/", views.identify_item, name="identify"),
    path("hinzufuegen/speichern/", views.save_identified_item, name="identify_save"),
    path("hinzufuegen/foto/<str:token>/", views.identified_photo, name="identified_photo"),
    path("<int:pk>/", views.item_detail, name="item_detail"),
]
