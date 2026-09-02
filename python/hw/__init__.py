"""
Hardware peripheral management package for Arduino UNO Q.

Contains modules for interfacing with hardware devices:
- CameraManager (Logitech Brio 105 USB camera / V4L2)
- MicrophoneManager (ALSA audio input / Whisper STT)
- AudioPlayer (ALSA audio playback via 3.5mm jack / Piper TTS)
- LocationRegistry (GPS coordinates & Haversine distance)
"""

from hw.audio_playback_module import AudioPlayer
from hw.camera_module import CameraManager
from hw.location_module import LocationRegistry
from hw.microphone_module import MicrophoneManager

__all__ = [
    "AudioPlayer",
    "CameraManager",
    "LocationRegistry",
    "MicrophoneManager",
]
