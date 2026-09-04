#include "camera_view.h"
#include "ui_manager.h"

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
  // Solid overlay banner across bottom of the screen
  tft.fillRect(0, 86, 160, 42, 0x0000); // Black background
  tft.drawRect(0, 86, 160, 42, 0xFFE0); // Yellow border
  
  tft.setTextColor(0xFFE0); // Yellow
  tft.setTextSize(1);
  tft.setCursor(6, 90);
  tft.print(F("Do you like the photo?"));
  
  tft.setTextColor(0x07E0); // Green
  tft.setCursor(6, 102);
  tft.print(F("Switch to Map: KEEP"));
  
  tft.setTextColor(0xF800); // Red
  tft.setCursor(6, 114);
  tft.print(F("Push Button: RETAKE"));
}

void drawNoPhotoWarningOverlay() {
  // Red alert box in center of screen
  tft.fillRoundRect(8, 28, 144, 70, 5, 0x0000); // Black fill
  tft.drawRoundRect(8, 28, 144, 70, 5, 0xF800); // Red border
  tft.drawRoundRect(9, 29, 142, 68, 4, 0xF800);
  
  tft.setTextColor(0xF800); // Red
  tft.setTextSize(1);
  tft.setCursor(18, 36);
  tft.print("! NO PHOTO TAKEN !");
  
  tft.drawFastHLine(14, 48, 132, 0xF800);
  
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
// Vision validation full-screen status screens
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
    tft.fillScreen(0x0000); // Black background

    // Top accent bar
    tft.fillRect(0, 0, 160, 3, 0x07FF); // Cyan stripe

    // Large camera / scan icon (simple crosshair lines)
    tft.drawRect(52, 20, 56, 42, 0x07FF);         // outer rect
    tft.drawRect(54, 22, 52, 38, 0x4208);         // inner shadow
    tft.drawFastHLine(68, 41, 24, 0x07FF);         // horizontal crosshair
    tft.drawFastVLine(80, 28, 24, 0x07FF);         // vertical crosshair
    tft.fillCircle(80, 41, 5, 0x07FF);             // center dot

    // Static label
    tft.setTextColor(0xFFFF); // White
    tft.setTextSize(1);
    tft.setCursor(24, 72);
    tft.print(F("Scanning photo"));
  }

  // Animated dots only — erase & redraw the dot area
  tft.setTextColor(0x07FF, 0x0000); // Cyan on black background
  tft.setTextSize(1);
  tft.setCursor(104, 72);
  tft.print(dots);

  if (fullRedraw) {
    // Subtitle hint (static)
    tft.setTextColor(0x4208); // Dark grey
    tft.setTextSize(1);
    tft.setCursor(14, 88);
    tft.print(F("Checking the monument..."));

    // Bottom accent bar
    tft.fillRect(0, 125, 160, 3, 0x07FF);
  }
}

void drawVisionValidScreen() {
  // Dark green background
  tft.fillScreen(tft.color565(10, 60, 25));

  // Top accent bar
  tft.fillRect(0, 0, 160, 3, 0x07E0); // Bright green

  // Large checkmark (two lines forming a tick)
  //  left arm: from (54,58) to (68,74)
  //  right arm: from (68,74) to (106,38)
  for (int t = 0; t <= 6; t++) {
    tft.drawLine(54 + t, 58, 68 + t, 74, 0x07E0);
    tft.drawLine(68 + t, 74, 106 + t, 38, 0x07E0);
  }

  // Title
  tft.setTextColor(0xFFFF); // White
  tft.setTextSize(1);
  tft.setCursor(28, 84);
  tft.print(F("Photo validated!"));

  // Subtitle
  tft.setTextColor(tft.color565(150, 230, 160)); // Light green
  tft.setCursor(16, 100);
  tft.print(F("Monument recognised."));

  // Bottom accent bar
  tft.fillRect(0, 125, 160, 3, 0x07E0);
}

void drawVisionInvalidScreen(const char* locationLabel) {
  // Dark red background
  tft.fillScreen(tft.color565(70, 10, 10));

  // Top accent bar
  tft.fillRect(0, 0, 160, 3, 0xF800); // Red

  // X symbol (two crossed lines)
  for (int t = -3; t <= 3; t++) {
    tft.drawLine(52, 20 + abs(t), 108, 60 + abs(t), 0xF800);
    tft.drawLine(108, 20 + abs(t), 52, 60 + abs(t), 0xF800);
  }

  // Title
  tft.setTextColor(0xFFFF); // White
  tft.setTextSize(1);
  tft.setCursor(8, 68);
  tft.print(F("Not a monument in:"));

  // Location label (highlight in yellow)
  tft.setTextColor(0xFFE0); // Yellow
  tft.setCursor(8, 80);
  tft.print(locationLabel);

  // Instruction
  tft.setTextColor(tft.color565(240, 180, 180)); // Light red
  tft.setCursor(8, 96);
  tft.print(F("Retake photo of a"));
  tft.setCursor(8, 107);
  tft.print(F("valid monument."));

  // Bottom accent bar
  tft.fillRect(0, 125, 160, 3, 0xF800);
}
