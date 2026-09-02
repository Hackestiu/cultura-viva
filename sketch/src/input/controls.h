#pragma once

#include <Arduino_Modulino.h>

extern ModulinoKnob    knob;
extern ModulinoButtons buttons;
extern ModulinoBuzzer  buzzer;

/**
 * Initializes peripheral pin modes, I2C bus Wire1, and Modulino modules.
 */
void initControls();

/**
 * Reads the knob encoder position with jump filtering to reject I2C read glitches.
 */
int16_t readKnobFiltered();

/**
 * Polls physical button D7, switch D6, Modulino buttons, and Modulino knob, updating system state.
 */
void updateControls();

