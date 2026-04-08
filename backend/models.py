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
