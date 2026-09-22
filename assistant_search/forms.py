from django import forms

from .models import SpecificationProposal
from .units import unit_matches_property


class ProposalReviewForm(forms.ModelForm):
    source_url = forms.URLField(label="Quellenlink", max_length=500, assume_scheme="https")

    class Meta:
        model = SpecificationProposal
        fields = (
            "property_name",
            "value_text",
            "min_value",
            "max_value",
            "unit",
            "source_url",
            "source_title",
            "source_kind",
        )

    def clean(self):
        data = super().clean()
        if (
            data.get("min_value") is not None
            and data.get("max_value") is not None
            and data["min_value"] > data["max_value"]
        ):
            self.add_error("max_value", "Das Maximum darf nicht kleiner als das Minimum sein.")
        if (data.get("min_value") is not None or data.get("max_value") is not None) and not data.get("unit"):
            self.add_error("unit", "Für Zahlenwerte ist eine Einheit erforderlich.")
        if data.get("unit") and not unit_matches_property(data.get("property_name"), data["unit"]):
            self.add_error("unit", "Die Einheit passt nicht zur angegebenen Messgröße.")
        return data
