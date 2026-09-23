from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.utils import timezone

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
