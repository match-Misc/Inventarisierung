from django.urls import path

from . import views

app_name = "loans"


def _action(slug, action):
    return path(f"<int:pk>/{slug}/", views.booking_action, {"action": action}, name=action)


# Eingebunden unter /ausleihen/ (die KI-Suche verlinkt auf /ausleihen/neu/<gerät>/)
urlpatterns = [
    path("neu/<int:pk>/", views.book_item, name="book"),
    path("<int:pk>/rueckgabe/", views.return_booking, name="return"),
    path("<int:pk>/verlaengern/", views.extend_booking, name="extend"),
    _action("genehmigen", "approve"),
    _action("ablehnen", "reject"),
    _action("stornieren", "cancel"),
    _action("entnehmen", "checkout"),
    _action("verlaengerung-genehmigen", "approve_extension"),
    _action("verlaengerung-ablehnen", "reject_extension"),
]
