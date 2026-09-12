"""
Automatic hardware device discovery for Cultura Viva.

Detects the Logitech Brio 105 camera (V4L2 index), USB microphone (ALSA card index),
and the 3.5mm headphone output (ALSA plughw device string) at runtime, so the app
survives USB re-enumerations without manual config changes.

Entry points:
    discover_camera_index()   -> int | None
    discover_mic_device()     -> dict | None
    discover_playback_device()-> str | None
    discover_all()            -> dict with keys: camera, mic, playback

All functions return None (not raise) on failure so callers can fall back gracefully.

STABILITY NOTE
--------------
V4L2/ALSA index numbers (e.g. /dev/video2, hw:1,0) are assigned by *enumeration
order*, which depends on USB scan timing at boot — not on which physical port a
device is plugged into. That means indices can flip even with nothing physically
changed, especially after a USB re-enumeration.

Both v4l2-ctl and /proc/asound/cards report a physical USB bus/port identifier
alongside each device (e.g. "usb-xhci-hcd.2.auto-1.4" for video, or a similar
token in the ALSA card's longname). If you know which physical port the camera
and mic will always be plugged into, set _CAMERA_KNOWN_PORT / _MIC_KNOWN_PORT
below to that port suffix (e.g. "1.4"). Discovery will then check the port match
FIRST, before falling back to name-keyword matching. This is the most reliable
way to survive re-enumeration, short of using /dev/v4l/by-path/ or
/dev/snd/by-path/ symlinks directly.

Leave the KNOWN_PORT constants as "" to disable port-based matching and rely on
keyword matching only (the original behavior).
"""

import re
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Camera (V4L2)
# ---------------------------------------------------------------------------

# Keywords that identify the Brio 105 camera in /sys or v4l2 driver names.
# Add extra keywords here if running on a different camera model.
_CAMERA_KEYWORDS = ("brio", "brio 105", "logitech", "webcam", "camera")

# Devices to explicitly ignore (e.g. Qualcomm Venus hardware decoder/encoder nodes)
_EXCLUDE_CAMERA_KEYWORDS = ("venus", "decoder", "encoder", "codec", "qcom-venus")

# Fallback: try these indices in order if keyword search yields nothing.
# Index 2 is tried first because on this Qualcomm board, Venus decoder is at 0/1.
_CAMERA_FALLBACK_INDICES = (2, 0, 1)

# Physical USB bus/port suffix for the camera, e.g. "1.4" (as reported inside the
# parentheses of 'v4l2-ctl --list-devices', e.g. "usb-xhci-hcd.2.auto-1.4").
# Set this once you've confirmed which port the camera is plugged into; it is
# checked BEFORE name-keyword matching since it survives re-enumeration and
# even name/driver-string changes. Leave "" to skip this check.
_CAMERA_KNOWN_PORT = ""


def _list_v4l2_devices() -> list[tuple[int, str]]:
    """Returns [(video_index, device_name), ...] parsed from 'v4l2-ctl --list-devices'."""
    devices: list[tuple[int, str]] = []
    for idx, name, _port in _list_v4l2_devices_with_port():
        devices.append((idx, name))
    return devices


def _list_v4l2_devices_with_port() -> list[tuple[int, str, str]]:
    """
    Returns [(video_index, device_name, usb_port), ...] parsed from
    'v4l2-ctl --list-devices'.

    usb_port is the bus/port string inside the parentheses of the header line,
    e.g. 'usb-xhci-hcd.2.auto-1.4', or '' if the header has no parenthesized
    part (e.g. for non-USB / platform devices).
    """
    devices: list[tuple[int, str, str]] = []
    try:
        res = subprocess.run(
            ["v4l2-ctl", "--list-devices"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if res.returncode == 0:
            current_name = ""
            current_port = ""
            for line in res.stdout.splitlines():
                if not line.startswith("\t") and not line.startswith(" ") and line.strip():
                    # Header line like: "Brio 105 (usb-xhci-hcd.2.auto-1.4):"
                    header = line.strip().rstrip(":")
                    m = re.search(r"\((.+)\)$", header)
                    current_port = m.group(1) if m else ""
                    current_name = re.sub(r"\s*\(.+\)$", "", header).strip()
                elif line.strip().startswith("/dev/video"):
                    m = re.search(r"/dev/video(\d+)", line.strip())
                    if m:
                        idx = int(m.group(1))
                        devices.append((idx, current_name, current_port))
    except Exception:
        pass
    return devices


def _v4l2_device_name(index: int) -> str:
    """Returns the device name string for /dev/videoN from the sysfs tree."""
    try:
        sysfs = Path(f"/sys/class/video4linux/video{index}/name")
        if sysfs.exists():
            return sysfs.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    # Fallback: ask v4l2-ctl
    try:
        result = subprocess.run(
            ["v4l2-ctl", f"--device=/dev/video{index}", "--info"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        for line in result.stdout.splitlines():
            if "card" in line.lower() or "bus" in line.lower():
                return line.strip()
    except Exception:
        pass
    return ""


def discover_camera_index() -> int | None:
    """
    Scans V4L2 devices for one whose name contains a camera keyword (e.g. Brio 105)
    and does NOT belong to a hardware decoder/encoder (e.g. Qualcomm Venus).

    Preference order:
      0. Physical USB port match (_CAMERA_KNOWN_PORT), if set — most stable,
         survives re-enumeration and driver name changes.
      1. v4l2-ctl name-keyword match.
      2. sysfs /dev/video0..15 name-keyword match.
      3. Fixed fallback indices (excluding known decoder/encoder nodes).
      4. Hardcoded last resort (index 2).
    """
    devices_with_port = _list_v4l2_devices_with_port()

    # 0. Try physical USB port match first (most stable across re-enumerations)
    if _CAMERA_KNOWN_PORT:
        for idx, name, port in devices_with_port:
            if port.endswith(_CAMERA_KNOWN_PORT):
                print(
                    f"[DISCOVERY] Camera found via fixed USB port: "
                    f"/dev/video{idx} (port '{port}', name '{name}')"
                )
                return idx

    # 1. Try parsing 'v4l2-ctl --list-devices' first (most reliable of the
    #    name-based methods)
    for idx, name, _port in devices_with_port:
        name_lower = name.lower()
        if any(exc in name_lower for exc in _EXCLUDE_CAMERA_KEYWORDS):
            continue
        if any(kw.lower() in name_lower for kw in _CAMERA_KEYWORDS):
            print(f"[DISCOVERY] Camera found via v4l2-ctl: /dev/video{idx} ('{name}')")
            return idx

    # 2. Try sysfs /dev/video0..15 inspection
    for i in range(16):
        dev = Path(f"/dev/video{i}")
        if not dev.exists():
            continue
        name = _v4l2_device_name(i)
        name_lower = name.lower()
        if any(exc in name_lower for exc in _EXCLUDE_CAMERA_KEYWORDS):
            continue
        if any(kw.lower() in name_lower for kw in _CAMERA_KEYWORDS):
            print(f"[DISCOVERY] Camera found via sysfs: /dev/video{i} ('{name}')")
            return i

    # 3. Fallback: try indices (excluding venus / decoder)
    for i in _CAMERA_FALLBACK_INDICES:
        if Path(f"/dev/video{i}").exists():
            name = _v4l2_device_name(i).lower()
            if not any(exc in name for exc in _EXCLUDE_CAMERA_KEYWORDS):
                print(
                    f"[DISCOVERY] Camera keyword not matched; "
                    f"falling back to /dev/video{i}"
                )
                return i

    print("[DISCOVERY] No camera device found. Falling back to index 2.")
    return 2


# ---------------------------------------------------------------------------
# Microphone (ALSA / sounddevice)
# ---------------------------------------------------------------------------

# Keywords that identify the Brio 105 microphone in ALSA card names.
# NOTE: "usb audio" and "usb-audio" are intentionally omitted — they are too
# generic and would match a plain "USB Audio" card before the Brio 105 card.
_MIC_KEYWORDS = ("brio", "b105", "logitech", "webcam")

# Sample rates to try when negotiating with the ALSA driver (highest first so
# we keep the native rate if the device supports it; Whisper needs 16 kHz but
# sounddevice can return any rate and we resample afterwards if necessary).
_MIC_SAMPLE_RATES = (48000, 44100, 16000, 8000)

# Physical USB bus/port suffix for the mic, e.g. "1.4". Checked against the
# longname reported in /proc/asound/cardN/usbid or usbbus (see
# _alsa_card_usb_port below) BEFORE name-keyword matching. Leave "" to skip.
_MIC_KNOWN_PORT = ""


def _list_alsa_cards() -> list[tuple[int, str]]:
    """Returns [(card_index, card_name_lower), ...] from /proc/asound/cards."""
    cards: list[tuple[int, str]] = []
    try:
        proc_cards = Path("/proc/asound/cards")
        if not proc_cards.exists():
            return cards
        text = proc_cards.read_text(encoding="utf-8")
        for line in text.splitlines():
            # Lines look like: " 0 [PCH            ]: HDA-Intel - ..."
            m = re.match(r"\s*(\d+)\s+\[.*?\]:\s*(.+)", line)
            if m:
                cards.append((int(m.group(1)), m.group(2).lower()))
    except Exception:
        pass
    return cards


def _alsa_card_usb_port(card_index: int) -> str:
    """
    Returns the physical USB bus/port path for an ALSA card, if it's a USB
    device, e.g. '1.4'. Reads the symlink target of
    /sys/class/sound/cardN/device, which for USB audio devices points into
    the USB topology (e.g. .../usb1/1-1.4/1-1.4:1.0/sound/card1).
    Returns '' if the card isn't a USB device or the info isn't available.
    """
    try:
        device_link = Path(f"/sys/class/sound/card{card_index}/device")
        if device_link.is_symlink() or device_link.exists():
            real = device_link.resolve()
            # Look for a path segment like '1-1.4' (bus-port.port...)
            for part in real.parts:
                m = re.match(r"^\d+-([\d.]+)(?::.*)?$", part)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return ""


def _probe_mic_sample_rate(alsa_device: str) -> int:
    """
    Probes the native sample rate supported by the given ALSA device string
    (e.g. 'hw:1,0').

    Strategy:
      1. sounddevice.query_devices() — most reliable, no process spawn needed.
      2. arecord --dump-hw-params — good fallback if sounddevice not available.
      3. Hard fallback: 48000 Hz (Brio 105 native rate; resampled to 16kHz for Whisper).
    """
    # 1. Try sounddevice (fastest and most reliable)
    try:
        import sounddevice as _sd  # type: ignore[import]
        info = _sd.query_devices(alsa_device, "input")
        default_rate = int(info["default_samplerate"])
        if default_rate >= 8000:
            return default_rate
    except Exception:
        pass

    # 2. Try arecord --dump-hw-params
    try:
        result = subprocess.run(
            ["arecord", "-D", alsa_device, "--dump-hw-params"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        output = result.stdout + result.stderr
        # Look for a RATE line: "RATE: 48000" or "RATE: [ 8000 48000 ]"
        for line in output.splitlines():
            if "RATE" in line.upper():
                numbers = re.findall(r"\d+", line)
                rates = [int(n) for n in numbers if int(n) >= 8000]
                for preferred in _MIC_SAMPLE_RATES:
                    if preferred in rates:
                        return preferred
                if rates:
                    return rates[0]
    except Exception:
        pass

    # 3. Safe fallback: 48000 Hz (Brio 105 native; microphone_module resamples to 16kHz)
    print(f"[DISCOVERY] Could not probe sample rate for '{alsa_device}'; defaulting to 48000 Hz")
    return 48000


def discover_mic_device() -> dict | None:
    """
    Scans ALSA sound cards for the microphone.

    Preference order:
      0. Physical USB port match (_MIC_KNOWN_PORT), if set — most stable.
      1. Name-keyword match against the card's longname.

    Returns a dict with:
        'alsa_device': str  — ALSA hw device string, e.g. 'hw:1,0'
        'card_index':  int  — ALSA card number
        'sample_rate': int  — first sample rate supported by the device
    or None if no matching card is found.
    """
    cards = _list_alsa_cards()

    # 0. Try physical USB port match first (most stable across re-enumerations)
    if _MIC_KNOWN_PORT:
        for card_idx, card_name in cards:
            port = _alsa_card_usb_port(card_idx)
            if port and port.endswith(_MIC_KNOWN_PORT):
                alsa_device = f"hw:{card_idx},0"
                rate = _probe_mic_sample_rate(alsa_device)
                print(
                    f"[DISCOVERY] Microphone found via fixed USB port: "
                    f"ALSA card {card_idx} ('{card_name}', port '{port}'), "
                    f"device '{alsa_device}', native rate {rate} Hz"
                )
                return {"alsa_device": alsa_device, "card_index": card_idx, "sample_rate": rate}

    # 1. Fall back to name-keyword match
    for card_idx, card_name in cards:
        if any(kw in card_name for kw in _MIC_KEYWORDS):
            alsa_device = f"hw:{card_idx},0"
            rate = _probe_mic_sample_rate(alsa_device)
            print(
                f"[DISCOVERY] Microphone found: ALSA card {card_idx} ('{card_name}'), "
                f"device '{alsa_device}', native rate {rate} Hz"
            )
            return {"alsa_device": alsa_device, "card_index": card_idx, "sample_rate": rate}

    print("[DISCOVERY] No USB microphone found in ALSA card list.")
    return None


# ---------------------------------------------------------------------------
# Audio playback / headphone output (ALSA plughw device string)
# ---------------------------------------------------------------------------

# Keywords that identify the headphone output in ALSA card names.
# The 3.5mm jack on most SBCs is on the built-in audio card.
_HEADPHONE_KEYWORDS = (
    "headphone",
    "audio jack",
    "3.5",
    "bcm2835",     # Raspberry Pi built-in
    "sunxi",       # Allwinner SBCs
    "imx",         # NXP/i.MX audio
    "sgtl5000",    # common on Arduino Linux boards
    "hda-intel",   # standard laptop/PC
    "realtek",
    "ac97",
    "imola",       # Arduino UNO Q (Qualcomm QCM2290) internal audio
    "qcm2290",     # Arduino UNO Q Qualcomm SoC audio
    "arduino-imola",
)

# Cards listed here should NOT be used for playback (prefer the headphone jack
# or the onboard USB Audio output over the Brio's built-in audio out).
# Also skip cheap USB audio dongles like JieLi.
_SKIP_PLAYBACK_KEYWORDS = ("brio", "b105", "logitech", "webcam", "jieli")


def discover_playback_device() -> str | None:
    """
    Finds the best ALSA card for headphone output: favours a built-in audio card
    (matching _HEADPHONE_KEYWORDS), skips known USB audio sources, and returns a
    'plughw:N,0' device string. Returns None if nothing is found.
    """
    cards = _list_alsa_cards()

    # Prefer cards matching headphone keywords, but skip USB audio sources
    for card_idx, card_name in cards:
        if any(skip in card_name for skip in _SKIP_PLAYBACK_KEYWORDS):
            continue
        if any(kw in card_name for kw in _HEADPHONE_KEYWORDS):
            device = f"plughw:{card_idx},0"
            print(f"[DISCOVERY] Playback device found: {device} ('{card_name}')")
            return device

    # Second pass: take the first non-USB-mic card available
    for card_idx, card_name in cards:
        if any(skip in card_name for skip in _SKIP_PLAYBACK_KEYWORDS):
            continue
        device = f"plughw:{card_idx},0"
        print(
            f"[DISCOVERY] No headphone keyword match; "
            f"falling back to {device} ('{card_name}')"
        )
        return device

    print("[DISCOVERY] No playback device found.")
    return None


# ---------------------------------------------------------------------------
# Discover all at once
# ---------------------------------------------------------------------------

def discover_all() -> dict:
    """
    Runs all three discovery functions and returns a dict::

        {
            "camera":      <int|None>,   # V4L2 device index for /dev/videoN
            "mic":         <dict|None>,  # keys: alsa_device, card_index, sample_rate
            "playback":    <str|None>,   # 'plughw:N,0' string for aplay
        }
    """
    return {
        "camera":   discover_camera_index(),
        "mic":      discover_mic_device(),
        "playback": discover_playback_device(),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(discover_all(), indent=2))