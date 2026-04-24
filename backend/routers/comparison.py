from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.constants import FEED_IN_PRICE, GRID_PRICE, PERIOD_MAP
from backend.database import get_db
from backend.models import EnergyData

router = APIRouter(prefix="/api/comparison", tags=["comparison"])

_TZ_CH = ZoneInfo("Europe/Zurich")
_LAT = 47.5927
_LON = 8.5903
_SOUTH_KWP = 7.1
_SOUTH_TILT = 38
_SOUTH_AZIMUTH = 26      # Open-Meteo convention: 0=South, positive=West
_NORTH_KWP = 7.2
_NORTH_TILT = 38
_NORTH_AZIMUTH = -154    # NNE: 26° compass → 26-180 = -154° Open-Meteo
_DEFAULT_SELF_RATIO = 0.5  # assumed when no historical south data is available

# Periods that can use the forecast API (≤ 92 days)
_FORECAST_API_URL = "https://api.open-meteo.com/v1/forecast"
_ARCHIVE_API_URL = "https://archive-api.open-meteo.com/v1/archive"
_FORECAST_MAX_DAYS = 92


def _resolve_range(period: str) -> tuple[datetime, datetime, int]:
    """Returns (start, end, days_in_period) for a given period string."""
    if PERIOD_MAP.get(period) is None:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid period '{period}'. Use: {list(PERIOD_MAP)}",
        )
    days = PERIOD_MAP[period]
    if period == "1d":
        today = datetime.now(tz=_TZ_CH).date()
        yesterday = today - timedelta(days=1)
        start = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0, tzinfo=_TZ_CH)
        end = datetime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59, tzinfo=_TZ_CH)
        return start, end, days
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=days)
    return start, end, days


def _fetch_gti(tilt: int, azimuth: int, period_days: int, start: datetime, end: datetime) -> dict:
    """Fetch hourly GTI from Open-Meteo (forecast or archive depending on period length)."""
    use_forecast = period_days <= _FORECAST_MAX_DAYS
    try:
        if use_forecast:
            resp = httpx.get(
                _FORECAST_API_URL,
                params={
                    "latitude": _LAT,
                    "longitude": _LON,
                    "hourly": "global_tilted_irradiance",
                    "tilt": tilt,
                    "azimuth": azimuth,
                    "past_days": period_days,
                    "forecast_days": 0,
                    "timezone": "Europe/Zurich",
                },
                timeout=30,
            )
        else:
            yesterday = (datetime.now(tz=_TZ_CH).date() - timedelta(days=1)).isoformat()
            resp = httpx.get(
                _ARCHIVE_API_URL,
                params={
                    "latitude": _LAT,
                    "longitude": _LON,
                    "hourly": "global_tilted_irradiance",
                    "tilt": tilt,
                    "azimuth": azimuth,
                    "start_date": start.astimezone(_TZ_CH).date().isoformat(),
                    "end_date": yesterday,
                    "timezone": "Europe/Zurich",
                },
                timeout=30,
            )
        resp.raise_for_status()
        return resp.json()
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Open-Meteo request timed out") from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502, detail=f"Open-Meteo returned {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="Could not reach Open-Meteo") from exc


def _sum_gti_per_day(raw: dict) -> dict[str, float]:
    """Sum hourly GTI values into a per-day dict keyed by date string."""
    try:
        hourly = raw["hourly"]
        times = hourly["time"]
        gti = hourly["global_tilted_irradiance"]
    except KeyError as exc:
        raise HTTPException(
            status_code=502, detail=f"Unexpected Open-Meteo response format: missing {exc}"
        ) from exc

    daily: dict[str, float] = {}
    for i, t in enumerate(times):
        day_str = t[:10]
        daily[day_str] = daily.get(day_str, 0.0) + float(gti[i] or 0)
    return daily


@router.get("")
def get_comparison(
    period: str = Query("7d"),
    db: Session = Depends(get_db),
):
    # --- Step A: Resolve date range and query DB ---
    start, end, period_days = _resolve_range(period)

    rows = (
        db.query(EnergyData)
        .filter(EnergyData.timestamp >= start, EnergyData.timestamp <= end)
        .order_by(EnergyData.timestamp)
        .all()
    )

    # Aggregate DB data per day
    south_daily: dict[str, dict] = {}
    for r in rows:
        day = r.timestamp.astimezone(_TZ_CH).date().isoformat()
        if day not in south_daily:
            south_daily[day] = {"south_kwh": 0.0, "self_kwh": 0.0}
        south_daily[day]["south_kwh"] += r.pv_production
        south_daily[day]["self_kwh"] += r.self_consumption

    # --- Step B: Fetch GTI for south and north roof ---
    south_raw = _fetch_gti(_SOUTH_TILT, _SOUTH_AZIMUTH, period_days, start, end)
    north_raw = _fetch_gti(_NORTH_TILT, _NORTH_AZIMUTH, period_days, start, end)

    south_gti_per_day = _sum_gti_per_day(south_raw)
    north_gti_per_day = _sum_gti_per_day(north_raw)

    # Collect all dates within the resolved period (clip GTI extras like today's partial data)
    period_end_date = end.astimezone(_TZ_CH).date().isoformat()
    all_dates = sorted(
        d for d in (set(south_gti_per_day) | set(north_gti_per_day) | set(south_daily))
        if d <= period_end_date
    )

    # --- Step C: Compute north estimate per day ---
    south_result: list[dict] = []
    north_result: list[dict] = []

    for day in all_dates:
        south_kwh_day = round(south_daily.get(day, {}).get("south_kwh", 0.0), 3)
        south_gti_day = south_gti_per_day.get(day, 0.0)
        north_gti_day = north_gti_per_day.get(day, 0.0)

        if south_gti_day > 0:
            north_kwh = south_kwh_day * (north_gti_day / south_gti_day) * (_NORTH_KWP / _SOUTH_KWP)
        else:
            north_kwh = 0.0

        south_result.append({"date": day, "kwh": south_kwh_day})
        north_result.append({"date": day, "kwh": round(north_kwh, 3)})

    total_south_kwh = sum(d["kwh"] for d in south_result)
    total_north_kwh = sum(d["kwh"] for d in north_result)
    total_self_kwh = sum(
        south_daily.get(day, {}).get("self_kwh", 0.0) for day in all_dates
    )

    # --- Step D: Financial calculation ---
    if total_south_kwh > 0:
        self_ratio = total_self_kwh / total_south_kwh
    else:
        self_ratio = _DEFAULT_SELF_RATIO

    annual_north_kwh = (total_north_kwh / period_days * 365) if period_days > 0 else 0.0
    north_self_kwh = annual_north_kwh * self_ratio
    north_feed_kwh = annual_north_kwh * (1 - self_ratio)
    annual_self_savings_chf = round(north_self_kwh * GRID_PRICE, 1)
    annual_feed_in_chf = round(north_feed_kwh * FEED_IN_PRICE, 1)
    annual_total_chf = round(annual_self_savings_chf + annual_feed_in_chf, 1)

    combined_total_kwh = round(total_south_kwh + total_north_kwh, 2)
    gain_pct = round((total_north_kwh / total_south_kwh * 100), 1) if total_south_kwh > 0 else 0.0

    return {
        "period": period,
        "period_days": period_days,
        "south": {
            "kwp": _SOUTH_KWP,
            "total_kwh": round(total_south_kwh, 2),
            "daily": south_result,
        },
        "north_estimate": {
            "kwp": _NORTH_KWP,
            "total_kwh": round(total_north_kwh, 2),
            "daily": north_result,
        },
        "combined_total_kwh": combined_total_kwh,
        "gain_pct": gain_pct,
        "financial": {
            "annual_extra_kwh": round(annual_north_kwh, 1),
            "annual_self_consumption_savings_chf": annual_self_savings_chf,
            "annual_feed_in_revenue_chf": annual_feed_in_chf,
            "annual_total_chf": annual_total_chf,
        },
    }
