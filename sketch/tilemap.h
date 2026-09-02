#pragma once

// 40x28 grid of 4px tiles (160x112px terrain map) adapted from a reference
// pixel map of Park Guell. Mirrors the "map" array in
// python/minimapa/landmarks.json — edit that first, then mirror the
// change here.
//
// NOTE: the original version of this file (written for an Uno/Nano) kept
// the map in PROGMEM (flash) to save the ~1.1KB of SRAM it takes, since a
// classic AVR Uno/Nano only has 2KB total. The Arduino UNO Q runs on
// arduino:zephyr, a completely different core with far more RAM, and
// PROGMEM/pgm_read_byte/pgm_read_word are AVR-specific macros that may not
// exist there — so this version just uses plain RAM arrays. If you ever
// port this back to a classic AVR board, PROGMEM is worth reintroducing.
//
// Tile legend: ' '=void '#'=path marker 'F'=dense pine 'f'=woodland
// 'g'=scrub/gardens 'p'=footpath 'S'=Nature Square 'w'=viaduct stone
// 'b'=pavilion roof 'c'=trencadis 'r'=rock

#define MAP_COL_COUNT 40
#define MAP_ROW_COUNT 28

const char* const MAP_ROWS[MAP_ROW_COUNT] = {
  "                                        ",
  "     FFFFFFF        FFFFF      FFFF     ",
  "   FFFFFFFFFFF   FFFFFFFFFFFFFFFFFFF    ",
  "  FFFFFFFFFFFFFFFFFFFFbbFFFFFFFFFFFFF   ",
  "  FFFFFFFFFFFFFFFFFFFpbbpFFFFFFFFFFFF   ",
  " FFFFFFFFFFFFFFFFFFFFpppFFFFFFFFFFFFFF  ",
  " FFFFFFFFFFFFFFFFFFFFpFFFFFFwwwwwwFFFF  ",
  " FFFFFFFFFFFFFFFFFFFpFFFFFFFwFFFFwFFFF  ",
  "FFFFFFFFFFFFFFFFFFFpFFFFFFwwwwwwwwwFFFF ",
  "FFFFFFFFFFFFFFFFFpFFFFFFFFwFFFFFFwFFFFF ",
  "FFFFFFFFFFFFFFFFpFFFFFFFwwwwwwwwwwFFFFF ",
  "FFFFFFFFFfffffppppppppppppppppppgggggggf",
  "FFFFFFFFffffpSSSSSSSSSSSSSSpggggggggggff",
  "FFFFFFFfffpSSSSSSSSSSSSSSSSpgggggggggggf",
  "FFFFFrFffpSSSSSSSSSSSSSSSSSpggggpgggggff",
  "FFFFrrrFfpSSSSSSSSSSSSSSSSSpggggpgggggff",
  "FFFFFrFFfpSSSSSSSSSSSSSSSSSpggggpgggggff",
  "FFFFFFFFfpFFcccccccccccccFpggggpggggggff",
  "FFFFFFFffpFFcccccccccccccFpgggggggggggff",
  "FFFFFFffpppFFbbbbbbbbbbbFFppppgggggggggf",
  "FFFFFffpFFFFFbccccccccbFFFFpppgggggggggf",
  "FFFFFffpFFFFFbccccccccbFFFFFppgggggggggf",
  "FFFFffpFFFFFFbbbbbbbbbbbFFFFFpgggggggggf",
  "FFFFffpFFFFbbbFFFFFbbbFFFFFFFpggggggggff",
  "FFFFffpppppppppppppppppppppppppgggggggff",
  "FFFffffppppppppppppppppppppppppgggggggff",
  "  ffff        ####     ####      gggg   ",
  "   ff         ####     ####       gg    "
};

// Park palette (r,g,b). Mirrors "palette" in python/minimapa/landmarks.json.
//
// NOTE: this struct is deliberately NOT called "RGB" -- that name
// collides with a macro/type already defined by the platform (most
// likely Arduino_LTR381RGB, the color-light-sensor library also used
// in this sketch, or Adafruit_SPITFT's color-order constants), which
// produced "'RGB' does not name a type" compile errors.
struct ParkColor { uint8_t r, g, b; };

const ParkColor PAL_VOID      = { 35, 36, 44 };
const ParkColor PAL_BLOCK     = { 58, 60, 72 };
const ParkColor PAL_BLOCK_D   = { 44, 46, 56 };
const ParkColor PAL_FOREST_DD = { 36, 81, 47 };
const ParkColor PAL_FOREST    = { 63, 122, 69 };
const ParkColor PAL_FOREST_L  = { 88, 146, 79 };
const ParkColor PAL_SCRUB     = { 111, 155, 74 };
const ParkColor PAL_SCRUB_L   = { 128, 176, 85 };
const ParkColor PAL_PATH      = { 217, 180, 119 };
const ParkColor PAL_PATH_D    = { 199, 159, 99 };
const ParkColor PAL_SAND      = { 226, 196, 143 };
const ParkColor PAL_SAND_D    = { 211, 177, 116 };
const ParkColor PAL_STONE     = { 154, 160, 166 };
const ParkColor PAL_STONE_D   = { 111, 117, 123 };
const ParkColor PAL_ROOF      = { 196, 87, 47 };
const ParkColor PAL_ROOF_L    = { 224, 122, 69 };
const ParkColor PAL_TILE      = { 74, 159, 196 };
const ParkColor PAL_TILE_L    = { 240, 230, 210 };
const ParkColor PAL_ROCK      = { 185, 179, 166 };
const ParkColor PAL_ROCK_D    = { 141, 136, 124 };
const ParkColor PAL_INK       = { 18, 19, 26 };