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

void drawCurrentUiStateScreen() {
  switch (currentUiState) {
    case UI_BOOT_INTRO:
      drawScreenIntro();
      break;
    case UI_OPTIONS:
      drawScreenOptions();
      break;
    case UI_TUTORIAL_1:
      drawScreenTutorial1();
      break;
    case UI_TUTORIAL_2:
      drawScreenTutorial2();
      break;
    case UI_TUTORIAL_3:
      drawScreenTutorial3();
      break;
    case UI_VOICE_SELECT:
      drawScreenPersonalitySelect();
      break;
    case UI_ACTIVE:
    default:
      drawCurrentView();
      break;
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
      borderColor = 0xF800; // Red
      msg = "Recording audio";
      dotX = 95;
      break;
    case UI_OVERLAY_SPEAKING:
      borderColor = 0x07E0; // Green
      msg = "Speaking answer";
      dotX = 95;
      break;
    case UI_OVERLAY_GENERATING:
    default:
      borderColor = 0xFFE0; // Yellow
      msg = "Generating answer";
      dotX = 107;
      break;
  }

  if (fullRedraw) {
    tft.fillRoundRect(2, 2, 126, 13, 2, ST77XX_BLACK);
    tft.drawRoundRect(2, 2, 126, 13, 2, borderColor);

    tft.setTextColor(0xFFFF, 0x0000); // White text on black background
    tft.setTextSize(1);
    tft.setCursor(5, 5);
    tft.print(msg);

    // Cancellation prompt shown only during processing
    if (type == UI_OVERLAY_GENERATING) {
      tft.fillRoundRect(10, 114, 140, 12, 2, ST77XX_BLACK);
      tft.drawRoundRect(10, 114, 140, 12, 2, 0xFFE0);
      tft.setTextColor(0xFFE0, 0x0000);
      tft.setTextSize(1);
      tft.setCursor(14, 116);
      tft.print("Push button: STOP");
    }
  }

  // Update animated dots in-place
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

  // Vertical volume bar capsule on the far right edge
  const int16_t trackX = 154;
  const int16_t trackY = 20;
  const int16_t trackW = 5;
  const int16_t trackH = 88;
  const int16_t innerX = 155;
  const int16_t innerY = 22;
  const int16_t innerW = 3;
  const int16_t innerH = 84;

  tft.fillRoundRect(trackX, trackY, trackW, trackH, 2, 0x2104); // Dark gray track
  tft.drawRoundRect(trackX, trackY, trackW, trackH, 2, 0x52AA); // Subtle border

  // Fill height from bottom upwards
  int16_t fillH = (int16_t)(((int32_t)volume * innerH) / 100);
  if (fillH > innerH) fillH = innerH;
  if (fillH < 0) fillH = 0;

  int16_t emptyH = innerH - fillH;

  if (emptyH > 0) {
    tft.fillRect(innerX, innerY, innerW, emptyH, 0x2104);
  }
  if (fillH > 0) {
    tft.fillRect(innerX, innerY + emptyH, innerW, fillH, 0xFFFF); // White fill
  }
}
