# PV Forecast — Design Spec

**Datum:** 2026-04-10  
**Status:** Approved

---

## Übersicht

Zweite Seite im bestehenden Dashboard: 7-Tage-PV-Produktionsprognose basierend auf der Open-Meteo Wettervorhersage (kostenlos, kein API-Key). Enthält Wetterdaten (Temperatur, Niederschlag, Bewölkung), stündliche Produktionsprognose und historischen Vergleich mit denselben 7 Tagen im Vorjahr.

---

## Architektur

```
Open-Meteo API (kostenlos, kein Key)
        │
        ▼
GET /api/forecast
  - Stündliche GTI, Temperatur, Niederschlag, Bewölkung
  - PV-Prognose: GTI (W/m²) × 7.1 kWp / 1000 = kWh/h
  - Aggregation zu Tageswerten
  - Historischer Vergleich: gleiche 7 Tage im Vorjahr aus DB
        │
        ▼
frontend/forecast.html + frontend/forecast.js
  - Eigene statische Seite, serviert via FastAPI StaticFiles
  - Navigation im Header auf beiden Seiten (Dashboard | Prognose)
```

---

## PV-Anlagenparameter

| Parameter    | Wert                        |
|--------------|-----------------------------|
| Leistung     | 7.1 kWp                     |
| Neigung      | 38°                         |
| Ausrichtung  | 206° (SSW) → Open-Meteo: 26 |
| Standort     | Embrach                     |
| Latitude     | 47.5927                     |
| Longitude    | 8.5903                      |

**Azimut-Konvention Open-Meteo:** 0 = Süd, −90 = Ost, +90 = West.  
206° Kompassrichtung (von Nord) = 26° westlich von Süd → `azimuth=26`.

---

## Backend

### Neuer Router: `backend/routers/forecast.py`

**Endpunkt:** `GET /api/forecast`

**Open-Meteo Anfrage:**
```
GET https://api.open-meteo.com/v1/forecast
  ?latitude=47.5927
  &longitude=8.5903
  &hourly=global_tilted_irradiance,temperature_2m,precipitation,cloud_cover
  &tilt=38
  &azimuth=26
  &forecast_days=8
  &timezone=Europe%2FZurich
```

**PV-Produktionsformel (pro Stunde):**
```
pv_kwh = GTI (W/m²) × 7.1 / 1000
```

**Historischer Vergleich:**
- DB-Abfrage: für jeden der 7 Prognosetage das Datum minus 1 Jahr
- `SUM(pv_production)` pro Tag aus `energy_data`
- Falls kein Eintrag vorhanden → `null`

**Antwortstruktur:**
```json
{
  "forecast": [
    {
      "date": "2026-04-11",
      "pv_kwh": 32.4,
      "temp_min": 8.2,
      "temp_max": 16.5,
      "precipitation_mm": 1.2,
      "cloud_cover_pct": 35,
      "hourly": [
        {
          "hour": "06:00",
          "pv_kwh": 0.8,
          "temp_c": 9.1,
          "precipitation_mm": 0.0,
          "cloud_cover_pct": 20
        }
      ]
    }
  ],
  "historical": [
    {
      "date": "2025-04-11",
      "pv_kwh": 28.1
    }
  ]
}
```

### `backend/main.py`
- Neuen Router `forecast_router` importieren und registrieren.

---

## Frontend

### Navigation

Beide Seiten (`index.html`, `forecast.html`) erhalten im Header rechts:
```html
<nav>
  <a href="/">Dashboard</a>
  <a href="/forecast">Prognose</a>
</nav>
```
Aktiver Link wird hervorgehoben (fett / Unterstrich).

### `frontend/forecast.html`

Seitenaufbau von oben nach unten:

1. **Wetterstreifen** — 7 Kästchen nebeneinander, eines pro Tag:
   - Datum (z.B. "Fr 11.4.")
   - Bewölkungsgrad %
   - Niederschlag mm
   - Temperatur min–max °C
   - PV-Prognose kWh
   - Klickbar → zeigt stündlichen Verlauf

2. **Balkendiagramm** (Chart.js `bar`):
   - Blau: PV-Prognose kWh pro Tag
   - Grau gestrichelt: Vorjahr gleiche Tage (oder leer wenn keine Daten)
   - X-Achse: 7 Tage, Y-Achse: kWh

3. **Tagesdetail-Header** — gewählter Tag als Titel (Standard: heute)

4. **Stündlicher Verlauf** (Chart.js `line`, zwei Y-Achsen):
   - Linie 1 (gelb): PV-Produktion kWh/h (links)
   - Linie 2 (rot): Temperatur °C (rechts)

5. **Niederschlag** (Chart.js `bar`):
   - Balken pro Stunde: mm Niederschlag (blau)

### `frontend/forecast.js`

- `loadForecast()` → `GET /api/forecast` → rendert alle 4 Elemente
- `selectDay(index)` → aktualisiert Tagesdetail + Niederschlagsdiagramm
- Standardauswahl: erster Tag (heute)

### `frontend/style.css`

Ergänzungen:
- `.nav-links` — flex-Reihe mit Links
- `.nav-links a.active` — Hervorhebung aktiver Seite
- `.weather-strip` — 7-Kästchen-Raster
- `.weather-day` — einzelnes Kästchen, klickbar, mit `.active`-State

---

## Neue / geänderte Dateien

| Datei | Änderung |
|---|---|
| `backend/routers/forecast.py` | Neu |
| `backend/main.py` | Router registrieren |
| `frontend/forecast.html` | Neu |
| `frontend/forecast.js` | Neu |
| `frontend/index.html` | Navigation ergänzen |
| `frontend/style.css` | Nav + Weather-Strip Styles |

---

## Nicht im Scope

- Caching der Open-Meteo Antwort (API ist schnell und kostenlos)
- Mehrere Standorte
- Windprognose
- PV-Prognose mit Batterie-Simulation
