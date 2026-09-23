from django.urls import path

from . import views

app_name = "loans"


def _action(slug, action):
    return path(f"buchungen/<int:pk>/{slug}/", views.booking_action, {"action": action}, name=action)


urlpatterns = [
    path("geraete/<int:pk>/buchen/", views.book_item, name="book"),
    path("buchungen/<int:pk>/rueckgabe/", views.return_booking, name="return"),
    path("buchungen/<int:pk>/verlaengern/", views.extend_booking, name="extend"),
    _action("genehmigen", "approve"),
    _action("ablehnen", "reject"),
    _action("stornieren", "cancel"),
    _action("entnehmen", "checkout"),
    _action("verlaengerung-genehmigen", "approve_extension"),
    _action("verlaengerung-ablehnen", "reject_extension"),
]
