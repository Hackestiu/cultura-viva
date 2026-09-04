#pragma once

#include <Adafruit_ST7735.h>
#include "ui_screens.h"

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
 * Renders a generating answer status overlay at top-left corner with animated dots.
 */
void drawGeneratingAnswerOverlay(uint8_t dotCount = 0, bool fullRedraw = true);

