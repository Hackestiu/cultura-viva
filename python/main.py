"""
Project Personality - MPU application entry point.

Functionalities triggered via RPC from sketch.ino:
- 'photo_trigger' (external button D7): takes a photo with the webcam (Brio 105)
  at full resolution (1080p, verified -- see hw/camera_module.py).
  When the photo is saved successfully, confirms to sketch ('confirm_photo_saved')
  to sound the buzzer.
- 'view_switch_state' (switch D6): if ON, sends a thumbnail of the webcam
  TO THE SKETCH IN CHUNKS ('receive_camera_chunk') every CAMERA_SEND_INTERVAL
  seconds, preventing RPC channel message size overflow (see hw/camera_module.py).
- 'is_recording_active' (button D7 in minimap mode, TOGGLE): 1st click starts
  recording, 2nd click stops. While active, records audio and on stop saves it
  tagged with the Personality selected via 'get_personality_index' (see
  hw/microphone_module.py and model_module.py). Then executes the Cultura Viva
  pipeline: STT -> Vision -> KG -> SLM -> TTS (played via 3.5mm jack headphones).
- 'get_volume' (Modulino Knob): returns volume percentage (0 - 100%) to dynamically
  adjust playback volume through amixer.

Modular code: hardware peripherals live in the hw/ package
(hw.camera_module, hw.microphone_module, hw.audio_playback_module,
hw.location_module) and high-level AI/logic modules live in the core/ package
(core.model_module, core.vision_module, core.minimap_module). Configuration is centralized in config.py.
"""

import sys
import time

# Ensure system-wide installed AI packages are accessible in Arduino App Lab sandbox
for p in [
    "/usr/local/lib/python3.13/dist-packages",
    "/usr/local/lib/python3.13/site-packages",
    "/usr/lib/python3/dist-packages",
    "/usr/lib/python3.13/dist-packages",
    "/home/arduino/.local/lib/python3.13/site-packages",
]:
    if p not in sys.path:
        sys.path.append(p)

from config import (
    CAM_CHUNK_PIXELS,
    CAM_THUMB_H,
    CAM_THUMB_W,
    CAMERA_CHUNK_DELAY_S,
    CAMERA_SEND_INTERVAL,
    MINIMAP_DIR,
    MODELS_DIR,
    PHOTOS_DIR,
    POLL_INTERVAL,
    RECORDINGS_DIR,
)
from core.minimap_module import MinimapManager
from core.model_module import ModelRegistry
from core.vision_module import VisionClassifier
from hw.audio_playback_module import AudioPlayer
from hw.camera_module import CameraManager
from hw.location_module import LocationRegistry
from hw.microphone_module import MicrophoneManager

try:
    from arduino.app_utils import App, Bridge
except ModuleNotFoundError:
    App = None
    Bridge = None

camera     = CameraManager()
microphone = MicrophoneManager()
models     = ModelRegistry()
vision     = VisionClassifier()
location   = LocationRegistry()
player     = AudioPlayer()


def run_app() -> None:
    if App is None or Bridge is None or not microphone.available:
        raise RuntimeError("Arduino App Lab not available; can only be executed via App Lab")

    microphone.start()
    camera.ensure_open()

    print(f"Photos will be saved to: {PHOTOS_DIR}")
    print(f"Recordings will be saved to: {RECORDINGS_DIR}")
    print(f"Models (A/B/C) read from: {MODELS_DIR}")
    print(f"Minimap content at: {MINIMAP_DIR}")
    print(f"Camera view: thumbnail {CAM_THUMB_W}x{CAM_THUMB_H} in {CAM_CHUNK_PIXELS}px chunks, every {CAMERA_SEND_INTERVAL:.0f}s")
    print("Waiting for button D7 (photo), buttons A/B/C (recording), Modulino Knob (volume) and switch D6...")

    last_camera_send = 0.0
    last_volume = -1

    def loop():
        nonlocal last_camera_send, last_volume

        # --- Modulino Knob: Volume control ---
        try:
            current_volume = Bridge.call("get_volume")
            if current_volume is not None and current_volume != last_volume:
                last_volume = current_volume
                player.set_volume(current_volume)
        except Exception:
            pass

        # --- Photo (button D7) ---
        try:
            if Bridge.call("photo_trigger"):
                saved_path = camera.take_photo()
                if saved_path is not None:
                    # Immediately send captured photo frame to LCD for preview
                    camera.send_view_frame_chunked(
                        Bridge, CAM_THUMB_W, CAM_THUMB_H, CAM_CHUNK_PIXELS, CAMERA_CHUNK_DELAY_S
                    )
                    Bridge.call("confirm_photo_saved")
        except Exception as exc:
            print(f"[ERROR] Checking button D7 / taking photo: {exc}")

        # --- Camera Live View (chunked) ---
        try:
            if Bridge.call("view_switch_state"):
                now = time.time()
                if now - last_camera_send >= CAMERA_SEND_INTERVAL:
                    last_camera_send = now
                    camera.send_view_frame_chunked(
                        Bridge, CAM_THUMB_W, CAM_THUMB_H, CAM_CHUNK_PIXELS, CAMERA_CHUNK_DELAY_S
                    )
        except Exception as exc:
            print(f"[ERROR] Sending camera frame chunks: {exc}")

        # --- Toggle Recording (D7 in minimap mode) ---
        try:
            if Bridge.call("is_recording_active"):
                photo_path = camera.last_photo_path
                if photo_path is None or not photo_path.exists():
                    print("[WARN] Audio recording rejected: No photo taken yet! Switch to camera mode and take a photo first.")
                else:
                    personality_index = Bridge.call("get_personality_index")  # 0/1/2
                    button_id = "ABC"[personality_index]
                    model_name = models.name_for(button_id)
                    print(f"[EVENT] Recording started (personality: {model_name}) -> recording...")
                    audio = microphone.record_while_held(
                        is_still_held=lambda: Bridge.call("is_recording_active")
                    )
                    if audio is not None:
                        wav_path = microphone.save(button_id, model_name, audio)

                        # --- Cultura Viva Pipeline ---
                        # Each step is individually guarded: if a model fails or is missing,
                        # the subsequent step receives an empty string/None and proceeds cleanly.
                        question_text = microphone.transcribe(wav_path)

                        site       = location.current()          # 'park_guell' / 'sagrada_familia'
                        element    = vision.classify(site, photo_path) if photo_path else None

                        kg_context = models.get_kg_context(element, personality=model_name) if element else ""
                        answer     = models.generate_response(
                            question=question_text,
                            element=element,
                            personality=model_name,
                            kg_context=kg_context,
                        )
                        player.synthesize_and_play(answer, personality=model_name)
                    else:
                        print("[WARN] Empty recording (0 chunks captured)")
        except Exception as exc:
            print(f"[ERROR] Recording/processing question: {exc}")

        time.sleep(POLL_INTERVAL)

    App.run(user_loop=loop)


if __name__ == "__main__":
    run_app()