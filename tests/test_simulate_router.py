from datetime import datetime, timedelta, timezone
from backend.models import EnergyData


def _seed(db, n_days: int = 10):
    base = datetime.now(tz=timezone.utc) - timedelta(days=n_days - 1)
    for d in range(n_days):
        for h in range(24):
            ts = base + timedelta(days=d, hours=h)
            db.add(EnergyData(
                timestamp=ts,
                pv_production=2.0,
                grid_consumption=0.5,
                grid_feed_in=1.5,
                self_consumption=0.5,
            ))
    db.commit()


def test_simulate_returns_comparison(client, db):
    _seed(db, n_days=10)
    resp = client.post("/api/simulate", json={
        "period": "7d",
        "capacity_kwh": 10.0,
        "efficiency": 0.9,
        "investment_chf": 8000.0,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert "without_battery" in body
    assert "with_battery" in body
    assert "roi" in body
    assert body["with_battery"]["grid_consumption_kwh"] <= body["without_battery"]["grid_consumption_kwh"]


def test_simulate_invalid_period(client, db):
    resp = client.post("/api/simulate", json={
        "period": "99x",
        "capacity_kwh": 10.0,
        "efficiency": 0.9,
        "investment_chf": 8000.0,
    })
    assert resp.status_code == 422


def test_simulate_empty_db(client, db):
    resp = client.post("/api/simulate", json={
        "period": "7d",
        "capacity_kwh": 10.0,
        "efficiency": 0.9,
        "investment_chf": 8000.0,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["without_battery"]["grid_consumption_kwh"] == 0.0
