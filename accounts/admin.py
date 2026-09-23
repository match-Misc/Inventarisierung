from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .invitations import send_invitation
from .models import NotificationPreferences, User


class NotificationPreferencesInline(admin.StackedInline):
    model = NotificationPreferences
    can_delete = False
    verbose_name_plural = "Benachrichtigungen"


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "last_name", "first_name", "email", "is_active", "is_staff")
    fieldsets = (
        *BaseUserAdmin.fieldsets,
        ("Kontakt", {"fields": ("phone", "room")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "description": (
                    "Benutzername = Institutskennung. Tipp: „Passwortbasierte Anmeldung“ "
                    "deaktiviert lassen und danach die Aktion „Einladung senden“ nutzen – "
                    "dann setzt die Person ihr Passwort selbst."
                ),
                "fields": (
                    "username",
                    "first_name",
                    "last_name",
                    "email",
                    "usable_password",
                    "password1",
                    "password2",
                ),
            },
        ),
    )
    inlines = [NotificationPreferencesInline]
    actions = ["send_invitations"]

    @admin.action(description="Einladung senden (Link zum Passwort-Setzen)")
    def send_invitations(self, request, queryset):
        sent = [user for user in queryset if send_invitation(user)]
        if sent:
            self.message_user(request, f"{len(sent)} Einladung(en) verschickt.", messages.SUCCESS)
        failed = queryset.count() - len(sent)
        if failed:
            self.message_user(
                request,
                f"{failed} Einladung(en) nicht verschickt (keine E-Mail-Adresse oder Versandfehler).",
                messages.WARNING,
            )
