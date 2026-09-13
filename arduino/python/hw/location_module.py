"""
Resolves the current site, from a manual override or from GPS proximity.

Reference coordinates live in `locations/locations.json` (id, name, lat, lon,
radius_m), not in this file -- adding a site is a data edit. The sketch exposes
the raw fix over Serial1 + TinyGPSPlus through has_gps_fix(), get_gps_lat() and
get_gps_lon(); resolve() turns that into a site id.

Three ways a site is decided, in order:

  override -- an operator forced it (CULTURA_LOCATION, or set_override() at
              runtime). GPS is not consulted at all.
  gps      -- there is a fix and it falls inside some site's radius_m. The
              nearest such site wins.
  default  -- no fix, or the fix is outside every radius (the visitor is
              somewhere we have no content for). The default site is used so
              the device stays usable, and needs_confirmation is set on the
              result so the caller can ask the visitor to pick a site instead.

The radius matters: without it the nearest site wins from any distance, so a
device switched on in Girona would confidently claim to be at the Sagrada
Família.
"""

import json
import math
import time
from dataclasses import dataclass

from config import DEFAULT_LOCATION, LOCATION_OVERRIDE, LOCATIONS_CONFIG_FILE
from logging_setup import logger

try:
    from arduino.app_utils import Bridge  # type: ignore[import]
except ModuleNotFoundError:
    Bridge = None

# Used only if locations.json is missing or unreadable, so a corrupted data file
# degrades to the two original sites instead of leaving the device with none.
_FALLBACK_SITES = [
    {"id": "park_guell", "name": "Park Güell", "lat": 41.413631, "lon": 2.152482, "radius_m": 400},
    {"id": "sagrada_familia", "name": "Sagrada Família", "lat": 41.403629, "lon": 2.174349, "radius_m": 300},
]

# Radius for an entry in locations.json that does not give one.
_DEFAULT_RADIUS_M = 300.0

# A resolved site is reused for this long instead of re-reading the fix. loop()
# asks for the current site every POLL_INTERVAL (0.1s); a visitor does not walk
# between monuments in that time, and each read is three Bridge round-trips.
_CACHE_SECONDS = 5.0

_EARTH_RADIUS_M = 6371000.0


@dataclass(frozen=True)
class Site:
    id: str
    name: str
    lat: float
    lon: float
    radius_m: float


@dataclass(frozen=True)
class LocationFix:
    """What resolve() decided, and on what grounds."""

    site: str
    source: str  # "override" | "gps" | "default"
    lat: float | None = None
    lon: float | None = None
    distance_m: float | None = None
    nearest: str | None = None
    needs_confirmation: bool = False


def _haversine_m(lat1, lon1, lat2, lon2) -> float:
    """Returns the great-circle distance in meters between two lat/lon points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


class LocationRegistry:
    def __init__(self, override: str | None = LOCATION_OVERRIDE):
        """Loads the site table from LOCATIONS_CONFIG_FILE (falling back to the built-in sites if it cannot be read) and applies the given manual override, if any."""
        self._sites: dict[str, Site] = {}
        self._default = DEFAULT_LOCATION
        self._override: str | None = None
        self._cached: LocationFix | None = None
        self._cached_at = 0.0
        self._logged: tuple | None = None

        self._load_sites()
        if override:
            self.set_override(override)

    # -- site table ---------------------------------------------------------

    def _load_sites(self) -> None:
        """Reads the site definitions and the default site id from LOCATIONS_CONFIG_FILE, skipping malformed entries. Falls back to the built-in sites if the file is absent or unreadable."""
        entries = _FALLBACK_SITES
        try:
            with open(LOCATIONS_CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            entries = data.get("locations") or _FALLBACK_SITES
            if data.get("default"):
                self._default = data["default"]
        except FileNotFoundError:
            logger.warning(
                "{} not found. Using built-in site coordinates.", LOCATIONS_CONFIG_FILE
            )
        except (OSError, ValueError) as exc:
            logger.warning(
                "Could not read {}: {}. Using built-in site coordinates.",
                LOCATIONS_CONFIG_FILE,
                exc,
            )

        for entry in entries:
            try:
                site_id = entry["id"]
                site = Site(
                    id=site_id,
                    name=entry.get("name", site_id),
                    lat=float(entry["lat"]),
                    lon=float(entry["lon"]),
                    radius_m=float(entry.get("radius_m", _DEFAULT_RADIUS_M)),
                )
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("Skipping malformed location entry {!r}: {}", entry, exc)
                continue
            self._sites[site.id] = site

        if self._default not in self._sites:
            logger.warning(
                "Default site {!r} is not in the site table; falling back to {!r}.",
                self._default,
                DEFAULT_LOCATION,
            )
            self._default = DEFAULT_LOCATION

        logger.info(
            "Sites loaded: {} (default {!r}).",
            ", ".join(sorted(self._sites)) or "none",
            self._default,
        )

    def sites(self) -> dict[str, Site]:
        """Returns the registered sites keyed by id."""
        return dict(self._sites)

    def display_name(self, site_id: str) -> str:
        """Returns the human-readable name of a site, or a title-cased form of the id if it is not registered."""
        site = self._sites.get(site_id)
        return site.name if site else site_id.replace("_", " ").title()

    @property
    def default(self) -> str:
        """The site used when GPS cannot place the visitor."""
        return self._default

    # -- manual override ----------------------------------------------------

    def set_override(self, site_id: str | None) -> bool:
        """Forces a site regardless of GPS (pass None to clear it). Returns False, leaving any previous override in place, if the id is not registered."""
        if site_id is None:
            self.clear_override()
            return True
        if site_id not in self._sites:
            logger.warning(
                "Cannot override to unknown site {!r}. Known sites: {}.",
                site_id,
                ", ".join(sorted(self._sites)) or "none",
            )
            return False
        self._override = site_id
        self._invalidate()
        logger.info("Location overridden to {!r}. GPS will be ignored.", site_id)
        return True

    def clear_override(self) -> bool:
        """Drops any manual override so the site is resolved from GPS again. Returns True if an override was actually in place."""
        had = self._override is not None
        self._override = None
        self._invalidate()
        if had:
            logger.info("Location override cleared. Resolving from GPS again.")
        return had

    @property
    def override(self) -> str | None:
        """The site currently forced by an override, or None."""
        return self._override

    def _invalidate(self) -> None:
        self._cached = None
        self._cached_at = 0.0
        self._logged = None

    # -- resolution ---------------------------------------------------------

    def nearest_to(self, lat: float, lon: float) -> tuple[str | None, str | None, float | None]:
        """Finds the site containing the given coordinates.

        Returns (site_id, nearest_id, distance_m): site_id is the nearest site whose
        radius_m contains the point, or None when the point is outside every radius.
        nearest_id and distance_m describe the closest site either way, so a caller
        can report how far off the visitor is.
        """
        if not self._sites:
            return (None, None, None)
        nearest = min(
            self._sites.values(),
            key=lambda s: _haversine_m(lat, lon, s.lat, s.lon),
        )
        distance = _haversine_m(lat, lon, nearest.lat, nearest.lon)
        inside = nearest.id if distance <= nearest.radius_m else None
        return (inside, nearest.id, distance)

    def _read_fix(self) -> tuple[float, float] | None:
        """Reads the current GPS fix from the sketch over Bridge, or None if the Bridge is unavailable, there is no fix, or the RPC call fails."""
        if Bridge is None:
            return None
        try:
            if not Bridge.call("has_gps_fix"):
                return None
            lat = Bridge.call("get_gps_lat")
            lon = Bridge.call("get_gps_lon")
        except Exception as exc:
            logger.warning("GPS read over Bridge failed: {}", exc)
            return None
        if not lat or not lon:
            # TinyGPSPlus reports 0.0/0.0 before it has really locked on.
            return None
        return (float(lat), float(lon))

    def resolve(self, force: bool = False) -> LocationFix:
        """Decides the current site -- from the override, else from the GPS fix, else from the default -- and returns the decision with its grounds. The result is cached for a few seconds; pass force=True to re-read the fix now."""
        now = time.monotonic()
        if not force and self._cached and (now - self._cached_at) < _CACHE_SECONDS:
            return self._cached

        fix = self._compute()
        # Logged on change only: resolve() runs every few seconds, and a device
        # sitting outside every radius would otherwise fill the log with one
        # identical line per cache miss for the whole visit.
        signature = (fix.site, fix.source, fix.nearest)
        if force or signature != self._logged:
            self._log_fix(fix)
            self._logged = signature
        self._cached = fix
        self._cached_at = now
        return fix

    def _log_fix(self, fix: LocationFix) -> None:
        """Writes one line saying which site was chosen and why -- including the raw
        coordinates, so a fix that lands nowhere near a monument can be read off the
        log instead of guessed at."""
        name = self.display_name(fix.site)
        if fix.source == "override":
            logger.info(
                "Site {!r} ({}) forced by override -- GPS is not consulted.",
                fix.site,
                name,
            )
            return
        if fix.source == "gps":
            logger.info(
                "GPS fix {:.6f}, {:.6f} -> site {!r} ({}), {:.0f} m from its centre.",
                fix.lat,
                fix.lon,
                fix.site,
                name,
                fix.distance_m or 0.0,
            )
            return
        if fix.lat is None:
            logger.warning(
                "No GPS fix. Defaulting to {!r} ({}). Set CULTURA_LOCATION=<id> to "
                "force a site. Known sites: {}.",
                fix.site,
                name,
                ", ".join(sorted(self._sites)) or "none",
            )
            return
        nearest = self._sites.get(fix.nearest)
        logger.warning(
            "GPS fix {:.6f}, {:.6f} is {:.0f} m from the nearest monument ({} -- "
            "radius {:.0f} m): too far from every known site. Defaulting to {!r} ({}). "
            "Set CULTURA_LOCATION=<id> to force a site. Known sites: {}.",
            fix.lat,
            fix.lon,
            fix.distance_m or 0.0,
            nearest.name if nearest else fix.nearest,
            nearest.radius_m if nearest else 0.0,
            fix.site,
            name,
            ", ".join(sorted(self._sites)) or "none",
        )

    def _compute(self) -> LocationFix:
        if self._override:
            return LocationFix(site=self._override, source="override")

        coords = self._read_fix()
        if coords is None:
            return LocationFix(
                site=self._default, source="default", needs_confirmation=True
            )

        site_id, nearest, distance = self.nearest_to(*coords)
        if site_id is not None:
            return LocationFix(
                site=site_id,
                source="gps",
                lat=coords[0],
                lon=coords[1],
                distance_m=distance,
                nearest=nearest,
            )

        return LocationFix(
            site=self._default,
            source="default",
            lat=coords[0],
            lon=coords[1],
            distance_m=distance,
            nearest=nearest,
            needs_confirmation=True,
        )

    def current(self) -> str:
        """Returns the id of the site the device is currently at. Equivalent to resolve().site."""
        return self.resolve().site

    def needs_confirmation(self) -> bool:
        """Returns True when the site is a fallback rather than a real placement -- no fix, or a fix outside every site's radius -- so the caller can ask the visitor to confirm or override it."""
        return self.resolve().needs_confirmation
