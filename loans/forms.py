from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

from inventory.models import Item

from .models import Booking
from .services import booking_mode


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        super().__init__(format="%Y-%m-%d", **kwargs)


class BookingForm(forms.Form):
    start_date = forms.DateField(label="Von", widget=DateInput())
    end_date = forms.DateField(
        label="Bis (voraussichtliche Rückgabe)",
        widget=DateInput(),
        help_text="Der letzte Tag gehört mit dazu.",
    )
    borrower = forms.ModelChoiceField(
        label="Ausleihe für",
        queryset=get_user_model().objects.filter(is_active=True),
        required=False,
        help_text="Nur für Verantwortliche: im Namen einer anderen Person buchen (z. B. bei Übergabe).",
    )
    purpose = forms.CharField(label="Zweck / Projekt", max_length=200, required=False)
    usage_location = forms.CharField(
        label="Einsatzort",
        max_length=200,
        required=False,
        help_text="Wo ist das Gerät während der Ausleihe? Hilft anderen beim Suchen.",
    )
    message = forms.CharField(
        label="Nachricht an die/den Verantwortliche/n",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    def __init__(self, *args, item, user, **kwargs):
        today = timezone.localdate()
        kwargs.setdefault("initial", {})
        kwargs["initial"].setdefault("start_date", today)
        kwargs["initial"].setdefault("end_date", today + timedelta(days=settings.DEFAULT_LOAN_DAYS))
        super().__init__(*args, **kwargs)
        self.mode = booking_mode(item, user)
        if not item.can_manage(user):
            del self.fields["borrower"]
        else:
            self.fields["borrower"].empty_label = f"mich selbst ({user.display_name})"
        if self.mode == "direct":
            del self.fields["message"]

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and start < timezone.localdate():
            self.add_error("start_date", "Der Zeitraum darf nicht in der Vergangenheit beginnen.")
        if start and end and end < start:
            self.add_error("end_date", "Das Enddatum darf nicht vor dem Startdatum liegen.")
        return cleaned

    def booking_kwargs(self):
        data = self.cleaned_data
        return {
            "start_date": data["start_date"],
            "end_date": data["end_date"],
            "borrower": data.get("borrower"),
            "purpose": data["purpose"],
            "usage_location": data["usage_location"],
            "message": data.get("message", ""),
        }


class ExtendForm(forms.Form):
    new_end_date = forms.DateField(label="Neues Enddatum", widget=DateInput())


class ReturnForm(forms.Form):
    note = forms.CharField(
        label="Hinweis zur Rückgabe (optional)",
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="z. B. „Netzteil fehlt“ oder „Kalibrierung prüfen“. Die/der Verantwortliche wird informiert.",
    )


# ---------- Buchungs-Modal im Kalender (Karina, #5) ----------


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


class CalendarBookingForm(forms.ModelForm):
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
            str(item.pk): item.get_condition_display()
            for item in items
            if item.condition != Item.Condition.OK
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
            raise forms.ValidationError(
                f"„{item}“ ist derzeit nicht verfügbar ({item.get_condition_display()})."
            )
        return item

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            raise forms.ValidationError("Das Enddatum darf nicht vor dem Startdatum liegen.")
        return cleaned
