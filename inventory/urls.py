from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("geraete/", views.item_list, name="item_list"),
    path("geraete/<int:pk>/", views.item_detail, name="item_detail"),
]
