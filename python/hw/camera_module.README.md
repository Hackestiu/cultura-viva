# `camera_module.py` — pendent #3: `last_photo_path`

**Estat**: ⏳ PENDENT PETIT — `CameraManager.last_photo_path` **no existeix**
encara. És el canvi més petit de tota la migració: dues línies de codi.

---

## Canvi a fer (mínim, sense risc)

```python
class CameraManager:
    def __init__(self):
        self._cap = None
        self.last_photo_path = None   # NOU — path de l'última foto presa

    # ... tot el codi existent intacte ...

    def take_photo(self):
        # ... codi existent intacte fins al final ...
        cv2.imwrite(str(filename), frame)
        print(f"[OK] Foto guardada a: {filename} ({width}x{height})")
        self.last_photo_path = filename   # NOU — desa el path
        return filename
```

### On exactament

- Línia `self.last_photo_path = None` → dins de `__init__`, **al costat
  de** `self._cap = None` (línia 29 actual del fitxer).
- Línia `self.last_photo_path = filename` → dins de `take_photo()`,
  **just abans** del `return filename` final (línia 120 actual).

---

## Per què és necessari

`vision_module.VisionClassifier.classify()` necessita el path de la
**foto presa per l'usuari** (no un fotograma de la vista en directe).
La foto es pren des del bloc `photo_trigger` del bucle de `main.py`, però
la pipeline de visió s'executa al bloc `is_recording_active`. La forma més
simple de passar-ho entre els dos blocs és `camera.last_photo_path` —
l'objecte `camera` ja és una variable global dins `main.py`.

```python
# main.py — bloc is_recording_active:
photo_path = camera.last_photo_path  # última foto presa per D7
element = vision.classify(site, photo_path) if photo_path else None
```

---

## Quan implementar-ho

**PAS 1 del pla de migració** — és el canvi de menys risc: no canvia cap
lògica existent, no té dependències de models ni de llibreries noves.
Fes-lo primer, comprova que `take_photo()` segueix funcionant igual
(foto a `photos/`, buzzer), i ja pots oblidar-te'n.
