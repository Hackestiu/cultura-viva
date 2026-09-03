#include "app_state.h"

AppUiState currentUiState = UI_BOOT_INTRO;
uint8_t personalityIndex = 0;
int16_t currentVolume = 70;
bool recordingActive = false;
bool photoTriggerFlag = false;
bool playShutterSoundFlag = false;
bool viewSwitchDebounced = true;
bool hasCapturedPhoto = false;
bool photoConfirmed = false;
bool photoWaitingConfirmation = false;

uint8_t get_personality_index() {
  return personalityIndex;
}

int get_volume() {
  return (int)currentVolume;
}

bool is_recording_active() {
  return recordingActive;
}

bool photo_trigger() {
  bool result = photoTriggerFlag;
  photoTriggerFlag = false;
  return result;
}

void confirm_photo_saved() {
  playShutterSoundFlag = true;
  hasCapturedPhoto = true;
  photoWaitingConfirmation = true;
}

bool view_switch_state() {
  return viewSwitchDebounced;
}

