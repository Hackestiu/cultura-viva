#pragma once

#include <stdint.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include "ui_assets.h"

// Single global declaration of the display instance.
// Defined once in a .cpp file (e.g. ui_manager.cpp) as:
//   Adafruit_ST7735 tft(TFT_CS, TFT_DC, TFT_RST);
extern Adafruit_ST7735 tft;

// Color palette structure for UI rendering
struct UiRGB { uint8_t r, g, b; };

const UiRGB UI_CREAM   = { 245, 243, 239 };  // Background cream
const UiRGB UI_DARK    = { 38,  38,  38  };  // Primary dark text
const UiRGB UI_SLATE   = { 73,  119, 141 };  // Secondary text
const UiRGB UI_MEDGREY = { 102, 102, 102 };  // Tertiary grey text
const UiRGB UI_TEAL    = { 63,  129, 121 };  // Button A accent
const UiRGB UI_PEACH   = { 222, 156, 105 };  // Button B accent
const UiRGB UI_NAVY    = { 31,  64,  86  };  // Title navy accent
const UiRGB UI_MUSTARD = { 227, 181, 82  };  // Button C accent

inline uint16_t uiColor(const UiRGB& c) {
  return tft.color565(c.r, c.g, c.b);
}

// Icon rendering helpers
inline void drawSwitchIcon(int16_t x, int16_t y) {
  tft.drawRoundRect(x, y, 20, 14, 6, uiColor(UI_NAVY));
  tft.fillCircle(x + 14, y + 7, 5, uiColor(UI_TEAL));
}

inline void drawButtonIcon(int16_t x, int16_t y) {
  tft.fillCircle(x + 7, y + 7, 7, uiColor(UI_PEACH));
  tft.drawCircle(x + 7, y + 7, 7, uiColor(UI_NAVY));
}

inline void drawKnobIcon(int16_t x, int16_t y) {
  tft.drawCircle(x + 7, y + 7, 7, uiColor(UI_NAVY));
  tft.drawLine(x + 7, y + 7, x + 7, y + 1, uiColor(UI_MUSTARD));
  tft.fillCircle(x + 7, y + 7, 2, uiColor(UI_MUSTARD));
}

// Text and card layout helpers
inline void uiHeader(const char* title) {
  tft.setTextSize(1);
  tft.setTextColor(uiColor(UI_NAVY));
  tft.setCursor(4, 3);
  tft.print(title);
  tft.setCursor(5, 3);  // 1px offset pass for bold effect
  tft.print(title);
  tft.drawFastHLine(4, 13, 152, uiColor(UI_TEAL));
}

inline void uiFooterNav(const char* left, const char* right) {
  tft.setTextSize(1);
  if (left != nullptr && left[0] != '\0') {
    tft.setTextColor(uiColor(UI_TEAL));
    tft.setCursor(4, 119);
    tft.print(left);
  }
  if (right != nullptr && right[0] != '\0') {
    int16_t rw = (int16_t)strlen(right) * 6;
    tft.setTextColor(uiColor(UI_MUSTARD));
    tft.setCursor(160 - 4 - rw, 119);
    tft.print(right);
  }
}

inline void uiCard(int16_t x, int16_t y, int16_t w, int16_t h, const char* label, uint16_t accent) {
  tft.drawRoundRect(x, y, w, h, 5, accent);
  tft.setTextColor(accent);
  tft.setCursor(x + 8, y + (h - 8) / 2);
  tft.print(label);
}

// Intro screen state
extern bool introPromptVisible;
extern unsigned long lastIntroBlinkMillis;
const unsigned long INTRO_BLINK_MS = 600;

void drawScreenIntro();
void blinkIntroPrompt();
void drawScreenOptions();
void drawScreenTutorial1();
void drawScreenTutorial2();
void drawScreenTutorial3();
void drawScreenPersonalitySelect();