from django.contrib import admin

from .models import FloorPlan, PlanElement


class PlanElementInline(admin.TabularInline):
    model = PlanElement
    extra = 0
    fields = ("kind", "label", "x", "y", "width", "height", "location")
    readonly_fields = ("location",)


@admin.register(FloorPlan)
class FloorPlanAdmin(admin.ModelAdmin):
    """Objekte werden bequemer im grafischen Editor unter /hallenplan/ bearbeitet."""

    list_display = ("name", "location", "width", "height")
    inlines = [PlanElementInline]
