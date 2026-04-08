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
