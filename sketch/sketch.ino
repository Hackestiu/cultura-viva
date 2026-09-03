/**
 * CULTURA VIVA — Arduino UNO Q Main Sketch
 *
 * System orchestration including display setup, control loops, GPS interface,
 * RPC provisions, and state machine iteration.
 */

#include <Arduino_RouterBridge.h>
#include <SPI.h>
#include <Wire.h>

#include "src/core/config.h"
#include "src/core/app_state.h"
#include "src/core/rpc_manager.h"
#include "src/display/ui_manager.h"
#include "src/display/camera_view.h"
#include "src/display/ui_screens.h"
#include "src/display/minimap.h"
#include "src/input/controls.h"
#include "src/location/gps_module.h"

static unsigned long lastStatusPrint = 0;

void setup() {
  Bridge.begin();
  Monitor.begin();
  delay(3000);

  Monitor.println("==================================");
  Monitor.println(" CULTURA VIVA — Arduino UNO Q");
  Monitor.println("==================================");
  delay(100);

  Monitor.println("[..] Registering RPCs...");
  delay(100);
  initRPC();
  Monitor.println("[OK] RPCs registered");
  delay(100);

  Monitor.println("[..] Configuring external button (D7)...");
  delay(100);
  Monitor.println("[OK] External button (D7) configured with internal pull-up");
  delay(100);

  Monitor.println("[..] Configuring switch (D6)...");
  delay(100);
  Monitor.println("[OK] Switch (D6) configured with internal pull-up");
  delay(100);

  Monitor.println("[..] Initializing LCD (tft.initR)...");
  delay(100);
  initDisplay();
  Monitor.println("[OK] LCD ST7735S initialized");
  delay(100);

  Monitor.println("[..] Initializing minimap colors...");
  delay(100);
  initMinimapColors();
  Monitor.println("[OK] Minimap colors initialized");
  delay(100);

  Monitor.println("[..] Initializing I2C bus Wire1 (Qwiic connector)...");
  delay(100);
  Monitor.println("[..] Initializing Modulino Knob...");
  Monitor.println("[..] Initializing Modulino Buttons...");
  Monitor.println("[..] Initializing Modulino Buzzer...");
  initControls();
  Monitor.println("[OK] I2C bus Wire1 + Modulinos initialized");
  delay(100);

  Monitor.println("[..] Initializing GPS (Serial1)...");
  delay(100);
  initGPS();
  Monitor.println("[OK] Serial1 (GPS) initialized -- waiting for fix...");
  delay(100);

  Monitor.println("==================================");
  Monitor.println("Starting main loop...");
  Monitor.println("==================================");

  drawScreenIntro();
}

void loop() {
  updateGPS();
  updateControls();

  // Periodically emit serial debug diagnostics every 2 seconds
  if (millis() - lastStatusPrint >= 2000) {
    lastStatusPrint = millis();
    Monitor.print("Status | D7: ");
    Monitor.print((digitalRead(EXT_BUTTON_PIN) == LOW) ? "pressed" : "free");
    Monitor.print(" | Switch D6: ");
    Monitor.print(viewSwitchDebounced ? "ON (camera)" : "OFF (minimap)");
    Monitor.print(" | Volume: ");
    Monitor.print(currentVolume);
    Monitor.print("%");
    Monitor.print(" | Personality idx: ");
    Monitor.print(personalityIndex);
    Monitor.print(" | Recording: ");
    Monitor.print(recordingActive ? "YES" : "no");
    Monitor.print(" | Processing: ");
    Monitor.print(processingActive ? "YES" : "no");
    Monitor.print(" | GPS fix: ");
    if (has_gps_fix()) {
      Monitor.print(get_gps_lat(), 6);
      Monitor.print(",");
      Monitor.println(get_gps_lon(), 6);
    } else {
      Monitor.println("no fix");
    }
  }

  delay(20);
}
