from django.urls import path

from . import views

app_name = "loans"

urlpatterns = [
    path("", views.booking_list, name="list"),
    path("anfragen/", views.pending_requests, name="pending"),
    path("neu/<int:item_id>/", views.booking_create, name="create"),
    path("<int:pk>/", views.booking_detail, name="detail"),
    path("<int:pk>/<str:action>/", views.booking_action, name="action"),
]
