"""
Gestio de l'estat del minimapa de Park Guell (switch D6 OFF).

DIFERENCIA CLAU respecte a la versio standalone original d'aquest
sketch: alla, un script separat (mark_visited.py) es connectava per
PORT SERIE des d'un PC extern i enviava linies de text ("V3",
"P40,90", "R"...). Aqui el Python ja corre DINS de la UNO Q i parla
amb el sketch pel mateix Bridge RPC que fan servir la resta de
moduls (camera_module.py, etc.) -- no hi ha cap port serie extern
de per mig.

Aquest modul nomes fa de traductor entre una etiqueta humana
("DR", 3, "@DR", "@40,110", "reset") i les crides RPC que exposa el
sketch:
    mark_landmark_visited(id)
    set_location_by_id(id)
    set_location_xy(x, y)
    reset_minimap()

D'ON VE EL TRIGGER (quin event marca un landmark com a visitat o
mou el "you are here")? Es queda FORA d'abast d'aquest modul, tal
com ja ho era a l'script original -- pot ser GPS, un boto, el Knob,
proximitat... el que decideixis, nomes has de cridar els metodes
d'aquesta classe (mark_visited/set_position/reset) des d'on calgui
(p.ex. main.py).
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
            print(f"[WARN] No s'ha trobat {LANDMARKS_FILE}")
            return []
        with open(LANDMARKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data["landmarks"]

    def _resolve_id(self, label: str):
        """Tradueix un codi ('DR'), un nom, o un id numeric a l'id
        numeric del landmark. Retorna None si no es reconeix."""
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

    # ---------- API publica ----------
    def mark_visited(self, label: str) -> bool:
        """Marca un landmark com a visitat (per codi, p.ex. 'DR', o
        per id numeric). Retorna True si s'ha pogut resoldre i enviar."""
        landmark_id = self._resolve_id(label)
        if landmark_id is None:
            print(f"[WARN] Landmark desconegut: {label!r}")
            return False
        if Bridge is None:
            print(f"[dry run] mark_landmark_visited({landmark_id})")
            return True
        return bool(Bridge.call("mark_landmark_visited", landmark_id))

    def set_position(self, label_or_xy) -> bool:
        """Mou el marcador 'you are here'. Accepta un codi/id de
        landmark, o una tupla/llista (x, y) per una posicio arbitraria."""
        if isinstance(label_or_xy, (tuple, list)) and len(label_or_xy) == 2:
            x, y = label_or_xy
            if Bridge is None:
                print(f"[dry run] set_location_xy({x}, {y})")
                return True
            return bool(Bridge.call("set_location_xy", int(x), int(y)))

        landmark_id = self._resolve_id(str(label_or_xy))
        if landmark_id is None:
            print(f"[WARN] Landmark desconegut: {label_or_xy!r}")
            return False
        if Bridge is None:
            print(f"[dry run] set_location_by_id({landmark_id})")
            return True
        return bool(Bridge.call("set_location_by_id", landmark_id))

    def reset(self) -> bool:
        """Neteja tots els landmarks visitats i la posicio actual."""
        if Bridge is None:
            print("[dry run] reset_minimap()")
            return True
        return bool(Bridge.call("reset_minimap"))
