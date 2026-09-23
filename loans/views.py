from django.shortcuts import render


def dashboard(request):
    """Vorläufige Startseite. Die richtige Übersicht (meine Ausleihen, Anfragen …) folgt mit Schritt 3."""
    return render(request, "home.html")
