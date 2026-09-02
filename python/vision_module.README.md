# `vision_module.py` — Classificador de visió per elements de Gaudí

**Estat**: ⏳ PENDENT D'IMPLEMENTAR — `vision_module.py` és un placeholder
que llença `NotImplementedError` si s'importa. No es connecta a `main.py`
fins que funcioni de forma aïllada.

---

## Responsabilitat d'aquest mòdul

Donat el **path d'una foto** feta per `CameraManager.take_photo()` i el
**nom de la ubicació** que retorna `LocationRegistry.current()`, retorna
el nom de l'**element de Gaudí detectat** a la foto (o `None` si no en
detecta cap).

```
foto (path .jpg)  +  ubicació ("park_guell" / "sagrada_familia")
           ↓
    VisionClassifier.classify(location, photo_path)
           ↓
    element detectat: "drac" / "xemeneia" / "nativity_facade" / ...
```

La ubicació és necessària perquè s'usen **classificadors diferents** per
cada lloc — no té sentit buscar la Sagrada Família en una foto feta al
Park Güell.

---

## Classe que cal implementar

```python
class VisionClassifier:
    def classify(self, location: str, photo_path: str) -> str | None:
        """Retorna l'element detectat (p.ex. 'drac', 'xemeneia')
        o None si no en detecta cap amb prou confiança.

        :param location: 'park_guell' o 'sagrada_familia'
                         (el que retorna location_module.LocationRegistry.current())
        :param photo_path: path absolut o Path al .jpg de la foto
        """
```

---

## D'on ve el codi original

El codi classificador ja existeix a **`src/vision/classifiers.py`** del
repo original de Cultura Viva. Cal portar-lo aquí i adaptar-lo perquè:

1. Accepti els dos valors de `location` que usa `location_module.py`
   (`"park_guell"` i `"sagrada_familia"`).
2. Importi les seves dependències des de `config.py` (paths de models,
   si n'hi ha algun).
3. Retorni un string (nom de l'element) o `None`.

---

## Dependències esperades

Depèn de quin enfocament fa servir `src/vision/classifiers.py`:

| Tècnica | Llibreria | Afegir a `requirements.txt` |
|---|---|---|
| Classificació per CNN | `torch` + `torchvision` | `torch torchvision` |
| Classificació per OpenCV + features | `opencv-python` | ja és a `requirements.txt` |
| Zero-shot amb CLIP | `transformers` + `torch` | `transformers torch` |

> ⚠️ **Si el classificador necessita fitxers de pesos** (`.pt`, `.onnx`,
> etc.), posa'ls a `models/vision/` i afegeix la ruta a `config.py`:
>
> ```python
> VISION_MODELS_DIR = MODELS_DIR / "vision"
> ```
>
> Si canvies de tècnica de classificació o de nom de fitxer de pesos,
> actualitza `VISION_MODELS_DIR` (o la constant específica) a `config.py`.

---

## Com provar-lo de forma aïllada (PAS 3 del pla de migració)

**Abans** de connectar-lo a `main.py`, prova'l sol amb una foto de
`photos/` ja existent:

```python
# test_vision.py (executa-ho des de la carpeta python/)
from vision_module import VisionClassifier
from pathlib import Path

clf = VisionClassifier()
foto = list(Path("photos").glob("*.jpg"))[0]  # primera foto que trobi
resultat = clf.classify("park_guell", str(foto))
print(f"Element detectat: {resultat}")
```

Executa:
```bash
cd python/
python test_vision.py
```

Si retorna un string sense llençar excepcions, el mòdul és llest.

---

## Com es crida des de `main.py` (quan estigui llest)

A `main.py`, dins el bloc `is_recording_active`, **després** que
`microphone.save(...)` hagi tornat el path del `.wav`:

```python
from vision_module import VisionClassifier
from location_module import LocationRegistry

vision = VisionClassifier()
location = LocationRegistry()

# ... dins del loop, bloc is_recording_active:
site = location.current()            # "park_guell" o "sagrada_familia"
photo_path = camera.last_photo_path  # última foto presa (pendent #3)
element = vision.classify(site, photo_path) if photo_path else None
```

> ⚠️ `camera.last_photo_path` no existeix encara a `camera_module.py`
> — és el **pendent #3** del `README.md` principal. Cal afegir-lo a
> `CameraManager` ABANS de connectar `vision_module` a `main.py`.

---

## Claus d'element que has de fer servir

Les claus que retorna `classify()` han de coincidir amb les claus del
**graf de coneixement** (`models/knowledge/gaudi_kg.json`), perquè
`ModelRegistry.get_kg_context(element)` les usa directament per fer el
lookup. Coordina amb qui crea el KG quins noms s'usen.
