from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Konto einer/eines Mitarbeitenden. Der Benutzername ist die Institutskennung."""

    email = models.EmailField("E-Mail", help_text="Für Anfragen, Entscheidungen und Erinnerungen.")
    phone = models.CharField("Telefon", max_length=50, blank=True)
    room = models.CharField("Raum", max_length=50, blank=True)
    email_reminders = models.BooleanField(
        "Erinnerungen per E-Mail",
        default=True,
        help_text="Tägliche Erinnerungen zu Rückgaben, Reservierungen und offenen Anfragen.",
    )

    class Meta:
        ordering = ["last_name", "first_name", "username"]
        verbose_name = "Benutzer/in"
        verbose_name_plural = "Benutzer/innen"

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        return self.get_full_name() or self.username

    @property
    def short_name(self):
        """Kurzform für Listen, z. B. „M. Muster“."""
        if self.first_name and self.last_name:
            return f"{self.first_name[0]}. {self.last_name}"
        return self.display_name
