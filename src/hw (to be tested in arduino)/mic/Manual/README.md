# Bluetooth Bidirectional Audio Bridge - Button Toggle

Two-way audio over Bluetooth using BlueALSA on the Qualcomm QRB2210
(Linux/MPU) side.

## How it works

| Mode        | Direction                          | Mechanism                                            |
|-------------|-------------------------------------|-------------------------------------------------------|
| Record      | Bluetooth device → UNO Q            | UNO Q acts as an A2DP **sink**; `arecord` captures the incoming stream to a WAV file. |
| Playback    | UNO Q → Bluetooth device            | UNO Q acts as an A2DP **source**; the local microphone is relayed live via `arecord \| aplay` piped into BlueALSA. |
| Pairing     | —                                    | Timed discovery window driven by `bluetoothctl`, followed by pair/trust/connect. |

Mode switching and pairing are triggered by a physical button. A short
press cycles idle -> record -> live microphone relay -> idle. A long
press starts pairing.

## Pairing

Set an optional `TRUSTED_DEVICE_NAME` in `python/config.py`, upload the
project, and hold the button for two seconds. The app scans, pairs,
trusts, connects, and retries the last trusted MAC on later startups.

The Linux image must provide `bluetoothctl`, BlueALSA, `arecord`, and
`aplay`, with both A2DP sink and source profiles enabled.

Standard A2DP is normally for music playback and does not provide a
headset microphone. True Bluetooth headset microphone support normally
requires HFP/HSP and must be available in the UNO Q Linux image. Check
the available BlueALSA profiles before relying on bidirectional headset
audio.

## Install on the UNO Q

```bash
sudo apt update
sudo apt install -y bluez bluealsa alsa-utils
sudo systemctl enable --now bluetooth
sudo systemctl enable --now bluealsa
command -v bluetoothctl bluealsa arecord aplay
systemctl --no-pager --full status bluetooth bluealsa
```

Check that BlueALSA exposes both A2DP profiles with
`systemctl cat bluealsa` and `bluealsa --help`. If a profile is missing,
add `--profile=a2dp-sink --profile=a2dp-source` to the image's BlueALSA
service configuration, then run `sudo systemctl daemon-reload` and
`sudo systemctl restart bluealsa`.

Verify the audio PCM with `aplay -L | grep -i blue`.
