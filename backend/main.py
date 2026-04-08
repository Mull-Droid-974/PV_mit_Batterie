import logging
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from backend.database import engine, SessionLocal
from backend.models import Base, EnergyData
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
    db = SessionLocal()
    try:
        count = db.query(EnergyData).count()
    finally:
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

# Serve frontend static files (frontend/ created in Task 9)
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(FRONTEND_DIR / "index.html")
