from django.urls import path

from . import views

app_name = "inventory"

# Eingebunden unter /geraete/
urlpatterns = [
    path("", views.item_list, name="item_list"),
    path("<int:pk>/", views.item_detail, name="item_detail"),
]
