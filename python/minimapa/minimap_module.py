"""
Minimap state management for the Park Güell map display (switch D6 OFF).

This module translates human-readable landmark identifiers (e.g. 'DR', 3)
into RPC calls exposed by the sketch:
    mark_landmark_visited(id)
    set_location_by_id(id)
    set_location_xy(x, y)
    reset_minimap()

The trigger that decides when to mark a landmark as visited or move the
'you are here' marker is outside the scope of this module. Call
mark_visited(), set_position(), or reset() from main.py or wherever
the triggering event occurs (GPS, button, knob, proximity, etc.).
"""

import json

from config import MINIMAP_DIR

try:
    from arduino.app_utils import Bridge
except ModuleNotFoundError:
    Bridge = None

LANDMARKS_FILE = MINIMAP_DIR / "landmarks.json"


class MinimapManager:
    def __init__(self):
        self._landmarks = self._load_landmarks()

    def _load_landmarks(self):
        if not LANDMARKS_FILE.exists():
            print(f"[WARN] Landmarks file not found: {LANDMARKS_FILE}")
            return []
        with open(LANDMARKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data["landmarks"]

    def _resolve_id(self, label: str):
        """Returns the numeric landmark id for a landmark code (e.g. 'DR'),
        a numeric index as a string, or a landmark name.
        Returns None if label does not match any known landmark."""
        label = label.strip()
        if not label:
            return None
        for lm in self._landmarks:
            if label.upper() == lm["code"]:
                return lm["id"]
        if label.isdigit():
            idx = int(label)
            if 0 <= idx < len(self._landmarks):
                return idx
        return None

    # ---------- Public API ----------
    def mark_visited(self, label: str) -> bool:
        """Marks the landmark identified by label as visited.
        label may be a landmark code (e.g. 'DR') or a numeric index as a string.
        Returns True if the landmark was resolved and the RPC call was dispatched,
        False if label does not match any known landmark."""
        landmark_id = self._resolve_id(label)
        if landmark_id is None:
            print(f"[WARN] Unknown landmark: {label!r}")
            return False
        if Bridge is None:
            print(f"[dry run] mark_landmark_visited({landmark_id})")
            return True
        return bool(Bridge.call("mark_landmark_visited", landmark_id))

    def set_position(self, label_or_xy) -> bool:
        """Moves the 'you are here' marker on the minimap.
        label_or_xy may be a landmark code or numeric index (str or int),
        or a tuple/list (x, y) for an arbitrary pixel position.
        Returns True if the position was set, False if the landmark is unknown."""
        if isinstance(label_or_xy, (tuple, list)) and len(label_or_xy) == 2:
            x, y = label_or_xy
            if Bridge is None:
                print(f"[dry run] set_location_xy({x}, {y})")
                return True
            return bool(Bridge.call("set_location_xy", int(x), int(y)))

        landmark_id = self._resolve_id(str(label_or_xy))
        if landmark_id is None:
            print(f"[WARN] Unknown landmark: {label_or_xy!r}")
            return False
        if Bridge is None:
            print(f"[dry run] set_location_by_id({landmark_id})")
            return True
        return bool(Bridge.call("set_location_by_id", landmark_id))

    def reset(self) -> bool:
        """Clears all visited landmarks and the current position marker.
        Returns True if the reset RPC call was dispatched successfully."""
        if Bridge is None:
            print("[dry run] reset_minimap()")
            return True
        return bool(Bridge.call("reset_minimap"))
