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
