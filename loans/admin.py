from django.contrib import admin

from .models import Booking, ReminderLog


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    """Nur lesen: Buchungsänderungen laufen über loans.services und die Webansichten."""

    list_display = ("item", "borrower", "start_date", "end_date", "status")
    list_filter = ("status",)
    search_fields = ("item__name", "borrower__username", "borrower__last_name")
    date_hierarchy = "start_date"
    autocomplete_fields = ("item", "borrower")
    list_select_related = ("item", "borrower")

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReminderLog)
class ReminderLogAdmin(admin.ModelAdmin):
    list_display = ("booking", "kind", "sent_on")
    list_filter = ("kind",)
