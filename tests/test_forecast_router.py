# tests/test_forecast_router.py
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import pytest
from backend.models import EnergyData


def _make_om_response(days: int = 2) -> dict:
    """Minimal Open-Meteo response for testing."""
    from datetime import date
    times = []
    for d in range(days):
        day = (date.today() + timedelta(days=d)).isoformat()
        for h in range(24):
            times.append(f"{day}T{h:02d}:00")
    n = len(times)
    return {
        "hourly": {
            "time": times,
            "global_tilted_irradiance": [500.0] * n,
            "temperature_2m": [15.0] * n,
            "precipitation": [0.1] * n,
            "cloud_cover": [30] * n,
        }
    }


def test_build_forecast_structure():
    from backend.routers.forecast import _build_forecast
    result = _build_forecast(_make_om_response(days=2))
    assert len(result) == 2
    day = result[0]
    assert "date" in day
    assert "pv_kwh" in day
    assert "temp_min" in day
    assert "temp_max" in day
    assert "precipitation_mm" in day
    assert "cloud_cover_pct" in day
    assert "hourly" in day
    assert len(day["hourly"]) == 24
    hourly_entry = day["hourly"][0]
    assert "hour" in hourly_entry
    assert "pv_kwh" in hourly_entry
    assert "temp_c" in hourly_entry
    assert "precipitation_mm" in hourly_entry
    assert "cloud_cover_pct" in hourly_entry


def test_build_forecast_pv_calculation():
    from backend.routers.forecast import _build_forecast
    # 500 W/m² × 7.1 kWp / 1000 = 3.55 kWh/h × 24h = 85.2 kWh/day
    result = _build_forecast(_make_om_response(days=1))
    assert abs(result[0]["pv_kwh"] - 85.2) < 0.1


def test_fetch_historical_returns_null_when_no_data(db):
    from backend.routers.forecast import _fetch_historical
    from datetime import date
    future_dates = [
        (date.today() + timedelta(days=i)).isoformat() for i in range(3)
    ]
    result = _fetch_historical(future_dates, db)
    assert len(result) == 3
    assert all(r["pv_kwh"] is None for r in result)


def test_fetch_historical_returns_value_when_data_exists(db):
    from backend.routers.forecast import _fetch_historical
    from datetime import date
    # Insert data exactly 365 days ago
    last_year = date.today() - timedelta(days=365)
    ts = datetime(last_year.year, last_year.month, last_year.day, 12, 0, 0, tzinfo=timezone.utc)
    db.add(EnergyData(
        timestamp=ts,
        pv_production=5.0,
        grid_consumption=0.5,
        grid_feed_in=4.0,
        self_consumption=1.0,
    ))
    db.commit()
    today_str = date.today().isoformat()
    result = _fetch_historical([today_str], db)
    assert result[0]["pv_kwh"] == 5.0


def test_forecast_endpoint(client):
    with patch("backend.routers.forecast._fetch_open_meteo", return_value=_make_om_response(days=7)):
        resp = client.get("/api/forecast")
    assert resp.status_code == 200
    data = resp.json()
    assert "forecast" in data
    assert "historical" in data
    assert len(data["forecast"]) == 7
