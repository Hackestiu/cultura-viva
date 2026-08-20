"""
Static configuration for the Bidirectional Bluetooth Audio Bridge.
"""

import os

# MAC address of the trusted device to auto-reconnect to.
TRUSTED_DEVICE_MAC = None  # e.g. "AA:BB:CC:DD:EE:FF"

# Optional name substring used to pick a device during manual pairing when several devices are discoverable at once.
TRUSTED_DEVICE_NAME = None  # e.g. "Galaxy Buds"

RECORDINGS_DIR = os.path.expanduser("~/bt_audio_bridge/recordings")

SAMPLE_RATE = 44100
CHANNELS = 2

BUTTON_POLL_INTERVAL = 0.15   # seconds between Bridge polls
RECONNECT_INTERVAL = 10       # seconds between reconnect attempts
PAIRING_SCAN_SECONDS = 20     # duration of the discovery window