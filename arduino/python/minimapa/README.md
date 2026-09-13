# Minimap  — `python/minimapa/`

This folder holds the source-of-truth data for the two minimap screens (Park Güell and Sagrada Família): tile grid, colour palette, zone/lock colouring, and the landmark registry (code, name, screen coordinates) for each site.

Rendering on the Arduino side is done from hand-ported C++ headers, not by reading these JSON files directly, so any change made here must be mirrored manually.

## Files

- **`landmarks_guell.json`** — Tile map and landmark data for the Park Güell minimap. Must stay in sync with `sketch/src/display/landmarks_guell.h` and `sketch/src/display/tilemap_guell.h`.
- **`landmarks_sagrada.json`** — Tile map, palette, zone-lock colours, and landmark data for the Sagrada Família minimap. Must stay in sync with `sketch/src/display/landmarks_sagrada.h` and `sketch/src/display/tilemap_sagrada.h`.

The active minimap (which of the two screens is shown) is selected elsewhere in the application logic based on current location/GPS zone; this folder only supplies the static per-site data.

## Usage

Consumed by `core/minimap_module.py` (`MinimapManager`), which translates human-readable landmark codes (e.g. `"DR"`) into numeric IDs and relays state changes to the sketch over Bridge RPC (`mark_landmark_visited`, `set_location_by_id`, `set_location_xy`, `reset_minimap`):

```python
from core.minimap_module import MinimapManager

minimap = MinimapManager()
minimap.mark_visited("DR")       # mark Dragon Stairway as visited
minimap.set_position("DR")       # move location marker to that landmark
minimap.set_position((40, 90))   # or move to an arbitrary (x, y) position
minimap.reset()                  # clear all state
```