/*
  Bluetooth Bidirectional Audio - MCU button interface
  Responsibilities:
    - Read a physical push button (short press = toggle mode,
      long press = enter manual pairing) and expose the last
      event to the MPU through the Bridge.
  All decision-making (Bluetooth pairing, BlueALSA streaming)
  happens on the Linux side; this sketch only reports button input.
*/

#include <Arduino_RouterBridge.h>

const uint8_t BUTTON_PIN = 2;
const unsigned long DEBOUNCE_MS = 40;
const unsigned long LONG_PRESS_MS = 2000;

volatile int pendingButtonEvent = 0;  // 0 = none, 1 = short press, 2 = long press

bool lastReading = HIGH;
bool buttonState = HIGH;
unsigned long lastDebounceTime = 0;
unsigned long pressStartTime = 0;
bool longPressReported = false;


int getButtonEvent() {
  int event = pendingButtonEvent;
  pendingButtonEvent = 0;
  return event;
}

void updateButton() {
  bool reading = digitalRead(BUTTON_PIN);

  if (reading != lastReading) {
    lastDebounceTime = millis();
  }

  if ((millis() - lastDebounceTime) > DEBOUNCE_MS && reading != buttonState) {
    buttonState = reading;
    if (buttonState == LOW) {
      pressStartTime = millis();
      longPressReported = false;
    } else {
      unsigned long heldFor = millis() - pressStartTime;
      if (!longPressReported && heldFor < LONG_PRESS_MS) {
        pendingButtonEvent = 1;
      }
    }
  }

  if (buttonState == LOW && !longPressReported &&
      (millis() - pressStartTime) >= LONG_PRESS_MS) {
    pendingButtonEvent = 2;
    longPressReported = true;
  }

  lastReading = reading;
}

void setup() {
  pinMode(BUTTON_PIN, INPUT_PULLUP);

  Bridge.begin();
  Bridge.provide("get_button_event", getButtonEvent);
}

void loop() {
  updateButton();
}