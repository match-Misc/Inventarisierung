# Mitgelieferte Frontend-Bibliotheken

Die Bibliotheken liegen bewusst im Repository statt auf einem CDN. So gehen keine Anfragen an Dritte (DSGVO), und das Tool läuft auch ohne Internetzugang.

| Bibliothek | Version | Quelle (jsDelivr/npm) | Lizenz |
|---|---|---|---|
| Bootstrap | 5.3.8 | `bootstrap@5.3.8/dist/css/bootstrap.min.css`, `dist/js/bootstrap.bundle.min.js` | MIT |
| Bootstrap Icons | 1.13.1 | `bootstrap-icons@1.13.1/font/bootstrap-icons.min.css` + `font/fonts/*` | MIT |
| htmx | 2.0.11 | `htmx.org@2.0.11/dist/htmx.min.js` | 0BSD |
| FullCalendar (Standard-Bundle) | 6.1.21 | `fullcalendar@6.1.21/index.global.min.js`, `@fullcalendar/core@6.1.21/locales/de.global.min.js` | MIT |

Aus den Bootstrap-Dateien wurden die `sourceMappingURL`-Kommentare entfernt. Die `.map`-Dateien werden nicht mitgeliefert, und ohne diese Änderung würde `collectstatic` abbrechen. Nach jedem Update erneut entfernen.
