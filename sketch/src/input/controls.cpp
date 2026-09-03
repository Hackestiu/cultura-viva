#include <Arduino.h>
#include <Wire.h>
#include <Arduino_RouterBridge.h>
#include "controls.h"
#include "../core/config.h"
#include "../core/app_state.h"
#include "../display/ui_manager.h"
#include "../display/camera_view.h"

ModulinoKnob    knob;
ModulinoButtons buttons;
ModulinoBuzzer  buzzer;

static bool lastExtBtnState = false;

static int16_t knobFiltered = 0;
static bool knobFilteredInit = false;

static int16_t lastKnobPos = 0;
static bool knobVolumeInit = false;

static bool viewSwitchRawLast = true;
static unsigned long viewSwitchLastChangeTime = 0;

static bool btnAHeld = false, btnBHeld = false, btnCHeld = false;
static bool btnAHeldPrev = false, btnBHeldPrev = false, btnCHeldPrev = false;

void initControls() {
  pinMode(EXT_BUTTON_PIN, INPUT_PULLUP);
  pinMode(VIEW_SWITCH_PIN, INPUT_PULLUP);

  Wire1.begin();
#if defined(WIRE_HAS_TIMEOUT) || defined(ARDUINO_ARCH_AVR) || defined(ARDUINO_ARCH_SAMD) || defined(ARDUINO_ARCH_RENESAS)
  Wire1.setWireTimeout(50000, true);
#endif
  Modulino.begin(Wire1);

  knob.begin();
  buttons.begin();
  buzzer.begin();

  buzzer.tone(1000, 150);
  delay(200);
}

int16_t readKnobFiltered() {
  int16_t raw = knob.get();
  if (!knobFilteredInit) {
    knobFiltered = raw;
    knobFilteredInit = true;
    return knobFiltered;
  }
  int16_t diff = raw - knobFiltered;
  if (diff > KNOB_MAX_JUMP || diff < -KNOB_MAX_JUMP) {
    return knobFiltered;
  }
  knobFiltered = raw;
  return knobFiltered;
}

void updateControls() {
  // Mode switch D6 handling with debouncing
  bool viewSwitchRaw = (digitalRead(VIEW_SWITCH_PIN) == HIGH);
  if (viewSwitchRaw != viewSwitchRawLast) {
    viewSwitchLastChangeTime = millis();
    viewSwitchRawLast = viewSwitchRaw;
  }
  if ((millis() - viewSwitchLastChangeTime) > VIEW_SWITCH_DEBOUNCE_MS
      && viewSwitchRaw != viewSwitchDebounced) {
    viewSwitchDebounced = viewSwitchRaw;
    Monitor.print("[EVENT] Switch D6 changed -> ");
    Monitor.println(viewSwitchDebounced ? "ON (camera mode)" : "OFF (map mode)");

    if (viewSwitchDebounced && recordingActive) {
      recordingActive = false;
      buzzer.tone(600, 150);
      Monitor.println("[EVENT] Recording forcibly stopped (switched to camera mode)");
    }

    if (!viewSwitchDebounced) {
      // Switched to Map mode: if a photo was taken, this confirms the photo!
      if (hasCapturedPhoto) {
        photoConfirmed = true;
        photoWaitingConfirmation = false;
        Monitor.println("[EVENT] Photo CONFIRMED via switch -> Map mode unlocked for audio!");
        buzzer.tone(1600, 80);
        delay(90);
        buzzer.tone(2000, 100);
      }
    } else {
      photoWaitingConfirmation = false;
    }

    if (currentUiState == UI_ACTIVE) {
      drawCurrentView();
    }
  }
  bool viewSwitchOn = viewSwitchDebounced;

  // External button D7 handling (active only in UI_ACTIVE state)
  bool extBtnPressed = (digitalRead(EXT_BUTTON_PIN) == LOW);
  if (extBtnPressed && !lastExtBtnState && currentUiState == UI_ACTIVE) {
    if (viewSwitchOn) {
      photoTriggerFlag = true;
      photoConfirmed = false;
      Monitor.println("[EVENT] Button D7 pressed -> taking photo");
    } else {
      if (!photoConfirmed) {
        recordingActive = false;
        Monitor.println("[WARN] Audio recording blocked: No photo taken yet!");
        buzzer.tone(350, 120);
        delay(80);
        buzzer.tone(250, 180);
        drawNoPhotoWarningOverlay();
      } else {
        recordingActive = !recordingActive;
        if (recordingActive) {
          buzzer.tone(1400, 90);
          Monitor.println("[EVENT] Button D7 pressed -> started recording question");
        } else {
          buzzer.tone(900, 90);
          Monitor.println("[EVENT] Button D7 pressed -> stopped recording question");
        }
      }
    }
  }
  lastExtBtnState = extBtnPressed;

  if (playShutterSoundFlag) {
    playShutterSoundFlag = false;
    buzzer.tone(2000, 100);
    drawPhotoConfirmationOverlay();
  }

  // Camera frame update rendering trigger
  if (newCameraFrameFlag) {
    newCameraFrameFlag = false;
    if (viewSwitchOn && currentUiState == UI_ACTIVE) {
      drawCameraFrame();
      if (photoWaitingConfirmation) {
        drawPhotoConfirmationOverlay();
      }
    }
  }

  // Modulino buttons handling for UI navigation and personality selection
  buttons.update();
  btnAHeld = (buttons.isPressed('A') == HIGH);
  btnBHeld = (buttons.isPressed('B') == HIGH);
  btnCHeld = (buttons.isPressed('C') == HIGH);

  bool btnAPressedEdge = btnAHeld && !btnAHeldPrev;
  bool btnBPressedEdge = btnBHeld && !btnBHeldPrev;
  bool btnCPressedEdge = btnCHeld && !btnCHeldPrev;
  btnAHeldPrev = btnAHeld;
  btnBHeldPrev = btnBHeld;
  btnCHeldPrev = btnCHeld;

  if (currentUiState == UI_BOOT_INTRO) {
    blinkIntroPrompt();
    if (btnAPressedEdge) {
      currentUiState = UI_OPTIONS;
      drawScreenOptions();
      buzzer.tone(1400, 50);
    }
  } else if (currentUiState == UI_OPTIONS) {
    if (btnAPressedEdge) {
      currentUiState = UI_TUTORIAL_1;
      drawScreenTutorial1();
      buzzer.tone(1500, 60);
    } else if (btnCPressedEdge) {
      currentUiState = UI_VOICE_SELECT;
      drawScreenPersonalitySelect();
      buzzer.tone(1500, 60);
    }
  } else if (currentUiState == UI_TUTORIAL_1) {
    if (btnAPressedEdge) {
      currentUiState = UI_TUTORIAL_2;
      drawScreenTutorial2();
      buzzer.tone(1500, 60);
    } else if (btnCPressedEdge) {
      currentUiState = UI_VOICE_SELECT;
      drawScreenPersonalitySelect();
      buzzer.tone(1500, 60);
    }
  } else if (currentUiState == UI_TUTORIAL_2) {
    if (btnAPressedEdge) {
      currentUiState = UI_TUTORIAL_3;
      drawScreenTutorial3();
      buzzer.tone(1500, 60);
    } else if (btnCPressedEdge) {
      currentUiState = UI_VOICE_SELECT;
      drawScreenPersonalitySelect();
      buzzer.tone(1500, 60);
    }
  } else if (currentUiState == UI_TUTORIAL_3) {
    if (btnAPressedEdge || btnCPressedEdge) {
      currentUiState = UI_VOICE_SELECT;
      drawScreenPersonalitySelect();
      buzzer.tone(1500, 60);
    }
  } else if (currentUiState == UI_VOICE_SELECT) {
    if (btnAPressedEdge || btnBPressedEdge || btnCPressedEdge) {
      personalityIndex = btnAPressedEdge ? 0 : (btnBPressedEdge ? 1 : 2);
      currentUiState = UI_ACTIVE;
      Monitor.print("[EVENT] Personality selected: index ");
      Monitor.println(personalityIndex);
      buzzer.tone(1800, 100);
      drawCurrentView();
    }
  } else if (currentUiState == UI_ACTIVE) {
    if (btnAPressedEdge || btnBPressedEdge || btnCPressedEdge) {
      personalityIndex = btnAPressedEdge ? 0 : (btnBPressedEdge ? 1 : 2);
      Monitor.print("[EVENT] Personality selected: index ");
      Monitor.println(personalityIndex);
      buzzer.tone(1800, 40);
    }
  }

  // Modulino LED status indicators
  if (currentUiState == UI_BOOT_INTRO || currentUiState == UI_OPTIONS) {
    buttons.setLeds(true, false, true);
  } else if (currentUiState == UI_TUTORIAL_1 || currentUiState == UI_TUTORIAL_2) {
    buttons.setLeds(true, false, true);
  } else if (currentUiState == UI_TUTORIAL_3) {
    buttons.setLeds(true, false, false);
  } else if (currentUiState == UI_VOICE_SELECT) {
    buttons.setLeds(true, true, true);
  } else if (currentUiState == UI_ACTIVE) {
    if (recordingActive) {
      bool blink = ((millis() / 300) % 2) == 0;
      buttons.setLeds(blink, blink, blink);
    } else {
      buttons.setLeds(personalityIndex == 0, personalityIndex == 1, personalityIndex == 2);
    }
  }

  // Filtered knob volume adjustment
  int16_t currentKnobPos = readKnobFiltered();
  if (!knobVolumeInit) {
    lastKnobPos = currentKnobPos;
    knobVolumeInit = true;
  } else {
    int16_t diff = currentKnobPos - lastKnobPos;
    if (diff != 0) {
      lastKnobPos = currentKnobPos;
      currentVolume += diff * 2;
      if (currentVolume < 0) currentVolume = 0;
      if (currentVolume > 100) currentVolume = 100;
      Monitor.print("[EVENT] Volume changed -> ");
      Monitor.print(currentVolume);
      Monitor.println("%");
    }
  }
}

