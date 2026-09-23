from django import forms
from PIL import Image, UnidentifiedImageError

from .models import Item
from .validators import validate_photo_size


class RecognitionInputForm(forms.Form):
    DIFFICULTY_CHOICES = [
        ("easy", "Einfach – günstige Erkennung"),
        ("medium", "Mittel – stärkere Erkennung mit Webrecherche"),
        ("hard", "Schwierig – gründliche Erkennung mit Webrecherche"),
    ]
    name_hint = forms.CharField(
        label="Name oder Aufschrift",
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "z. B. Hersteller und Typ"}),
    )
    photo = forms.ImageField(
        label="Foto vom Gerät oder Typenschild",
        required=False,
        validators=[validate_photo_size],
        widget=forms.ClearableFileInput(
            attrs={"class": "form-control", "accept": "image/*", "capture": "environment"}
        ),
    )
    difficulty = forms.ChoiceField(
        label="Schwierigkeit",
        choices=DIFFICULTY_CHOICES,
        initial="easy",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("name_hint") and not cleaned.get("photo"):
            raise forms.ValidationError("Bitte einen Namen eingeben oder ein Foto aufnehmen.")
        photo = cleaned.get("photo")
        if photo:
            try:
                photo.seek(0)
                with Image.open(photo) as image:
                    if image.width * image.height > 40_000_000:
                        raise forms.ValidationError(
                            "Das Foto hat zu viele Bildpunkte (maximal 40 Megapixel)."
                        )
                    image.verify()
                photo.seek(0)
            except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
                raise forms.ValidationError(
                    "Das Foto kann nicht verarbeitet werden. Bitte JPEG oder PNG verwenden."
                ) from exc
        return cleaned


class IdentifiedItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = [
            "name",
            "category",
            "manufacturer",
            "model_number",
            "serial_number",
            "inventory_number",
            "description",
            "location",
            "location_note",
            "loan_policy",
            "condition",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "manufacturer": forms.TextInput(attrs={"class": "form-control"}),
            "model_number": forms.TextInput(attrs={"class": "form-control"}),
            "serial_number": forms.TextInput(attrs={"class": "form-control"}),
            "inventory_number": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "location": forms.Select(attrs={"class": "form-select"}),
            "location_note": forms.TextInput(attrs={"class": "form-control"}),
            "loan_policy": forms.Select(attrs={"class": "form-select"}),
            "condition": forms.Select(attrs={"class": "form-select"}),
        }
