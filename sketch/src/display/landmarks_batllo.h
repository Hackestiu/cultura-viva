#pragma once

#include <stdint.h>
#include "minimap.h"  // shared Landmark struct

/**
 * Landmark pins + marker colors for the Casa Batlló minimap.
 *
 * Mirrors landmarks_sagrada.h: one Landmark per zone of the facade (see
 * "zones" in landmarks_batllo.json), positioned at the (x, y) pixel where
 * its pin is drawn on the 160x112 map, plus the short label shown in the
 * status bar once it's the nearest/last-visited landmark.
 *
 * Values are copied straight from landmarks_batllo.json's "landmarks" and
 * "markerColors" so the firmware and the Python-side MinimapManager agree.
 * The JSON's numeric "id" is just this array's index (0 = Pla Superior,
 * 1 = Pla Inferior) - mark_landmark_visited(id) / set_location_by_id(id)
 * index into this array directly. The JSON's "code" (PS/PI) is only used
 * on the Python side to resolve a label to an id; the firmware never sees it.
 *
 * NOTE: this assumes the shared Landmark struct (declared in minimap.h)
 * exposes members `x`, `y`, `screen` - the only fields minimap.cpp reads
 * for any site. Designated initializers are used on purpose: if the real
 * struct uses different field names or a different member order, this will
 * fail to *compile* rather than silently storing values in the wrong
 * field - if that happens, paste minimap.h's Landmark definition (or
 * landmarks_sagrada.h) and I'll line these up exactly.
 */

#define NUM_LANDMARKS_BATLLO 2

const Landmark LANDMARKS_BATLLO[NUM_LANDMARKS_BATLLO] = {
  { "PS", "PLA SUPERIOR", 80, 44 },  // id 0: teulada del drac, torre, planta noble
  { "PI", "PLA INFERIOR", 80, 96 },  // id 1: arcs parabolics, facana d'acces
};

// Marker colors -> landmarks_batllo.json "markerColors"
const uint8_t BAT_COLOR_RING[3]      = { 240, 230, 210 };  // ring       #f0e6d2
const uint8_t BAT_COLOR_UNVISITED[3] = { 18,  19,  26  };  // unvisitedDot #12131a
const uint8_t BAT_COLOR_VISITED[3]   = { 255, 207, 63  };  // visitedDot #ffcf3f
const uint8_t BAT_COLOR_LOCATION[3]  = { 255, 85,  68  };  // location   #ff5544