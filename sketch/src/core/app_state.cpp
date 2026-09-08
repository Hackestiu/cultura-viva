#include "app_state.h"
#include <Arduino.h>

AppUiState currentUiState = UI_BOOT_INTRO;
uint8_t personalityIndex = 0;
int16_t currentVolume = 70;
bool recordingActive = false;
bool processingActive = false;
bool playbackActive = false;
bool photoTriggerFlag = false;
bool playShutterSoundFlag = false;
bool viewSwitchDebounced = true;
bool hasCapturedPhoto = false;
bool photoConfirmed = false;
bool photoWaitingConfirmation = false;
bool volumeOverlayVisible = false;
unsigned long lastVolumeChangeMillis = 0;
int8_t photoValidationState = -1;
char retakeLocationLabel[40] = "this location";

uint8_t get_personality_index() {
  return personalityIndex;
}

int get_volume() {
  return (int)currentVolume;
}

void set_recording_active(bool active) {
  recordingActive = active;
}

bool is_recording_active() {
  return recordingActive;
}

bool is_playback_active() {
  return playbackActive;
}

bool camera_live_view_active() {
  return viewSwitchDebounced && !photoWaitingConfirmation && !processingActive && !playbackActive && (photoValidationState == -1);
}

void set_processing_active(bool active) {
  processingActive = active;
}

void set_playback_active(bool active) {
  playbackActive = active;
}

UiOverlayType getCurrentOverlayType() {
  if (recordingActive) {
    return UI_OVERLAY_RECORDING;
  }
  if (processingActive) {
    return UI_OVERLAY_GENERATING;
  }
  if (playbackActive) {
    return UI_OVERLAY_SPEAKING;
  }
  return UI_OVERLAY_NONE;
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

void set_photo_validation_state(int state) {
  photoValidationState = (int8_t)state;
}

void set_retake_message(String msg) {
  strncpy(retakeLocationLabel, msg.c_str(), sizeof(retakeLocationLabel) - 1);
  retakeLocationLabel[sizeof(retakeLocationLabel) - 1] = '\0';
}
