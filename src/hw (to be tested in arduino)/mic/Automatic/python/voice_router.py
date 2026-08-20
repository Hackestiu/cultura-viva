"""
Automatic voice-activated switching between "speak" and "listen"
modes, with a button-controlled microphone mute.

The local microphone is captured continuously and analyzed for
voice activity (VAD). While the user is silent, incoming Bluetooth
audio is relayed live to the local speaker ("listen" state). As
soon as the user starts talking, the incoming BT stream is stopped
and the local microphone is relayed live to the Bluetooth device
("speak" state) instead. 
"""

import array
import math
import logging
import subprocess
import threading
import time
from enum import Enum
from typing import Optional

from config import (
    SAMPLE_RATE,
    CHANNELS,
    VAD_THRESHOLD,
    VAD_ATTACK_CHUNKS,
    VAD_RELEASE_MS,
    VAD_CHUNK_MS,
)

log = logging.getLogger("bt_audio_bridge.voice_router")

SAMPLE_WIDTH_BYTES = 2  # S16_LE


def _rms(chunk: bytes) -> float:
    if not chunk:
        return 0.0
    samples = array.array("h")
    try:
        samples.frombytes(chunk)
    except ValueError:
        return 0.0
    if not samples:
        return 0.0
    total = sum(s * s for s in samples)
    return math.sqrt(total / len(samples))


class VoiceState(Enum):
    LISTEN = "listen"
    SPEAK = "speak"


class DuplexVoiceRouter:
    """Owns the microphone capture process and switches between a
    live BT-to-speaker relay and a live mic-to-BT relay based on
    voice activity, with no external trigger required."""

    def __init__(self, on_state_change=None):
        self._mac: Optional[str] = None
        self._state = VoiceState.LISTEN
        self._muted = False
        self._on_state_change = on_state_change

        self._mic_proc: Optional[subprocess.Popen] = None
        self._bt_out_proc: Optional[subprocess.Popen] = None       # mic -> BT (speak)
        self._listen_rec_proc: Optional[subprocess.Popen] = None   # BT -> local (listen)
        self._listen_play_proc: Optional[subprocess.Popen] = None

        self._loud_chunks = 0
        self._last_loud_time = 0.0

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self, mac: str) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._mac = mac
            self._stop_event.clear()
            self._start_mic_capture()
            self._enter_listen()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
        self._teardown_all()

    def set_muted(self, muted: bool) -> None:
        # Muting forces the LISTEN state and stops forwarding mic
        # audio, without tearing down the capture process.
        with self._lock:
            self._muted = muted
            if muted and self._state == VoiceState.SPEAK:
                self._enter_listen()

    @property
    def state(self) -> VoiceState:
        return self._state

    # -- mic capture: always running, used both for VAD metering
    #    and, while speaking, as the source forwarded to Bluetooth --

    def _start_mic_capture(self) -> None:
        cmd = [
            "arecord", "-D", "default",
            "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", str(CHANNELS),
            "-t", "raw",
        ]
        self._mic_proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def _run(self) -> None:
        chunk_bytes = int(SAMPLE_RATE * CHANNELS * SAMPLE_WIDTH_BYTES * VAD_CHUNK_MS / 1000)
        stream = self._mic_proc.stdout
        while not self._stop_event.is_set():
            chunk = stream.read(chunk_bytes)
            if not chunk:
                break
            level = _rms(chunk)
            now = time.monotonic()

            if level >= VAD_THRESHOLD:
                self._loud_chunks += 1
                self._last_loud_time = now
            else:
                self._loud_chunks = 0

            if (not self._muted and self._state == VoiceState.LISTEN and
                    self._loud_chunks >= VAD_ATTACK_CHUNKS):
                self._enter_speak()

            if not self._muted and self._state == VoiceState.SPEAK:
                silence_ms = (now - self._last_loud_time) * 1000
                if silence_ms >= VAD_RELEASE_MS:
                    self._enter_listen()
                elif self._bt_out_proc is not None and self._bt_out_proc.stdin:
                    try:
                        self._bt_out_proc.stdin.write(chunk)
                    except (BrokenPipeError, OSError):
                        log.warning("BT output pipe closed unexpectedly")
                        self._enter_listen()

        self._teardown_all()

    # -- state transitions ------------------------------------------

    def _enter_listen(self) -> None:
        self._stop_speak_pipe()
        self._start_listen_pipe()
        self._set_state(VoiceState.LISTEN)

    def _enter_speak(self) -> None:
        self._stop_listen_pipe()
        self._start_speak_pipe()
        self._set_state(VoiceState.SPEAK)

    def _set_state(self, new_state: VoiceState) -> None:
        if self._state != new_state:
            self._state = new_state
            log.info("Voice router state: %s", new_state.value)
            if self._on_state_change:
                self._on_state_change(new_state)

    def _start_speak_pipe(self) -> None:
        if self._bt_out_proc is not None or self._mac is None:
            return
        cmd = [
            "aplay", "-D", f"bluealsa:DEV={self._mac},PROFILE=a2dp",
            "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", str(CHANNELS),
            "-t", "raw",
        ]
        self._bt_out_proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    def _stop_speak_pipe(self) -> None:
        if self._bt_out_proc is None:
            return
        try:
            if self._bt_out_proc.stdin:
                self._bt_out_proc.stdin.close()
        except OSError:
            pass
        self._bt_out_proc.terminate()
        try:
            self._bt_out_proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._bt_out_proc.kill()
        self._bt_out_proc = None

    def _start_listen_pipe(self) -> None:
        if self._listen_play_proc is not None or self._mac is None:
            return
        record_cmd = [
            "arecord", "-D", f"bluealsa:DEV={self._mac},PROFILE=a2dp",
            "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", str(CHANNELS),
            "-t", "raw",
        ]
        play_cmd = [
            "aplay", "-D", "default",
            "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", str(CHANNELS),
            "-t", "raw",
        ]
        self._listen_rec_proc = subprocess.Popen(record_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._listen_play_proc = subprocess.Popen(play_cmd, stdin=self._listen_rec_proc.stdout, stderr=subprocess.PIPE)
        self._listen_rec_proc.stdout.close()

    def _stop_listen_pipe(self) -> None:
        for proc in (self._listen_rec_proc, self._listen_play_proc):
            if proc is None:
                continue
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        self._listen_rec_proc = None
        self._listen_play_proc = None

    def _teardown_all(self) -> None:
        self._stop_speak_pipe()
        self._stop_listen_pipe()
        if self._mic_proc is not None:
            self._mic_proc.terminate()
            try:
                self._mic_proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._mic_proc.kill()
            self._mic_proc = None