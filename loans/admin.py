from django.contrib import admin

from .models import Booking, ReminderLog


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    """Achtung: Änderungen hier umgehen die Konfliktprüfung aus loans.services."""

    list_display = ("item", "borrower", "start_date", "end_date", "status")
    list_filter = ("status",)
    search_fields = ("item__name", "borrower__username", "borrower__last_name")
    date_hierarchy = "start_date"
    autocomplete_fields = ("item", "borrower")
    list_select_related = ("item", "borrower")


@admin.register(ReminderLog)
class ReminderLogAdmin(admin.ModelAdmin):
    list_display = ("booking", "kind", "sent_on")
    list_filter = ("kind",)
