"""
Minimap state management for the Sagrada Família map display (switch D6 OFF).

This module translates human-readable landmark identifiers (e.g. 'FN', 3)
into RPC calls exposed by the sketch:
    mark_landmark_visited(id)
    set_location_by_id(id)
    set_location_xy(x, y)
    reset_minimap()

The trigger that decides when to mark a landmark as visited or move the
'you are here' marker is outside the scope of this module. Call
mark_visited(), set_position(), or reset() from main.py or wherever
the triggering event occurs (GPS, button, knob, proximity, etc.).

mark_detected(location, vision_label) is the high-level entry-point for the
vision pipeline: it maps the label returned by VisionClassifier.classify()
directly to a landmark code and marks it as visited on the minimap.
"""

import json

from config import MINIMAP_DIR

try:
    from arduino.app_utils import Bridge
except ModuleNotFoundError:
    Bridge = None

LANDMARKS_FILES = {
    "park_guell": MINIMAP_DIR / "landmarks_guell.json",
    "sagrada_familia": MINIMAP_DIR / "landmarks_sagrada.json",
}

# ---------------------------------------------------------------------------
# Mapping: vision model label  →  landmark code (per location)
# Keys must match the labels in models/vision/<location>/labels.json exactly.
# Values must match the 'code' field in minimapa/landmarks.json.
# ---------------------------------------------------------------------------
VISION_LABEL_TO_LANDMARK: dict[str, dict[str, str]] = {
    "park_guell": {
        "escalinata_drac":      "DR",  # Dragon Stairway
        "sala_hipostila":       "HH",  # Hypostyle Hall
        "placa_natura":         "NS",  # Nature Square
        "casa_museu":           "CG",  # Casa Museu Gaudí
        "3_viaductes":          "TV",  # The Three Viaducts
        "turo_3_creus":         "CH",  # Calvary Hill
        "pavellons_consergeria":"PL",  # Porter's Lodge
    },
    "sagrada_familia": {
        "cupula":              "CU",  # Cúpula / Absis interior
        "facana_naixement":    "FN",  # Façana del Naixement (Nativity)
        "facana_passio":       "FP",  # Façana de la Passió  (Passion)
        "lateral_esquerra":    "NL",  # Nau Lateral esquerra
        "lateral_dreta":       "NR",  # Nau Lateral dreta
        "laterals":            "NL",  # Nau Lateral genèric → esquerra
        "posterior":           "PO",  # Absis / Posterior exterior
        "torres":              "TO",  # Torres del Creuer
    },
}


class MinimapManager:
    def __init__(self):
        self._landmarks = []
        self._active_location = None

    def _load_landmarks(self, location: str):
        landmarks_file = LANDMARKS_FILES.get(location)
        if landmarks_file is None or not landmarks_file.exists():
            print(f"[WARN] Landmarks file not found for {location}: {landmarks_file}")
            return []
        with open(landmarks_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data["landmarks"]

    def set_location(self, location: str) -> bool:
        """Selects the map and landmark data used by the firmware."""
        if location not in LANDMARKS_FILES:
            print(f"[WARN] minimap: unknown location '{location}'")
            return False
        if location == self._active_location:
            return True

        self._landmarks = self._load_landmarks(location)
        self._active_location = location
        map_id = 1 if location == "sagrada_familia" else 0
        if Bridge is None:
            print(f"[dry run] set_minimap_location({map_id})")
            return True
        return bool(Bridge.call("set_minimap_location", map_id))

    def _resolve_id(self, label: str):
        """Returns the numeric landmark id for a landmark code (e.g. 'FN'),
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
    def mark_detected(self, location: str, vision_label: str) -> bool:
        """Marks the minimap landmark that corresponds to *vision_label* for
        *location* as visited (illuminated on the minimap).

        Called automatically by the Cultura Viva pipeline after VisionClassifier
        returns a recognised, non-unknown element.

        :param location:     'park_guell' or 'sagrada_familia'.
        :param vision_label: Raw label from VisionClassifier.classify().
        :returns:            True if the landmark was resolved and the RPC call
                             was dispatched; False if the label has no mapping or
                             the landmark code is None (location not yet mapped).
        """
        location_map = VISION_LABEL_TO_LANDMARK.get(location)
        if location_map is None:
            print(f"[WARN] minimap: no landmark mapping for location '{location}'")
            return False

        code = location_map.get(vision_label)
        if code is None:
            # Label is either unknown/non-monument or not yet mapped.
            return False

        print(f"[INFO] minimap: vision detected '{vision_label}' -> marking landmark '{code}'")
        return self.mark_visited(code)

    def mark_visited(self, label: str) -> bool:
        """Marks the landmark identified by label as visited.
        label may be a landmark code (e.g. 'FN') or a numeric index as a string.
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