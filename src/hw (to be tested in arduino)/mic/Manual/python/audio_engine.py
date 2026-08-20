"""
Audio capture and playback over BlueALSA.

Two profiles are used against the same bluealsa PCM device string:
  - Recording: the UNO Q behaves as an A2DP sink, capturing whatever
    audio a connected phone/source streams to it.
  - Playback:  the UNO Q behaves as an A2DP source, relaying its
    local microphone input live to a connected speaker/headset.

Both directions require the bluealsa daemon to be started with
both the a2dp-sink and a2dp-source profiles enabled (see README).
"""

import logging
import subprocess
import threading
from typing import List, Optional

from config import SAMPLE_RATE, CHANNELS

log = logging.getLogger("bt_audio_bridge.audio")


class AudioEngine:
    def __init__(self):
        self._record_proc: Optional[subprocess.Popen] = None
        self._playback_procs: List[subprocess.Popen] = []
        self._lock = threading.Lock()

    @staticmethod
    def _bluealsa_device(mac: str) -> str:
        return f"bluealsa:DEV={mac},PROFILE=a2dp"

    def start_recording(self, mac: str, output_path: str) -> bool:
        with self._lock:
            if self._record_proc is not None:
                return False
            cmd = [
                "arecord", "-D", self._bluealsa_device(mac),
                "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", str(CHANNELS),
                output_path,
            ]
            log.info("Starting recording: %s", " ".join(cmd))
            self._record_proc = subprocess.Popen(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
            )
            return True

    def stop_recording(self) -> None:
        with self._lock:
            if self._record_proc is not None:
                self._terminate(self._record_proc)
                self._record_proc = None

    def start_playback(self, mac: str, source_path: str) -> bool:
        """Plays a local audio file out to the trusted Bluetooth device."""
        with self._lock:
            if self._playback_procs:
                return False
            cmd = ["aplay", "-D", self._bluealsa_device(mac), source_path]
            log.info("Starting file playback: %s", " ".join(cmd))
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
            self._playback_procs = [proc]
            return True

    def start_playback_live_mic(self, mac: str) -> bool:
        """Relays the local microphone input live to the Bluetooth device."""
        with self._lock:
            if self._playback_procs:
                return False
            record_cmd = [
                "arecord", "-D", "default",
                "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", str(CHANNELS),
                "-t", "raw",
            ]
            play_cmd = [
                "aplay", "-D", self._bluealsa_device(mac),
                "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", str(CHANNELS),
                "-t", "raw",
            ]
            log.info("Starting live microphone relay to %s", mac)
            rec_proc = subprocess.Popen(record_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            play_proc = subprocess.Popen(play_cmd, stdin=rec_proc.stdout, stderr=subprocess.PIPE)
            rec_proc.stdout.close()
            self._playback_procs = [rec_proc, play_proc]
            return True

    def stop_playback(self) -> None:
        with self._lock:
            for proc in self._playback_procs:
                self._terminate(proc)
            self._playback_procs = []

    def is_recording(self) -> bool:
        return self._record_proc is not None and self._record_proc.poll() is None

    def is_playing(self) -> bool:
        return bool(self._playback_procs) and all(p.poll() is None for p in self._playback_procs)

    def stop_all(self) -> None:
        self.stop_recording()
        self.stop_playback()

    @staticmethod
    def _terminate(proc: subprocess.Popen) -> None:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()