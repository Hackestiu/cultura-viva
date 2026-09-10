#pragma once

#include <Adafruit_ST7735.h>
#include "ui_screens.h"
#include "../core/app_state.h"

/**
 * Subclass of Adafruit_ST7735 exposing setColRowStart() as a public method.
 * Required to correct the hardware pixel offset (colstart/rowstart) for
 * generic ST7735S displays that differ from the INITR_GREENTAB default offsets.
 */
class DisplayST7735 : public Adafruit_ST7735 {
public:
  using Adafruit_ST7735::Adafruit_ST7735;
  void setOffsets(int8_t col, int8_t row) {
    setColRowStart(col, row);
  }
};

extern DisplayST7735 tft;

/**
 * Initializes ST7735S display hardware, pin modes, and backlight.
 */
void initDisplay();

/**
 * Renders either the camera view placeholder or the minimap depending on switch state.
 */
void drawCurrentView();

/**
 * Redraws the current screen based on currentUiState (used to restore screen after volume bar overlay in tutorial/options/active).
 */
void drawCurrentUiStateScreen();

/**
 * Renders an assistant status overlay pill at the top-left corner with animated dots:
 *  - UI_OVERLAY_RECORDING:  Red border, "Recording audio"
 *  - UI_OVERLAY_GENERATING: Yellow border, "Generating answer"
 *  - UI_OVERLAY_SPEAKING:   Green border, "Speaking answer"
 */
void drawAssistantOverlay(UiOverlayType type, uint8_t dotCount = 0, bool fullRedraw = true);

/**
 * Backward-compatible helper for the generating answer status overlay.
 */
void drawGeneratingAnswerOverlay(uint8_t dotCount = 0, bool fullRedraw = true);

/**
 * Renders a discreet vertical volume bar on the right edge of the screen (0-100%).
 */
void drawVolumeBar(int16_t volume);


