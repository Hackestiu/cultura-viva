#include "ui_manager.h"
#include "../core/config.h"
#include "../core/app_state.h"
#include "minimap.h"
#include "camera_view.h"

Adafruit_ST7735 tft = Adafruit_ST7735(TFT_CS, TFT_DC, TFT_RST);

bool introPromptVisible = true;
unsigned long lastIntroBlinkMillis = 0;

void initDisplay() {
  pinMode(TFT_BL, OUTPUT);
  digitalWrite(TFT_BL, HIGH);
  tft.initR(INITR_GREENTAB);
  tft.setRotation(1);
  tft.fillScreen(ST77XX_BLACK);
  tft.setTextColor(ST77XX_WHITE);
  tft.setTextSize(1);
  tft.setCursor(0, 0);
  tft.println("Cultura Viva");
  tft.println("UNO Q");
}

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

void drawCurrentView() {
  if (viewSwitchDebounced) {
    drawCameraViewPlaceholder();
  } else {
    drawParkMap();
  }
}
