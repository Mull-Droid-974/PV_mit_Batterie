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
