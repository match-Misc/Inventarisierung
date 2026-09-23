from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("profil/", views.profile, name="profile"),
    path("benachrichtigungen/", views.notification_settings, name="notifications"),
    path("benachrichtigungen/testmail/", views.send_test_mail, name="test_mail"),
]
