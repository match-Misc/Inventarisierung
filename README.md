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

Die Anwendung überträgt Nutzerfragen sowie bei der Webrecherche Hersteller, Modell und gesuchten
Kennwert. Namen, Kontakt- und Standortdaten, Serien-/Inventarnummern und Buchungsverläufe bleiben lokal.
Recherchierte Kennwerte werden erst nach Prüfung durch die verantwortliche Person verwendet.

Weitere Projektregeln, Status und Betriebsbefehle stehen in `AGENTS.md`.
