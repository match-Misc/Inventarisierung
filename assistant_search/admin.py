from django.contrib import admin

from .models import ItemSpecification, SpecificationProposal


@admin.register(ItemSpecification)
class ItemSpecificationAdmin(admin.ModelAdmin):
    list_display = ("item", "property_name", "value_text", "source_kind", "verified_by")
    list_filter = ("property_name", "source_kind")
    search_fields = ("item__name", "property_name", "value_text")
    readonly_fields = ("verified_by", "verified_at")

    def save_model(self, request, obj, form, change):
        if not change:
            obj.verified_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(SpecificationProposal)
class SpecificationProposalAdmin(admin.ModelAdmin):
    list_display = ("item", "property_name", "value_text", "status", "source_kind")
    list_filter = ("status", "source_kind")
    search_fields = ("item__name", "property_name", "value_text")
    readonly_fields = ("reviewed_by", "reviewed_at")

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
