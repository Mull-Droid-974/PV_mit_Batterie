from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import EnergyData

router = APIRouter(prefix="/api/forecast", tags=["forecast"])

_LAT = 47.5927
_LON = 8.5903
_KWP = 7.1
_TILT = 38
_AZIMUTH = 26  # Open-Meteo: 0=South, 26° west of south = 206° compass


def _fetch_open_meteo() -> dict:
    try:
        resp = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": _LAT,
                "longitude": _LON,
                "hourly": "global_tilted_irradiance,temperature_2m,precipitation,cloud_cover",
                "tilt": _TILT,
                "azimuth": _AZIMUTH,
                "forecast_days": 8,
                "timezone": "Europe/Zurich",
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Open-Meteo request timed out") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Open-Meteo returned {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Open-Meteo") from exc


def _build_forecast(raw: dict) -> list[dict]:
    try:
        hourly = raw["hourly"]
        times = hourly["time"]
        gti = hourly["global_tilted_irradiance"]
        temp = hourly["temperature_2m"]
        precip = hourly["precipitation"]
        cloud = hourly["cloud_cover"]
    except KeyError as exc:
        raise HTTPException(status_code=502, detail=f"Unexpected Open-Meteo response format: missing {exc}") from exc

    days: dict[str, dict] = {}
    for i, t in enumerate(times):
        day_str = t[:10]
        hour_str = t[11:16]
        pv_kwh = round(float(gti[i] or 0) * _KWP / 1000, 3)
        if day_str not in days:
            days[day_str] = {
                "date": day_str,
                "pv_kwh": 0.0,
                "temps": [],
                "precipitation_mm": 0.0,
                "cloud_covers": [],
                "hourly": [],
            }
        d = days[day_str]
        d["pv_kwh"] = round(d["pv_kwh"] + pv_kwh, 3)
        d["temps"].append(float(temp[i]) if temp[i] is not None else 0.0)
        d["precipitation_mm"] = round(d["precipitation_mm"] + float(precip[i] or 0), 2)
        d["cloud_covers"].append(int(cloud[i] or 0))
        d["hourly"].append({
            "hour": hour_str,
            "pv_kwh": pv_kwh,
            "temp_c": float(temp[i]) if temp[i] is not None else 0.0,
            "precipitation_mm": float(precip[i] or 0),
            "cloud_cover_pct": int(cloud[i] or 0),
        })

    today = date.today().isoformat()
    result = []
    for k, d in sorted(days.items()):
        if k < today:
            continue
        result.append({
            "date": d["date"],
            "pv_kwh": d["pv_kwh"],
            "temp_min": round(min(d["temps"]), 1) if d["temps"] else 0.0,
            "temp_max": round(max(d["temps"]), 1) if d["temps"] else 0.0,
            "precipitation_mm": d["precipitation_mm"],
            "cloud_cover_pct": int(sum(d["cloud_covers"]) / len(d["cloud_covers"])) if d["cloud_covers"] else 0,
            "hourly": d["hourly"],
        })
    return result[:7]


def _fetch_historical(forecast_dates: list[str], db: Session) -> list[dict]:
    result = []
    for d in forecast_dates:
        dt = date.fromisoformat(d)
        try:
            last_year = dt.replace(year=dt.year - 1)
        except ValueError:
            # Feb 29 in a leap year → use Feb 28 in prior year
            last_year = dt.replace(year=dt.year - 1, day=28)
        start = datetime(last_year.year, last_year.month, last_year.day, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(last_year.year, last_year.month, last_year.day, 23, 59, 59, tzinfo=timezone.utc)
        total = (
            db.query(func.sum(EnergyData.pv_production))
            .filter(EnergyData.timestamp >= start, EnergyData.timestamp <= end)
            .scalar()
        )
        result.append({
            "date": last_year.isoformat(),
            "pv_kwh": round(float(total), 2) if total else None,
        })
    return result


@router.get("")
def get_forecast(db: Session = Depends(get_db)):
    raw = _fetch_open_meteo()
    forecast = _build_forecast(raw)
    historical = _fetch_historical([f["date"] for f in forecast], db)
    return {"forecast": forecast, "historical": historical}
