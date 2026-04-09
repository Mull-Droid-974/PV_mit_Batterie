"""
Solar Manager API client.

Confirmed endpoints (verified 2026-04-09):
- POST https://cloud.solar-manager.ch/v1/oauth/login
  Body: {"email": "...", "password": "..."}
  Response: {"accessToken": "...", "refreshToken": "...", ...}

- GET  https://cloud.solar-manager.ch/v1/users
  Response: [{"sm_id": "...", ...}]

- GET  https://cloud.solar-manager.ch/v3/users/{smId}/data/range
  Params: from (ISO datetime), to (ISO datetime), interval (3600 for hourly)
  Response: {"data": [{"t": "...", "pWh": ..., "iWh": ..., "eWh": ..., "cPvWh": ...}, ...]}
  All energy values in Watt-hours (Wh) → divide by 1000 for kWh.

Note: uses synchronous httpx — safe for APScheduler background jobs.
Do NOT call from async FastAPI route handlers without wrapping in a thread.
"""
import os
from datetime import datetime
import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = "https://cloud.solar-manager.ch"


class SolarManagerError(Exception):
    pass


class SolarManagerClient:
    def __init__(self, email: str = "", password: str = ""):
        self._email = email or os.getenv("SOLAR_MANAGER_EMAIL", "")
        self._password = password or os.getenv("SOLAR_MANAGER_PASSWORD", "")
        self._token: str | None = None
        self._sm_id: str | None = None

    def _authenticate(self) -> str:
        """POST /v1/oauth/login, return bearer access token."""
        resp = httpx.post(
            f"{BASE_URL}/v1/oauth/login",
            json={"email": self._email, "password": self._password},
            timeout=30,
        )
        if resp.status_code != 200:
            raise SolarManagerError(f"Auth failed: {resp.status_code} {resp.text}")
        return resp.json()["accessToken"]

    def _get_token(self) -> str:
        if not self._token:
            self._token = self._authenticate()
        return self._token

    def _get_sm_id(self) -> str:
        """GET /v1/users, return sm_id of the first user."""
        if self._sm_id:
            return self._sm_id
        resp = httpx.get(
            f"{BASE_URL}/v1/users",
            headers={"Authorization": f"Bearer {self._get_token()}"},
            timeout=30,
        )
        if resp.status_code != 200:
            raise SolarManagerError(f"Failed to get users: {resp.status_code} {resp.text}")
        users = resp.json()
        if not users:
            raise SolarManagerError("No users found in Solar Manager account")
        self._sm_id = users[0]["sm_id"]
        return self._sm_id

    def get_hourly_data(self, start: datetime, end: datetime, _retry: bool = True) -> list[dict]:
        """
        Fetch hourly energy data between start and end.
        Returns list of dicts with keys:
          timestamp, pv_production, grid_consumption, grid_feed_in, self_consumption
        All values in kWh.

        API returns Wh → divide by 1000 for kWh.
        """
        token = self._get_token()
        sm_id = self._get_sm_id()
        resp = httpx.get(
            f"{BASE_URL}/v3/users/{sm_id}/data/range",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "from": start.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "to": end.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                "interval": 3600,
            },
            timeout=60,
        )
        if resp.status_code == 401:
            if not _retry:
                raise SolarManagerError("Auth failed after token refresh (persistent 401)")
            self._token = self._authenticate()
            self._sm_id = None
            return self.get_hourly_data(start, end, _retry=False)
        if resp.status_code != 200:
            raise SolarManagerError(f"Data fetch failed: {resp.status_code} {resp.text}")

        raw = resp.json()
        return [
            {
                "timestamp": item["t"],
                "pv_production": float(item.get("pWh", 0)) / 1000,
                "grid_consumption": float(item.get("iWh", 0)) / 1000,
                "grid_feed_in": float(item.get("eWh", 0)) / 1000,
                "self_consumption": float(item.get("cPvWh", 0)) / 1000,
            }
            for item in raw.get("data", [])
        ]
