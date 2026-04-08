from datetime import datetime, timedelta, timezone
from backend.models import EnergyData


def _seed(db, n_days: int = 10):
    """Insert n_days × 24 hourly rows."""
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


def test_data_endpoint_returns_summary(client, db):
    _seed(db, n_days=10)
    resp = client.get("/api/data?period=7d")
    assert resp.status_code == 200
    body = resp.json()
    assert "summary" in body
    assert "daily" in body
    assert body["summary"]["pv_production_kwh"] > 0


def test_data_endpoint_invalid_period(client, db):
    resp = client.get("/api/data?period=99x")
    assert resp.status_code == 422


def test_data_endpoint_empty_db(client, db):
    resp = client.get("/api/data?period=7d")
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"]["pv_production_kwh"] == 0.0
