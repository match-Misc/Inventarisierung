from django.urls import path

from . import views

app_name = "floorplan"

urlpatterns = [
    path("", views.plan_list, name="list"),
    path("<int:pk>/", views.plan_detail, name="detail"),
    path("<int:pk>/bearbeiten/", views.plan_detail, {"edit": True}, name="edit"),
    path("<int:pk>/speichern/", views.plan_save, name="save"),
    path("<int:pk>/suche/", views.item_search, name="search"),
    path("objekt/<int:pk>/", views.element_panel, name="element"),
]
