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
# Logging sinks are installed by config.py, which is imported above.
from logging_setup import get_log_file, logger
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
    "park_guell": "Parc Guell",
    "sagrada_familia": "Sagrada Familia",
}

_ELEMENT_DISPLAY_NAMES: dict[str, str] = {
    # Park Guell
    "escalinata_drac": "Escalinata del Drac",
    "sala_hipostila": "Sala Hipostila",
    "placa_natura": "Placa de la Natura",
    "casa_museu": "Casa Museu Gaudi",
    "3_viaductes": "Els Tres Viaductes",
    "turo_3_creus": "Turo Tres Creus",
    "pavellons_consergeria": "Pavello Consergeria",
    # Sagrada Familia
    "cupula": "Cupula",
    "facana_naixement": "Facana del Naixement",
    "facana_passio": "Facana de la Passio",
    "laterals": "Nau Lateral",
    "lateral_esquerra": "Nau Lateral Esquerra",
    "lateral_dreta": "Nau Lateral Dreta",
    "posterior": "Absis Posterior",
    "torres": "Torres de la Basilica",
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
                logger.warning("Could not delete {}: {}", f, exc)
    logger.info("Cleaned {} file(s) from {!r}.", deleted, str(directory))


def _preload_models() -> None:
    """Loads every AI model up front so the first user does not absorb the cold-start cost.

    Without this, the vision, STT, SLM and TTS models each load on first use, stacked inside
    a single interaction: the first question spends roughly twice the steady-state latency
    waiting on library imports and weight reads. Nothing is ever unloaded afterwards, so
    this moves the memory peak earlier rather than raising it.

    Every stage degrades gracefully — a failure here is logged and the on-demand loading
    path in each module still runs as before, so a missing model never blocks startup.
    """
    site = location.current()
    stages = (
        (f"vision ({site})", lambda: vision.preload(site)),
        ("speech-to-text", microphone.preload),
        ("language model", models.preload),
        ("text-to-speech", player.preload),
    )

    logger.info("Preloading AI models (first run may take a while)...")
    total = time.time()
    for label, load in stages:
        started = time.time()
        try:
            ok = load()
        except Exception as exc:
            logger.exception("Preload of {} failed: {}", label, exc)
            continue
        emit = logger.success if ok else logger.warning
        emit("Preloaded {} in {:.1f}s", label, time.time() - started)
    logger.info("Model preload finished in {:.1f}s.", time.time() - total)


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

    log_file = get_log_file()
    if log_file is not None:
        logger.info("Logging this run to: {}", log_file)

    microphone.start()
    camera.ensure_open()

    # Clean transient directories on every startup (disabled during testing to preserve files)
    # logger.info("Cleaning recordings and responses directories...")
    # _clean_dir(RECORDINGS_DIR)
    # _clean_dir(RESPONSES_DIR)

    logger.info("Photos will be saved to: {}", PHOTOS_DIR)
    logger.info("Recordings will be saved to: {}", RECORDINGS_DIR)
    logger.info("Models (A/B/C) read from: {}", MODELS_DIR)
    logger.info("Minimap content at: {}", MINIMAP_DIR)
    logger.info(
        "Camera view: thumbnail {}x{} in {}px chunks, every {:.0f}s",
        CAM_THUMB_W,
        CAM_THUMB_H,
        CAM_CHUNK_PIXELS,
        CAMERA_SEND_INTERVAL,
    )
    logger.info(
        "Hardware devices: camera=/dev/video{}, mic=ALSA card {}, playback={!r}",
        CAMERA_DEVICE_INDEX,
        MIC_DEVICE,
        PLAYBACK_DEVICE,
    )
    _preload_models()

    logger.info(
        "Waiting for button D7 (photo/recording), buttons A/B/C (personality), "
        "Modulino Knob (volume) and switch D6..."
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
                        logger.info(
                            "Photo is not a monument in {!r} -> retake screen shown.",
                            site,
                        )
                    else:
                        last_detected_element = element
                        last_detected_site = site
                        element_display = _ELEMENT_DISPLAY_NAMES.get(
                            element, element.replace("_", " ").title()
                        )
                        Bridge.call("set_detected_monument", element_display)
                        Bridge.call("set_photo_validation_state", 1)
                        logger.info(
                            "Photo validated: element={!r} ({!r}) at {!r} -> showing "
                            "valid screen, then confirmation.",
                            element,
                            element_display,
                            site,
                        )

                        if element and element != VISION_UNKNOWN_LABEL:
                            minimap.mark_detected(site, element)

                        # Prefill the SLM prompt now, on a background thread. Everything
                        # it needs — personality, element, facts — is already known, and
                        # the board is otherwise idle from here until the user finishes
                        # speaking. Doing it later, after STT, would put those ~20s of
                        # Cortex-A53 prefill squarely in the user's wait.
                        try:
                            warm_personality = models.name_for(
                                "ABC"[Bridge.call("get_personality_index")]
                            )
                            models.warm_prefix_async(element, warm_personality)
                        except Exception as exc:
                            logger.warning("Could not start SLM prefill: {}", exc)

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
            logger.exception(
                "Checking button D7 / taking photo / vision: {}", exc
            )

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
            logger.exception("Sending camera frame chunks: {}", exc)

        try:
            if Bridge.call("is_recording_active"):
                photo_path = camera.last_photo_path
                if photo_path is None or not photo_path.exists():
                    logger.warning(
                        "Audio recording rejected: no photo taken yet. Switch to "
                        "camera mode and take a photo first."
                    )
                else:
                    personality_index = Bridge.call("get_personality_index")
                    button_id = "ABC"[personality_index]
                    model_name = models.name_for(button_id)
                    logger.info(
                        "Recording started (personality: {}) -> speak now, "
                        "press D7 to stop...",
                        model_name,
                    )
                    # No-op when the photo already warmed this exact prompt. It only does
                    # work if the user switched personality after taking the photo, and
                    # then it overlaps the recording instead of the answer.
                    if last_detected_element:
                        models.warm_prefix_async(last_detected_element, model_name)
                    audio = microphone.record_until_stopped(
                        is_recording=lambda: Bridge.call("is_recording_active")
                    )
                    if audio is not None:
                        Bridge.call("set_processing_active", True)
                        try:
                            wav_path = microphone.save(button_id, model_name, audio)

                            question_text = microphone.transcribe(wav_path)
                            if not Bridge.call("is_processing_active"):
                                logger.info("Generation cancelled by user after STT.")
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
                                logger.info("Generation cancelled by user before SLM.")
                                return

                            kg_context = (
                                models.get_kg_context(element, personality=model_name)
                                if element
                                else ""
                            )

                            # The answer is spoken sentence by sentence as it decodes, so
                            # the first words are heard after one sentence instead of all
                            # sixty tokens.
                            speaking = False

                            def on_first_audio():
                                # Sound is starting: hand the UI over from the generating
                                # overlay to the speaking one, exactly as the non-streamed
                                # path used to at the same moment.
                                nonlocal speaking
                                speaking = True
                                try:
                                    Bridge.call("set_processing_active", False)
                                    Bridge.call("set_playback_active", True)
                                except Exception as exc:
                                    logger.warning(
                                        "Failed to flip bridge state at first audio: {}",
                                        exc,
                                    )

                            def still_active():
                                # Once playback has begun the sketch clears the processing
                                # flag and D7 no longer cancels, so polling it would abort
                                # the decode that is feeding the speaker.
                                if speaking:
                                    return True
                                return Bridge.call("is_processing_active")

                            speaker = player.stream(
                                personality=model_name,
                                bridge=Bridge,
                                on_first_audio=on_first_audio,
                            )
                            try:
                                answer = models.generate_response(
                                    question=question_text,
                                    element=element,
                                    personality=model_name,
                                    kg_context=kg_context,
                                    is_active_fn=still_active,
                                    on_sentence=speaker.feed,
                                )

                                if answer is None:
                                    # Cancelled mid-generation — drop whatever is queued
                                    logger.info(
                                        "Generation cancelled by user during SLM streaming."
                                    )
                                    speaker.cancel()
                                    return
                            except BaseException:
                                speaker.cancel()
                                raise

                            spoke = speaker.close()
                            if not spoke and answer:
                                # Nothing was streamed (an answer with no sentence
                                # boundary at all, or a synthesis failure): fall back to
                                # speaking it in one piece rather than staying silent.
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
                        logger.warning("Empty recording (0 chunks captured)")
        except Exception as exc:
            logger.exception("Recording/processing question: {}", exc)

        time.sleep(POLL_INTERVAL)

    App.run(user_loop=loop)


if __name__ == "__main__":
    run_app()
