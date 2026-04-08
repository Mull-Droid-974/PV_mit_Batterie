"""
Sync worker: fetches Solar Manager data and upserts into PostgreSQL.
- On first run: fetches last 12 months
- Daily: fetches last 2 days (overlap to catch late-arriving data)
"""
import os
from datetime import datetime, timedelta, timezone
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from backend.database import SessionLocal, engine
from backend.models import EnergyData, Base
from backend.solar_manager import SolarManagerClient, SolarManagerError

logger = logging.getLogger(__name__)


def _upsert_readings(db: Session, readings: list[dict]) -> int:
    """Insert or update hourly readings. Returns count of upserted rows."""
    count = 0
    for r in readings:
        ts = r["timestamp"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        row = db.get(EnergyData, ts)
        if row is None:
            row = EnergyData(timestamp=ts)
            db.add(row)
        row.pv_production = r["pv_production"]
        row.grid_consumption = r["grid_consumption"]
        row.grid_feed_in = r["grid_feed_in"]
        row.self_consumption = r["self_consumption"]
        count += 1
    db.commit()
    return count


def sync_historical(months: int = 12) -> None:
    """Fetch and store the last N months of data. Called once on startup if DB is empty."""
    client = SolarManagerClient()
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=months * 30)
    logger.info(f"Starting historical sync: {start.date()} → {end.date()}")
    try:
        readings = client.get_hourly_data(start, end)
        db = SessionLocal()
        count = _upsert_readings(db, readings)
        db.close()
        logger.info(f"Historical sync complete: {count} rows")
    except SolarManagerError as e:
        logger.error(f"Historical sync failed: {e}")


def sync_recent() -> None:
    """Fetch last 2 days. Called daily by APScheduler."""
    client = SolarManagerClient()
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=2)
    logger.info(f"Daily sync: {start.date()} → {end.date()}")
    try:
        readings = client.get_hourly_data(start, end)
        db = SessionLocal()
        count = _upsert_readings(db, readings)
        db.close()
        logger.info(f"Daily sync complete: {count} rows")
    except SolarManagerError as e:
        logger.error(f"Daily sync failed: {e}")


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Europe/Zurich")
    scheduler.add_job(sync_recent, "cron", hour=3, minute=0)
    return scheduler
