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
extern bool playRecordingStoppedSoundFlag;
extern bool viewSwitchDebounced;
extern bool hasCapturedPhoto;
extern bool photoConfirmed;
extern bool photoWaitingConfirmation;
extern bool highResPhotoDrawn;
extern bool volumeOverlayVisible;
extern unsigned long lastVolumeChangeMillis;
const unsigned long VOLUME_OVERLAY_TIMEOUT_MS = 1500;

bool is_photo_waiting_confirmation();

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
 * Observed monument label for the "Photo validated!" screen.
 * Set by Python via set_detected_monument() before state 1.
 */
extern char detectedMonumentLabel[40];

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
 *
 * Called over the Bridge by the MPU, which ends a recording once the visitor falls
 * silent. Stopping this way raises playRecordingStoppedSoundFlag so the visitor hears
 * the same confirmation tone the D7 button gives.
 *
 * @param active True to activate recording, false to deactivate.
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
 * Returns true when the system is ready to receive and display live camera frames.
 * Returns false while awaiting photo confirmation, during AI processing/playback, or while validating.
 */
bool camera_live_view_active();

/**
 * Sets whether the AI pipeline is actively processing a question (STT transcription, SLM generation, TTS synthesis).
 *
 * @param active True while processing is running, false when complete.
 */
void set_processing_active(bool active);

/**
 * Returns whether the AI pipeline is currently generating a response.
 */
bool is_processing_active();

/**
 * Sets whether speech response audio playback is currently running.
 *
 * @param active True during playback, false when complete.
 */
void set_playback_active(bool active);

/**
 * Returns true once when a photo capture has been triggered, then atomically resets the flag.
 * Subsequent calls return false until the next trigger event.
 */
bool photo_trigger();

/**
 * Notifies the MCU that the captured photo has been persisted by Python.
 * Schedules the shutter sound and shows the confirmation prompt on the LCD.
 */
void confirm_photo_saved();

/**
 * Returns the current debounced physical mode switch position.
 * True = camera mode (switch ON), false = map mode (switch OFF).
 */
bool view_switch_state();

/**
 * Sets the photo vision validation state and redraws the corresponding status screen.
 *
 * @param state -1 for idle, 0 for in-progress scan, 1 for valid monument, 2 for non-monument / retake.
 */
void set_photo_validation_state(int state);

/**
 * Sets the human-readable site name shown on the invalid monument retake screen.
 * Must be called before set_photo_validation_state(2).
 *
 * @param msg Location name (e.g., "Park Guell").
 */
void set_retake_message(String msg);

/**
 * Sets the detected monument label string for the "Photo validated!" screen.
 * Called by Python before set_photo_validation_state(1).
 *
 * @param msg Monument element name (e.g., "Escalinata del Drac").
 */
void set_detected_monument(String msg);

