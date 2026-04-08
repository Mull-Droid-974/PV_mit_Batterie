# PV Batterie-Analyse Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a web dashboard that fetches PV energy data from the Solar Manager API, simulates a battery storage system, and shows the ROI of adding a battery.

**Architecture:** FastAPI backend with PostgreSQL cache on Railway. A daily APScheduler job syncs data from the Solar Manager API. The frontend is vanilla HTML/JS with Chart.js — no build pipeline. The battery simulation runs server-side in Python.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, PostgreSQL (psycopg2), APScheduler, httpx, Chart.js, Railway

---

## File Map

```
PV_mit_Batterie/
├── backend/
│   ├── main.py              # FastAPI app: mounts static files, includes routers, starts scheduler
│   ├── models.py            # SQLAlchemy ORM: EnergyData, Config
│   ├── database.py          # Engine, SessionLocal, Base, get_db dependency
│   ├── solar_manager.py     # HTTP client for Solar Manager API (auth + data fetch)
│   ├── simulation.py        # Pure-Python battery simulation + ROI logic
│   ├── sync.py              # APScheduler job: fetch new data and upsert into DB
│   └── routers/
│       ├── __init__.py
│       ├── data.py          # GET /api/data?period=7d
│       └── simulate.py      # POST /api/simulate
├── frontend/
│   ├── index.html           # Single-page app shell
│   ├── app.js               # Fetches API data, renders charts, handles UI state
│   └── style.css            # Layout and styling
├── tests/
│   ├── conftest.py          # SQLite test DB fixture, TestClient fixture
│   ├── test_simulation.py   # Unit tests for simulation.py (no DB, no HTTP)
│   ├── test_data_router.py  # Integration tests for /api/data
│   └── test_simulate_router.py  # Integration tests for /api/simulate
├── .env.example
├── .gitignore
├── requirements.txt
├── Procfile
└── railway.toml
```

---

## Task 1: Project Scaffolding

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `Procfile`
- Create: `railway.toml`

- [ ] **Step 1: Connect local repo to GitHub remote**

```bash
git remote add origin https://github.com/Mull-Droid-974/PV_mit_Batterie.git
git branch -M main
git push -u origin main
```

- [ ] **Step 2: Create `requirements.txt`**

```
fastapi==0.111.0
uvicorn[standard]==0.29.0
sqlalchemy==2.0.30
psycopg2-binary==2.9.9
apscheduler==3.10.4
httpx==0.27.0
python-dotenv==1.0.1
pytest==8.2.0
pytest-asyncio==0.23.6
httpx==0.27.0
```

- [ ] **Step 3: Create `.env.example`**

```
DATABASE_URL=postgresql://user:password@localhost:5432/pv_analyse
SOLAR_MANAGER_EMAIL=your@email.com
SOLAR_MANAGER_PASSWORD=yourpassword
GRID_PRICE_CHF=0.32
FEED_IN_PRICE_CHF=0.08
```

- [ ] **Step 4: Create `.gitignore`**

```
__pycache__/
*.pyc
.env
*.db
.venv/
venv/
dist/
.pytest_cache/
docs/superpowers/
```

- [ ] **Step 5: Create `Procfile`**

```
web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

- [ ] **Step 6: Create `railway.toml`**

```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "uvicorn backend.main:app --host 0.0.0.0 --port $PORT"
restartPolicyType = "on_failure"
```

- [ ] **Step 7: Install dependencies**

```bash
pip install -r requirements.txt
```

- [ ] **Step 8: Create package init files**

```bash
mkdir -p backend/routers tests
touch backend/__init__.py backend/routers/__init__.py tests/__init__.py
```

- [ ] **Step 9: Commit**

```bash
git add requirements.txt .env.example .gitignore Procfile railway.toml backend/__init__.py backend/routers/__init__.py tests/__init__.py
git commit -m "feat: project scaffolding"
```

---

## Task 2: Database Layer

**Files:**
- Create: `backend/models.py`
- Create: `backend/database.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient


TEST_DATABASE_URL = "sqlite:///./test.db"


@pytest.fixture(scope="function")
def db_engine():
    from backend.database import Base
    engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db(db_engine):
    SessionLocal = sessionmaker(bind=db_engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture(scope="function")
def client(db):
    from backend.main import app
    from backend.database import get_db

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

Write the first model test:

```python
# tests/test_models.py
from datetime import datetime, timezone


def test_energy_data_insert(db):
    from backend.models import EnergyData
    row = EnergyData(
        timestamp=datetime(2025, 1, 1, 12, 0, tzinfo=timezone.utc),
        pv_production=2.5,
        grid_consumption=0.3,
        grid_feed_in=2.0,
        self_consumption=0.5,
    )
    db.add(row)
    db.commit()
    fetched = db.query(EnergyData).first()
    assert fetched.pv_production == 2.5
    assert fetched.grid_feed_in == 2.0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_models.py -v
```

Expected: `ModuleNotFoundError` or `ImportError` — models don't exist yet.

- [ ] **Step 3: Create `backend/database.py`**

```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")

# Railway sets DATABASE_URL with postgres:// prefix — SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 4: Create `backend/models.py`**

```python
from datetime import datetime
from sqlalchemy import Float, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from backend.database import Base


class EnergyData(Base):
    __tablename__ = "energy_data"

    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    pv_production: Mapped[float] = mapped_column(Float, nullable=False)
    grid_consumption: Mapped[float] = mapped_column(Float, nullable=False)
    grid_feed_in: Mapped[float] = mapped_column(Float, nullable=False)
    self_consumption: Mapped[float] = mapped_column(Float, nullable=False)


class Config(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(String, nullable=False)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_models.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/database.py backend/models.py tests/conftest.py tests/test_models.py tests/__init__.py
git commit -m "feat: database layer with SQLAlchemy models"
```

---

## Task 3: Battery Simulation

**Files:**
- Create: `backend/simulation.py`
- Create: `tests/test_simulation.py`

This is pure Python — no database, no HTTP. Easiest to test in isolation.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_simulation.py
from backend.simulation import (
    HourlyReading,
    BatteryScenario,
    simulate_without_battery,
    simulate_with_battery,
    calculate_roi,
)


GRID_PRICE = 0.32
FEED_IN_PRICE = 0.08


def make_reading(pv: float, grid_in: float, feed_out: float) -> HourlyReading:
    """pv=production, grid_in=from grid, feed_out=to grid"""
    return HourlyReading(
        timestamp="2025-01-01T12:00:00Z",
        pv_production=pv,
        grid_consumption=grid_in,
        grid_feed_in=feed_out,
        self_consumption=pv - feed_out,
    )


def test_without_battery_aggregates_cost():
    # 1 hour: consumed 0.5 kWh from grid, fed in 2.0 kWh
    readings = [make_reading(pv=2.5, grid_in=0.5, feed_out=2.0)]
    result = simulate_without_battery(readings, GRID_PRICE, FEED_IN_PRICE)
    assert result.grid_consumption_kwh == 0.5
    assert result.grid_feed_in_kwh == 2.0
    assert abs(result.net_cost_chf - (0.5 * 0.32 - 2.0 * 0.08)) < 0.001


def test_with_battery_charges_surplus():
    # Surplus of 2.0 kWh, battery can hold 5 kWh, efficiency 100%
    readings = [make_reading(pv=2.5, grid_in=0.0, feed_out=2.0)]
    battery = BatteryScenario(capacity_kwh=5.0, efficiency=1.0, investment_chf=8000.0)
    result = simulate_with_battery(readings, battery, GRID_PRICE, FEED_IN_PRICE)
    # Battery absorbs the 2.0 surplus → no feed-in
    assert result.grid_feed_in_kwh == 0.0
    assert result.grid_consumption_kwh == 0.0


def test_with_battery_covers_deficit():
    # Deficit of 1.0 kWh (more consumed than produced), battery has charge
    # pv=1.0, self_consumption=1.0, grid=1.0 kWh deficit
    readings = [make_reading(pv=1.0, grid_in=1.0, feed_out=0.0)]
    battery = BatteryScenario(capacity_kwh=5.0, efficiency=1.0, investment_chf=8000.0)
    # Pre-charge battery manually by passing a surplus hour first
    surplus_hour = make_reading(pv=3.0, grid_in=0.0, feed_out=2.0)
    deficit_hour = make_reading(pv=1.0, grid_in=1.0, feed_out=0.0)
    result = simulate_with_battery([surplus_hour, deficit_hour], battery, GRID_PRICE, FEED_IN_PRICE)
    # Battery charged 2.0 in hour 1, covers 1.0 deficit in hour 2 → 0 grid draw total
    assert result.grid_consumption_kwh == 0.0


def test_calculate_roi():
    from backend.simulation import SimulationResult
    without = SimulationResult(
        grid_consumption_kwh=100.0, grid_feed_in_kwh=200.0,
        grid_cost_chf=32.0, feed_in_revenue_chf=16.0, net_cost_chf=16.0
    )
    with_bat = SimulationResult(
        grid_consumption_kwh=30.0, grid_feed_in_kwh=50.0,
        grid_cost_chf=9.6, feed_in_revenue_chf=4.0, net_cost_chf=5.6
    )
    roi = calculate_roi(without, with_bat, investment_chf=8000.0, days_in_period=30)
    assert roi["annual_savings_chf"] > 0
    assert roi["payback_years"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_simulation.py -v
```

Expected: `ModuleNotFoundError` — simulation.py doesn't exist yet.

- [ ] **Step 3: Create `backend/simulation.py`**

```python
from dataclasses import dataclass
from typing import TypedDict


class HourlyReading(TypedDict):
    timestamp: str
    pv_production: float      # kWh produced by PV
    grid_consumption: float   # kWh drawn from grid
    grid_feed_in: float       # kWh fed into grid
    self_consumption: float   # kWh directly self-consumed (pv - feed_in)


@dataclass
class SimulationResult:
    grid_consumption_kwh: float
    grid_feed_in_kwh: float
    grid_cost_chf: float
    feed_in_revenue_chf: float
    net_cost_chf: float       # grid_cost - feed_in_revenue


@dataclass
class BatteryScenario:
    capacity_kwh: float
    efficiency: float         # round-trip efficiency, e.g. 0.9
    investment_chf: float


def simulate_without_battery(
    readings: list[HourlyReading],
    grid_price: float,
    feed_in_price: float,
) -> SimulationResult:
    grid_consumption = sum(r["grid_consumption"] for r in readings)
    grid_feed_in = sum(r["grid_feed_in"] for r in readings)
    grid_cost = grid_consumption * grid_price
    feed_in_revenue = grid_feed_in * feed_in_price
    return SimulationResult(
        grid_consumption_kwh=grid_consumption,
        grid_feed_in_kwh=grid_feed_in,
        grid_cost_chf=grid_cost,
        feed_in_revenue_chf=feed_in_revenue,
        net_cost_chf=grid_cost - feed_in_revenue,
    )


def simulate_with_battery(
    readings: list[HourlyReading],
    battery: BatteryScenario,
    grid_price: float,
    feed_in_price: float,
) -> SimulationResult:
    soc = 0.0  # state of charge in kWh
    total_grid = 0.0
    total_feed_in = 0.0

    for r in readings:
        # Net surplus (positive = excess PV, negative = deficit)
        net = r["grid_feed_in"] - r["grid_consumption"]

        if net > 0:
            # Surplus: charge battery first, remainder feeds to grid
            can_charge = (battery.capacity_kwh - soc) / battery.efficiency
            charged_energy = min(net, can_charge)
            soc += charged_energy * battery.efficiency
            feed_in = net - charged_energy
            grid = 0.0
        else:
            # Deficit: discharge battery first, remainder from grid
            deficit = abs(net)
            can_discharge = soc * battery.efficiency
            discharged_energy = min(deficit, can_discharge)
            soc -= discharged_energy / battery.efficiency
            grid = deficit - discharged_energy
            feed_in = 0.0

        total_grid += grid
        total_feed_in += feed_in

    grid_cost = total_grid * grid_price
    feed_in_revenue = total_feed_in * feed_in_price
    return SimulationResult(
        grid_consumption_kwh=total_grid,
        grid_feed_in_kwh=total_feed_in,
        grid_cost_chf=grid_cost,
        feed_in_revenue_chf=feed_in_revenue,
        net_cost_chf=grid_cost - feed_in_revenue,
    )


def calculate_roi(
    without: SimulationResult,
    with_battery: SimulationResult,
    investment_chf: float,
    days_in_period: int,
) -> dict:
    period_savings = without.net_cost_chf - with_battery.net_cost_chf
    annual_savings = period_savings * (365 / days_in_period)
    payback_years = investment_chf / annual_savings if annual_savings > 0 else float("inf")
    return {
        "period_savings_chf": round(period_savings, 2),
        "annual_savings_chf": round(annual_savings, 2),
        "payback_years": round(payback_years, 1),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_simulation.py -v
```

Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/simulation.py tests/test_simulation.py
git commit -m "feat: battery simulation and ROI logic"
```

---

## Task 4: Solar Manager API Exploration

**Files:**
- Create: `backend/solar_manager.py` (skeleton)

Before implementing the client, explore the actual API endpoints.

- [ ] **Step 1: Find the Solar Manager API documentation**

Open a browser and check these URLs:
- `https://cloud.solarmanager.ch/api-docs` or
- `https://api.solarmanager.ch/docs` or
- `https://app.solarmanager.ch/api/v1/docs`

Also try: search for "Solar Manager API documentation" or check the Solar Manager app settings for an API section.

- [ ] **Step 2: Test authentication manually with curl**

Try Basic Auth:
```bash
curl -X POST "https://cloud.solarmanager.ch/api/v1/user/login" \
  -H "Content-Type: application/json" \
  -d '{"email": "YOUR_EMAIL", "password": "YOUR_PASSWORD"}'
```

Note the response structure and the token field name.

- [ ] **Step 3: Test a data endpoint**

Using the token from Step 2:
```bash
curl "https://cloud.solarmanager.ch/api/v1/sensor-data/latest" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

Look for fields matching: pv_production, grid_consumption, grid_feed_in, self_consumption (or their equivalents).

- [ ] **Step 4: Find the historical data endpoint**

Look for an endpoint that accepts a `from` and `to` date range and returns hourly data. Note:
- The exact URL
- The date format used (ISO 8601, Unix timestamp, etc.)
- The field names in the response

- [ ] **Step 5: Document findings in `.env.example`**

Add a comment block to `.env.example`:
```
# Solar Manager API base URL (confirmed during exploration)
SOLAR_MANAGER_BASE_URL=https://cloud.solarmanager.ch
```

- [ ] **Step 6: Create `backend/solar_manager.py` skeleton**

```python
"""
Solar Manager API client.

Confirmed endpoints (fill in during Task 4 exploration):
- POST {BASE_URL}/api/v1/user/login  → returns {"token": "..."}
- GET  {BASE_URL}/api/v1/sensor-data?from=ISO&to=ISO&interval=hour
       → returns list of hourly readings

Update BASE_URL, endpoint paths, and field name mappings below
based on findings from the exploration step.
"""
import os
from datetime import datetime
import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("SOLAR_MANAGER_BASE_URL", "https://cloud.solarmanager.ch")
EMAIL = os.getenv("SOLAR_MANAGER_EMAIL", "")
PASSWORD = os.getenv("SOLAR_MANAGER_PASSWORD", "")


class SolarManagerError(Exception):
    pass


class SolarManagerClient:
    def __init__(self):
        self._token: str | None = None

    def _authenticate(self) -> str:
        """POST login, return bearer token. Update path/field if needed."""
        resp = httpx.post(
            f"{BASE_URL}/api/v1/user/login",
            json={"email": EMAIL, "password": PASSWORD},
            timeout=30,
        )
        if resp.status_code != 200:
            raise SolarManagerError(f"Auth failed: {resp.status_code} {resp.text}")
        data = resp.json()
        # UPDATE: replace "token" with actual field name from API response
        return data["token"]

    def _get_token(self) -> str:
        if not self._token:
            self._token = self._authenticate()
        return self._token

    def get_hourly_data(self, start: datetime, end: datetime) -> list[dict]:
        """
        Fetch hourly energy data between start and end.
        Returns list of dicts with keys:
          timestamp, pv_production, grid_consumption, grid_feed_in, self_consumption
        All values in kWh.

        UPDATE: adjust endpoint path, date format, and field name mapping below.
        """
        token = self._get_token()
        resp = httpx.get(
            f"{BASE_URL}/api/v1/sensor-data",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "from": start.isoformat(),
                "to": end.isoformat(),
                "interval": "hour",
            },
            timeout=60,
        )
        if resp.status_code == 401:
            # Token expired — re-authenticate once
            self._token = self._authenticate()
            return self.get_hourly_data(start, end)
        if resp.status_code != 200:
            raise SolarManagerError(f"Data fetch failed: {resp.status_code} {resp.text}")

        raw = resp.json()
        # UPDATE: replace field names with actual API field names
        return [
            {
                "timestamp": item["timestamp"],
                "pv_production": float(item.get("pvPower", item.get("pv_production", 0))) / 1000,
                "grid_consumption": float(item.get("gridPower", item.get("grid_consumption", 0))) / 1000,
                "grid_feed_in": float(item.get("feedIn", item.get("grid_feed_in", 0))) / 1000,
                "self_consumption": float(item.get("selfConsumption", item.get("self_consumption", 0))) / 1000,
            }
            for item in (raw if isinstance(raw, list) else raw.get("data", []))
        ]
```

- [ ] **Step 7: Commit**

```bash
git add backend/solar_manager.py .env.example
git commit -m "feat: Solar Manager API client skeleton (update endpoints after exploration)"
```

---

## Task 5: Sync Worker

**Files:**
- Create: `backend/sync.py`

- [ ] **Step 1: Create `backend/sync.py`**

```python
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
```

- [ ] **Step 2: Commit**

```bash
git add backend/sync.py
git commit -m "feat: APScheduler sync worker for Solar Manager data"
```

---

## Task 6: Data API Endpoint

**Files:**
- Create: `backend/routers/data.py`
- Create: `tests/test_data_router.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_data_router.py
from datetime import datetime, timedelta, timezone
from backend.models import EnergyData


def _seed(db, n_days: int = 10):
    """Insert n_days × 24 hourly rows."""
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_data_router.py -v
```

Expected: errors because the router doesn't exist yet.

- [ ] **Step 3: Create `backend/routers/data.py`**

```python
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from backend.database import get_db
from backend.models import EnergyData

router = APIRouter(prefix="/api/data", tags=["data"])

PERIOD_MAP: dict[str, int] = {
    "7d": 7,
    "1m": 30,
    "3m": 90,
    "6m": 180,
    "9m": 270,
    "1y": 365,
}


def _period_to_range(period: str) -> tuple[datetime, datetime]:
    days = PERIOD_MAP.get(period)
    if days is None:
        raise HTTPException(status_code=422, detail=f"Invalid period '{period}'. Use: {list(PERIOD_MAP)}")
    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=days)
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_data_router.py -v
```

Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/routers/data.py tests/test_data_router.py
git commit -m "feat: GET /api/data endpoint with period filter"
```

---

## Task 7: Simulate API Endpoint

**Files:**
- Create: `backend/routers/simulate.py`
- Create: `tests/test_simulate_router.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_simulate_router.py
from datetime import datetime, timedelta, timezone
from backend.models import EnergyData


def _seed(db, n_days: int = 10):
    base = datetime(2025, 1, 1, tzinfo=timezone.utc)
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
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_simulate_router.py -v
```

Expected: errors because router doesn't exist.

- [ ] **Step 3: Create `backend/routers/simulate.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_simulate_router.py -v
```

Expected: All 3 tests PASS

- [ ] **Step 5: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/routers/simulate.py tests/test_simulate_router.py
git commit -m "feat: POST /api/simulate endpoint with battery comparison"
```

---

## Task 8: FastAPI App Assembly

**Files:**
- Create: `backend/main.py`

- [ ] **Step 1: Create `backend/main.py`**

```python
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from backend.database import engine
from backend.models import Base
from backend.routers.data import router as data_router
from backend.routers.simulate import router as simulate_router
from backend.sync import create_scheduler, sync_historical

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    # Trigger historical sync if DB is empty
    from backend.database import SessionLocal
    from backend.models import EnergyData
    db = SessionLocal()
    count = db.query(EnergyData).count()
    db.close()
    if count == 0:
        logger.info("Empty database — starting historical sync (12 months)")
        sync_historical(months=12)

    # Start daily sync scheduler
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started")

    yield

    scheduler.shutdown()
    logger.info("Scheduler stopped")


app = FastAPI(title="PV Batterie-Analyse", lifespan=lifespan)

app.include_router(data_router)
app.include_router(simulate_router)

# Serve frontend static files
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(FRONTEND_DIR / "index.html")
```

- [ ] **Step 2: Test that the app starts**

```bash
uvicorn backend.main:app --reload
```

Open `http://localhost:8000/docs` — the FastAPI Swagger UI should show `/api/data` and `/api/simulate`.

Expected: No import errors, Swagger UI visible.

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: FastAPI app assembly with lifespan, routers, and static files"
```

---

## Task 9: Frontend

**Files:**
- Create: `frontend/index.html`
- Create: `frontend/app.js`
- Create: `frontend/style.css`

- [ ] **Step 1: Create `frontend/style.css`**

```css
*, *::before, *::after { box-sizing: border-box; }

body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  margin: 0;
  background: #f5f7fa;
  color: #1a1a2e;
}

header {
  background: #1a1a2e;
  color: #fff;
  padding: 1rem 2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

header h1 { margin: 0; font-size: 1.25rem; }
#last-sync { font-size: 0.8rem; opacity: 0.6; }

main { max-width: 1100px; margin: 2rem auto; padding: 0 1rem; }

.period-bar {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1.5rem;
  flex-wrap: wrap;
}

.period-btn {
  padding: 0.4rem 1rem;
  border: 2px solid #1a1a2e;
  border-radius: 20px;
  background: #fff;
  cursor: pointer;
  font-weight: 600;
  transition: all 0.15s;
}

.period-btn.active, .period-btn:hover {
  background: #1a1a2e;
  color: #fff;
}

.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.stat-card {
  background: #fff;
  border-radius: 12px;
  padding: 1.25rem;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}

.stat-card h3 {
  margin: 0 0 1rem;
  font-size: 0.9rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  opacity: 0.5;
}

.stat-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
  font-size: 0.95rem;
}

.stat-row .val { font-weight: 700; }
.stat-row.highlight .val { color: #16a34a; font-size: 1.1rem; }

.battery-config {
  background: #fff;
  border-radius: 12px;
  padding: 1.25rem;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
  margin-bottom: 1.5rem;
}

.battery-config h3 { margin: 0 0 1rem; }

.preset-btns { display: flex; gap: 0.5rem; margin-bottom: 1rem; flex-wrap: wrap; }

.preset-btn {
  padding: 0.4rem 0.9rem;
  border: 2px solid #4f46e5;
  border-radius: 8px;
  background: #fff;
  color: #4f46e5;
  cursor: pointer;
  font-weight: 600;
}

.preset-btn.active, .preset-btn:hover {
  background: #4f46e5;
  color: #fff;
}

.config-inputs { display: flex; gap: 1rem; flex-wrap: wrap; }

.config-inputs label {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  font-size: 0.85rem;
  font-weight: 600;
}

.config-inputs input {
  padding: 0.4rem 0.6rem;
  border: 1.5px solid #d1d5db;
  border-radius: 6px;
  font-size: 0.95rem;
  width: 130px;
}

#simulate-btn {
  padding: 0.6rem 1.5rem;
  background: #4f46e5;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  align-self: flex-end;
}

#simulate-btn:hover { background: #3730a3; }

.charts { display: grid; gap: 1.5rem; }

.chart-card {
  background: #fff;
  border-radius: 12px;
  padding: 1.25rem;
  box-shadow: 0 1px 4px rgba(0,0,0,0.08);
}

.chart-card h3 { margin: 0 0 1rem; }

.roi-highlight {
  background: #f0fdf4;
  border: 2px solid #16a34a;
  border-radius: 12px;
  padding: 1rem 1.25rem;
  margin-bottom: 1.5rem;
  display: flex;
  gap: 2rem;
  flex-wrap: wrap;
}

.roi-item { display: flex; flex-direction: column; }
.roi-label { font-size: 0.8rem; opacity: 0.6; text-transform: uppercase; }
.roi-value { font-size: 1.5rem; font-weight: 800; color: #16a34a; }

@media (max-width: 600px) {
  .stats-grid { grid-template-columns: 1fr; }
}
```

- [ ] **Step 2: Create `frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PV Batterie-Analyse</title>
  <link rel="stylesheet" href="/static/style.css">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
</head>
<body>
  <header>
    <h1>PV Batterie-Analyse — Chüngstrasse 8, Embrach</h1>
    <span id="last-sync">Laden...</span>
  </header>
  <main>
    <div class="period-bar" id="period-bar">
      <button class="period-btn active" data-period="7d">7 Tage</button>
      <button class="period-btn" data-period="1m">1 Monat</button>
      <button class="period-btn" data-period="3m">3 Monate</button>
      <button class="period-btn" data-period="6m">6 Monate</button>
      <button class="period-btn" data-period="9m">9 Monate</button>
      <button class="period-btn" data-period="1y">1 Jahr</button>
    </div>

    <div id="roi-highlight" class="roi-highlight" style="display:none">
      <div class="roi-item">
        <span class="roi-label">Jährliche Ersparnis</span>
        <span class="roi-value" id="roi-annual">—</span>
      </div>
      <div class="roi-item">
        <span class="roi-label">Amortisation</span>
        <span class="roi-value" id="roi-payback">—</span>
      </div>
      <div class="roi-item">
        <span class="roi-label">Ersparnis im Zeitraum</span>
        <span class="roi-value" id="roi-period">—</span>
      </div>
    </div>

    <div class="stats-grid">
      <div class="stat-card">
        <h3>Ohne Batterie</h3>
        <div class="stat-row"><span>Netzbezug</span><span class="val" id="wo-grid">—</span></div>
        <div class="stat-row"><span>Einspeisung</span><span class="val" id="wo-feed">—</span></div>
        <div class="stat-row"><span>Netzkosten</span><span class="val" id="wo-cost">—</span></div>
        <div class="stat-row"><span>Einspeise-Erlös</span><span class="val" id="wo-rev">—</span></div>
        <div class="stat-row highlight"><span>Netto</span><span class="val" id="wo-net">—</span></div>
      </div>
      <div class="stat-card">
        <h3>Mit Batterie</h3>
        <div class="stat-row"><span>Netzbezug</span><span class="val" id="wb-grid">—</span></div>
        <div class="stat-row"><span>Einspeisung</span><span class="val" id="wb-feed">—</span></div>
        <div class="stat-row"><span>Netzkosten</span><span class="val" id="wb-cost">—</span></div>
        <div class="stat-row"><span>Einspeise-Erlös</span><span class="val" id="wb-rev">—</span></div>
        <div class="stat-row highlight"><span>Netto</span><span class="val" id="wb-net">—</span></div>
      </div>
    </div>

    <div class="battery-config">
      <h3>Batterie-Konfigurator</h3>
      <div class="preset-btns">
        <button class="preset-btn active" data-cap="5">5 kWh</button>
        <button class="preset-btn" data-cap="10">10 kWh</button>
        <button class="preset-btn" data-cap="15">15 kWh</button>
      </div>
      <div class="config-inputs">
        <label>Kapazität (kWh)<input id="cap-input" type="number" value="5" min="1" step="0.5"></label>
        <label>Wirkungsgrad (%)<input id="eff-input" type="number" value="90" min="50" max="100"></label>
        <label>Investition (CHF)<input id="inv-input" type="number" value="8000" min="100" step="100"></label>
        <button id="simulate-btn">Simulieren</button>
      </div>
    </div>

    <div class="charts">
      <div class="chart-card">
        <h3>Tagesgang — Ø PV-Produktion vs. Verbrauch</h3>
        <canvas id="chart-daily-profile"></canvas>
      </div>
      <div class="chart-card">
        <h3>Energiefluss im Zeitraum</h3>
        <canvas id="chart-energy-flow"></canvas>
      </div>
      <div class="chart-card" id="chart-amort-card" style="display:none">
        <h3>Kumulierte Ersparnis mit Batterie</h3>
        <canvas id="chart-amortisation"></canvas>
      </div>
    </div>
  </main>
  <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 3: Create `frontend/app.js`**

```javascript
// State
let currentPeriod = "7d";
let currentData = null;
let currentSim = null;
const charts = {};

// Chart instances — destroy before recreating
function destroyChart(id) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

// Period buttons
document.getElementById("period-bar").addEventListener("click", (e) => {
  const btn = e.target.closest(".period-btn");
  if (!btn) return;
  document.querySelectorAll(".period-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  currentPeriod = btn.dataset.period;
  loadData();
});

// Preset battery buttons
document.querySelector(".preset-btns").addEventListener("click", (e) => {
  const btn = e.target.closest(".preset-btn");
  if (!btn) return;
  document.querySelectorAll(".preset-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  document.getElementById("cap-input").value = btn.dataset.cap;
});

// Simulate button
document.getElementById("simulate-btn").addEventListener("click", runSimulation);

async function loadData() {
  const resp = await fetch(`/api/data?period=${currentPeriod}`);
  currentData = await resp.json();
  renderEnergyFlow(currentData);
  renderDailyProfile(currentData);
  document.getElementById("last-sync").textContent =
    `Daten bis: ${new Date().toLocaleDateString("de-CH")}`;
  if (currentSim) runSimulation();
}

async function runSimulation() {
  const capacity_kwh = parseFloat(document.getElementById("cap-input").value);
  const efficiency = parseFloat(document.getElementById("eff-input").value) / 100;
  const investment_chf = parseFloat(document.getElementById("inv-input").value);

  const resp = await fetch("/api/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ period: currentPeriod, capacity_kwh, efficiency, investment_chf }),
  });
  currentSim = await resp.json();
  renderStats(currentSim);
  renderAmortisation(currentSim);
}

function renderStats(sim) {
  const wo = sim.without_battery;
  const wb = sim.with_battery;
  const fmt = (v) => `${v.toFixed(1)} kWh`;
  const fmtCHF = (v) => `CHF ${v.toFixed(2)}`;

  document.getElementById("wo-grid").textContent = fmt(wo.grid_consumption_kwh);
  document.getElementById("wo-feed").textContent = fmt(wo.grid_feed_in_kwh);
  document.getElementById("wo-cost").textContent = fmtCHF(wo.grid_cost_chf);
  document.getElementById("wo-rev").textContent = fmtCHF(wo.feed_in_revenue_chf);
  document.getElementById("wo-net").textContent = fmtCHF(wo.net_cost_chf);

  document.getElementById("wb-grid").textContent = fmt(wb.grid_consumption_kwh);
  document.getElementById("wb-feed").textContent = fmt(wb.grid_feed_in_kwh);
  document.getElementById("wb-cost").textContent = fmtCHF(wb.grid_cost_chf);
  document.getElementById("wb-rev").textContent = fmtCHF(wb.feed_in_revenue_chf);
  document.getElementById("wb-net").textContent = fmtCHF(wb.net_cost_chf);

  const roi = sim.roi;
  document.getElementById("roi-annual").textContent = `CHF ${roi.annual_savings_chf.toFixed(0)}/Jahr`;
  document.getElementById("roi-payback").textContent =
    roi.payback_years === Infinity ? "∞" : `${roi.payback_years} Jahre`;
  document.getElementById("roi-period").textContent = `CHF ${roi.period_savings_chf.toFixed(2)}`;
  document.getElementById("roi-highlight").style.display = "flex";
}

function renderDailyProfile(data) {
  destroyChart("daily-profile");
  if (!data.hourly || data.hourly.length === 0) return;

  // Average by hour-of-day
  const hourBuckets = Array.from({ length: 24 }, () => ({ pv: 0, consumption: 0, count: 0 }));
  for (const r of data.hourly) {
    const h = new Date(r.timestamp).getHours();
    hourBuckets[h].pv += r.pv_production;
    hourBuckets[h].consumption += r.self_consumption + r.grid_consumption;
    hourBuckets[h].count += 1;
  }
  const labels = hourBuckets.map((_, i) => `${i}:00`);
  const pvAvg = hourBuckets.map(b => b.count ? +(b.pv / b.count).toFixed(3) : 0);
  const consAvg = hourBuckets.map(b => b.count ? +(b.consumption / b.count).toFixed(3) : 0);

  const ctx = document.getElementById("chart-daily-profile").getContext("2d");
  charts["daily-profile"] = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "PV-Produktion (kWh)", data: pvAvg, borderColor: "#f59e0b", backgroundColor: "rgba(245,158,11,0.1)", fill: true, tension: 0.4 },
        { label: "Verbrauch (kWh)", data: consAvg, borderColor: "#6366f1", backgroundColor: "rgba(99,102,241,0.1)", fill: true, tension: 0.4 },
      ],
    },
    options: { responsive: true, plugins: { legend: { position: "top" } } },
  });
}

function renderEnergyFlow(data) {
  destroyChart("energy-flow");
  if (!data.daily || data.daily.length === 0) return;

  const labels = data.daily.map(d => d.date);
  const ctx = document.getElementById("chart-energy-flow").getContext("2d");
  charts["energy-flow"] = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Eigenverbrauch (kWh)", data: data.daily.map(d => +d.self_consumption.toFixed(2)), backgroundColor: "#f59e0b" },
        { label: "Einspeisung (kWh)", data: data.daily.map(d => +d.grid_feed_in.toFixed(2)), backgroundColor: "#10b981" },
        { label: "Netzbezug (kWh)", data: data.daily.map(d => +d.grid_consumption.toFixed(2)), backgroundColor: "#6366f1" },
      ],
    },
    options: { responsive: true, scales: { x: { stacked: true }, y: { stacked: false } }, plugins: { legend: { position: "top" } } },
  });
}

function renderAmortisation(sim) {
  destroyChart("amortisation");
  const roi = sim.roi;
  if (!roi || roi.annual_savings_chf <= 0) return;

  const years = Math.min(Math.ceil(roi.payback_years) + 5, 30);
  const labels = Array.from({ length: years + 1 }, (_, i) => `Jahr ${i}`);
  const cumSavings = labels.map((_, i) => +(i * roi.annual_savings_chf).toFixed(2));
  const investLine = labels.map(() => sim.battery.investment_chf);

  document.getElementById("chart-amort-card").style.display = "block";
  const ctx = document.getElementById("chart-amortisation").getContext("2d");
  charts["amortisation"] = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Kumulierte Ersparnis (CHF)", data: cumSavings, borderColor: "#10b981", backgroundColor: "rgba(16,185,129,0.1)", fill: true, tension: 0.3 },
        { label: "Investition (CHF)", data: investLine, borderColor: "#ef4444", borderDash: [6, 3], pointRadius: 0 },
      ],
    },
    options: { responsive: true, plugins: { legend: { position: "top" } } },
  });
}

// Init
loadData();
```

- [ ] **Step 4: Test frontend in browser**

Start the backend:
```bash
uvicorn backend.main:app --reload
```

Open `http://localhost:8000` — the dashboard should load.

Check:
- Period buttons switch correctly
- "Simulieren" button triggers POST /api/simulate
- Charts render (may be empty if no data yet)

- [ ] **Step 5: Commit**

```bash
git add frontend/
git commit -m "feat: web dashboard with Chart.js visualizations"
```

---

## Task 10: Update Solar Manager Client After Exploration

**Files:**
- Modify: `backend/solar_manager.py`

This task depends on completing Task 4's manual API exploration. Do this task after you have confirmed:
- The exact base URL
- The authentication endpoint and response format
- The data endpoint path and query parameters
- The field names in the API response

- [ ] **Step 1: Update `BASE_URL` and auth endpoint**

In `backend/solar_manager.py`, update the `_authenticate` method with the confirmed endpoint and token field name.

- [ ] **Step 2: Update `get_hourly_data` field mapping**

Update the field name mapping in the list comprehension to use the confirmed API field names. Remove the fallback `.get()` aliases once confirmed.

- [ ] **Step 3: Test manually**

```bash
# Set credentials in .env, then:
python -c "
from backend.solar_manager import SolarManagerClient
from datetime import datetime, timedelta, timezone
c = SolarManagerClient()
end = datetime.now(tz=timezone.utc)
start = end - timedelta(days=7)
data = c.get_hourly_data(start, end)
print(f'Got {len(data)} readings')
print('First:', data[0] if data else 'empty')
"
```

Expected: A list of hourly dicts with the correct field values.

- [ ] **Step 4: Trigger historical sync and verify data in DB**

```bash
python -c "
from backend.sync import sync_historical
sync_historical(months=12)
"
```

Then check the DB:
```bash
python -c "
from backend.database import SessionLocal
from backend.models import EnergyData
db = SessionLocal()
count = db.query(EnergyData).count()
print(f'Rows in DB: {count}')
first = db.query(EnergyData).order_by(EnergyData.timestamp).first()
print(f'Oldest: {first.timestamp if first else None}')
"
```

- [ ] **Step 5: Commit**

```bash
git add backend/solar_manager.py
git commit -m "feat: Solar Manager API client updated with confirmed endpoints"
```

---

## Task 11: Railway Deployment

**Files:**
- No new files — uses existing `Procfile`, `railway.toml`

- [ ] **Step 1: Push all changes to GitHub**

```bash
git push origin main
```

- [ ] **Step 2: Create Railway project**

1. Go to [railway.app](https://railway.app) and log in
2. Click "New Project" → "Deploy from GitHub repo"
3. Select `Mull-Droid-974/PV_mit_Batterie`

- [ ] **Step 3: Add PostgreSQL database**

In the Railway dashboard:
1. Click "+ New" → "Database" → "Add PostgreSQL"
2. Railway will set `DATABASE_URL` automatically in the service environment

- [ ] **Step 4: Set environment variables**

In the Railway service settings → Variables, add:
```
SOLAR_MANAGER_EMAIL=your@email.com
SOLAR_MANAGER_PASSWORD=yourpassword
SOLAR_MANAGER_BASE_URL=https://cloud.solarmanager.ch
GRID_PRICE_CHF=0.32
FEED_IN_PRICE_CHF=0.08
```

- [ ] **Step 5: Deploy and verify**

Railway will auto-deploy on push. Check the deployment logs for:
- "Database tables created/verified"
- "Starting historical sync (12 months)"
- "Scheduler started"
- Uvicorn listening on port

- [ ] **Step 6: Open the public URL**

Railway provides a `.railway.app` URL. Open it — the dashboard should load with live data.

---

## Self-Review Checklist

- [x] **Spec coverage:** All spec sections covered — architecture (Tasks 1, 8), data model (Task 2), simulation (Task 3), Solar Manager API (Tasks 4, 10), sync worker (Task 5), REST endpoints (Tasks 6, 7), dashboard UI (Task 9), deployment (Task 11). Future forecast feature intentionally out of scope.
- [x] **No placeholders:** All code steps contain complete, runnable code. Solar Manager field names use `.get()` with fallbacks, explicitly documented as "update after exploration".
- [x] **Type consistency:** `HourlyReading`, `BatteryScenario`, `SimulationResult` defined in Task 3 and used identically in Tasks 7 and 9. `PERIOD_MAP` defined identically in Tasks 6 and 7.
- [x] **Test coverage:** simulation.py (4 tests), data router (3 tests), simulate router (3 tests), models (1 test). Solar Manager client tested manually in Task 10 (no mock — exploration-dependent).
