from django.contrib import admin

from .models import PurchaseOrder


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "company",
        "price",
        "tool_type",
        "purchase_date",
        "project",
        "manually_verified",
        "is_missing",
    )
    list_editable = ("manually_verified",)
    list_filter = ("tool_type", "project", "manually_verified", "is_missing")
    search_fields = ("name", "company", "project", "source_folder")
    date_hierarchy = "purchase_date"
    readonly_fields = ("source_folder", "created_at", "last_synced", "is_missing")
