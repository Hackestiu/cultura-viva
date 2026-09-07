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
  UiOverlayType overlay = getCurrentOverlayType();
  if (overlay != UI_OVERLAY_NONE) {
    drawAssistantOverlay(overlay, 0, true);
  }
  if (volumeOverlayVisible) {
    drawVolumeBar(currentVolume);
  }
}

void drawAssistantOverlay(UiOverlayType type, uint8_t dotCount, bool fullRedraw) {
  if (type == UI_OVERLAY_NONE) return;

  static const char* const dotSuffixes[] = {
    "   ",
    ".  ",
    ".. ",
    "..."
  };
  const char* dots = dotSuffixes[dotCount % 4];

  uint16_t borderColor;
  const char* msg;
  uint8_t dotX;

  switch (type) {
    case UI_OVERLAY_RECORDING:
      borderColor = 0xF800; // Red border for recording
      msg = "Recording audio";
      dotX = 95;
      break;
    case UI_OVERLAY_SPEAKING:
      borderColor = 0x07E0; // Green border for speaking/answering
      msg = "Speaking answer";
      dotX = 95;
      break;
    case UI_OVERLAY_GENERATING:
    default:
      borderColor = 0xFFE0; // Yellow border for generating (STT/SLM/TTS synthesis)
      msg = "Generating answer";
      dotX = 107;
      break;
  }

  if (fullRedraw) {
    // High-contrast pill container in top-left corner
    tft.fillRoundRect(2, 2, 126, 13, 2, ST77XX_BLACK);
    tft.drawRoundRect(2, 2, 126, 13, 2, borderColor);

    // Static message text
    tft.setTextColor(0xFFFF, 0x0000); // White text on black
    tft.setTextSize(1);
    tft.setCursor(5, 5);
    tft.print(msg);
  }

  // Only the animated dots update
  tft.setTextColor(0xFFFF, 0x0000);
  tft.setTextSize(1);
  tft.setCursor(dotX, 5);
  tft.print(dots);
}

void drawGeneratingAnswerOverlay(uint8_t dotCount, bool fullRedraw) {
  drawAssistantOverlay(UI_OVERLAY_GENERATING, dotCount, fullRedraw);
}

void drawVolumeBar(int16_t volume) {
  if (volume < 0) volume = 0;
  if (volume > 100) volume = 100;

  // Very discreet vertical volume bar capsule on the far right edge
  const int16_t trackX = 154;
  const int16_t trackY = 20;
  const int16_t trackW = 5;
  const int16_t trackH = 88;
  const int16_t innerX = 155;
  const int16_t innerY = 22;
  const int16_t innerW = 3;
  const int16_t innerH = 84;

  // Draw pill track capsule
  tft.fillRoundRect(trackX, trackY, trackW, trackH, 2, 0x2104); // Dark gray track
  tft.drawRoundRect(trackX, trackY, trackW, trackH, 2, 0x52AA); // Subtle border

  // Calculate fill height from bottom upwards
  int16_t fillH = (int16_t)(((int32_t)volume * innerH) / 100);
  if (fillH > innerH) fillH = innerH;
  if (fillH < 0) fillH = 0;

  int16_t emptyH = innerH - fillH;

  // Unfilled top portion
  if (emptyH > 0) {
    tft.fillRect(innerX, innerY, innerW, emptyH, 0x2104);
  }
  // Filled bottom portion (white)
  if (fillH > 0) {
    tft.fillRect(innerX, innerY + emptyH, innerW, fillH, 0xFFFF);
  }
}
