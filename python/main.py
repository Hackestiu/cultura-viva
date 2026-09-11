"""
Main entry point managing hardware interactions and AI pipelines.

Manages Bridge RPC communication with the microcontroller to process camera feeds,
vision classifications, audio recordings, speech recognition, language models,
and text-to-speech synthesis.
"""

import sys
import time

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
    CAMERA_DEVICE_INDEX,
    CAMERA_SEND_INTERVAL,
    MIC_DEVICE,
    MINIMAP_DIR,
    MODELS_DIR,
    PHOTOS_DIR,
    PHOTO_PREVIEW_W,
    PHOTO_PREVIEW_H,
    PHOTO_CHUNK_PIXELS,
    PLAYBACK_DEVICE,
    POLL_INTERVAL,
    RECORDINGS_DIR,
    RESPONSES_DIR,
    VISION_UNKNOWN_LABEL,
)
from core.minimap_module import MinimapManager
from core.model_module import ModelRegistry
from core.vision_module import VisionClassifier
from hw.audio_playback_module import AudioPlayer
from hw.camera_module import CameraManager
from hw.location_module import LocationRegistry
from hw.microphone_module import MicrophoneManager

try:
    from arduino.app_utils import App, Bridge  # type: ignore[import]
except ModuleNotFoundError:
    App = None
    Bridge = None

camera = CameraManager()
microphone = MicrophoneManager()
models = ModelRegistry()
vision = VisionClassifier()
location = LocationRegistry()
player = AudioPlayer()
minimap = MinimapManager()

_LOCATION_LABELS: dict[str, str] = {
    "park_guell": "Parc Güell",
    "sagrada_familia": "Sagrada Família",
}


def _clean_dir(directory) -> None:
    """Deletes all files in a directory without removing the directory itself."""
    deleted = 0
    for f in directory.iterdir():
        if f.is_file():
            try:
                f.unlink()
                deleted += 1
            except Exception as exc:
                print(f"[WARN] Could not delete {f}: {exc}")
    print(f"[STARTUP] Cleaned {deleted} file(s) from '{directory}'.")


def run_app() -> None:
    """Initializes hardware connections and runs the main event polling loop.

    Monitors physical controls over Bridge RPC to stream live camera view, handle
    photo capture and landmark validation, record voice input, execute AI pipeline
    processing, and drive audio response synthesis.
    """
    if App is None or Bridge is None or not microphone.available:
        raise RuntimeError(
            "Arduino App Lab not available; can only be executed via App Lab"
        )

    microphone.start()
    camera.ensure_open()

    # Clean transient directories on every startup (photos are kept intentionally)
    print("[STARTUP] Cleaning recordings and responses directories...")
    _clean_dir(RECORDINGS_DIR)
    _clean_dir(RESPONSES_DIR)

    print(f"Photos will be saved to: {PHOTOS_DIR}")
    print(f"Recordings will be saved to: {RECORDINGS_DIR}")
    print(f"Models (A/B/C) read from: {MODELS_DIR}")
    print(f"Minimap content at: {MINIMAP_DIR}")
    print(
        f"Camera view: thumbnail {CAM_THUMB_W}x{CAM_THUMB_H} in {CAM_CHUNK_PIXELS}px chunks, every {CAMERA_SEND_INTERVAL:.0f}s"
    )
    print(
        f"Hardware devices: camera=/dev/video{CAMERA_DEVICE_INDEX}, "
        f"mic=ALSA card {MIC_DEVICE}, playback='{PLAYBACK_DEVICE}'"
    )
    print(
        "Waiting for button D7 (photo/recording), buttons A/B/C (personality), Modulino Knob (volume) and switch D6..."
    )

    last_camera_send = 0.0
    last_volume = -1

    last_detected_element: str | None = None
    last_detected_site: str | None = None

    def loop():
        nonlocal last_camera_send, last_volume, last_detected_element, last_detected_site

        minimap.set_location(location.current())

        try:
            current_volume = Bridge.call("get_volume")
            if current_volume is not None and current_volume != last_volume:
                last_volume = current_volume
                player.set_volume(current_volume)
        except Exception:
            pass

        try:
            if Bridge.call("photo_trigger"):
                saved_path = camera.take_photo()
                if saved_path is not None:
                    camera.send_view_frame_chunked(
                        Bridge,
                        CAM_THUMB_W,
                        CAM_THUMB_H,
                        CAM_CHUNK_PIXELS,
                        CAMERA_CHUNK_DELAY_S,
                    )

                    Bridge.call("set_photo_validation_state", 0)

                    site = location.current()
                    element = vision.classify(site, saved_path)

                    if element is None or element == "unknown":
                        location_label = _LOCATION_LABELS.get(
                            site, site.replace("_", " ").title()
                        )
                        Bridge.call("set_retake_message", location_label)
                        Bridge.call("set_photo_validation_state", 2)
                        last_detected_element = None
                        last_detected_site = None
                        print(
                            f"[VISION] Photo is not a monument in '{site}' -> retake screen shown."
                        )
                    else:
                        last_detected_element = element
                        last_detected_site = site
                        Bridge.call("set_photo_validation_state", 1)
                        print(
                            f"[VISION] Photo validated: element='{element}' at '{site}' -> showing valid screen, then confirmation."
                        )

                        if element and element != VISION_UNKNOWN_LABEL:
                            minimap.mark_detected(site, element)

                        # Wait for the "Photo validated!" hold screen (~2.2s) then stream high-res photo
                        time.sleep(2.2)
                        camera.send_photo_preview(
                            Bridge,
                            saved_path,
                            PHOTO_PREVIEW_W,
                            PHOTO_PREVIEW_H,
                            PHOTO_CHUNK_PIXELS,
                        )

        except Exception as exc:
            print(f"[ERROR] Checking button D7 / taking photo / vision: {exc}")

        try:
            if Bridge.call("camera_live_view_active"):
                now = time.time()
                if now - last_camera_send >= CAMERA_SEND_INTERVAL:
                    last_camera_send = now
                    camera.send_view_frame_chunked(
                        Bridge,
                        CAM_THUMB_W,
                        CAM_THUMB_H,
                        CAM_CHUNK_PIXELS,
                        CAMERA_CHUNK_DELAY_S,
                    )
        except Exception as exc:
            print(f"[ERROR] Sending camera frame chunks: {exc}")

        try:
            if Bridge.call("is_recording_active"):
                photo_path = camera.last_photo_path
                if photo_path is None or not photo_path.exists():
                    print(
                        "[WARN] Audio recording rejected: No photo taken yet! Switch to camera mode and take a photo first."
                    )
                else:
                    personality_index = Bridge.call("get_personality_index")
                    button_id = "ABC"[personality_index]
                    model_name = models.name_for(button_id)
                    print(
                        f"[EVENT] Recording started (personality: {model_name}) -> speak now, press D7 to stop..."
                    )
                    audio = microphone.record_until_stopped(
                        is_recording=lambda: Bridge.call("is_recording_active")
                    )
                    if audio is not None:
                        Bridge.call("set_processing_active", True)
                        try:
                            wav_path = microphone.save(button_id, model_name, audio)

                            question_text = microphone.transcribe(wav_path)
                            if not Bridge.call("is_processing_active"):
                                print("[INFO] Generation cancelled by user after STT.")
                                return

                            element = last_detected_element
                            site = last_detected_site or location.current()

                            if element is None:
                                element = (
                                    vision.classify(site, photo_path)
                                    if photo_path
                                    else None
                                )
                                if element and element != VISION_UNKNOWN_LABEL:
                                    minimap.mark_detected(site, element)

                            if not Bridge.call("is_processing_active"):
                                print("[INFO] Generation cancelled by user before SLM.")
                                return

                            kg_context = (
                                models.get_kg_context(element, personality=model_name)
                                if element
                                else ""
                            )
                            answer = models.generate_response(
                                question=question_text,
                                element=element,
                                personality=model_name,
                                kg_context=kg_context,
                            )

                            if not Bridge.call("is_processing_active"):
                                print("[INFO] Generation cancelled by user after SLM.")
                                return

                            player.synthesize_and_play(
                                answer, personality=model_name, bridge=Bridge
                            )
                        finally:
                            try:
                                Bridge.call("set_processing_active", False)
                            except Exception:
                                pass
                            try:
                                Bridge.call("set_playback_active", False)
                            except Exception:
                                pass
                    else:
                        print("[WARN] Empty recording (0 chunks captured)")
        except Exception as exc:
            print(f"[ERROR] Recording/processing question: {exc}")

        time.sleep(POLL_INTERVAL)

    App.run(user_loop=loop)


if __name__ == "__main__":
    run_app()
