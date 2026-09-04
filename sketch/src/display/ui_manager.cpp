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
  tft.drawRGBBitmap(0, 0, UI_START_BITMAP, UI_BITMAP_W, UI_BITMAP_H);
}

void blinkIntroPrompt() {
}

void drawScreenOptions() {
  tft.drawRGBBitmap(0, 0, UI_OPTIONS_BITMAP, UI_BITMAP_W, UI_BITMAP_H);
}

void drawScreenTutorial1() {
  tft.drawRGBBitmap(0, 0, UI_TUTORIAL1_BITMAP, UI_BITMAP_W, UI_BITMAP_H);
}

void drawScreenTutorial2() {
  tft.drawRGBBitmap(0, 0, UI_TUTORIAL2_BITMAP, UI_BITMAP_W, UI_BITMAP_H);
}

void drawScreenTutorial3() {
  tft.drawRGBBitmap(0, 0, UI_TUTORIAL3_BITMAP, UI_BITMAP_W, UI_BITMAP_H);
}

void drawScreenPersonalitySelect() {
  tft.drawRGBBitmap(0, 0, UI_PERSONALITY_BITMAP, UI_BITMAP_W, UI_BITMAP_H);
}

void drawCurrentView() {
  if (viewSwitchDebounced) {
    drawCameraViewPlaceholder();
  } else {
    drawParkMap();
  }
}

void drawGeneratingAnswerOverlay(uint8_t dotCount, bool fullRedraw) {
  static const char* const dotSuffixes[] = {
    "   ",
    ".  ",
    ".. ",
    "..."
  };
  const char* dots = dotSuffixes[dotCount % 4];

  if (fullRedraw) {
    // High-contrast pill container in top-left corner
    tft.fillRoundRect(2, 2, 126, 13, 2, ST77XX_BLACK);
    tft.drawRoundRect(2, 2, 126, 13, 2, 0xFFE0); // Yellow border

    // Static message text
    tft.setTextColor(0xFFFF, 0x0000); // White text on black
    tft.setTextSize(1);
    tft.setCursor(5, 5);
    tft.print(F("Generating answer"));
  }

  // Only the animated dots update
  tft.setTextColor(0xFFFF, 0x0000);
  tft.setTextSize(1);
  tft.setCursor(107, 5);
  tft.print(dots);
}
