from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Konto einer/eines Mitarbeitenden. Der Benutzername ist die Institutskennung."""

    email = models.EmailField("E-Mail", help_text="Für Anfragen, Entscheidungen und Erinnerungen.")
    phone = models.CharField("Telefon", max_length=50, blank=True)
    room = models.CharField("Raum", max_length=50, blank=True)

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

    @property
    def notification_settings(self):
        """Benachrichtigungseinstellungen; werden beim ersten Zugriff mit Standardwerten angelegt."""
        if not hasattr(self, "_notification_settings"):
            self._notification_settings, _ = NotificationPreferences.objects.get_or_create(user=self)
        return self._notification_settings


OFF = -1


class NotificationPreferences(models.Model):
    """Welche E-Mails eine Person bekommt. Auswertung in loans/notifications.py und loans/reminders.py."""

    START_CHOICES = [(1, "1 Tag vorher"), (0, "am Starttag"), (OFF, "keine Erinnerung")]
    DUE_CHOICES = [
        (2, "2 Tage vorher"),
        (1, "1 Tag vorher"),
        (0, "am Rückgabetag"),
        (OFF, "keine Erinnerung"),
    ]
    OVERDUE_CHOICES = [(1, "täglich"), (2, "alle 2 Tage"), (7, "wöchentlich")]
    PENDING_CHOICES = [(1, "nach 1 Tag"), (2, "nach 2 Tagen"), (3, "nach 3 Tagen"), (OFF, "keine Erinnerung")]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notification_preferences"
    )
    enabled = models.BooleanField(
        "E-Mail-Benachrichtigungen",
        default=True,
        help_text="Hauptschalter. Mahnungen zu überfälligen Rückgaben kommen trotzdem.",
    )

    # Als Ausleiher/in
    booking_updates = models.BooleanField(
        "Neuigkeiten zu meinen Buchungen",
        default=True,
        help_text="Anfrage oder Verlängerung genehmigt/abgelehnt, Storno durch Verantwortliche, "
        "verfallene Anfragen und Reservierungen, für mich eingetragene Buchungen.",
    )
    start_reminder = models.SmallIntegerField(
        "Erinnerung: Reservierung beginnt", choices=START_CHOICES, default=1
    )
    due_reminder = models.SmallIntegerField("Erinnerung: Rückgabe fällig", choices=DUE_CHOICES, default=1)
    overdue_interval = models.SmallIntegerField(
        "Mahnung bei überfälliger Rückgabe",
        choices=OVERDUE_CHOICES,
        default=2,
        help_text="Lässt sich nicht abschalten – andere warten vielleicht auf das Gerät.",
    )
    item_available = models.BooleanField(
        "Gerät ist wieder da",
        default=True,
        help_text="Wenn ein Gerät zurückgegeben wurde und meine Reservierung bald beginnt.",
    )

    # Als Verantwortliche/r
    new_requests = models.BooleanField(
        "Neue Ausleih- und Verlängerungsanfragen", default=True, help_text="Sofort per E-Mail."
    )
    pending_digest = models.SmallIntegerField(
        "Erinnerung an unbeantwortete Anfragen", choices=PENDING_CHOICES, default=2
    )
    owner_returns = models.BooleanField(
        "Rückgabe und Storno bei genehmigungspflichtigen Geräten",
        default=True,
        help_text="Rückgaben mit Hinweis (z. B. „Kabel fehlt“) kommen immer.",
    )
    owner_activity = models.BooleanField(
        "Aktivität an frei entnehmbaren Geräten",
        default=False,
        help_text="Wenn jemand eines meiner frei entnehmbaren Geräte ausleiht, reserviert oder zurückgibt.",
    )
    owner_overdue = models.BooleanField(
        "Mein Gerät ist überfällig",
        default=True,
        help_text="Am ersten Tag der Überfälligkeit, danach wöchentlich.",
    )

    class Meta:
        verbose_name = "Benachrichtigungseinstellungen"
        verbose_name_plural = "Benachrichtigungseinstellungen"

    def __str__(self):
        return f"Benachrichtigungen von {self.user}"

    def wants(self, field):
        """True, wenn die E-Mail-Art gewünscht ist (Hauptschalter und Einzeleinstellung)."""
        value = getattr(self, field)
        return self.enabled and (value is True or (not isinstance(value, bool) and value != OFF))
