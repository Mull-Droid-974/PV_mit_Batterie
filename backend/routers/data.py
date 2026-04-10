from datetime import datetime, timedelta, timezone, date as date_type
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import EnergyData
from backend.constants import PERIOD_MAP

router = APIRouter(prefix="/api/data", tags=["data"])

_TZ_CH = ZoneInfo("Europe/Zurich")


def _resolve_range(period: str, from_date: str | None, to_date: str | None) -> tuple[datetime, datetime, int]:
    """Returns (start, end, days_in_period)."""
    if period == "custom":
        if not from_date or not to_date:
            raise HTTPException(status_code=422, detail="from_date and to_date required for custom period")
        try:
            start_d = date_type.fromisoformat(from_date)
            end_d = date_type.fromisoformat(to_date)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid date format. Use YYYY-MM-DD")
        if start_d > end_d:
            raise HTTPException(status_code=422, detail="from_date must not be after to_date")
        start = datetime(start_d.year, start_d.month, start_d.day, 0, 0, 0, tzinfo=_TZ_CH)
        end = datetime(end_d.year, end_d.month, end_d.day, 23, 59, 59, tzinfo=_TZ_CH)
        days = (end_d - start_d).days + 1
        return start, end, days

    if PERIOD_MAP.get(period) is None:
        raise HTTPException(status_code=422, detail=f"Invalid period '{period}'. Use: {list(PERIOD_MAP)} or 'custom'")
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


@router.get("")
def get_data(
    period: str = Query("7d"),
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    db: Session = Depends(get_db),
):
    start, end, days = _resolve_range(period, from_date, to_date)
    rows = (
        db.query(EnergyData)
        .filter(EnergyData.timestamp >= start, EnergyData.timestamp <= end)
        .order_by(EnergyData.timestamp)
        .all()
    )

    if not rows:
        return {
            "period": period,
            "days_in_period": days,
            "summary": {
                "pv_production_kwh": 0.0,
                "grid_consumption_kwh": 0.0,
                "grid_feed_in_kwh": 0.0,
                "self_consumption_kwh": 0.0,
            },
            "daily": [],
        }

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
        "days_in_period": days,
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
