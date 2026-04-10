from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import EnergyData
from backend.constants import PERIOD_MAP

router = APIRouter(prefix="/api/data", tags=["data"])

_TZ_CH = ZoneInfo("Europe/Zurich")


def _period_to_range(period: str) -> tuple[datetime, datetime]:
    if PERIOD_MAP.get(period) is None:
        raise HTTPException(status_code=422, detail=f"Invalid period '{period}'. Use: {list(PERIOD_MAP)}")
    if period == "1d":
        today = datetime.now(tz=_TZ_CH).date()
        yesterday = today - timedelta(days=1)
        start = datetime(yesterday.year, yesterday.month, yesterday.day, 0, 0, 0, tzinfo=_TZ_CH)
        end = datetime(yesterday.year, yesterday.month, yesterday.day, 23, 59, 59, tzinfo=_TZ_CH)
        return start, end
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=PERIOD_MAP[period])
    return start, end


@router.get("")
def get_data(period: str = Query("7d"), db: Session = Depends(get_db)):
    start, end = _period_to_range(period)
    rows = (
        db.query(EnergyData)
        .filter(EnergyData.timestamp >= start, EnergyData.timestamp <= end)
        .order_by(EnergyData.timestamp)
        .all()
    )

    if not rows:
        return {
            "period": period,
            "days_in_period": PERIOD_MAP[period],
            "summary": {
                "pv_production_kwh": 0.0,
                "grid_consumption_kwh": 0.0,
                "grid_feed_in_kwh": 0.0,
                "self_consumption_kwh": 0.0,
            },
            "daily": [],
        }

    # Aggregate by day
    daily: dict[str, dict] = {}
    for r in rows:
        day = r.timestamp.date().isoformat()
        if day not in daily:
            daily[day] = {"date": day, "pv_production": 0.0, "grid_consumption": 0.0,
                          "grid_feed_in": 0.0, "self_consumption": 0.0}
        daily[day]["pv_production"] += r.pv_production
        daily[day]["grid_consumption"] += r.grid_consumption
        daily[day]["grid_feed_in"] += r.grid_feed_in
        daily[day]["self_consumption"] += r.self_consumption

    return {
        "period": period,
        "days_in_period": PERIOD_MAP[period],
        "summary": {
            "pv_production_kwh": round(sum(r.pv_production for r in rows), 2),
            "grid_consumption_kwh": round(sum(r.grid_consumption for r in rows), 2),
            "grid_feed_in_kwh": round(sum(r.grid_feed_in for r in rows), 2),
            "self_consumption_kwh": round(sum(r.self_consumption for r in rows), 2),
        },
        "daily": list(daily.values()),
        "hourly": [
            {
                "timestamp": r.timestamp.isoformat(),
                "pv_production": r.pv_production,
                "grid_consumption": r.grid_consumption,
                "grid_feed_in": r.grid_feed_in,
                "self_consumption": r.self_consumption,
            }
            for r in rows
        ],
    }
