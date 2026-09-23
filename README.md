# Inventarisierung

Webbasiertes Inventar- und Ausleihtool für Forschungsgeräte mit einer optionalen KI-Suche.

## Lokal starten

Voraussetzung ist Python 3.12. Unter Windows:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Danach sind das Portal unter `http://localhost:8000/` und die Verwaltung unter
`http://localhost:8000/admin/` erreichbar.

## KI-Inventarsuche

Die Seite `/assistent/` funktioniert ohne externen Dienst als lokale Textsuche. Für die vollständige
Sprach- und Webrecherche wird ein **neu erzeugter** OpenRouter-Schlüssel benötigt:

```dotenv
OPENROUTER_API_KEY=<neuer Schlüssel>
ASSISTANT_MODEL=openai/gpt-6-luna
ASSISTANT_WEB_SEARCH=True
ASSISTANT_REQUESTS_PER_HOUR=20
```

Den Anwendungsschlüssel bei OpenRouter auf **10 USD pro Monat** begrenzen und ausschließlich über die
Serverumgebung oder die nicht eingecheckte `.env` bereitstellen. Ein Schlüssel, der in einem Chat,
Ticket oder Commit sichtbar war, muss vorher widerrufen werden.

Die KI-Suche überträgt Nutzerfragen sowie bei der Webrecherche Hersteller, Modell und gesuchten
Kennwert. Namen, Kontakt- und Standortdaten, Serien-/Inventarnummern und Buchungsverläufe bleiben lokal.
Recherchierte Kennwerte werden erst nach Prüfung durch die verantwortliche Person verwendet.

## Gerät per Foto oder Namen hinzufügen

Unter `/geraete/hinzufuegen/` kann jede angemeldete Person ein Foto aufnehmen oder einen Namen eingeben.
Die Erkennung füllt einen bearbeitbaren Vorschlag aus. Erst nach Bestätigung wird das Gerät gespeichert;
die anlegende Person wird verantwortlich. Ohne OpenRouter-Schlüssel funktioniert die Seite als manuelles Formular.
Während der Verarbeitung zeigt die Seite den aktuellen Schritt und bereits erledigte Schritte an. Bei einer
unterbrochenen Verbindung kann die Erkennung erneut gestartet werden.

Die Stufen **Einfach**, **Mittel** und **Schwierig** verwenden standardmäßig `openai/gpt-4.1-nano`,
`openai/gpt-4.1-mini` und `openai/gpt-4.1`. Sie lassen sich in `.env` mit
`ITEM_RECOGNITION_MODEL_EASY`, `ITEM_RECOGNITION_MODEL_MEDIUM` und `ITEM_RECOGNITION_MODEL_HARD`
austauschen. Mittel und schwierig recherchieren zusätzlich anhand von Hersteller und Modell;
eine recherchierte Beschreibung wird nur mit zitierter HTTPS-Quelle vorgeschlagen.

Bei dieser Funktion wird das bereinigte Foto an OpenRouter gesendet. Angaben auf einem Typenschild,
einschließlich Seriennummern, können darin sichtbar sein. Nutzer sollten das Foto vor dem Absenden prüfen.

Weitere Projektregeln, Status und Betriebsbefehle stehen in `AGENTS.md`.
