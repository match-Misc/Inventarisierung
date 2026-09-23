import django_filters

from .models import PurchaseOrder


class PurchaseOrderFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="filter_search", label="Suche")

    class Meta:
        model = PurchaseOrder
        fields = ["tool_type", "project"]

    def filter_search(self, queryset, name, value):
        from django.db.models import Q

        return queryset.filter(
            Q(name__icontains=value) | Q(company__icontains=value) | Q(project__icontains=value)
        )
