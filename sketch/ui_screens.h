#pragma once

#include <stdint.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include "logo_bitmap.h"

// Forward declaration of global tft defined in sketch.ino
extern Adafruit_ST7735 tft;

// ---------- "Cultura Viva" colour palette ----------
struct UiRGB { uint8_t r, g, b; };

const UiRGB UI_CREAM   = { 245, 243, 239 };  // #F5F3EF -- general background
const UiRGB UI_DARK    = { 38,  38,  38  };  // #262626 -- primary text
const UiRGB UI_SLATE   = { 73,  119, 141 };  // #49778D -- secondary text
const UiRGB UI_MEDGREY = { 102, 102, 102 };  // #666666 -- tertiary text
const UiRGB UI_TEAL    = { 63,  129, 121 };  // #3F8179 -- accent (button A)
const UiRGB UI_PEACH   = { 222, 156, 105 };  // #DE9C69 -- accent (button B)
const UiRGB UI_NAVY    = { 31,  64,  86  };  // #1F4056 -- accent (titles)
const UiRGB UI_MUSTARD = { 227, 181, 82  };  // #E3B552 -- accent (button C)

inline uint16_t uiColor(const UiRGB& c) {
  return tft.color565(c.r, c.g, c.b);
}

// ---------- Small icons (~20x14 px) ----------
void drawSwitchIcon(int16_t x, int16_t y) {
  tft.drawRoundRect(x, y, 20, 14, 6, uiColor(UI_NAVY));
  tft.fillCircle(x + 14, y + 7, 5, uiColor(UI_TEAL));  // "ON" position (right)
}

void drawButtonIcon(int16_t x, int16_t y) {
  tft.fillCircle(x + 7, y + 7, 7, uiColor(UI_PEACH));
  tft.drawCircle(x + 7, y + 7, 7, uiColor(UI_NAVY));
}

void drawKnobIcon(int16_t x, int16_t y) {
  tft.drawCircle(x + 7, y + 7, 7, uiColor(UI_NAVY));
  tft.drawLine(x + 7, y + 7, x + 7, y + 1, uiColor(UI_MUSTARD));
  tft.fillCircle(x + 7, y + 7, 2, uiColor(UI_MUSTARD));
}

// ---------- Text/layout helpers ----------
void uiHeader(const char* title) {
  tft.setTextSize(1);
  tft.setTextColor(uiColor(UI_NAVY));
  tft.setCursor(4, 3);
  tft.print(title);
  tft.setCursor(5, 3);  // second pass 1px offset -> "semi-bold" effect
  tft.print(title);
  tft.drawFastHLine(4, 13, 152, uiColor(UI_TEAL));
}

void uiFooterNav(const char* left, const char* right) {
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

void uiCard(int16_t x, int16_t y, int16_t w, int16_t h, const char* label, uint16_t accent) {
  tft.drawRoundRect(x, y, w, h, 5, accent);
  tft.setTextColor(accent);
  tft.setCursor(x + 8, y + (h - 8) / 2);
  tft.print(label);
}

// ============================================================
// SCREEN 1: Intro / Welcome
// ============================================================
bool introPromptVisible = true;
unsigned long lastIntroBlinkMillis = 0;
const unsigned long INTRO_BLINK_MS = 600;

void drawScreenIntro() {
  tft.fillScreen(uiColor(UI_CREAM));
  tft.drawRGBBitmap(0, 0, LOGO_BITMAP, LOGO_W, LOGO_H);
  introPromptVisible = true;
  lastIntroBlinkMillis = millis();
  const char* msg = "PRESS ANY BUTTON";
  int16_t textW = (int16_t)strlen(msg) * 6;
  tft.setTextSize(1);
  tft.setTextColor(uiColor(UI_NAVY));
  tft.setCursor((160 - textW) / 2, LOGO_H + 10);
  tft.print(msg);
}

// Blinks "press button" message -- call every loop() iteration while in UI_BOOT_INTRO.
void blinkIntroPrompt() {
  unsigned long now = millis();
  if (now - lastIntroBlinkMillis < INTRO_BLINK_MS) return;
  lastIntroBlinkMillis = now;
  introPromptVisible = !introPromptVisible;

  tft.fillRect(0, LOGO_H, 160, 128 - LOGO_H, uiColor(UI_CREAM));
  if (introPromptVisible) {
    const char* msg = "PRESS ANY BUTTON";
    int16_t textW = (int16_t)strlen(msg) * 6;
    tft.setTextSize(1);
    tft.setTextColor(uiColor(UI_NAVY));
    tft.setCursor((160 - textW) / 2, LOGO_H + 10);
    tft.print(msg);
  }
}

// ============================================================
// SCREEN 2: Options (Tutorial / Skip to Personality)
// ============================================================
void drawScreenOptions() {
  tft.fillScreen(uiColor(UI_CREAM));
  uiHeader("GET STARTED");

  tft.setTextSize(1);
  tft.setTextColor(uiColor(UI_MEDGREY));
  tft.setCursor(8, 26);
  tft.print("How do you want to");
  tft.setCursor(8, 35);
  tft.print("begin?");

  uiCard(8, 70, 68, 40, "", uiColor(UI_TEAL));
  tft.setTextColor(uiColor(UI_TEAL));
  tft.setCursor(16, 82);
  tft.print("[A]");
  tft.setTextColor(uiColor(UI_DARK));
  tft.setCursor(16, 94);
  tft.print("Tutorial");

  uiCard(84, 70, 68, 40, "", uiColor(UI_MUSTARD));
  tft.setTextColor(uiColor(UI_MUSTARD));
  tft.setCursor(92, 78);
  tft.print("[C]");
  tft.setTextColor(uiColor(UI_DARK));
  tft.setCursor(92, 90);
  tft.print("Skip to");
  tft.setCursor(92, 99);
  tft.print("Personality");
}

// ============================================================
// SCREEN 3: Tutorial (1/3) - Controls
// ============================================================
void drawScreenTutorial1() {
  tft.fillScreen(uiColor(UI_CREAM));
  uiHeader("TUTORIAL 1/3: CONTROLS");

  tft.setTextSize(1);
  tft.setTextColor(uiColor(UI_DARK));

  drawSwitchIcon(6, 20);
  tft.setCursor(32, 20);
  tft.print("Switch ON =");
  tft.setCursor(32, 29);
  tft.print("Camera Mode");
  tft.setCursor(32, 38);
  tft.print("OFF = Map Mode");

  drawButtonIcon(6, 52);
  tft.setCursor(32, 52);
  tft.print("Button: Photo");
  tft.setCursor(32, 61);
  tft.print("(Camera) / Record");
  tft.setCursor(32, 70);
  tft.print("question (Map)");

  drawKnobIcon(6, 86);
  tft.setCursor(32, 88);
  tft.print("Knob: Volume");
  tft.setCursor(32, 97);
  tft.print("(0-100%)");

  uiFooterNav("[A] Next", "[C] Skip");
}

// ============================================================
// SCREEN 4: Tutorial (2/3) - How it works
// ============================================================
void drawScreenTutorial2() {
  tft.fillScreen(uiColor(UI_CREAM));
  uiHeader("TUTORIAL 2/3: HOW IT WORKS");

  tft.setTextSize(1);
  tft.setTextColor(uiColor(UI_DARK));

  tft.setCursor(6, 20);
  tft.print("1. Set Switch to");
  tft.setCursor(6, 29);
  tft.print("   Camera & frame");
  tft.setCursor(6, 38);
  tft.print("   the monument.");

  tft.setCursor(6, 52);
  tft.print("2. Press button to");
  tft.setCursor(6, 61);
  tft.print("   take a photo.");

  tft.setCursor(6, 75);
  tft.print("3. Set Switch to Map,");
  tft.setCursor(6, 84);
  tft.print("   press button & ask");
  tft.setCursor(6, 93);
  tft.print("   your question!");

  uiFooterNav("[A] Next", "[C] Skip");
}

// ============================================================
// SCREEN 5: Tutorial (3/3) - AI Personality
// ============================================================
void drawScreenTutorial3() {
  tft.fillScreen(uiColor(UI_CREAM));
  uiHeader("TUTORIAL 3/3: PERSONALITY");

  tft.setTextSize(1);
  tft.setTextColor(uiColor(UI_DARK));
  tft.setCursor(6, 20);
  tft.print("The AI guide answers");
  tft.setCursor(6, 29);
  tft.print("adapting to your");
  tft.setCursor(6, 38);
  tft.print("chosen personality:");

  tft.setTextColor(uiColor(UI_TEAL));
  tft.setCursor(20, 54);
  tft.print("[A] ARTISTIC");
  tft.setTextColor(uiColor(UI_PEACH));
  tft.setCursor(20, 66);
  tft.print("[B] TECHNICAL");
  tft.setTextColor(uiColor(UI_MUSTARD));
  tft.setCursor(20, 78);
  tft.print("[C] KIDS");

  tft.setTextColor(uiColor(UI_MEDGREY));
  tft.setCursor(6, 96);
  tft.print("Change personality");
  tft.setCursor(6, 105);
  tft.print("anytime you like.");

  uiFooterNav("[A] Choose Personality", "");
}

// ============================================================
// SCREEN 6: Personality selection
// ============================================================
void drawScreenPersonalitySelect() {
  tft.fillScreen(uiColor(UI_CREAM));
  uiHeader("CHOOSE YOUR PERSONALITY");

  tft.setTextSize(1);
  tft.setTextColor(uiColor(UI_MEDGREY));
  tft.setCursor(6, 18);
  tft.print("Which fits you best?");

  uiCard(8, 30, 144, 22, "[A] ARTISTIC",   uiColor(UI_TEAL));
  uiCard(8, 58, 144, 22, "[B] TECHNICAL",  uiColor(UI_PEACH));
  uiCard(8, 86, 144, 22, "[C] KIDS / FUN", uiColor(UI_MUSTARD));

  tft.setTextColor(uiColor(UI_DARK));
  tft.setCursor(6, 118);
  tft.print("Press A, B or C to start");
}
