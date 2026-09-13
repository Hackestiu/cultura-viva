#include "camera_view.h"
#include "ui_manager.h"
#include "../core/app_state.h"

uint8_t camFrameBuf[CAM_TOTAL_PIXELS * 2];
int camExpectedChunk = 0;
unsigned long camLastChunkMillis = 0;
bool newCameraFrameFlag = false;

static int base64Value(char c) {
  if (c >= 'A' && c <= 'Z') return c - 'A';
  if (c >= 'a' && c <= 'z') return c - 'a' + 26;
  if (c >= '0' && c <= '9') return c - '0' + 52;
  if (c == '+') return 62;
  if (c == '/') return 63;
  return -1;
}

int base64Decode(const String &input, uint8_t *output, int maxOutputLen) {
  int outLen = 0;
  int val = 0, valb = -8;
  for (unsigned int i = 0; i < input.length(); i++) {
    int d = base64Value(input[i]);
    if (d == -1) continue;
    val = (val << 6) + d;
    valb += 6;
    if (valb >= 0) {
      if (outLen >= maxOutputLen) break;
      output[outLen++] = (uint8_t)((val >> valb) & 0xFF);
      valb -= 8;
    }
  }
  return outLen;
}

void receive_camera_chunk(int chunkIndex, int totalChunks, String data) {
  unsigned long now = millis();

  if (camExpectedChunk > 0 && (now - camLastChunkMillis) > CAM_CHUNK_TIMEOUT_MS) {
    camExpectedChunk = 0;
  }

  if (totalChunks != CAM_TOTAL_CHUNKS || chunkIndex != camExpectedChunk) {
    if (chunkIndex == 0) {
      camExpectedChunk = 0;
    } else {
      return;
    }
  }

  int byteOffset = chunkIndex * CAM_CHUNK_PIXELS * 2;
  int maxBytesThisChunk = (int)sizeof(camFrameBuf) - byteOffset;
  if (maxBytesThisChunk > CAM_CHUNK_PIXELS * 2) {
    maxBytesThisChunk = CAM_CHUNK_PIXELS * 2;
  }
  if (maxBytesThisChunk <= 0) return;

  base64Decode(data, camFrameBuf + byteOffset, maxBytesThisChunk);

  camLastChunkMillis = now;
  camExpectedChunk = chunkIndex + 1;

  if (chunkIndex == totalChunks - 1) {
    newCameraFrameFlag = true;
    camExpectedChunk = 0;
  }
}

void receive_photo_chunk(int chunkIndex, int totalChunks, String data) {
  if (totalChunks != PHOTO_TOTAL_CHUNKS) {
    return;
  }

  // On the very first chunk: clear the photo area to solid black, transition state,
  // and draw the confirmation footer immediately so the green validation screen
  // is never partially visible behind the incoming photo rows.
  if (chunkIndex == 0) {
    photoValidationState = -1;
    photoWaitingConfirmation = true;
    hasCapturedPhoto = true;
    highResPhotoDrawn = true;
    tft.fillRect(0, 0, PHOTO_PREVIEW_W, PHOTO_PREVIEW_H, 0x0000);
    drawPhotoConfirmationOverlay();
  }

  uint16_t chunkPixels[PHOTO_CHUNK_PIXELS];
  int maxBytes = PHOTO_CHUNK_PIXELS * 2;
  int decodedBytes = base64Decode(data, (uint8_t *)chunkPixels, maxBytes);
  if (decodedBytes <= 0) return;

  // Calculate coordinates: each row is PHOTO_PREVIEW_W (160) pixels wide.
  // Since PHOTO_CHUNK_PIXELS is 80, exactly 2 chunks form one full row.
  int col = (chunkIndex % 2) * PHOTO_CHUNK_PIXELS;
  int row = chunkIndex / 2;
  if (row < PHOTO_PREVIEW_H) {
    tft.drawRGBBitmap(col, row, chunkPixels, PHOTO_CHUNK_PIXELS, 1);
  }
}

void drawCameraViewPlaceholder() {
  tft.fillScreen(ST77XX_BLACK);
  tft.setTextColor(ST77XX_WHITE);
  tft.setTextSize(1);
  tft.setCursor(0, 0);
  tft.println("CAMERA VIEW");
  tft.println("(switch ON)");
  tft.println("");
  tft.println("Waiting for image...");
  int x = (160 - CAM_THUMB_W * CAM_SCALE) / 2;
  int y = (128 - CAM_THUMB_H * CAM_SCALE) / 2;
  tft.drawRect(x - 2, y - 2, CAM_THUMB_W * CAM_SCALE + 4, CAM_THUMB_H * CAM_SCALE + 4, ST77XX_WHITE);
}

void drawCameraFrame() {
  int x0 = (160 - CAM_THUMB_W * CAM_SCALE) / 2;
  int y0 = (128 - CAM_THUMB_H * CAM_SCALE) / 2;
  uint16_t *pixels = (uint16_t *)camFrameBuf;
  for (int row = 0; row < CAM_THUMB_H; row++) {
    for (int col = 0; col < CAM_THUMB_W; col++) {
      uint16_t color = pixels[row * CAM_THUMB_W + col];
      tft.fillRect(x0 + col * CAM_SCALE, y0 + row * CAM_SCALE, CAM_SCALE, CAM_SCALE, color);
    }
  }
}

void drawPhotoConfirmationOverlay() {
  // Solid banner with border across the bottom 42px of the display
  tft.fillRect(0, 86, 160, 42, 0x0000);
  tft.drawRect(0, 86, 160, 42, 0xFFE0); // Yellow border

  tft.setTextColor(0xFFE0); // Yellow
  tft.setTextSize(1);
  tft.setCursor(6, 90);
  tft.print(F("Do you like the photo?"));

  tft.setTextColor(0x07E0); // Green
  tft.setCursor(6, 102);
  tft.print(F("Switch to Map: KEEP"));

  tft.setTextColor(0x001F); // Red in ST7735 BGR mode
  tft.setCursor(6, 114);
  tft.print(F("Push Button: RETAKE"));
}

void drawNoPhotoWarningOverlay() {
  // Alert box in center of screen (0x001F = red in ST7735 BGR mode)
  tft.fillRoundRect(8, 28, 144, 70, 5, 0x0000);
  tft.drawRoundRect(8, 28, 144, 70, 5, 0x001F);
  tft.drawRoundRect(9, 29, 142, 68, 4, 0x001F);

  tft.setTextColor(0x001F); // Red
  tft.setTextSize(1);
  tft.setCursor(18, 36);
  tft.print("! NO PHOTO TAKEN !");

  tft.drawFastHLine(14, 48, 132, 0x001F);
  tft.setTextColor(0xFFFF); // White
  tft.setCursor(14, 54);
  tft.print("Switch ON to Camera");
  tft.setCursor(14, 66);
  tft.print("& take photo first");

  tft.setTextColor(0xFFE0); // Yellow
  tft.setCursor(14, 80);
  tft.print("to ask your question!");
}

// ---------------------------------------------------------------------------
// Vision validation status screens
// ---------------------------------------------------------------------------

void drawVisionCheckingScreen(uint8_t dotCount, bool fullRedraw) {
  static const char* const dotSuffixes[] = {
    "   ",
    ".  ",
    ".. ",
    "..."
  };
  const char* dots = dotSuffixes[dotCount % 4];

  if (fullRedraw) {
    tft.fillScreen(0x0000);
    tft.fillRect(0, 0, 160, 3, 0x07FF); // Top cyan stripe

    // Crosshair viewfinder icon
    tft.drawRect(52, 20, 56, 42, 0x07FF);
    tft.drawRect(54, 22, 52, 38, 0x4208);
    tft.drawFastHLine(68, 41, 24, 0x07FF);
    tft.drawFastVLine(80, 28, 24, 0x07FF);
    tft.fillCircle(80, 41, 5, 0x07FF);

    // Static label: "Scanning photo" (ends at X=107)
    tft.setTextColor(0xFFFF); // White
    tft.setTextSize(1);
    tft.setCursor(24, 72);
    tft.print(F("Scanning photo"));
  }

  // Animated dots only — erase & redraw starting at X=112 so dots do not overlap text
  tft.setTextColor(0x07FF, 0x0000); // Cyan on black
  tft.setTextSize(1);
  tft.setCursor(112, 72);
  tft.print(dots);

  if (fullRedraw) {
    tft.setTextColor(0x4208); // Dark grey
    tft.setTextSize(1);
    tft.setCursor(14, 88);
    tft.print(F("Checking the monument..."));

    tft.fillRect(0, 125, 160, 3, 0x07FF); // Cyan accent bar
  }
}

void drawVisionValidScreen(const char* monumentLabel) {
  // Dark green background
  tft.fillScreen(tft.color565(10, 60, 25));

  // Top accent bar
  tft.fillRect(0, 0, 160, 3, 0x07E0); // Bright green

  // Compact checkmark tick geometry (Y=12..38, centered horizontally)
  for (int t = 0; t <= 4; t++) {
    tft.drawLine(60 + t, 24, 72 + t, 38, 0x07E0);
    tft.drawLine(72 + t, 38, 100 + t, 12, 0x07E0);
  }

  tft.setTextColor(0xFFFF); // White
  tft.setTextSize(1);
  const char* title = "Photo validated!";
  int xTitle = (160 - (strlen(title) * 6)) / 2;
  tft.setCursor(xTitle, 46);
  tft.print(title);

  // Observation label: "Detected:"
  const char* obsLabel = "Detected:";
  int xObs = (160 - (strlen(obsLabel) * 6)) / 2;
  tft.setTextColor(tft.color565(150, 230, 160)); // Light green
  tft.setCursor(xObs, 62);
  tft.print(obsLabel);

  // Detected monument name in prominent warm gold/yellow
  const char* name = (monumentLabel != nullptr && monumentLabel[0] != '\0')
                     ? monumentLabel
                     : "Monument recognized";
  int len = strlen(name);
  int xMon = (160 - (len * 6)) / 2;
  if (xMon < 4) xMon = 4;
  tft.setTextColor(0xFFE0); // Yellow / Gold
  tft.setCursor(xMon, 76);
  tft.print(name);

  // Subtitle hint
  tft.setTextColor(tft.color565(120, 200, 140)); // Soft light green
  const char* hint = "Monument recognized.";
  int xHint = (160 - (strlen(hint) * 6)) / 2;
  tft.setCursor(xHint, 94);
  tft.print(hint);

  tft.fillRect(0, 125, 160, 3, 0x07E0);
}

void drawVisionInvalidScreen(const char* locationLabel) {
  // ST7735 BGR hardware channel order: bits[15:11]=Blue, bits[10:5]=Green, bits[4:0]=Red.
  // color565(B, G, R) maps to hardware channels correctly.
  // 0x001F has bits[4:0]=31 (maximum red, 0 blue).
  const uint16_t COLOR_RED = 0x001F;

  // Dark rich red background (Blue=12, Green=10, Red=90)
  tft.fillScreen(tft.color565(12, 10, 90));

  // Top accent bar
  tft.fillRect(0, 0, 160, 3, COLOR_RED);

  // Cross 'X' icon geometry centered at (80, 30)
  for (int t = -2; t <= 2; t++) {
    tft.drawLine(68, 18 + abs(t), 92, 42 + abs(t), COLOR_RED);
    tft.drawLine(92, 18 + abs(t), 68, 42 + abs(t), COLOR_RED);
  }

  tft.setTextSize(1);

  const char* title = "Not a monument in:";
  int xTitle = (160 - (strlen(title) * 6)) / 2;
  tft.setTextColor(0xFFFF); // White
  tft.setCursor(xTitle, 52);
  tft.print(title);

  // Clamp x to prevent text overflow for long location names
  int xLabel = (160 - (strlen(locationLabel) * 6)) / 2;
  if (xLabel < 0) xLabel = 0;
  // Bright soft red text: Blue=120, Green=120, Red=255
  tft.setTextColor(tft.color565(120, 120, 255));
  tft.setCursor(xLabel, 68);
  tft.print(locationLabel);

  const char* line1 = "Retake photo of a";
  int xLine1 = (160 - (strlen(line1) * 6)) / 2;
  // Soft pastel red: Blue=180, Green=180, Red=240
  tft.setTextColor(tft.color565(180, 180, 240));
  tft.setCursor(xLine1, 88);
  tft.print(line1);

  const char* line2 = "valid monument.";
  int xLine2 = (160 - (strlen(line2) * 6)) / 2;
  tft.setCursor(xLine2, 100);
  tft.print(line2);

  // Bottom accent bar
  tft.fillRect(0, 125, 160, 3, COLOR_RED);
}