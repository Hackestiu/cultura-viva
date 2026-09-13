#pragma once

#include <stdint.h>

/**
 * 40x28 grid tilemap representation of the Casa Milà (La Pedrera) facade.
 *
 * Like Casa Batlló, this is a stylized front ELEVATION seen from the
 * sidewalk across Passeig de Gràcia — not an aerial terrain map. Unlike
 * Batlló, Casa Milà sits on a street corner (Passeig de Gràcia / Carrer de
 * Provença) with a continuous wave of stone wrapping around it, so the
 * layout is split into three horizontal bands instead of top/bottom zones:
 *
 *   - cols 0-9   -> ALA ESQUERRA  (left wing, receding — a "punt de fuga"
 *                   toward Provença, drawn shorter/compressed)
 *   - cols 10-29 -> CANTONADA     (the street corner itself, straight-on
 *                   from the far sidewalk — tallest, most detailed band)
 *   - cols 30-39 -> ALA DRETA     (right wing, receding — the other
 *                   vanishing point, continuing along Passeig de Gràcia)
 *
 * rows 0-19  -> zona SUPERIOR (coronament ondulat, xemeneies, façana de pedra)
 * row  20    -> cornisa divisòria entre planta noble i planta baixa
 * rows 21-27 -> zona INFERIOR (planta baixa, portals, vorera)
 */

#define MAP_ROW_COUNT_MILA 28
// MAP_COL_COUNT (40) is shared globally, defined in tilemap_guell.h

const char* const MAP_ROWS_MILA[MAP_ROW_COUNT_MILA] = {
  "                                        ",
  "                 cc    cc               ",  // xemeneies (rooftop chimneys) peeking above the crown
  "            wwwwwwwwwwwwwwww            ",  // coronament ondulat (wavy parapet) - Cantonada, tallest
  "           wwowwwowwwowwwowww           ",  // ulls de bou (oculus windows) along the crown
  "          wwwwwwwwwwwwwwwwwwww          ",
  "    wwwwww                    wwwwww    ",  // ales: coronament més baix (recessió / punt de fuga)
  "    wwwwwwsssssssssssssssssssswwwwww    ",
  "    ssssssssssssssssssssssssssssssss    ",
  "rrrrrrrrrrssssssssssssssssssssrrrrrrrrrr",
  "rrrrrrrrrrssiissiissiissiisiisrrrrrrrrrr",  // finestres, planta noble (pis 1)
  "rrrrrriirrssbbssbbssbbssbbsbbsrriirrrrrr",  // balcons de ferro forjat
  "rrrrrrrrrrssssssssssssssssssssrrrrrrrrrr",
  "rrrrrrrrrrssssssssssssssssssssrrrrrrrrrr",
  "rrrrrrrrrrsiissiissiissiisiissrrrrrrrrrr",  // finestres, planta noble (pis 2)
  "rrrrrrrrrrsbbssbbssbbssbbsbbssrrrrrrrrrr",  // balcons de ferro forjat
  "rrrrriirrrssssssssssssssssssssrrriirrrrr",
  "rrrrrrrrrrssssssssssssssssssssrrrrrrrrrr",
  "rrrrrrrrrrssiissiissiissiisiisrrrrrrrrrr",  // finestres, planta noble (pis 3)
  "rrrrrrrrrrssbbssbbssbbssbbsbbsrrrrrrrrrr",  // balcons de ferro forjat
  "rrrrrrrrrrssssssssssssssssssssrrrrrrrrrr",
  "dddddddddddddddddddddddddddddddddddddddd",  // cornisa divisoria (planta noble / planta baixa)
  "aaaaaaaaaaaaapppaaapppaapppaaaaaaaaaaaaa",  // portals de pedra, planta baixa
  "aaaaappaaaaaapppaaapppaapppaaaaaappaaaaa",
  "aaaaappaaaaaapppaaapppaapppaaaaaappaaaaa",
  "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "ggglgggggggggggggggggggggggggggggggglggg",  // vorera + fanals
  "ggggggggttggggggggggggggggggggttgggggggg",  // vorera + arbrat (plataners)
  "jjjggggggggggggggggggggggggggggggggggjjj",  // cantonades amb els edificis veïns
};

// Tile legend:
//  ' ' cel                          'c' xemeneia (espantabruixes, entrevista al capdamunt)
//  'w' cornisa ondulada de coronament 'o' ull de bou / finestra d'àtic
//  's' pedra ondulada de la façana   'i' finestra
//  'b' balcó de ferro forjat         'r' pedra en perspectiva (ales, punt de fuga)
//  'd' cornisa divisòria de planta   'a' pedra de la planta baixa
//  'p' ombra dels portals de pedra   'j' edifici veí / cantonada del carrer
//  't' arbre de vorera (plataner)    'l' fanal de vorera
//  'g' vorera

// Color palette, sampled from the real facade (reuses the shared ParkColor
// struct defined in tilemap_guell.h).
const ParkColor MILA_PAL_VOID     = { 120, 178, 214 };  // cel
const ParkColor MILA_PAL_PARAPET  = { 224, 214, 188 };  // coronament ondulat, pedra clara
const ParkColor MILA_PAL_OCULUS   = { 90,  84,  72  };  // ull de bou (obertura fosca)
const ParkColor MILA_PAL_CHIMNEY  = { 158, 132, 108 };  // xemeneia (trencadís terrós)
const ParkColor MILA_PAL_STONE    = { 214, 199, 168 };  // pedra ondulada principal
const ParkColor MILA_PAL_WINDOW   = { 46,  54,  64  };  // finestra (vidre fosc)
const ParkColor MILA_PAL_BALCONY  = { 42,  40,  36  };  // ferro forjat (balcons "d'algues")
const ParkColor MILA_PAL_RECEDE   = { 176, 172, 158 };  // pedra de les ales, apagada (recessió)
const ParkColor MILA_PAL_DIVIDER  = { 150, 130, 100 };  // cornisa divisòria
const ParkColor MILA_PAL_GROUND   = { 158, 146, 122 };  // pedra planta baixa
const ParkColor MILA_PAL_PORTAL   = { 58,  50,  42  };  // ombra dels portals
const ParkColor MILA_PAL_NEIGHBOR = { 140, 96,  80  };  // edifici veí a la cantonada
const ParkColor MILA_PAL_TREE     = { 70,  128, 76  };  // arbrat (plataners)
const ParkColor MILA_PAL_SIDEWALK = { 168, 162, 150 };  // vorera
const ParkColor MILA_PAL_LAMP     = { 60,  58,  54  };  // fanal
const ParkColor MILA_PAL_INK      = { 28,  24,  20  };  // contorn / detall fosc