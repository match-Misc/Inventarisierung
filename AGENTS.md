# AGENTS.md: Leitfaden für KI-Agenten und Mitwirkende

Diese Datei ist der Einstieg für alle Agenten (Claude Code, Copilot, Codex, …) und Menschen, die über GitHub an diesem Projekt mitarbeiten. **Vor jeder Änderung lesen** und bei relevanten Änderungen aktuell halten, vor allem den Abschnitt „Stand der Umsetzung“.

---

## 1. Ziel des Projekts

Am Institut fehlt ein gemeinsamer Überblick über die Forschungsgeräte (Sensoren, Aktoren, Werkzeuge): *Was gibt es, wo liegt es, wer hat es gerade und bis wann?*

Deshalb bauen wir ein **webbasiertes Inventarisierungs- und Ausleihtool**:

- Mitarbeitende melden sich mit ihrer Kennung an. Vorerst gibt es eigene Konten im Tool, LDAP/SSO kommt später.
- Alle können **Geräte ins Inventar aufnehmen**. Wer ein Gerät anlegt, ist dafür **verantwortlich**, kann die Verantwortung aber übertragen.
- Die verantwortliche Person legt pro Gerät die **Ausleihregel** fest:
  - **frei entnehmbar:** direkt ausleihen oder reservieren
  - **nur mit Genehmigung:** Ausleihe anfragen, die verantwortliche Person genehmigt oder lehnt ab
- Alle sehen, **wer ein Gerät gerade ausgeliehen hat** und bis wann.
- Ein **Buchungskalender** zeigt laufende Ausleihen, Reservierungen und offene Anfragen. Überschneidungen werden verhindert.
- Jedes Gerät hat eine **Detailseite** mit Fotos, Handbüchern und Dokumenten, Beschreibung, Ablageort und Zubehör.
- **E-Mails** gehen bei Anfragen und Entscheidungen raus. Dazu kommen **tägliche Erinnerungen** (Rückgabe fällig oder überfällig, Reservierung beginnt, offene Anfragen).

## 2. Tech-Stack und Grundsatzentscheidungen

| Bereich | Wahl |
|---|---|
| Backend | Python 3.12, **Django 5.2 LTS** |
| Datenbank | SQLite (Entwicklung), PostgreSQL (Betrieb), gesetzt über `DATABASE_URL` |
| Frontend | Django-Templates (serverseitig), Bootstrap 5.3, Bootstrap Icons, HTMX 2 |
| Kalender | FullCalendar 6.1 (Standard-Bundle, MIT) |
| Pakete | django-environ, django-filter, django-crispy-forms + crispy-bootstrap5, django-htmx, Pillow, whitenoise, psycopg, gunicorn |
| Qualität | pytest + pytest-django + factory_boy, ruff (Lint + Format), CI mit GitHub Actions |
| Betrieb | Docker Compose (App + PostgreSQL) hinter dem HTTPS-Reverse-Proxy der IT |

Festgelegte Annahmen (nicht ohne Rücksprache ändern):

- **Ein Eintrag ist ein physisches Gerät oder Set**, Stückzahlen gibt es nicht. Für baugleiche Geräte gibt es die Funktion „Duplizieren“.
- **Buchungen sind tageweise.** Start- und Endtag gehören beide zum Zeitraum.
- **Benutzername = Institutskennung.** Damit klappt der spätere Umstieg auf LDAP (`django-python3-ldap`) ohne Migration.
- **Rechte:**
  - Anlegen dürfen alle.
  - Bearbeiten, Genehmigen und Rückgaben anderer buchen dürfen nur die/der Verantwortliche und Admins (`is_staff`).
- **Sichtbarkeit:**
  - Aktuelle und künftige Buchungen sehen alle.
  - Die vergangene Ausleihhistorie eines Geräts sehen nur die/der Verantwortliche und Admins (Datenschutz).
- **Kein CDN:** Alle JS/CSS-Bibliotheken liegen in `static/vendor/` (DSGVO, läuft auch offline). Versionen stehen in `static/vendor/README.md`.
- **Sprache:** Oberfläche, URLs und Hilfetexte auf Deutsch. Code-Bezeichner (Klassen, Felder, Funktionen) auf Englisch.

## 3. Projektstruktur

```
config/      settings.py (alles über Umgebungsvariablen), urls.py, wsgi.py
accounts/    User-Modell (AbstractUser + phone, room, email_reminders), Profil, Einladungen
inventory/   Category/Location (Baumstruktur mit gespeichertem `path`), Item, ItemPhoto,
             ItemDocument, Accessory; Bildverarbeitung (images.py), Validatoren, Signale
loans/       Booking (Statusmaschine), ReminderLog, services.py (Fachlogik), notifications.py,
             Kalender-Feed, Management-Commands (send_reminders, seed_demo)
templates/   base.html, registration/, email/ (Text-Mails), partials/
static/      css/, js/, img/, vendor/ (Bootstrap, Icons, htmx, FullCalendar)
tests/       pytest-Tests (conftest.py, factories.py)
```

## 4. Fachlogik: das Wichtigste

### Datenmodell (Kurzfassung)

- **Item**
  - `name`, `category`, `manufacturer`, `model_number`, `serial_number`, `inventory_number` (eindeutig, falls gesetzt), `description`
  - `location` und `location_note` (Ablagehinweis)
  - `responsible`
  - `loan_policy`: `free` oder `approval`
  - `condition`: `ok`, `defect`, `repair` oder `retired`
- **Verfügbarkeit** wird *nicht gespeichert*, sondern aus den Buchungen berechnet (`Item.current_booking`, `Item.objects.with_status()`).
- **Category/Location:** Baumstruktur über `parent`, der volle Pfad liegt denormalisiert in `path`, z. B. „Geb. A › Raum 1“. Mit `subtree_q()` filtert man inklusive aller Untereinträge.
- **Fotos** werden beim Upload EXIF-korrigiert, auf höchstens 2560 px verkleinert und als JPEG gespeichert, dazu entsteht ein Vorschaubild (`inventory/images.py`).
- **Dokumente:** entweder eine Datei oder ein Link. HTML-, SVG- und JS-Uploads sind verboten.
- **Mediendateien** liefert eine eigene View unter `/medien/` aus, nur für angemeldete Nutzer.

### Buchungsstatus (`loans.models.Booking.Status`)

| Von | Aktion | Nach |
|---|---|---|
| – | buchen, direkt erlaubt¹, Start heute | `active` (ausgeliehen) |
| – | buchen, direkt erlaubt¹, Start später | `reserved` |
| – | buchen, Genehmigung nötig | `requested` |
| `requested` | genehmigen / ablehnen | `reserved` / `rejected` |
| `requested`, `reserved` | zurückziehen / stornieren | `cancelled` |
| `reserved` | entnehmen (ab Starttag) | `active` |
| `active` | zurückgeben | `returned` |
| `requested`, `reserved` | Zeitraum verstrichen (täglicher Lauf) | `expired` |

¹ Das Gerät ist frei entnehmbar, oder die buchende Person ist dafür verantwortlich bzw. Admin.

Regeln:

- **Nur `reserved` und `active` blockieren einen Zeitraum.**
  - Eine überfällige Ausleihe blockiert bis zur Rückgabe: Ihr effektives Ende ist das spätere von Enddatum und heute.
  - Offene Anfragen blockieren nicht. Beim Genehmigen wird erneut auf Konflikte geprüft.
- **Verlängern:**
  - Bei freien Geräten geht das direkt.
  - Bei genehmigungspflichtigen Geräten wird es eine Anfrage über `requested_end_date`.
- **Ausmustern statt löschen:** Ein Gerät, das schon Buchungen hat, wird nicht gelöscht, sondern auf `retired` gesetzt.
- **Alle Statuswechsel laufen über `loans/services.py`.** Das gilt für Views, Admin-Aktionen und Commands, und dort sollen auch die Tests ansetzen. Die Funktionen laufen in `transaction.atomic()` und sperren das Gerät mit `select_for_update()`. Fachliche Fehler lösen `BookingError` aus (die Meldung wird Nutzer:innen angezeigt), fehlende Rechte `PermissionDenied`.
- **E-Mails** werden mit `transaction.on_commit` verschickt. Ein Versandfehler wird nur geloggt und blockiert nichts. In Tests `django_capture_on_commit_callbacks(execute=True)` verwenden.

## 5. Projektplan und Stand der Umsetzung

Ein Häkchen heißt erledigt. Wer einen Schritt fertigstellt, hakt ihn hier im selben PR ab.

1. **Grundgerüst**
   - [x] venv, Requirements, `config/settings.py` über Umgebungsvariablen (`de`, `Europe/Berlin`), `LoginRequiredMiddleware`, WhiteNoise
   - [x] Custom User (`accounts.User`), Admin mit Aktion „Einladung senden“, Profil-View
   - [x] Vendor-Bibliotheken in `static/vendor/`
   - [x] ruff- und pytest-Konfiguration (`pyproject.toml`), `.env.example`
   - [ ] `base.html` mit Navigationsleiste, Templates für Login und Passwort, `templates/email/invitation.txt`
   - [ ] CI-Workflow (`.github/workflows/ci.yml`: ruff, `makemigrations --check`, `check`, pytest)
2. **Inventar**
   - [x] Modelle und Migrationen (inklusive Startkategorien Sensoren/Aktoren/Werkzeuge/Sonstiges), Django-Admin
   - [x] Bildverarbeitung (`images.py`), Upload-Validatoren, Aufräumen der Dateien beim Löschen (`signals.py`)
   - [ ] Formulare (ItemForm mit Zubehör-Formset, Upload mehrerer Fotos, DocumentForm, LocationForm), Filter (django-filter)
   - [ ] Views und Templates: Liste mit Suche und Filtern (HTMX), Detailseite, Anlegen, Bearbeiten, Duplizieren (`?vorlage=<id>`), Ausmustern, Fotos und Dokumente, Orte (mit HTMX-Modal), geschützte Medien-View
3. **Ausleihe**
   - [x] Modelle `Booking` und `ReminderLog`, Context-Processor für das Badge mit offenen Anfragen
   - [ ] `services.py` (alle Übergänge und die Konfliktprüfung), `notifications.py` und E-Mail-Templates
   - [ ] Buchungsformular, Aktionen (genehmigen, ablehnen, stornieren, entnehmen, zurückgeben, verlängern), Übersicht unter `/`
4. **Kalender:** [ ] JSON-Feed unter `/kalender/events/` (Enddatum exklusiv, also +1 Tag), Kalenderseite mit Filtern, Gerätekalender mit Zeitraumauswahl
5. **Konten:** [ ] Profilseite, Passwort vergessen und ändern (Templates)
6. **Erinnerungen:** [ ] `manage.py send_reminders` (Rückgabe morgen fällig, überfällig, Reservierung beginnt heute, Sammelmail zu offenen Anfragen, Verfallen-Logik), abgesichert gegen Doppelversand über `ReminderLog`
7. **Demo und Betrieb**
   - [ ] `manage.py seed_demo`
   - [ ] `Dockerfile` und `compose.yaml` (web + postgres)
   - [ ] README-Abschnitt zu Betrieb und Backup
   - [ ] `check --deploy` sauber

**Später (nicht Teil des aktuellen Plans):** LDAP-Anbindung, QR-Etiketten, Excel-Import, Änderungshistorie, Aufbewahrungsfrist für die Ausleihhistorie.

## 6. Installation (Entwicklung)

Voraussetzung ist Python 3.12. Node.js wird nicht gebraucht.

**Windows (PowerShell oder Git Bash):**

```bash
py -3.12 -m venv .venv
.venv\Scripts\activate            # Git Bash: source .venv/Scripts/activate
pip install -r requirements-dev.txt
copy .env.example .env            # Git Bash: cp .env.example .env  (setzt DEBUG=True)
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

**Linux/macOS:**

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python manage.py migrate && python manage.py createsuperuser && python manage.py runserver
```

Danach im Browser `http://localhost:8000` aufrufen. Die Verwaltung liegt unter `/admin/`. In der Entwicklung werden Mails auf der Konsole ausgegeben.

Alle Einstellungen kommen aus Umgebungsvariablen oder der `.env`-Datei; siehe `.env.example`. Die `.env` wird nie eingecheckt.

## 7. Nutzung und wichtige Befehle

```bash
python manage.py runserver                 # Entwicklungsserver
python manage.py makemigrations            # nach Modelländerungen, Migrationen mit einchecken
python manage.py migrate
pytest                                     # Tests
ruff check . && ruff format .              # Lint und Format (vor jedem Commit)
python manage.py check                     # Django-Systemprüfung
python manage.py send_reminders            # tägliche Erinnerungen (in Arbeit, Schritt 6)
python manage.py seed_demo                 # Demo-Daten (in Arbeit, Schritt 7)
```

**Konten anlegen:** Unter `/admin/` ein neues Konto anlegen, mit der Institutskennung als Benutzername und E-Mail-Adresse. „Passwortbasierte Anmeldung“ bleibt deaktiviert. Danach in der Nutzerliste die Aktion **„Einladung senden“** wählen; die Person bekommt dann einen Link, über den sie ihr Passwort selbst setzt.

## 8. Arbeitsweise und Konventionen

- **Git:**
  - Nicht direkt auf `main` arbeiten. Stattdessen einen Feature-Branch anlegen (`feature/<thema>`) und einen Pull Request stellen.
  - Kleine, thematisch abgeschlossene Commits.
  - Commit-Nachrichten gerne auf Deutsch.
- **Vor jedem Push** müssen diese Befehle fehlerfrei durchlaufen: `ruff check .`, `ruff format --check .`, `python manage.py makemigrations --check --dry-run`, `python manage.py check`, `pytest`.
- **Stil:**
  - Gleiche Muster wie im umgebenden Code, sparsame deutsche Kommentare.
  - Django-Modelle bekommen `verbose_name` auf Deutsch.
  - Auswahllisten als `models.TextChoices` mit englischem Wert und deutschem Label.
- **Rechte:**
  - Die Prüfung läuft über `Item.can_manage(user)`, ohne zusätzliche Pakete.
  - Seiten sind automatisch login-pflichtig (`LoginRequiredMiddleware`). Öffentliche Views brauchen `@login_not_required`, und die sollte es praktisch nie geben.
- **Frontend:**
  - Keine CDN-Links und kein Build-Schritt.
  - Neue Bibliotheken nach `static/vendor/` legen und in `static/vendor/README.md` eintragen. `sourceMappingURL`-Kommentare entfernen, sonst scheitert `collectstatic`.
- **Tests:**
  - Liegen unter `tests/`.
  - Fachlogik direkt über `loans.services` testen, Views über den Django-Test-Client.
  - Tests laufen mit `DEBUG=False`. Deshalb schaltet `tests/conftest.py` den Manifest-Static-Storage und `SECURE_SSL_REDIRECT` ab.
- **Migrationen:**
  - Immer mit einchecken.
  - In Data-Migrations das eigene `save()` nicht voraussetzen, sondern `path` bei Category/Location selbst setzen.
- **Datenschutz:**
  - Die Ausleihhistorie sind personenbezogene Daten von Beschäftigten, also sparsam anzeigen.
  - Keine echten Personendaten in Tests oder Demo-Daten.

## 9. Offene Punkte und Hinweise

- Vor dem produktiven Einsatz Datenschutzbeauftragte und Personalrat einbinden, wegen der Ausleihhistorie.
- Zielserver, SMTP-Zugang und Hostname sind noch mit der IT abzustimmen.
