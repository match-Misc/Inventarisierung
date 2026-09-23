from django.urls import path

from . import views

app_name = "loans"


def _action(slug, action):
    return path(f"ausleihen/<int:pk>/{slug}/", views.booking_action, {"action": action}, name=action)


# Eingebunden ohne Präfix. Die KI-Suche verlinkt auf /ausleihen/neu/<gerät>/.
urlpatterns = [
    path("ausleihen/neu/<int:pk>/", views.book_item, name="book"),
    path("ausleihen/<int:pk>/rueckgabe/", views.return_booking, name="return"),
    path("ausleihen/<int:pk>/verlaengern/", views.extend_booking, name="extend"),
    _action("genehmigen", "approve"),
    _action("ablehnen", "reject"),
    _action("stornieren", "cancel"),
    _action("entnehmen", "checkout"),
    _action("verlaengerung-genehmigen", "approve_extension"),
    _action("verlaengerung-ablehnen", "reject_extension"),
    # Buchungskalender
    path("kalender/", views.calendar_page, name="calendar"),
    path("kalender/events/", views.calendar_events, name="calendar_events"),
    path("kalender/buchen/", views.booking_create, name="booking_create"),
    path("kalender/buchung/<int:pk>/", views.booking_detail, name="booking_detail"),
]
