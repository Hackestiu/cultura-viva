"""
GPS Minimap - MPU application entry point.

Polls the MCU for the current position and writes it to a small
JSON file that any other process (a web dashboard, a Brick, your
own minimap code) can read to know where the user is right now.
"""

import json
import logging
import os
import time

try:
    from arduino.app_utils import App, Bridge
except ModuleNotFoundError:
    App = None
    Bridge = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("gps_minimap")

POSITION_FILE = os.path.expanduser("~/gps_minimap/position.json")
POLL_INTERVAL = 1.0  # seconds, matches the NEO-6M's typical 1 Hz update rate

os.makedirs(os.path.dirname(POSITION_FILE), exist_ok=True)


def _write_position(lat: float, lon: float, valid: bool) -> None:
    payload = {"lat": lat, "lon": lon, "valid": valid, "updated_at": time.time()}
    tmp_path = POSITION_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    os.replace(tmp_path, POSITION_FILE)  # atomic on the same filesystem


def run_app() -> None:
    if App is None:
        raise RuntimeError("Arduino App Lab is unavailable; use the host tests instead")

    def loop():
        try:
            if Bridge is None:
                raise RuntimeError("Bridge unavailable")

            raw = Bridge.call("get_position")
            if raw is None:
                return

            parts = raw.split(";")
            if len(parts) != 3:
                raise ValueError(f"Unexpected GPS payload: {raw!r}")

            lat_str, lon_str, valid_str = parts
            lat, lon = float(lat_str), float(lon_str)
            valid = valid_str.strip().lower() in ("1", "true")
            _write_position(lat, lon, valid)
            if valid:
                log.info("Position: %.6f, %.6f", lat, lon)
        except Exception as exc:
            log.debug("Position poll failed: %s", exc)

        time.sleep(POLL_INTERVAL)

    App.run(user_loop=loop)


if __name__ == "__main__":
    run_app()