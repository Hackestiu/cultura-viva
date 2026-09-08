#pragma once

#include <stdint.h>

/**
 * 40x28 grid tilemap representation of Park Güell terrain.
 */

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

// Color structure for terrain rendering (named ParkColor to prevent platform identifier conflicts)
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

