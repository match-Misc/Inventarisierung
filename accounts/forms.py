from django import forms

from .models import NotificationPreferences, User


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "room"]


class NotificationPreferencesForm(forms.ModelForm):
    class Meta:
        model = NotificationPreferences
        fields = [
            "enabled",
            "booking_updates",
            "start_reminder",
            "due_reminder",
            "overdue_interval",
            "item_available",
            "new_requests",
            "pending_digest",
            "owner_returns",
            "owner_activity",
            "owner_overdue",
        ]
