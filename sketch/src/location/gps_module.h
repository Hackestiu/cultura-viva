#pragma once

#include <TinyGPSPlus.h>

extern TinyGPSPlus gps;

/**
 * Initializes the hardware serial port for the GPS module.
 */
void initGPS();

/**
 * Reads available data bytes from the GPS serial interface and feeds the GPS parser.
 */
void updateGPS();

/**
 * Returns true if a valid GPS location fix is available.
 */
bool has_gps_fix();

/**
 * Returns the current latitude in decimal degrees, or 0.0 if fix is invalid.
 */
float get_gps_lat();

/**
 * Returns the current longitude in decimal degrees, or 0.0 if fix is invalid.
 */
float get_gps_lon();

