from django.contrib import admin
from django.utils.html import format_html

from .models import Accessory, Category, Item, ItemDocument, ItemPhoto, Location


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("path",)
    search_fields = ("name",)
    fields = ("name", "parent")


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ("path", "description")
    search_fields = ("name", "description")
    fields = ("name", "parent", "description")


class AccessoryInline(admin.TabularInline):
    model = Accessory
    extra = 0


class DocumentInline(admin.TabularInline):
    model = ItemDocument
    extra = 0
    fields = ("title", "doc_type", "file", "url")


class PhotoInline(admin.TabularInline):
    """Fotos werden über die Detailseite hochgeladen (dort werden sie verkleinert)."""

    model = ItemPhoto
    extra = 0
    fields = ("preview", "caption", "is_primary")
    readonly_fields = ("preview",)

    def has_add_permission(self, request, obj=None):
        return False

    @admin.display(description="Vorschau")
    def preview(self, photo):
        return format_html('<img src="{}" style="height:60px">', photo.thumb_url)


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "location", "responsible", "loan_policy", "condition")
    list_filter = ("loan_policy", "condition", "category")
    search_fields = ("name", "manufacturer", "model_number", "serial_number", "inventory_number")
    autocomplete_fields = ("responsible",)
    list_select_related = ("category", "location", "responsible")
    inlines = [AccessoryInline, DocumentInline, PhotoInline]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
