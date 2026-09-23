from django.contrib import messages
from django.shortcuts import redirect, render

from .forms import ProfileForm


def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profil gespeichert.")
        return redirect("accounts:profile")
    return render(request, "accounts/profile.html", {"form": form})
