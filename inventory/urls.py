from django.urls import path

from . import views

app_name = "inventory"

urlpatterns = [
    path("<int:pk>/", views.item_detail, name="item_detail"),
]
