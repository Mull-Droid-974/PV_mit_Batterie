from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import EnergyData
from backend.simulation import (
    HourlyReading,
    BatteryScenario,
    simulate_without_battery,
    simulate_with_battery,
    calculate_roi,
)

router = APIRouter(prefix="/api/simulate", tags=["simulate"])

PERIOD_MAP = {"7d": 7, "1m": 30, "3m": 90, "6m": 180, "9m": 270, "1y": 365}

GRID_PRICE = 0.32
FEED_IN_PRICE = 0.08


class SimulateRequest(BaseModel):
    period: str = Field(..., description="One of: 7d, 1m, 3m, 6m, 9m, 1y")
    capacity_kwh: float = Field(..., gt=0)
    efficiency: float = Field(0.9, ge=0.1, le=1.0)
    investment_chf: float = Field(..., gt=0)


def _result_to_dict(r) -> dict:
    return {
        "grid_consumption_kwh": round(r.grid_consumption_kwh, 2),
        "grid_feed_in_kwh": round(r.grid_feed_in_kwh, 2),
        "grid_cost_chf": round(r.grid_cost_chf, 2),
        "feed_in_revenue_chf": round(r.feed_in_revenue_chf, 2),
        "net_cost_chf": round(r.net_cost_chf, 2),
    }


@router.post("")
def simulate(req: SimulateRequest, db: Session = Depends(get_db)):
    days = PERIOD_MAP.get(req.period)
    if days is None:
        raise HTTPException(status_code=422, detail=f"Invalid period. Use: {list(PERIOD_MAP)}")

    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=days)

    rows = (
        db.query(EnergyData)
        .filter(EnergyData.timestamp >= start, EnergyData.timestamp <= end)
        .order_by(EnergyData.timestamp)
        .all()
    )

    readings: list[HourlyReading] = [
        HourlyReading(
            timestamp=r.timestamp.isoformat(),
            pv_production=r.pv_production,
            grid_consumption=r.grid_consumption,
            grid_feed_in=r.grid_feed_in,
            self_consumption=r.self_consumption,
        )
        for r in rows
    ]

    battery = BatteryScenario(
        capacity_kwh=req.capacity_kwh,
        efficiency=req.efficiency,
        investment_chf=req.investment_chf,
    )

    without = simulate_without_battery(readings, GRID_PRICE, FEED_IN_PRICE)
    with_bat = simulate_with_battery(readings, battery, GRID_PRICE, FEED_IN_PRICE)
    roi = calculate_roi(without, with_bat, req.investment_chf, days)

    return {
        "period": req.period,
        "battery": {
            "capacity_kwh": req.capacity_kwh,
            "efficiency": req.efficiency,
            "investment_chf": req.investment_chf,
        },
        "without_battery": _result_to_dict(without),
        "with_battery": _result_to_dict(with_bat),
        "roi": roi,
    }
