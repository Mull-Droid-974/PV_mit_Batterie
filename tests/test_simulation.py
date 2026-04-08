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
    # Pre-charge battery with surplus hour, then cover deficit in second hour
    battery = BatteryScenario(capacity_kwh=5.0, efficiency=1.0, investment_chf=8000.0)
    surplus_hour = make_reading(pv=3.0, grid_in=0.0, feed_out=2.0)
    deficit_hour = make_reading(pv=1.0, grid_in=1.0, feed_out=0.0)
    result = simulate_with_battery([surplus_hour, deficit_hour], battery, GRID_PRICE, FEED_IN_PRICE)
    # Battery charged 2.0 in hour 1, covers 1.0 deficit in hour 2 → 0 grid draw total
    assert result.grid_consumption_kwh == 0.0


def test_with_battery_efficiency_loss():
    # 2.0 kWh surplus charged at 90% efficiency → 1.8 kWh stored
    # Then 2.0 kWh deficit: battery delivers 1.8 * 0.9 = 1.62 kWh, grid covers 0.38 kWh
    battery = BatteryScenario(capacity_kwh=5.0, efficiency=0.9, investment_chf=8000.0)
    surplus = make_reading(pv=2.0, grid_in=0.0, feed_out=2.0)
    deficit = make_reading(pv=0.0, grid_in=2.0, feed_out=0.0)
    result = simulate_with_battery([surplus, deficit], battery, GRID_PRICE, FEED_IN_PRICE)
    assert result.grid_feed_in_kwh == 0.0
    assert abs(result.grid_consumption_kwh - 0.38) < 0.01


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
    # period_savings = 16.0 - 5.6 = 10.4, annual = 10.4 * 365/30 ≈ 126.53
    assert abs(roi["annual_savings_chf"] - 126.53) < 0.01
    assert abs(roi["payback_years"] - 63.2) < 0.1
