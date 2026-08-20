"""
Bluetooth connection management for the Bidirectional Audio Bridge.

Wraps bluetoothctl to provide:
  - Manual pairing to a new device through a timed discovery window.
  - Trust configuration so future connections happen without user input.
  - A background thread that keeps the trusted device connected.
"""

import re
import time
import logging
import threading
import subprocess
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
                ["bluetoothctl", *args],
                capture_output=True, text=True, timeout=timeout,
            )
            return result.stdout
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
            log.warning("bluetoothctl %s failed: %s", " ".join(args), exc)
            return ""

    def is_connected(self) -> bool:
        if not self.mac:
            return False
        output = self._run_oneshot(["info", self.mac])
        return "Connected: yes" in output

    def connect(self) -> bool:
        if not self.mac:
            return False
        output = self._run_oneshot(["connect", self.mac], timeout=15)
        return "Connection successful" in output or self.is_connected()

    def trust(self, mac: str) -> None:
        self._run_oneshot(["trust", mac])

    def pair(self, mac: str) -> bool:
        output = self._run_oneshot(["pair", mac], timeout=20)
        return "Pairing successful" in output or "already paired" in output.lower()

    def pair_new_device(self, scan_seconds: int = 20) -> Optional[str]:
        """
        Opens a discovery window, pairs and trusts the first device
        matching name_hint (or the first discoverable device if no
        hint is set), and stores it as the trusted MAC address.
        """
        try:
            proc = subprocess.Popen(
                ["bluetoothctl"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1,
            )
        except (FileNotFoundError, OSError) as exc:
            log.error("Could not start bluetoothctl: %s", exc)
            return None
        discovered = {}

        def read_output():
            for line in proc.stdout:
                match = DEVICE_LINE_RE.search(line)
                if match:
                    mac, name = match.group(1), match.group(2).strip()
                    discovered[mac] = name

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()

        def send(cmd: str):
            proc.stdin.write(cmd + "\n")
            proc.stdin.flush()

        send("agent NoInputNoOutput")
        send("default-agent")
        send("power on")
        send("pairable on")
        send("discoverable on")
        send("scan on")
        time.sleep(scan_seconds)
        send("scan off")
        time.sleep(1)
        send("quit")
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            log.error("bluetoothctl pairing session timed out")
            return None

        target_mac = self._select_target(discovered)
        if target_mac is None:
            return None

        if self.pair(target_mac):
            self.trust(target_mac)
            # Set the address before connecting so connect() uses the new device.
            previous_mac = self.mac
            self.mac = target_mac
            if self.connect():
                return f"{discovered.get(target_mac, target_mac)} ({target_mac})"
            self.mac = previous_mac
        return None

    def _select_target(self, discovered: dict) -> Optional[str]:
        if not discovered:
            return None
        if self.name_hint:
            for mac, name in discovered.items():
                if self.name_hint.lower() in name.lower():
                    return mac
            return None
        return next(iter(discovered))

    def start_auto_reconnect(self, interval: int = 10) -> None:
        if self._reconnect_thread is not None:
            return
        self._stop_event.clear()
        self._reconnect_thread = threading.Thread(
            target=self._reconnect_loop, args=(interval,), daemon=True
        )
        self._reconnect_thread.start()

    def stop_auto_reconnect(self) -> None:
        self._stop_event.set()
        if self._reconnect_thread is not None:
            self._reconnect_thread.join(timeout=2)
            self._reconnect_thread = None

    def _reconnect_loop(self, interval: int) -> None:
        while not self._stop_event.is_set():
            if self.mac and not self.is_connected():
                log.info("Trusted device not connected, attempting reconnect...")
                if self.connect():
                    log.info("Reconnected to %s", self.mac)
                else:
                    log.info("Reconnect attempt failed, retrying in %ss", interval)
            self._stop_event.wait(interval)