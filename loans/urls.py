from django.urls import path

from . import views

app_name = "loans"

urlpatterns = [
    path("", views.calendar_page, name="calendar"),
    path("events/", views.calendar_events, name="calendar_events"),
    path("buchen/", views.booking_create, name="booking_create"),
    path("buchung/<int:pk>/", views.booking_detail, name="booking_detail"),
]
