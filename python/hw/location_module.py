"""
Current location (Park Güell / Sagrada Família), determined by GPS PROXIMITY.

The sketch exposes raw GPS fix data via Serial1 + TinyGPSPlus:
has_gps_fix(), get_gps_lat(), get_gps_lon().
This module holds reference coordinates for both known sites and computes
the nearest location using the Haversine distance formula (~2km apart).

Two locations in Barcelona:
    park_guell      -> 41.414052, 2.152335
    sagrada_familia -> 41.403879, 2.173909
"""

import json
import math

from config import DEFAULT_LOCATION, LOCATIONS_CONFIG_FILE

try:
    from arduino.app_utils import Bridge
except ModuleNotFoundError:
    Bridge = None

_DEFAULT_LOCATIONS = {
    "park_guell": {"lat": 41.414052, "lon": 2.152335},
    "sagrada_familia": {"lat": 41.403879, "lon": 2.173909},
}

_EARTH_RADIUS_M = 6371000.0


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


class LocationRegistry:
    def __init__(self):
        self._locations = dict(_DEFAULT_LOCATIONS)
        self._load_overrides()

    def _load_overrides(self) -> None:
        if not LOCATIONS_CONFIG_FILE.exists():
            return
        try:
            with open(LOCATIONS_CONFIG_FILE, "r", encoding="utf-8") as f:
                overrides = json.load(f)
            for name, info in overrides.items():
                if isinstance(info, dict) and "lat" in info and "lon" in info:
                    self._locations[name] = info
        except (OSError, ValueError) as exc:
            print(f"[WARN] Could not read {LOCATIONS_CONFIG_FILE}: {exc}")

    def nearest_to(self, lat: float, lon: float) -> str:
        """Returns the name of the nearest known location to (lat, lon)."""
        if not self._locations:
            return DEFAULT_LOCATION
        best_name = min(
            self._locations,
            key=lambda name: _haversine_m(
                lat, lon, self._locations[name]["lat"], self._locations[name]["lon"]
            ),
        )
        return best_name

    def current(self) -> str:
        """Queries GPS via Bridge and returns the nearest known location name,
        or DEFAULT_LOCATION ('park_guell') if no GPS fix is available yet (e.g. testing indoors)."""
        if Bridge is None:
            return DEFAULT_LOCATION
        try:
            if not Bridge.call("has_gps_fix"):
                return DEFAULT_LOCATION
            lat = Bridge.call("get_gps_lat")
            lon = Bridge.call("get_gps_lon")
            if lat and lon:
                return self.nearest_to(lat, lon)
        except Exception:
            pass
        return DEFAULT_LOCATION
