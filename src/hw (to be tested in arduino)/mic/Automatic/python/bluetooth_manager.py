"""Small bluetoothctl wrapper with pairing and reconnect support."""

import logging
import re
import subprocess
import threading
import time
from typing import Optional

log = logging.getLogger("bt_audio_bridge.bluetooth")
DEVICE_LINE_RE = re.compile(r"Device\s+([0-9A-Fa-f:]{17})\s+(.*)")


class BluetoothManager:
    def __init__(self, mac: Optional[str], name_hint: Optional[str] = None):
        self.mac = mac
        self.name_hint = name_hint
        self._stop_event = threading.Event()
        self._reconnect_thread: Optional[threading.Thread] = None

    @staticmethod
    def _run_oneshot(args, timeout=10) -> str:
        try:
            result = subprocess.run(
                ["bluetoothctl", *args], capture_output=True, text=True, timeout=timeout
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            log.warning("bluetoothctl %s unavailable: %s", " ".join(args), exc)
            return ""
        return result.stdout

    def is_connected(self) -> bool:
        return bool(self.mac and "Connected: yes" in self._run_oneshot(["info", self.mac]))

    def connect(self) -> bool:
        if not self.mac:
            return False
        output = self._run_oneshot(["connect", self.mac], timeout=15)
        return "Connection successful" in output or self.is_connected()

    def pair_new_device(self, scan_seconds: int = 20) -> Optional[str]:
        try:
            proc = subprocess.Popen(
                ["bluetoothctl"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1,
            )
        except (FileNotFoundError, OSError) as exc:
            log.error("Could not start bluetoothctl: %s", exc)
            return None
        discovered = {}

        def collect():
            for line in proc.stdout:
                match = DEVICE_LINE_RE.search(line)
                if match:
                    discovered[match.group(1)] = match.group(2).strip()

        threading.Thread(target=collect, daemon=True).start()
        for command in ("agent NoInputNoOutput", "default-agent", "power on", "pairable on", "discoverable on", "scan on"):
            proc.stdin.write(command + "\n")
            proc.stdin.flush()
        time.sleep(scan_seconds)
        for command in ("scan off", "quit"):
            proc.stdin.write(command + "\n")
            proc.stdin.flush()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            log.error("bluetoothctl pairing session timed out")
            return None

        target = next((mac for mac, name in discovered.items()
                       if not self.name_hint or self.name_hint.lower() in name.lower()), None)
        if not target:
            return None
        pair_output = self._run_oneshot(["pair", target], timeout=20)
        if "Pairing successful" not in pair_output and "already paired" not in pair_output.lower():
            return None
        self._run_oneshot(["trust", target])
        previous = self.mac
        self.mac = target
        if self.connect():
            return f"{discovered.get(target, target)} ({target})"
        self.mac = previous
        return None

    def start_auto_reconnect(self, interval: int = 10) -> None:
        if self._reconnect_thread:
            return
        self._stop_event.clear()
        self._reconnect_thread = threading.Thread(target=self._reconnect_loop, args=(interval,), daemon=True)
        self._reconnect_thread.start()

    def stop_auto_reconnect(self) -> None:
        self._stop_event.set()
        if self._reconnect_thread:
            self._reconnect_thread.join(timeout=2)
            self._reconnect_thread = None

    def _reconnect_loop(self, interval: int) -> None:
        while not self._stop_event.is_set():
            if self.mac and not self.is_connected():
                self.connect()
            self._stop_event.wait(interval)
