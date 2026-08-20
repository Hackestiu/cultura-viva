"""
Bluetooth Bidirectional Audio - MPU application entry point.

Orchestrates BlueALSA-based audio capture/playback and coordinates
with the MCU sketch through the Bridge for button input.
"""

import os
import time
import signal
import logging
from datetime import datetime
from enum import IntEnum

try:
    from arduino.app_utils import App, Bridge
except ModuleNotFoundError:
    App = None
    Bridge = None

from config import (
    TRUSTED_DEVICE_MAC,
    TRUSTED_DEVICE_NAME,
    RECORDINGS_DIR,
    BUTTON_POLL_INTERVAL,
    RECONNECT_INTERVAL,
    PAIRING_SCAN_SECONDS,
)
from bluetooth_manager import BluetoothManager
from audio_engine import AudioEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bt_audio_bridge")


class Mode(IntEnum):
    IDLE = 0
    RECORD = 1
    PLAYBACK = 2


class Application:
    def __init__(self):
        os.makedirs(RECORDINGS_DIR, exist_ok=True)
        self.bt = BluetoothManager(TRUSTED_DEVICE_MAC, TRUSTED_DEVICE_NAME)
        self.audio = AudioEngine()
        self.mode = Mode.IDLE
        self.bt.start_auto_reconnect(interval=RECONNECT_INTERVAL)

    def _next_recording_path(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(RECORDINGS_DIR, f"capture_{timestamp}.wav")

    def _enter_idle(self) -> None:
        self.audio.stop_all()
        self.mode = Mode.IDLE
        log.info("Mode: IDLE")

    def _enter_record(self) -> None:
        if not self.bt.is_connected():
            log.warning("No trusted device connected, cannot start recording")
            self._flash_error()
            return
        self.audio.stop_all()
        output_path = self._next_recording_path()
        if self.audio.start_recording(self.bt.mac, output_path):
            self.mode = Mode.RECORD
            log.info("Mode: RECORD -> %s", output_path)
        else:
            self._flash_error()

    def _enter_playback(self) -> None:
        if not self.bt.is_connected():
            log.warning("No trusted device connected, cannot start playback")
            self._flash_error()
            return
        self.audio.stop_all()
        if self.audio.start_playback_live_mic(self.bt.mac):
            self.mode = Mode.PLAYBACK
            log.info("Mode: PLAYBACK (live microphone relay)")
        else:
            self._flash_error()

    def _flash_error(self) -> None:
        log.warning("Audio mode change failed")

    def toggle_mode(self) -> None:
        if self.mode == Mode.IDLE:
            self._enter_record()
        elif self.mode == Mode.RECORD:
            self._enter_playback()
        else:
            self._enter_idle()

    def start_pairing(self) -> None:
        log.info("Manual pairing requested")
        self.audio.stop_all()
        self.mode = Mode.IDLE
        found = self.bt.pair_new_device(scan_seconds=PAIRING_SCAN_SECONDS)
        if found:
            log.info("Paired and trusted device: %s", found)
        else:
            log.warning("No matching device found during pairing window")

    def poll(self) -> None:
        if Bridge is None:
            return
        try:
            event = Bridge.call("get_button_event")
        except Exception as exc:
            log.debug("Bridge poll failed: %s", exc)
            return
        if event == 1:
            self.toggle_mode()
        elif event == 2:
            self.start_pairing()


def run_app() -> None:
    if App is None:
        raise RuntimeError("Arduino App Lab is unavailable; use the host tests instead")
    app_state = Application()

    def loop():
        app_state.poll()
        time.sleep(BUTTON_POLL_INTERVAL)

    def shutdown(*_args):
        log.info("Shutting down, stopping audio and Bluetooth threads")
        app_state.audio.stop_all()
        app_state.bt.stop_auto_reconnect()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    App.run(user_loop=loop)


if __name__ == "__main__":
    run_app()