"""
Automatic hardware device discovery for Cultura Viva.

Detects the Logitech Brio 105 camera (V4L2 index), USB microphone (ALSA card index),
and the 3.5mm headphone output (ALSA plughw device string) at runtime, so the app
survives USB re-enumerations without manual config changes.

Entry points:
    discover_camera_index()   -> int | None
    discover_mic_device()     -> int | None
    discover_playback_device()-> str | None
    discover_all()            -> dict with keys: camera, mic, playback

All functions return None (not raise) on failure so callers can fall back gracefully.
"""

import re
import subprocess
from pathlib import Path


# ---------------------------------------------------------------------------
# Camera (V4L2)
# ---------------------------------------------------------------------------

# Keywords that identify the Brio 105 camera in /sys or v4l2 driver names.
# Add extra keywords here if running on a different camera model.
_CAMERA_KEYWORDS = ("Brio", "Brio 105", "logitech")

# Fallback: try these indices in order if keyword search yields nothing.
_CAMERA_FALLBACK_INDICES = (0, 1, 2, 3, 4)


def _v4l2_device_name(index: int) -> str:
    """Returns the device name string for /dev/videoN from the sysfs tree."""
    try:
        sysfs = Path(f"/sys/class/video4linux/video{index}/name")
        if sysfs.exists():
            return sysfs.read_text(encoding="utf-8").strip().lower()
    except Exception:
        pass
    # Fallback: ask v4l2-ctl
    try:
        result = subprocess.run(
            ["v4l2-ctl", f"--device=/dev/video{index}", "--info"],
            capture_output=True, text=True, timeout=2
        )
        for line in result.stdout.splitlines():
            if "card" in line.lower() or "bus" in line.lower():
                return line.lower()
    except Exception:
        pass
    return ""


def discover_camera_index() -> int | None:
    """
    Scans /dev/video0..15 for a device whose name contains one of the Brio 105
    keywords. Returns the first matching index, or None if not found.
    """
    for i in range(16):
        dev = Path(f"/dev/video{i}")
        if not dev.exists():
            continue
        name = _v4l2_device_name(i)
        if any(kw in name for kw in _CAMERA_KEYWORDS):
            print(f"[DISCOVERY] Camera found: /dev/video{i} ('{name}')")
            return i

    # No keyword match — try the first capture-capable device as a fallback
    for i in _CAMERA_FALLBACK_INDICES:
        if Path(f"/dev/video{i}").exists():
            print(
                f"[DISCOVERY] Camera keyword not matched; "
                f"falling back to /dev/video{i}"
            )
            return i

    print("[DISCOVERY] No camera device found.")
    return None


# ---------------------------------------------------------------------------
# Microphone (ALSA / sounddevice card index)
# ---------------------------------------------------------------------------

# Keywords that identify the Brio 105 microphone in ALSA card names.
_MIC_KEYWORDS = ("Brio", "logitech", "usb audio", "usb-audio", "webcam")


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


def discover_mic_device() -> int | None:
    """
    Scans ALSA sound cards for one whose name contains a microphone keyword.
    Returns the card index (usable as sounddevice device parameter), or None.
    """
    for card_idx, card_name in _list_alsa_cards():
        if any(kw in card_name for kw in _MIC_KEYWORDS):
            print(f"[DISCOVERY] Microphone found: ALSA card {card_idx} ('{card_name}')")
            return card_idx

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
)

# Cards listed here are USB audio devices and should NOT be used for playback
# (prefer the headphone jack over the Brio's audio out).
_SKIP_PLAYBACK_KEYWORDS = ("brio", "logitech", "webcam", "usb audio")


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
            "camera":   <int|None>,    # V4L2 device index for /dev/videoN
            "mic":      <int|None>,    # ALSA card index for sounddevice
            "playback": <str|None>,    # 'plughw:N,0' string for aplay
        }
    """
    return {
        "camera":   discover_camera_index(),
        "mic":      discover_mic_device(),
        "playback": discover_playback_device(),
    }
