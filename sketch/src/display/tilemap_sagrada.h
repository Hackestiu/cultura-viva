#pragma once

#include <stdint.h>
#include "tilemap_guell.h"  // reuses the ParkColor struct defined for Park Güell

/**
 * 40×28 grid tilemap for the Sagrada Família (Latin-cross floor plan).
 * Same screen dimensions as the Park Güell map (160×112 tile area, 4px/tile).
 *
 * Palette uses warm limestone/sandstone tones to match the real architecture:
 * cream exterior, warm stone walls, blue-teal sacristies, golden ochre crossing,
 * terracotta towers, and pale warm stone for the nave.
 */

#define MAP_COL_COUNT_SAGRADA 40
#define MAP_ROW_COUNT_SAGRADA 28

const char* const MAP_ROWS_SAGRADA[MAP_ROW_COUNT_SAGRADA] = {
  "                                        ",
  "       yy                      yy       ",
  "      yyy         ####         yyy      ",
  "     yyyyy      aaaaaaaa      yyyyy     ",
  "     yyyyyywwaaaaaaaaaaaaaawwyyyyyy     ",
  "     yyyyyywaaaaaaaaaaaaaaaawyyyyyy     ",
  "     yyyyyaaaaaaaaaaaaaaaaaaaayyyyy     ",
  "      yyywwwwwwwwwwwwwwwwwwwwwwyyy      ",
  "     wwyywwwwwwwwwwwwwwwwwwwwwwyyww     ",
  "    #xxxxxxxxxxxxxxttxxxxxxxxxxxxxx#    ",
  "    #xxxxxxxxxxxxxttttxxxxxxxxxxxxx#    ",
  "    #xxxxxxxxxxxxttttttxxxxxxxxxxxx#    ",
  "    #xxxxxxxxxxxxttttttxxxxxxxxxxxx#    ",
  "    #xxxxxxxxxxxxxttttxxxxxxxxxxxxx#    ",
  "    #x#xxxxxxxxxxxxttxxxxxxxxxxxx#x#    ",
  "         #lllllnnnnnnnnnnlllll#         ",
  "         #lllllnnnnnnnnnnlllll#         ",
  "         #lllllnnnnnnnnnnlllll#         ",
  "         #lllllnnnnnnnnnnlllll#         ",
  "         #lllllnnnnnnnnnnlllll#         ",
  "         #lllllnnnnnnnnnnlllll#         ",
  "         #lllllnnnnnnnnnnlllll#         ",
  "         #lllllnnnnnnnnnnlllll#         ",
  "         #lllllnnnnnnnnnnlllll#         ",
  "          #cccccccccccccccccc#          ",
  "         #cccccccccccccccccccc#         ",
  "         cccwwwcccwwwcccwwwcccw         ",
  "                                        ",
};

// Tile legend:
//  ' ' void / exterior    '#' outer wall edge (buttress/pinnacle)
//  'w' wall fill masonry  'a' absis (apse) floor
//  'y' sagristia floor    'x' creuer / transsepte floor
//  't' base torres        'n' nau central floor
//  'l' nau lateral        'c' porxo / Façana de la Glòria

// ---------------------------------------------------------------------------
// Unlocked (revealed) tile colors — warm limestone/sandstone real-life palette
// ---------------------------------------------------------------------------
const ParkColor SAG_PAL_VOID      = { 245, 237, 224 }; // warm cream exterior  #f5ede0
const ParkColor SAG_PAL_WALL_EDGE = { 168, 152, 104 }; // warm dark stone       #a89868
const ParkColor SAG_PAL_WALL_FILL = { 196, 180, 138 }; // warm mid stone        #c4b48a
const ParkColor SAG_PAL_APSE      = { 240, 232, 216 }; // pale limestone cream  #f0e8d8
const ParkColor SAG_PAL_SACRISTY  = { 136, 188, 200 }; // blue-teal stone       #88bcc8
const ParkColor SAG_PAL_CRUCERO   = { 212, 184, 112 }; // warm golden ochre     #d4b870
const ParkColor SAG_PAL_TORRES    = { 192, 112,  80 }; // terracotta brick      #c07050
const ParkColor SAG_PAL_NAVE      = { 220, 200, 138 }; // light warm stone      #dcc88a
const ParkColor SAG_PAL_LATERAL   = { 200, 176, 122 }; // medium tan stone      #c8b07a
const ParkColor SAG_PAL_PORCH     = { 200, 192, 176 }; // pale grey stone       #c8c0b0

// ---------------------------------------------------------------------------
// Locked (greyscale, unvisited) versions — luminance-matched grey tones
// ---------------------------------------------------------------------------
const ParkColor SAG_PAL_VOID_L      = { 232, 232, 232 }; // #e8e8e8
const ParkColor SAG_PAL_WALL_EDGE_L = { 136, 136, 136 }; // #888888
const ParkColor SAG_PAL_WALL_FILL_L = { 168, 168, 168 }; // #a8a8a8
const ParkColor SAG_PAL_APSE_L      = { 216, 216, 216 }; // #d8d8d8
const ParkColor SAG_PAL_SACRISTY_L  = { 144, 144, 144 }; // #909090
const ParkColor SAG_PAL_CRUCERO_L   = { 176, 176, 176 }; // #b0b0b0
const ParkColor SAG_PAL_TORRES_L    = { 120, 120, 120 }; // #787878
const ParkColor SAG_PAL_NAVE_L      = { 192, 192, 192 }; // #c0c0c0
const ParkColor SAG_PAL_LATERAL_L   = { 164, 164, 164 }; // #a4a4a4
const ParkColor SAG_PAL_PORCH_L     = { 184, 184, 184 }; // #b8b8b8