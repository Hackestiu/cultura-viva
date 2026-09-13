"""
Minimap state management for the Park Güell and
Sagrada Família displays.

Translates human-readable landmark identifiers (a landmark code such as
'FN', or a numeric index) into the RPC calls exposed by the sketch:
mark_landmark_visited(id), set_location_by_id(id), set_location_xy(x, y),
and reset_minimap(). Deciding when to mark a landmark visited or move the
"you are here" marker is outside the scope of this module — call
mark_visited(), set_position(), or reset() from main.py or wherever the
triggering event (GPS, button, knob, proximity...) occurs.

mark_detected(location, vision_label) is the high-level entry point used by
the vision pipeline: it maps a label returned by VisionClassifier.classify()
to a landmark code and marks it visited on the minimap.
"""

import json

from config import MINIMAP_DIR
from logging_setup import logger

try:
    from arduino.app_utils import Bridge  # type: ignore[import]
except ModuleNotFoundError:
    Bridge = None

LANDMARKS_FILES = {
    "park_guell": MINIMAP_DIR / "landmarks_guell.json",
    "sagrada_familia": MINIMAP_DIR / "landmarks_sagrada.json",
    "casa_batllo": MINIMAP_DIR / "landmarks_batllo.json",
}


# Mapping: vision model label  →  landmark code (per location)
# Keys must match the labels in models/vision/<location>/labels.json exactly.
# Values must match the 'code' field in minimapa/landmarks.json.
VISION_LABEL_TO_LANDMARK: dict[str, dict[str, str]] = {
    "park_guell": {
        "escalinata_drac": "DR",
        "sala_hipostila": "HH",
        "placa_natura": "NS",
        "casa_museu": "CG",
        "3_viaductes": "TV",
        "turo_3_creus": "CH",
        "pavellons_consergeria": "PL",
    },
    "sagrada_familia": {
        "cupula": "CU",
        "facana_naixement": "FN",
        "facana_passio": "FP",
        "lateral_esquerra": "NL",
        "lateral_dreta": "NR",
        "laterals": "NL",
        "posterior": "PO",
        "torres": "TO",
    },
    "casa_batllo": {
        # Vision labels for Casa Batlló map to one of the two zones:
        # 'PS' = Pla Superior (roof + tower + noble floor)
        # 'PI' = Pla Inferior (ground floor arches + main facade)
        "pla_frontal_casa_batllo": "PS",  # full-facade shot -> upper zone
        "pla_inferior_casa_batllo": "PI",  # lower half shot -> lower zone
        "casa_batllo": "PS",              # generic building label
    },
}

LINKED_LANDMARKS: dict[str, tuple[tuple[str, ...], ...]] = {
    "sagrada_familia": (("NL", "NR"),),
}


class MinimapManager:
    def __init__(self):
        """Creates a manager with no active site and an empty landmark list; call set_location() before using it."""
        self._landmarks = []
        self._active_location = None
        self._visited: dict[str, set[int]] = {
            "park_guell": set(),
            "sagrada_familia": set(),
            "casa_batllo": set(),
        }

    def _load_landmarks(self, location: str):
        """Reads and returns the landmark list for a site from its JSON file, or an empty list if the file is missing or unregistered."""
        landmarks_file = LANDMARKS_FILES.get(location)
        if landmarks_file is None or not landmarks_file.exists():
            logger.warning(
                "Landmarks file not found for {}: {}", location, landmarks_file
            )
            return []
        with open(landmarks_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data["landmarks"]

    def set_location(self, location: str) -> bool:
        """Activates a monument site ('park_guell' or 'sagrada_familia'), loading its landmarks and switching the firmware's active tilemap via RPC if the site actually changes. Returns True once the site is active (or already was), and False for an unrecognized location."""
        if location not in LANDMARKS_FILES:
            logger.warning("Unknown location {!r}", location)
            return False
        if location == self._active_location:
            return True

        self._landmarks = self._load_landmarks(location)
        self._active_location = location
        map_ids = {"park_guell": 0, "sagrada_familia": 1, "casa_batllo": 2}
        map_id = map_ids.get(location, 0)
        if Bridge is None:
            logger.debug("[dry run] set_minimap_location({})", map_id)
            return True
        return bool(Bridge.call("set_minimap_location", map_id))

    def _resolve_id(self, label: str):
        """Resolves a landmark code (case-insensitive) or a numeric string index into the landmark's internal id, returning None if it cannot be matched against the active site's landmark list."""
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

    # Public API
    def is_completed(self, location: str | None = None) -> bool:
        """Returns True if all landmarks of the specified (or active) location are marked as visited."""
        loc = location or self._active_location
        if not loc:
            return False
        landmarks = self._load_landmarks(loc)
        if not landmarks:
            return False
        visited_set = self._visited.get(loc, set())
        return len(visited_set) >= len(landmarks)

    def get_progress(self, location: str | None = None) -> tuple[int, int]:
        """Returns (visited_count, total_count) for the specified (or active) location."""
        loc = location or self._active_location
        if not loc:
            return (0, 0)
        landmarks = self._load_landmarks(loc)
        visited_set = self._visited.get(loc, set())
        return (len(visited_set), len(landmarks))

    def mark_detected(self, location: str, vision_label: str) -> bool:
        """Marks as visited the landmark corresponding to a label recognized by the vision classifier for the given site. Returns False silently if the label is unknown or not yet mapped for that location."""
        location_map = VISION_LABEL_TO_LANDMARK.get(location)
        if location_map is None:
            logger.warning("No landmark mapping for location {!r}", location)
            return False

        code = location_map.get(vision_label)
        if code is None:
            return False

        logger.info(
            "Vision detected {!r} -> marking landmark {!r}", vision_label, code
        )
        return self.mark_visited(code)

    def mark_visited(self, label: str) -> bool:
        """Marks a landmark as visited on the display, identified by its code or numeric id. Returns True if the landmark was resolved and the RPC dispatched, False if the identifier is unknown."""
        landmark_id = self._resolve_id(label)
        if landmark_id is None:
            logger.warning("Unknown landmark: {!r}", label)
            return False

        linked_codes = (self._landmarks[landmark_id]["code"],)
        if self._active_location:
            for group in LINKED_LANDMARKS.get(self._active_location, ()):
                if linked_codes[0] in group:
                    linked_codes = group
                    break

        landmark_ids = [self._resolve_id(code) for code in linked_codes]
        landmark_ids = [id_ for id_ in landmark_ids if id_ is not None]

        if self._active_location:
            was_completed = self.is_completed(self._active_location)
            self._visited.setdefault(self._active_location, set()).update(landmark_ids)
            now_completed = self.is_completed(self._active_location)

            if not was_completed and now_completed:
                visited_count, total = self.get_progress(self._active_location)
                logger.success(
                    "MAP COMPLETED! Enhorabona! Has visitat tots els {} monuments "
                    "de {!r}! ({}/{})",
                    total,
                    self._active_location,
                    visited_count,
                    total,
                )

        if Bridge is None:
            logger.debug("[dry run] mark_landmark_visited({})", landmark_ids)
            return True
        return all(
            bool(Bridge.call("mark_landmark_visited", id_)) for id_ in landmark_ids
        )

    def set_position(self, label_or_xy) -> bool:
        """Moves the "you are here" marker, accepting either a landmark identifier (code or numeric id) or an explicit (x, y) coordinate pair. Returns True if the position update was dispatched successfully, False if a given identifier could not be resolved."""
        if isinstance(label_or_xy, (tuple, list)) and len(label_or_xy) == 2:
            x, y = label_or_xy
            if Bridge is None:
                logger.debug("[dry run] set_location_xy({}, {})", x, y)
                return True
            return bool(Bridge.call("set_location_xy", int(x), int(y)))

        landmark_id = self._resolve_id(str(label_or_xy))
        if landmark_id is None:
            logger.warning("Unknown landmark: {!r}", label_or_xy)
            return False
        if Bridge is None:
            logger.debug("[dry run] set_location_by_id({})", landmark_id)
            return True
        return bool(Bridge.call("set_location_by_id", landmark_id))

    def reset(self, location: str | None = None) -> bool:
        """Clears all visited-landmark states and the position marker on the display. Always returns True when the reset RPC is dispatched."""
        if location:
            self._visited[location] = set()
        else:
            for k in self._visited:
                self._visited[k] = set()
        if Bridge is None:
            logger.debug("[dry run] reset_minimap()")
            return True
        return bool(Bridge.call("reset_minimap"))
