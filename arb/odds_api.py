"""Minimal client for The Odds API v4 (https://the-odds-api.com)."""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

BASE = "https://api.the-odds-api.com/v4"


class OddsAPIError(RuntimeError):
    pass


def _get(path: str, params: dict, retries: int = 3) -> tuple[object, dict]:
    for attempt in range(retries):
        try:
            return _get_once(path, params)
        except OddsAPIError as e:
            if "HTTP 429" not in str(e) or attempt == retries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))  # rate limited: back off and retry
    raise AssertionError("unreachable")


def _get_once(path: str, params: dict) -> tuple[object, dict]:
    url = f"{BASE}{path}?{urllib.parse.urlencode(params)}"
    headers = {"User-Agent": "arb-scanner/1.0", "x-api-key": api_key()}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            quota = {
                "remaining": resp.headers.get("x-requests-remaining"),
                "used": resp.headers.get("x-requests-used"),
            }
            return json.load(resp), quota
    except urllib.error.HTTPError as e:
        raise OddsAPIError(f"HTTP {e.code}: {e.read().decode(errors='replace')}") from e


def api_key() -> str:
    """Key from ODDS_API_KEY. Sent as the x-api-key header (never in the URL).

    In Claude Code cloud sessions the key is stored as a network secret and the
    proxy fills in this header, so a placeholder value is used when unset.
    """
    return os.environ.get("ODDS_API_KEY", "injected-by-proxy")


def list_sports() -> list[dict]:
    data, _ = _get("/sports", {})
    return data  # type: ignore[return-value]


def get_odds(sport: str, regions: str, markets: str) -> tuple[list[dict], dict]:
    data, quota = _get(
        f"/sports/{sport}/odds",
        {
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal",
            "dateFormat": "iso",
        },
    )
    return data, quota  # type: ignore[return-value]


def get_events(sport: str) -> list[dict]:
    """Upcoming events for a sport. Free: does not use API quota."""
    data, _ = _get(f"/sports/{sport}/events", {"dateFormat": "iso"})
    return data  # type: ignore[return-value]
