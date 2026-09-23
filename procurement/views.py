from django.shortcuts import render

from .filters import PurchaseOrderFilter
from .models import PurchaseOrder


def purchase_order_list(request):
    """Tabellarische Übersicht aller Bestellungen mit Suche und Filtern."""
    orders = PurchaseOrder.objects.all()
    order_filter = PurchaseOrderFilter(request.GET or None, queryset=orders)
    return render(
        request,
        "procurement/purchase_order_list.html",
        {"filter": order_filter, "orders": order_filter.qs},
    )
