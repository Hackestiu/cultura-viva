# Bluetooth and audio settings.
TRUSTED_DEVICE_MAC = None  # Set after first pairing, for example "AA:BB:CC:DD:EE:FF".
TRUSTED_DEVICE_NAME = None  # Optional name filter during pairing.
SAMPLE_RATE = 44100
CHANNELS = 2
BUTTON_POLL_INTERVAL = 0.2
RECONNECT_INTERVAL = 10
PAIRING_SCAN_SECONDS = 20

# Voice-activity detection (automatic speak/listen switching)
VAD_THRESHOLD = 600      # RMS amplitude (16-bit PCM) above which the mic is "speaking"
VAD_ATTACK_CHUNKS = 2     # consecutive loud chunks required to trigger "speak"
VAD_RELEASE_MS = 700      # silence duration required to fall back to "listen"
VAD_CHUNK_MS = 30         # size of each analysis chunk, in milliseconds