# Bluetooth Bidirectional Audio - Automatic VOX

This UNO Q variant starts the voice router whenever the
trusted Bluetooth device is connected. Silence sends Bluetooth audio to
the local speaker. Voice activity switches to local microphone ->
Bluetooth, giving a half-duplex intercom. Short press mutes/unmutes the
local microphone while listening continues. A two-second long press
starts Bluetooth discovery, pairing, trusting, and connecting.

Important: standard A2DP is normally a music playback profile and does
not provide a headset microphone. This project can relay audio in the
directions exposed by the UNO Q image, but true headset microphone use
requires an HFP/HSP telephony profile supported by that image. Verify
the available BlueALSA profiles before expecting microphone audio from a
Bluetooth headset.

The sketch uses D2 with `INPUT_PULLUP`; connect the button between D2 and
GND.

## Pairing and reconnect

Set an optional `TRUSTED_DEVICE_NAME` in `python/config.py`. On the first
run, hold the button for two seconds. The app scans, pairs, trusts, and
connects the matching headset. Copy its MAC to `TRUSTED_DEVICE_MAC` for
faster startup reconnects. The manager retries that address automatically.

## Install on the UNO Q

```bash
sudo apt update
sudo apt install -y bluez bluealsa alsa-utils
sudo systemctl enable --now bluetooth
sudo systemctl enable --now bluealsa
command -v bluetoothctl bluealsa arecord aplay
systemctl --no-pager --full status bluetooth bluealsa
```

BlueALSA must expose the profile required by the connected device. A2DP
is suitable for playback; HFP/HSP is normally required for a headset
microphone. Check the service arguments and available profiles:

```bash
systemctl cat bluealsa
bluealsa --help | grep -E 'a2dp-sink|a2dp-source|profile'
```

If the required profile is missing, use the profile options supported by
the installed BlueALSA version and image, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart bluealsa
```

Check that BlueALSA exposes PCM devices with
`aplay -L | grep -i blue`.

## Hardware

The companion `sketch/sketch.ino` reads the D2 button through
`Arduino_RouterBridge`. Arduino App Lab compiles and uploads this sketch;
Windows does not need to import the Arduino library.

## Main settings

Tune `VAD_THRESHOLD`, `VAD_ATTACK_CHUNKS`, and `VAD_RELEASE_MS` in
`python/config.py` for the microphone and room. This variant is
experimental because A2DP profile switching can interrupt a stream.
