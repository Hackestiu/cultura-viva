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
extern bool photoTriggerFlag;
extern bool playShutterSoundFlag;
extern bool viewSwitchDebounced;
extern bool hasCapturedPhoto;
extern bool photoConfirmed;
extern bool photoWaitingConfirmation;

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
 * Returns whether user audio recording is currently active.
 */
bool is_recording_active();

/**
 * Returns whether Python should continue sending live camera frames.
 */
bool camera_live_view_active();

/**
 * Sets whether the Python audio/AI pipeline is processing the current question.
 */
void set_processing_active(bool active);

/**
 * Returns true if a photo capture was triggered and clears the trigger flag.
 */
bool photo_trigger();

/**
 * Confirms that a photo was successfully saved by Python, scheduling shutter sound feedback.
 */
void confirm_photo_saved();

/**
 * Returns the debounced state of the display mode selection switch.
 */
bool view_switch_state();

/**
 * Sets the photo vision validation state:
 *  -1 = idle, 0 = checking, 1 = valid, 2 = invalid/retake
 */
void set_photo_validation_state(int state);

/**
 * Sets the location label string for the "not a monument in <X>" retake screen.
 * Called by Python before set_photo_validation_state(2).
 */
void set_retake_message(String msg);

