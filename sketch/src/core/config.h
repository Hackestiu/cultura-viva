#pragma once

#include <stdint.h>

/**
 * Centralized hardware configuration and constant definitions for Arduino UNO Q.
 */

// Display SPI hardware pins
#define TFT_CS   10
#define TFT_DC    8
#define TFT_RST   9
#define TFT_BL    5   // Display backlight PWM/digital control pin

// Input peripheral pins
#define EXT_BUTTON_PIN 7   // External button (photo trigger / audio recording toggle)
#define VIEW_SWITCH_PIN 6  // Mode switch (LOW = map mode, HIGH = camera live view mode)

// Hardware Serial baud rate for NEO-6M GPS module
#define GPS_BAUD 9600

// Camera live view thumbnail parameters
#define CAM_THUMB_W 48
#define CAM_THUMB_H 36
#define CAM_CHUNK_PIXELS 72
#define CAM_TOTAL_PIXELS (CAM_THUMB_W * CAM_THUMB_H)
#define CAM_TOTAL_CHUNKS ((CAM_TOTAL_PIXELS + CAM_CHUNK_PIXELS - 1) / CAM_CHUNK_PIXELS)
#define CAM_CHUNK_TIMEOUT_MS 3000
#define CAM_SCALE 4

// Input filtering and debouncing thresholds
const int16_t KNOB_MAX_JUMP = 150;
const unsigned long VIEW_SWITCH_DEBOUNCE_MS = 50;

