from django.urls import path

from . import views

app_name = "procurement"

urlpatterns = [
    path("", views.purchase_order_list, name="list"),
]
