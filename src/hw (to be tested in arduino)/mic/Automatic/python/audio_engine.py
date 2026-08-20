"""BlueALSA live audio process helpers."""

import logging
import subprocess
from typing import Optional

from config import CHANNELS, SAMPLE_RATE

log = logging.getLogger("bt_audio_bridge.audio")


class AudioEngine:
    def __init__(self):
        self._processes = []

    def start_relay(self, mac: str) -> bool:
        if self._processes:
            return False
        record = subprocess.Popen(
            ["arecord", "-D", f"bluealsa:DEV={mac},PROFILE=a2dp", "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", str(CHANNELS), "-t", "raw"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
        play = subprocess.Popen(
            ["aplay", "-D", "default", "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", str(CHANNELS), "-t", "raw"],
            stdin=record.stdout, stderr=subprocess.PIPE,
        )
        record.stdout.close()
        self._processes = [record, play]
        return True

    def stop_all(self) -> None:
        for process in self._processes:
            process.terminate()
        for process in self._processes:
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
        self._processes = []
