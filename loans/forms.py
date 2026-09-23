from datetime import timedelta

from django import forms
from django.conf import settings
from django.utils import timezone

from inventory.models import Item

from .models import Booking


class AvailabilitySelect(forms.Select):
    """Zeigt alle Geräte, deaktiviert aber die, die gerade nicht verfügbar sind (mit Hinweis im Label)."""

    def __init__(self, *args, unavailable=None, **kwargs):
        self.unavailable = unavailable or {}
        super().__init__(*args, **kwargs)

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex, attrs)
        reason = self.unavailable.get(str(value))
        if reason:
            option["attrs"]["disabled"] = True
            option["label"] = f"{label} – nicht verfügbar ({reason})"
        return option


class BookingForm(forms.ModelForm):
    """Formular fürs Buchungs-Modal im Kalender. Die Statuslogik liegt in loans.services."""

    class Meta:
        model = Booking
        fields = ["item", "start_date", "end_date", "purpose", "usage_location", "request_message"]
        widgets = {
            "start_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "end_date": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "request_message": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, initial_item=None, **kwargs):
        super().__init__(*args, **kwargs)
        items = Item.objects.exclude(condition=Item.Condition.RETIRED).order_by("name")
        unavailable = {
            str(item.pk): item.get_condition_display() for item in items if item.condition != Item.Condition.OK
        }
        self.fields["item"] = forms.ModelChoiceField(
            queryset=items,
            label="Gerät",
            empty_label="Bitte Gerät wählen",
            widget=AvailabilitySelect(unavailable=unavailable),
        )
        self.fields["start_date"].label = "Von"
        self.fields["end_date"].label = "Bis (voraussichtliche Rückgabe)"
        self.fields["request_message"].label = "Nachricht an Verantwortliche/n"
        today = timezone.localdate()
        if not self.initial.get("start_date"):
            self.initial["start_date"] = today
        if not self.initial.get("end_date"):
            self.initial["end_date"] = today + timedelta(days=settings.DEFAULT_LOAN_DAYS)
        if initial_item is not None:
            self.initial["item"] = initial_item.pk

    def clean_item(self):
        item = self.cleaned_data["item"]
        if item.condition != Item.Condition.OK:
            raise forms.ValidationError(f"„{item}“ ist derzeit nicht verfügbar ({item.get_condition_display()}).")
        return item

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError("Das Enddatum darf nicht vor dem Startdatum liegen.")
        return cleaned
