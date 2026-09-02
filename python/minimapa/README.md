# Carpeta del minimapa

Minimapa de Park Güell: un terreny pintat per tiles (bosc, camins, la
Plaça de la Natura, els viaductes, trencadís...) amb un pin per cada
punt d'interès (visitat/no visitat) i un marcador de "estàs aquí".
Es mostra a la LCD quan el switch D6 està OFF.

## Fitxers

- **`landmarks.json`** — font de veritat: mapa de tiles, paleta de
  colors i llista de landmarks (codi, nom, posició a pantalla). Si
  el canvies, cal reflectir el canvi a mà a `arduino/landmarks.h` i
  `arduino/tilemap.h` (aquests SÍ que han d'estar al mateix directori
  que `sketch.ino`, no aquí — és un requisit del compilador
  d'Arduino).
- **`minimap_module.py`** — `MinimapManager`, amb els mètodes
  `mark_visited(codi)`, `set_position(codi_o_(x,y))` i `reset()`.
  Tradueix un codi humà (p.ex. `"DR"`) a l'id numèric i crida el
  sketch pel mateix Bridge RPC que fan servir `camera_module.py` i
  la resta de mòduls (`mark_landmark_visited`, `set_location_by_id`,
  `set_location_xy`, `reset_minimap`).

## Què s'ha NO decidit encara (a proposit)

**Qui dispara `mark_visited()`/`set_position()`?** Igual que en la
versió original d'aquest sketch (que rebia les crides per port sèrie
des d'un script extern), aquest mòdul només tradueix i envia — no
decideix quan cridar-se. Pot ser per GPS (proximitat a cada
landmark), per un botó, pel Knob, manualment... el que triïs, només
cal instanciar `MinimapManager` des d'on calgui (típicament
`main.py`) i cridar els seus mètodes.

Exemple d'ús un cop decidit el trigger:

```python
from minimap_module import MinimapManager

minimap = MinimapManager()
minimap.mark_visited("DR")       # marca "Dragon Stairway" com a visitat
minimap.set_position("DR")       # mou el marcador a la posició d'aquell landmark
minimap.set_position((40, 90))   # o a una posició x,y arbitrària
minimap.reset()                  # neteja tot l'estat
```
