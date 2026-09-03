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
  tft.println("VISTA CAMERA");
  tft.println("(switch ON)");
  tft.println("");
  tft.println("Esperant imatge...");
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
  tft.fillRect(0, 90, 160, 38, 0x0000); // Black background
  tft.drawRect(0, 90, 160, 38, 0xFFE0); // Yellow border
  
  tft.setTextColor(0xFFE0); // Yellow
  tft.setTextSize(1);
  tft.setCursor(4, 94);
  tft.print("Are you sure of photo?");
  
  tft.setTextColor(0x07FF); // Cyan
  tft.setCursor(4, 106);
  tft.print("-> Switch to Map: YES");
  
  tft.setTextColor(0xFFFF); // White
  tft.setCursor(4, 117);
  tft.print("-> Push button: Retake");
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


