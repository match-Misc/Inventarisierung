import django_filters

from .models import PurchaseOrder


class PurchaseOrderFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_search", label="Suche")
    linked = django_filters.BooleanFilter(method="filter_linked", label="Als Gerät angelegt")

    class Meta:
        model = PurchaseOrder
        fields = ["tool_type", "project", "research_status"]

    def filter_search(self, queryset, name, value):
        from django.db.models import Q

        return queryset.filter(
            Q(name__icontains=value) | Q(company__icontains=value) | Q(project__icontains=value)
        )

    def filter_linked(self, queryset, name, value):
        return queryset.filter(inventory_item__isnull=not value)
