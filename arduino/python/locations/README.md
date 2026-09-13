# Locations — `python/locations/`

`locations.json` is the site table: the reference coordinates the GPS fix is matched
against, and the display names shown on the device. It is read by
`hw/location_module.py` (`LocationRegistry`); adding a site is a data edit here, not a
code change.

```json
{
  "locations": [
    { "id": "sagrada_familia", "name": "Sagrada Família",
      "lat": 41.403629, "lon": 2.174349, "radius_m": 300, "minimap_id": 1 }
  ],
  "default": "sagrada_familia"
}
```

- **`id`** — must match the folder names used elsewhere for the same site:
  `models/vision/<id>/`, the keys of `LANDMARKS_FILES` and `VISION_LABEL_TO_LANDMARK`
  in `core/minimap_module.py`.
- **`radius_m`** — how close the visitor has to be for the site to be chosen. Outside
  every radius, no site is claimed (see below) — without it the nearest site would win
  from any distance, and a device switched on in Girona would announce the Sagrada
  Família.
- **`minimap_id`** — the tilemap the sketch shows for this site.
- **`default`** — the site used when GPS cannot place the visitor.

## How the site is decided

1. **Override** — `CULTURA_LOCATION=<id>` in the environment, or `set_override(id)` at
   runtime, forces a site and GPS is not consulted at all.
2. **GPS** — with a fix inside some site's `radius_m`, the nearest such site wins.
3. **Default** — no fix, or a fix outside every radius: the `default` site is used so
   the device stays usable, and `LocationFix.needs_confirmation` is set so the caller
   can ask the visitor to pick a site instead.

```bash
CULTURA_LOCATION=park_guell python3 main.py   # test away from the monument
```

```python
from hw.location_module import LocationRegistry

location = LocationRegistry()
location.current()          # 'sagrada_familia'
location.resolve()          # LocationFix(site=..., source='gps', distance_m=42.0, ...)
location.set_override("casa_batllo")
location.clear_override()
```

Which site is active, and on what grounds, is logged once at startup by `main.py`.
