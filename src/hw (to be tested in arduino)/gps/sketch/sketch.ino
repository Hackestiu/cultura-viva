/*
  GPS Minimap - MCU-side position tracking
  Runs on the STM32U585 (MCU) side of the Arduino UNO Q.
*/

#include <Arduino_RouterBridge.h>
#include <TinyGPSPlus.h>

TinyGPSPlus gps;

const unsigned long GPS_BAUD = 9600;

float currentLat = 0.0f;
float currentLon = 0.0f;
bool fixValid = false;

String getPosition() {
  String result;
  result.reserve(48);
  result += String(currentLat, 6); result += ";";
  result += String(currentLon, 6); result += ";";
  result += String(fixValid);
  return result;
}

void setup() {
  Serial1.begin(GPS_BAUD);

  Bridge.begin();
  Bridge.provide_safe("get_position", getPosition);
}

void loop() {
  while (Serial1.available() > 0) {
    gps.encode(Serial1.read());
  }

  if (gps.location.isUpdated()) {
    currentLat = gps.location.lat();
    currentLon = gps.location.lng();
    fixValid = gps.location.isValid();
  }
}