#include <Arduino.h>
#include "gps_module.h"
#include "../core/config.h"

TinyGPSPlus gps;

void initGPS() {
  Serial1.begin(GPS_BAUD);
}

void updateGPS() {
  while (Serial1.available() > 0) {
    gps.encode(Serial1.read());
  }
}

bool has_gps_fix() {
  return gps.location.isValid();
}

float get_gps_lat() {
  return gps.location.isValid() ? (float)gps.location.lat() : 0.0f;
}

float get_gps_lon() {
  return gps.location.isValid() ? (float)gps.location.lng() : 0.0f;
}

