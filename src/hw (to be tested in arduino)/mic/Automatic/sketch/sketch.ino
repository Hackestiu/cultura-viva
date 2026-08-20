/*
  Bluetooth audio button interface for Arduino UNO Q.

  Short press: mute/unmute the local microphone.
  Long press: start Bluetooth discovery and pairing.
*/

#include <Arduino_RouterBridge.h>

const uint8_t BUTTON_PIN = 2;
const unsigned long DEBOUNCE_MS = 40;
const unsigned long LONG_PRESS_MS = 2000;

volatile int pendingButtonEvent = 0;
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
    } else if (!longPressReported && millis() - pressStartTime < LONG_PRESS_MS) {
      pendingButtonEvent = 1;
    }
  }

  if (buttonState == LOW && !longPressReported &&
      millis() - pressStartTime >= LONG_PRESS_MS) {
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
