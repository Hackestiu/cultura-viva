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

// High-resolution captured photo preview parameters (fits above 42px confirmation overlay)
#define PHOTO_PREVIEW_W 160
#define PHOTO_PREVIEW_H 86
#define PHOTO_CHUNK_PIXELS 80
#define PHOTO_TOTAL_PIXELS (PHOTO_PREVIEW_W * PHOTO_PREVIEW_H)
#define PHOTO_TOTAL_CHUNKS ((PHOTO_TOTAL_PIXELS + PHOTO_CHUNK_PIXELS - 1) / PHOTO_CHUNK_PIXELS)


// Input filtering and debouncing thresholds
const int16_t KNOB_MAX_JUMP = 150;
const unsigned long VIEW_SWITCH_DEBOUNCE_MS = 50;

