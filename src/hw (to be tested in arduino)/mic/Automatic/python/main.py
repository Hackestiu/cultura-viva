"""
Bluetooth Bidirectional Audio - MPU application entry point.

The application starts in automatic voice-activated mode: as soon
as a trusted device is connected, DuplexVoiceRouter continuously
listens to the local microphone and switches, with no manual
interaction, between relaying incoming Bluetooth audio to the local
speaker ("listen") and relaying the local microphone to the
Bluetooth device ("speak").

The physical button is only used for:
  - Short press: mute/unmute the local microphone (forces "listen").
  - Long press: open a manual Bluetooth pairing window.

"""

import time
import signal
import logging

try:
    from arduino.app_utils import App, Bridge
except ModuleNotFoundError:
    App = None
    Bridge = None

from config import (
    TRUSTED_DEVICE_MAC,
    TRUSTED_DEVICE_NAME,
    RECONNECT_INTERVAL,
    PAIRING_SCAN_SECONDS,
)
from bluetooth_manager import BluetoothManager
from voice_router import DuplexVoiceRouter, VoiceState

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("bt_audio_bridge")


class Application:
    def __init__(self):
        self.bt = BluetoothManager(TRUSTED_DEVICE_MAC, TRUSTED_DEVICE_NAME)
        self.router = DuplexVoiceRouter(on_state_change=self._on_voice_state_change)
        self.muted = False
        self._router_active = False
        self.bt.start_auto_reconnect(interval=RECONNECT_INTERVAL)

    def _on_voice_state_change(self, state: VoiceState) -> None:
        log.info("Voice router state: %s", state.value)

    def _sync_router(self) -> None:
        """Starts or stops the automatic voice router based on the
        current Bluetooth connection state, with no manual step."""
        connected = self.bt.is_connected()
        if connected and not self._router_active:
            log.info("Trusted device connected, starting automatic voice router")
            self.router.start(self.bt.mac)
            self.router.set_muted(self.muted)
            self._router_active = True
        elif not connected and self._router_active:
            log.info("Trusted device lost, stopping automatic voice router")
            self.router.stop()
            self._router_active = False

    def toggle_mute(self) -> None:
        self.muted = not self.muted
        self.router.set_muted(self.muted)
        log.info("Microphone %s", "muted" if self.muted else "unmuted")

    def start_pairing(self) -> None:
        log.info("Manual pairing requested")
        self.router.stop()
        self._router_active = False
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
            event = 0
        if event == 1:
            self.toggle_mute()
        elif event == 2:
            self.start_pairing()
        self._sync_router()


def run_app() -> None:
    if App is None:
        raise RuntimeError("Arduino App Lab is unavailable; use the host tests instead")
    app_state = Application()

    def loop():
        app_state.poll()
        time.sleep(0.2)

    def shutdown(*_args):
        log.info("Shutting down, stopping voice router and Bluetooth threads")
        app_state.router.stop()
        app_state.bt.stop_auto_reconnect()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    App.run(user_loop=loop)


if __name__ == "__main__":
    run_app()