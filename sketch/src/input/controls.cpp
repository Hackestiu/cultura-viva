#include <Arduino.h>
#include <Wire.h>
#include <Arduino_RouterBridge.h>
#include "controls.h"
#include "../core/config.h"
#include "../core/app_state.h"
#include "../display/ui_manager.h"
#include "../display/camera_view.h"
#include "../display/minimap.h"

ModulinoKnob    knob;
ModulinoButtons buttons;
ModulinoBuzzer  buzzer;

static bool lastExtBtnState = false;

static int16_t knobFiltered = 0;
static bool knobFilteredInit = false;
static uint8_t knobOutlierCount = 0;

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
  Wire1.setWireTimeout(25000, true);
#endif
  Modulino.begin(Wire1);

  knob.begin();
  buttons.begin();
  buzzer.begin();

  buzzer.tone(1000, 150);
  delay(200);
}

// Reads raw knob position directly via I2C.
// Unlike knob.get() which returns 0 on communication failure (creating false jumps),
// readKnobRaw() returns false if the I2C read fails or times out,
// preventing spurious readings from corrupting the encoder state.
static bool readKnobRaw(int16_t &outPos) {
  if (!knob) {
    static unsigned long lastBeginAttempt = 0;
    if (millis() - lastBeginAttempt > 1000) {
      lastBeginAttempt = millis();
      knob.begin();
    }
    return false;
  }
  uint8_t buf[3];
  if (!knob.read(buf, 3)) {
    return false;
  }
  outPos = (int16_t)((uint16_t)buf[0] | ((uint16_t)buf[1] << 8));
  return true;
}

int16_t readKnobFiltered() {
  int16_t raw = 0;
  if (!readKnobRaw(raw)) {
    return knobFiltered;
  }

  if (!knobFilteredInit) {
    knobFiltered = raw;
    knobFilteredInit = true;
    knobOutlierCount = 0;
    return knobFiltered;
  }

  // Use a wider type for the delta: raw and knobFiltered are int16_t,
  // and on a fast spin their true difference can exceed the int16_t range.
  // Computing/storing the diff as int16_t would silently overflow/wrap,
  // flipping its sign and corrupting the outlier check below.
  int32_t diff = (int32_t)raw - (int32_t)knobFiltered;

  // Protect against extreme single-cycle electrical noise spikes,
  // but if the new value persists for 2 consecutive cycles, accept it
  // so the encoder never becomes permanently locked or frozen.
  if (diff > KNOB_MAX_JUMP || diff < -KNOB_MAX_JUMP) {
    knobOutlierCount++;
    if (knobOutlierCount < 2) {
      return knobFiltered;
    }
  }

  knobOutlierCount = 0;
  knobFiltered = raw;
  return knobFiltered;
}

void updateControls() {
  // Mode switch D6 handling with debouncing
  bool viewSwitchRaw = (digitalRead(VIEW_SWITCH_PIN) == HIGH);
  if (!processingActive && photoValidationState == -1) {
    if (viewSwitchRaw != viewSwitchRawLast) {
      viewSwitchLastChangeTime = millis();
      viewSwitchRawLast = viewSwitchRaw;
    }
    if ((millis() - viewSwitchLastChangeTime) > VIEW_SWITCH_DEBOUNCE_MS
        && viewSwitchRaw != viewSwitchDebounced) {
      viewSwitchDebounced = viewSwitchRaw;
      Monitor.print("[EVENT] Switch D6 changed -> ");
      Monitor.println(viewSwitchDebounced ? "ON (camera mode)" : "OFF (map mode)");

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
  }
  bool viewSwitchOn = viewSwitchDebounced;

  // External button D7 handling
  bool extBtnPressed = (digitalRead(EXT_BUTTON_PIN) == LOW);
  if (processingActive && extBtnPressed && !lastExtBtnState && currentUiState == UI_ACTIVE) {
    // Cancel answer generation on button press
    processingActive = false;
    buzzer.tone(700, 120);
    Monitor.println("[EVENT] Button D7 pressed -> CANCELLED answer generation!");
    drawCurrentView();
  } else if (!processingActive && !playbackActive && photoValidationState == -1 && extBtnPressed && !lastExtBtnState && currentUiState == UI_ACTIVE) {
    if (recordingActive) {
      recordingActive = false;
      buzzer.tone(900, 90);
      Monitor.println("[EVENT] Button D7 pressed -> stopped recording question");
    } else if (viewSwitchOn) {
      if (photoWaitingConfirmation) {
        hasCapturedPhoto = false;
        photoConfirmed = false;
        photoWaitingConfirmation = false;
        Monitor.println("[EVENT] Button D7 pressed -> photo rejected, returning to live camera");
        buzzer.tone(700, 100);
        drawCameraViewPlaceholder();
      } else {
        photoTriggerFlag = true;
        photoConfirmed = false;
        Monitor.println("[EVENT] Button D7 pressed -> taking photo");
      }
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
      UiOverlayType overlay = getCurrentOverlayType();
      if (overlay != UI_OVERLAY_NONE) {
        drawAssistantOverlay(overlay, 0, true);
      }
      if (volumeOverlayVisible) {
        drawVolumeBar(currentVolume);
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

  // Make all buttons unavailable when generating an answer, speaking, or validating photo
  if (processingActive || playbackActive || photoValidationState != -1) {
    btnAPressedEdge = false;
    btnBPressedEdge = false;
    btnCPressedEdge = false;
  }

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
      currentUiState = UI_OPTIONS;
      drawScreenOptions();
      buzzer.tone(1500, 60);
    } else if (btnBPressedEdge) {
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
      currentUiState = UI_TUTORIAL_1;
      drawScreenTutorial1();
      buzzer.tone(1500, 60);
    } else if (btnBPressedEdge) {
      currentUiState = UI_TUTORIAL_3;
      drawScreenTutorial3();
      buzzer.tone(1500, 60);
    } else if (btnCPressedEdge) {
      currentUiState = UI_VOICE_SELECT;
      drawScreenPersonalitySelect();
      buzzer.tone(1500, 60);
    }
  } else if (currentUiState == UI_TUTORIAL_3) {
    if (btnAPressedEdge) {
      currentUiState = UI_TUTORIAL_2;
      drawScreenTutorial2();
      buzzer.tone(1500, 60);
    } else if (btnBPressedEdge) {
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
    if (!recordingActive && !processingActive && !playbackActive
        && (btnAPressedEdge || btnBPressedEdge || btnCPressedEdge)) {
      personalityIndex = btnAPressedEdge ? 0 : (btnBPressedEdge ? 1 : 2);
      Monitor.print("[EVENT] Personality selected: index ");
      Monitor.println(personalityIndex);
      buzzer.tone(1800, 40);
    }
  }

  // Modulino LED status indicators (only write I2C if state changed to prevent bus saturation)
  bool ledA = false, ledB = false, ledC = false;
  if (currentUiState == UI_BOOT_INTRO || currentUiState == UI_OPTIONS) {
    buttons.setLeds(true, false, currentUiState == UI_OPTIONS);
  } else if (currentUiState == UI_TUTORIAL_1 || currentUiState == UI_TUTORIAL_2 || currentUiState == UI_TUTORIAL_3) {
    ledA = true; ledB = true; ledC = currentUiState != UI_TUTORIAL_3;
  } else if (currentUiState == UI_VOICE_SELECT) {
    ledA = true; ledB = true; ledC = true;
  } else if (currentUiState == UI_ACTIVE) {
    if (recordingActive || processingActive || playbackActive) {
      bool blink = ((millis() / 300) % 2) == 0;
      ledA = blink; ledB = blink; ledC = blink;
    } else {
      ledA = (personalityIndex == 0);
      ledB = (personalityIndex == 1);
      ledC = (personalityIndex == 2);
    }
  }

  static bool lastLedA = false, lastLedB = false, lastLedC = false;
  static bool ledsInit = false;
  if (!ledsInit || ledA != lastLedA || ledB != lastLedB || ledC != lastLedC) {
    buttons.setLeds(ledA, ledB, ledC);
    lastLedA = ledA;
    lastLedB = ledB;
    lastLedC = ledC;
    ledsInit = true;
  }

  // Filtered knob volume adjustment
  int16_t currentKnobPos = readKnobFiltered();
  if (!knobVolumeInit) {
    if (knobFilteredInit) {
      lastKnobPos = currentKnobPos;
      knobVolumeInit = true;
    }
  } else {
    // Same overflow hazard as in readKnobFiltered(): on a fast/abrupt spin
    // the per-cycle delta between two int16_t positions can exceed the
    // int16_t range. Compute it in int32_t so it can never wrap sign,
    // which previously caused the volume to be driven far below 0 (and
    // therefore clamped to 0) regardless of turn direction.
    int32_t diff = (int32_t)currentKnobPos - (int32_t)lastKnobPos;
    if (diff != 0) {
      lastKnobPos = currentKnobPos;
      currentVolume += (int)(diff * 2);
      if (currentVolume < 0) currentVolume = 0;
      if (currentVolume > 100) currentVolume = 100;
      Monitor.print("[EVENT] Volume changed -> ");
      Monitor.print(currentVolume);
      Monitor.println("%");

      // Show volume overlay during active use or tutorial walkthrough
      if (currentUiState == UI_ACTIVE ||
          currentUiState == UI_TUTORIAL_1 ||
          currentUiState == UI_TUTORIAL_2 ||
          currentUiState == UI_TUTORIAL_3 ||
          currentUiState == UI_OPTIONS ||
          currentUiState == UI_VOICE_SELECT) {
        lastVolumeChangeMillis = millis();
        volumeOverlayVisible = true;
        drawVolumeBar(currentVolume);
      }
    }
  }

  // Auto-hide volume bar after timeout and restore screen
  if (volumeOverlayVisible) {
    if (millis() - lastVolumeChangeMillis >= VOLUME_OVERLAY_TIMEOUT_MS) {
      volumeOverlayVisible = false;
      drawCurrentUiStateScreen();
    }
  }

  // Assistant overlay handling (Recording / Generating / Speaking with animated dots)
  static UiOverlayType lastOverlayType = UI_OVERLAY_NONE;
  static unsigned long lastOverlayAnimMillis = 0;
  static uint8_t overlayDotCount = 0;

  UiOverlayType currentOverlay = getCurrentOverlayType();

  if (currentOverlay != lastOverlayType) {
    if (lastOverlayType != UI_OVERLAY_NONE && currentOverlay == UI_OVERLAY_NONE) {
      // Completed all assistant phases -> restore current view to clear the overlay
      drawCurrentView();
    }
    lastOverlayType = currentOverlay;
    if (currentOverlay != UI_OVERLAY_NONE) {
      drawAssistantOverlay(currentOverlay, 0, true);
      lastOverlayAnimMillis = millis();
      overlayDotCount = 0;
    }
  } else if (currentOverlay != UI_OVERLAY_NONE) {
    if (millis() - lastOverlayAnimMillis >= 400) {
      lastOverlayAnimMillis = millis();
      overlayDotCount = (overlayDotCount + 1) % 4;
      drawAssistantOverlay(currentOverlay, overlayDotCount, false);
    }
  }

  // Vision validation state machine — non-blocking, millis()-based
  // State: -1=idle, 0=checking (animated dots), 1=valid (hold ~1.8s), 2=invalid (hold ~2.0s)
  static int8_t lastPhotoValidationState = -1;
  static unsigned long validationHoldStart = 0;
  static uint8_t visionDotCount = 0;
  static unsigned long lastVisionDotMillis = 0;

  if (photoValidationState != lastPhotoValidationState) {
    lastPhotoValidationState = photoValidationState;

    if (photoValidationState == 0) {
      // Entered checking state: draw full scanning screen
      drawVisionCheckingScreen(0, true);
      visionDotCount = 0;
      lastVisionDotMillis = millis();
      Monitor.println("[EVENT] Vision: Scanning photo...");

    } else if (photoValidationState == 1) {
      // Valid monument: draw success screen and start hold timer
      drawVisionValidScreen();
      buzzer.tone(1800, 80);
      delay(90);
      buzzer.tone(2200, 120);
      validationHoldStart = millis();
      Monitor.println("[EVENT] Vision: Photo validated!");

    } else if (photoValidationState == 2) {
      // Invalid: draw retake screen and start hold timer
      drawVisionInvalidScreen(retakeLocationLabel);
      buzzer.tone(350, 120);
      delay(80);
      buzzer.tone(250, 200);
      validationHoldStart = millis();
      Monitor.print("[EVENT] Vision: Not a monument in ");
      Monitor.println(retakeLocationLabel);

    } else if (photoValidationState == -1 && lastPhotoValidationState != -1) {
      // Returning to idle
    }
  }

  // Animate dots while checking (state 0)
  if (photoValidationState == 0) {
    if (millis() - lastVisionDotMillis >= 400) {
      lastVisionDotMillis = millis();
      visionDotCount = (visionDotCount + 1) % 4;
      drawVisionCheckingScreen(visionDotCount, false);
    }
  }

  // Auto-advance from state 1 (valid) after ~1800ms -> show photo confirmation
  if (photoValidationState == 1 && (millis() - validationHoldStart >= 5000)) {
    photoValidationState = -1;
    lastPhotoValidationState = -1;
    hasCapturedPhoto = true;
    photoWaitingConfirmation = true;
    if (viewSwitchOn && currentUiState == UI_ACTIVE) {
      drawCameraFrame();
      drawPhotoConfirmationOverlay();
    }
    buzzer.tone(2000, 100);
    Monitor.println("[EVENT] Vision: transitioning to photo confirmation.");
  }

  // Auto-advance from state 2 (invalid) after ~2000ms -> back to camera live view
  if (photoValidationState == 2 && (millis() - validationHoldStart >= 6000)) {
    photoValidationState = -1;
    lastPhotoValidationState = -1;
    hasCapturedPhoto = false;
    photoConfirmed = false;
    photoWaitingConfirmation = false;
    if (viewSwitchOn && currentUiState == UI_ACTIVE) {
      drawCameraViewPlaceholder();
    } else if (!viewSwitchOn && currentUiState == UI_ACTIVE) {
      drawParkMap();
    }
    Monitor.println("[EVENT] Vision: returning to camera after invalid photo.");
  }
}

