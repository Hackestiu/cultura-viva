# GPS Minimap — Arduino UNO Q

Reports the current GPS position from a NEO-6M module so it can be
shown as a marker on a minimap.

## Hardware wiring

| NEO-6M pin | UNO Q pin | Notes                                       |
|------------|-----------|-----------------------------------------------|
| VCC        | 5V        | Verify your specific breakout's regulator.     |
| GND        | GND       | Common ground.                                  |
| TX         | D0 (RX)   | GPS transmits NMEA; UNO Q receives.             |
| RX         | D1 (TX)   | Optional, not needed for a read-only receiver.  |

## Deploying in Arduino App Lab

1. Create a new App named `gps_minimap`.
2. Paste `sketch/sketch.ino`, add the **TinyGPSPlus** library from
   the library manager (this fills in `sketch/sketch.yaml`).
3. Paste `python/main.py`. 
4. Paste `app.yaml`.
5. Click **Run**.

## Reading the position from your minimap code

The app writes the latest fix to `~/gps_minimap/position.json`,
updated roughly once per second:

```json
{"lat": 41.385064, "lon": 2.173404, "valid": true, "updated_at": 1755690000.12}
```

Any process on the same device can read and poll this file directly instead
of talking to the Bridge itself.