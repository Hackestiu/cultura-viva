#pragma once

#include <stdint.h>

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
extern bool photoTriggerFlag;
extern bool playShutterSoundFlag;
extern bool viewSwitchDebounced;
extern bool hasCapturedPhoto;
extern bool photoConfirmed;
extern bool photoWaitingConfirmation;

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

