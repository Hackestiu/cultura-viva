#pragma once

#include <stdint.h>

/**
 * Landmark definitions for Casa Milà (La Pedrera).
 * Coordinates are mapped to the 160x112 tile-map area.
 * Reuses the shared `Landmark` struct declared in landmarks_guell.h.
 *
 * 3 landmarks, matching the three sidewalk viewpoints of tilemap_mila.h:
 *   CN -> Cantonada     (straight-on from the far sidewalk, the classic shot)
 *   AE -> Ala Esquerra  (left wing, receding toward Provença)
 *   AD -> Ala Dreta     (right wing, receding along Passeig de Gràcia)
 */

const uint8_t NUM_LANDMARKS_MILA = 3;

const Landmark LANDMARKS_MILA[NUM_LANDMARKS_MILA] = {
  /* 0 */ { "CN", "CANTONADA",    80,  60 },  // Vista frontal des de l'acera de l'altra banda
  /* 1 */ { "AE", "ALA ESQUERRA", 20,  60 },  // Punt de fuga cap a Provenca
  /* 2 */ { "AD", "ALA DRETA",    140, 60 },  // Punt de fuga cap a Passeig de Gracia
};

// Marker colors (r, g, b) — kept identical to the Park Güell reference so the
// "you are here" / visited-pin visual language stays consistent across sites.
const uint8_t MILA_COLOR_RING[3]      = { 240, 230, 210 };
const uint8_t MILA_COLOR_UNVISITED[3] = { 18,  19,  26  };
const uint8_t MILA_COLOR_VISITED[3]   = { 255, 207, 63  };
const uint8_t MILA_COLOR_LOCATION[3]  = { 255, 85,  68  };
