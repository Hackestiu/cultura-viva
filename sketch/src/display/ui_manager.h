#pragma once

#include <Adafruit_ST7735.h>
#include "ui_screens.h"
#include "../core/app_state.h"

extern Adafruit_ST7735 tft;

/**
 * Initializes ST7735S display hardware, pin modes, and backlight.
 */
void initDisplay();

/**
 * Renders either the camera view placeholder or the minimap depending on switch state.
 */
void drawCurrentView();

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


