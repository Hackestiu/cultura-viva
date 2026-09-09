#pragma once

#include <stdint.h>
#include <Arduino.h>

/**
 * Onboarding, tutorial, and active runtime UI states.
 */
enum AppUiState {
  UI_BOOT_INTRO,
  UI_OPTIONS,
  UI_TUTORIAL_1,
  UI_TUTORIAL_2,
  UI_TUTORIAL_3,
  UI_VOICE_SELECT,
  UI_ACTIVE
};

// Global system state variables
extern AppUiState currentUiState;
extern uint8_t personalityIndex;
extern int16_t currentVolume;
extern bool recordingActive;
extern bool processingActive;
extern bool playbackActive;
extern bool photoTriggerFlag;
extern bool playShutterSoundFlag;
extern bool viewSwitchDebounced;
extern bool hasCapturedPhoto;
extern bool photoConfirmed;
extern bool photoWaitingConfirmation;
extern bool volumeOverlayVisible;
extern unsigned long lastVolumeChangeMillis;
const unsigned long VOLUME_OVERLAY_TIMEOUT_MS = 1500;

/**
 * Assistant status overlay states for UI pill messages.
 */
enum UiOverlayType {
  UI_OVERLAY_NONE = 0,
  UI_OVERLAY_RECORDING,
  UI_OVERLAY_GENERATING,
  UI_OVERLAY_SPEAKING
};

UiOverlayType getCurrentOverlayType();

/**
 * Vision validation state for the photo flow.
 *  -1 = idle (not validating)
 *   0 = checking / scanning the photo (animated dots)
 *   1 = valid monument detected (show success screen, then confirmation)
 *   2 = not a monument (show retake screen, then back to camera)
 */
extern int8_t photoValidationState;

/**
 * Location label for the "not a monument in <X>" retake screen.
 * Set by Python via set_retake_message() before state 2.
 */
extern char retakeLocationLabel[40];

/**
 * Returns the currently selected personality index (0=Artistic, 1=Technical, 2=Child).
 */
uint8_t get_personality_index();

/**
 * Returns the current output volume percentage (0 to 100).
 */
int get_volume();

/**
 * Sets whether user audio recording is active.
 */
void set_recording_active(bool active);

/**
 * Returns whether user audio recording is currently active.
 */
bool is_recording_active();

/**
 * Returns whether audio playback is currently active.
 */
bool is_playback_active();

/**
 * Returns whether Python should continue sending live camera frames.
 * Returns whether the system is currently ready to receive and display live camera frames.
 * Returns false when awaiting photo confirmation, during assistant processing/playback, or while validating.
 */
bool camera_live_view_active();

/**
 * Sets whether the Python audio/AI pipeline is processing the current question (STT, SLM, TTS synthesis).
 * Sets whether the AI pipeline is actively processing an audio question (transcription, reasoning, speech synthesis).
 *
 * @param active True if processing is running, false otherwise.
 */
void set_processing_active(bool active);

/**
 * Returns whether the system is currently processing an answer.
 * Returns whether the AI pipeline is currently generating a response.
 */
bool is_processing_active();

/**
 * Sets whether the Python audio playback is active through headphones/speaker.
 * Sets whether speech response audio playback is currently running.
 *
 * @param active True during playback, false otherwise.
 */
void set_playback_active(bool active);

/**
 * Returns true if a photo capture was triggered and clears the trigger flag.
 * Checks if a capture event occurred and atomically resets the event flag.
 *
 * @return True once upon capture trigger, false thereafter.
 */
bool photo_trigger();

/**
 * Confirms that a photo was successfully saved by Python, scheduling shutter sound feedback.
 * Notifies the MCU that the captured photo has been persisted, initiating confirmation UI and audio feedback.
 */
void confirm_photo_saved();

/**
 * Returns the debounced state of the display mode selection switch.
 * Returns the current debounced physical mode switch position (true for camera mode, false for map mode).
 */
bool view_switch_state();

/**
 * Sets the photo vision validation state:
 *  -1 = idle, 0 = checking, 1 = valid, 2 = invalid/retake
 * Updates the monument validation status shown on screen.
 *
 * @param state -1 for idle, 0 for in-progress scan, 1 for valid monument, 2 for non-monument / retake.
 */
void set_photo_validation_state(int state);

/**
 * Sets the location label string for the "not a monument in <X>" retake screen.
 * Called by Python before set_photo_validation_state(2).
 * Sets the human-readable site name displayed on the invalid monument retake screen.
 *
 * @param msg Location name (e.g., "Park Guell").
 */
void set_retake_message(String msg);

