# PV Batterie-Analyse Dashboard — Design Spec

**Datum:** 2026-04-08  
**Status:** Approved

---

## Übersicht

Web-Dashboard zur Analyse einer bestehenden PV-Anlage (7.1 kWp) und Simulation eines Batteriespeichers zur Bewertung der wirtschaftlichen Rentabilität. Daten werden von der Solar Manager API bezogen, lokal gecacht und im Browser visualisiert.

---

## Anlagenparameter

| Parameter        | Wert                        |
|------------------|-----------------------------|
| Leistung         | 7.1 kWp                     |
| Module           | 24 × 300 W                  |
| Neigung          | 38.0°                       |
| Ausrichtung      | 206.0° (SSW)                |
| Standort         | Chüngstrasse 8, 8424 Embrach |

---

## Energietarife

| Richtung      | Preis        |
|---------------|--------------|
| Einspeisung   | 0.08 CHF/kWh |
| Netzbezug     | 0.32 CHF/kWh |

---

## Systemarchitektur

```
Solar Manager API
        │
        ▼
┌─────────────────────────────────────────────┐
│            FastAPI Backend                  │
│  ┌──────────────┐   ┌─────────────────────┐ │
│  │  Sync Worker │   │  REST API Endpoints │ │
│  │ (tägl. Cron) │   │  /api/data          │ │
│  └──────┬───────┘   │  /api/simulate      │ │
│         │           └──────────┬──────────┘ │
│         ▼                      ▼            │
│  ┌──────────────────────────────────────┐   │
│  │         PostgreSQL (Railway)         │   │
│  │  - Einspeise- & Verbrauchsdaten      │   │
│  │  - Stündliche Granularität           │   │
│  └──────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────────────────┐
│         Frontend (HTML + Chart.js)          │
│  - Zeitraum-Auswahl (7T / 1M / 3M / …)      │
│  - Batterie-Szenario-Konfigurator           │
│  - Vergleichscharts: mit / ohne Batterie    │
│  - ROI-Berechnung & Amortisation            │
└─────────────────────────────────────────────┘
```

**Deployment:** Railway — 1 FastAPI-Service + PostgreSQL Add-on

---

## Datenmodell

```sql
-- Rohdaten vom Solar Manager (stündliche Auflösung)
energy_data (
  timestamp        TIMESTAMPTZ  PRIMARY KEY,
  pv_production    FLOAT,   -- kWh produziert
  grid_consumption FLOAT,   -- kWh vom Netz bezogen
  grid_feed_in     FLOAT,   -- kWh ins Netz eingespeist
  self_consumption FLOAT    -- kWh direkt selbst verbraucht
)

-- Konfigurationsparameter (Tarife, Anlage)
config (
  key   TEXT PRIMARY KEY,
  value TEXT
)
```

Initialer Sync beim ersten Start: letzte 12 Monate historische Daten.  
Täglicher Sync: neue Daten des Vortages.

---

## Solar Manager API

- Basis-URL: `https://api.solarmanager.ch`
- Authentifizierung: HTTP Basic Auth (Email + Password) oder Token — wird beim Implementieren exploriert
- Umgebungsvariablen: `SOLAR_MANAGER_EMAIL`, `SOLAR_MANAGER_PASSWORD`
- Granularität: stündliche Messwerte

---

## Batterie-Simulation

Stündliche Simulation über den gewählten Zeitraum:

```
für jede Stunde:
  überschuss = pv_produktion - direktverbrauch
  if überschuss > 0:
    lade batterie (bis max. kapazität)
    restüberschuss → ins netz einspeisen
  else:
    defizit = |überschuss|
    entlade batterie (bis 0)
    restdefizit → vom netz beziehen
```

**Batterie-Parameter:**

| Parameter         | Voreinstellungen / Eingabe        |
|-------------------|-----------------------------------|
| Kapazität         | 5 kWh / 10 kWh / 15 kWh + manuell |
| Wirkungsgrad      | 90% (konfigurierbar)              |
| Investitionskosten| Manuell in CHF                    |

**ROI-Berechnung:**

```
Ersparnis = (netz_bezug_ohne - netz_bezug_mit) × 0.32
          - (einspeisung_ohne - einspeisung_mit) × 0.08

Amortisation [Jahre] = Investitionskosten / Ersparnis_pro_Jahr
```

---

## Dashboard UI

**Zeitraum-Auswahl:** 7 Tage / 1 Monat / 3 Monate / 6 Monate / 9 Monate / 1 Jahr (rollierend)

**Kennzahlen-Vergleich (mit / ohne Batterie):**
- Netzbezug (kWh & CHF)
- Einspeisung (kWh & CHF)
- Gesamtkosten (CHF)
- Jährliche Ersparnis (CHF)
- Amortisationsdauer (Jahre)

**Charts (Chart.js):**
1. **Tagesgang** — Linien-Chart: Ø PV-Produktion vs. Ø Verbrauch im Zeitraum
2. **Energiefluss** — Gestapeltes Balken-Chart: Eigenverbrauch / Einspeisung / Netzbezug
3. **Amortisationskurve** — Linien-Chart: Kumulierte Ersparnis mit Batterie über die Zeit

**Batterie-Konfigurator:**
- Schnellauswahl: 5 / 10 / 15 kWh
- Manuelle Eingabe: Kapazität, Wirkungsgrad, Kosten

---

## Projektstruktur

```
PV_mit_Batterie/
├── backend/
│   ├── main.py              # FastAPI app, StaticFiles
│   ├── models.py            # SQLAlchemy Modelle
│   ├── database.py          # DB-Verbindung (DATABASE_URL)
│   ├── solar_manager.py     # Solar Manager API Client
│   ├── simulation.py        # Batterie-Simulationslogik
│   ├── sync.py              # APScheduler täglicher Sync-Job
│   └── routers/
│       ├── data.py          # GET /api/data?period=7d
│       └── simulate.py      # POST /api/simulate
├── frontend/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── .env.example
├── requirements.txt
├── Procfile
└── railway.toml
```

---

## Umgebungsvariablen

```
DATABASE_URL=postgresql://...
SOLAR_MANAGER_EMAIL=...
SOLAR_MANAGER_PASSWORD=...
```

---

## Geplante Erweiterung (später)

**7-Tage-Prognose** — Wettervorhersage-API (z.B. Open-Meteo, kostenlos) liefert Globalstrahlung → Schätzung der PV-Produktion der nächsten 7 Tage → Simulierte Ersparnis in der Vorschau.

---

## Nicht im Scope

- Benutzer-Authentifizierung (Single-User-App)
- Mobile-App
- Echtzeit-Monitoring (< 1h Granularität)
- Mehrere PV-Anlagen
