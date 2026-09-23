from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from loans import notifications

from .forms import NotificationPreferencesForm, ProfileForm


def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profil gespeichert.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form})


def notification_settings(request):
    form = NotificationPreferencesForm(request.POST or None, instance=request.user.notification_settings)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Benachrichtigungseinstellungen gespeichert.")
        return redirect("accounts:notifications")
    return render(request, "accounts/notifications.html", {"form": form})


@require_POST
def send_test_mail(request):
    if not request.user.email:
        messages.error(request, "In deinem Profil ist keine E-Mail-Adresse hinterlegt.")
    elif notifications.test_mail(request.user):
        messages.success(request, f"Testmail an {request.user.email} verschickt.")
    else:
        messages.error(
            request, "Die Testmail konnte nicht verschickt werden. Bitte die Administration informieren."
        )
    return redirect("accounts:notifications")
