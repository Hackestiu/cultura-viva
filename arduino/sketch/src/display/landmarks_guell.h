#pragma once

#include <stdint.h>

/**
 * Landmark definitions for Park Güell.
 * Coordinates are mapped to the 160x112 tile-map area.
 */

struct Landmark {
  const char* code;    // 2-letter identifier
  const char* screen;  // Short uppercase display name for the HUD status bar
  int16_t x, y;
};

const uint8_t NUM_LANDMARKS = 8;

const Landmark LANDMARKS[NUM_LANDMARKS] = {
  /* 0 */ { "PL", "PORTERS LODGE",  50,  94 },  // Porter's Lodge
  /* 1 */ { "DR", "DRAGON STAIRS",  70,  82 },  // Dragon Stairway
  /* 2 */ { "HH", "HYPOSTYLE HALL", 74,  70 },  // Hypostyle Hall
  /* 3 */ { "NS", "NATURE SQUARE",  82,  58 },  // Nature Square
  /* 4 */ { "CG", "CASA GAUDI",     90,  18 },  // Casa Museu Gaudi
  /* 5 */ { "TV", "3 VIADUCTS",     124, 34 },  // The Three Viaducts
  /* 6 */ { "CH", "CALVARY HILL",   22,  62 },  // Calvary Hill
};

// Marker color definitions (r, g, b)
const uint8_t COLOR_RING[3]      = { 240, 230, 210 };  // Pin outline color
const uint8_t COLOR_UNVISITED[3] = { 18,  19,  26  };  // Pin center color (unvisited)
const uint8_t COLOR_VISITED[3]   = { 255, 207, 63  };  // Pin center color (visited)
const uint8_t COLOR_LOCATION[3]  = { 255, 85,  68  };  // Location marker color

