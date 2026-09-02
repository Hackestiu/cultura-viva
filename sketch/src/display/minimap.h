#pragma once

#include <stdint.h>
#include "landmarks.h"

extern bool visited[NUM_LANDMARKS];
extern int8_t lastVisitedId;
extern bool hasLocation;
extern int16_t locX;
extern int16_t locY;

/**
 * Pre-computes saturated and desaturated RGB565 color lookup values for tilemap rendering.
 */
void initMinimapColors();

/**
 * Determines the nearest landmark ID for a given tile coordinate.
 *
 * @param x X coordinate on the 160x112 tile map.
 * @param y Y coordinate on the 160x112 tile map.
 * @return Index of the nearest landmark (0 to NUM_LANDMARKS - 1).
 */
uint8_t nearestLandmarkId(int16_t x, int16_t y);

/**
 * Renders the terrain, landmark pins, location marker, and status bar on the display.
 */
void drawParkMap();

/**
 * Marks a landmark as visited by index and refreshes display if map mode is currently visible.
 */
void markVisited(uint8_t id);

/**
 * Sets current location marker coordinates and refreshes display if map mode is currently visible.
 */
void setLocation(int16_t x, int16_t y);

/**
 * Resets all visited landmark states and location marker.
 */
void resetMinimapState();

/**
 * RPC callback: Marks landmark visited by ID.
 */
bool mark_landmark_visited(int id);

/**
 * RPC callback: Sets location marker to a landmark's coordinates by ID.
 */
bool set_location_by_id(int id);

/**
 * RPC callback: Sets location marker to arbitrary (x, y) coordinates.
 */
bool set_location_xy(int x, int y);

/**
 * RPC callback: Resets all minimap state.
 */
bool reset_minimap();

