#pragma once

#include <stdint.h>
#include "landmarks_guell.h"  // reutilitza el struct Landmark ja definit per Park Güell

/**
 * Landmark definitions for la Sagrada Família (switch D6 ON).
 *
 * v7: coordenades de píxel actualitzades per coincidir amb els dots de color
 * de la imatge de referencia de la planta (160x112 px, tile 4px):
 *   CU (30, 14)  — punt morat, sagristia esquerra / zona absis
 *   PO (138,  8) — punt taronja, exterior NE (exterior Façana del Naixement)
 *   TO ( 80, 58) — punt verd, creuer / confluencia nau central
 *   NL ( 50, 84) — punt vermell fosc, nau lateral esquerra (inferior)
 *   NR (110, 84) — punt vermell fosc, nau lateral dreta (inferior)
 *   FN (118, 54) — punt blau, brac dret del transsepte / Façana Naixement
 *   FP ( 38, 54) — punt cian, brac esquerre del transsepte / Façana Passio
 *
 * Colors del marcador actualitzats a tons calids que complementen la paleta
 * de pedra calcaria real de la Sagrada Familia.
 */

const uint8_t NUM_LANDMARKS_SAGRADA = 7;

const Landmark LANDMARKS_SAGRADA[NUM_LANDMARKS_SAGRADA] = {
  /* 0 CU */ { "CU", "CUPULA",       30,   14 },  // Cúpula / Absis (sagristia esq.)
  /* 1 PO */ { "PO", "POSTERIOR",   138,    8 },  // Absis exterior NE (Façana Naixement ext.)
  /* 2 TO */ { "TO", "TORRES",       80,   58 },  // Torres / Creuer (centre creuer-nau)
  /* 3 NL */ { "NL", "NAU LATERAL",  50,   84 },  // Nau Lateral esquerra
  /* 4 NR */ { "NR", "NAU LATERAL", 110,   84 },  // Nau Lateral dreta
  /* 5 FN */ { "FN", "F. NAIXEMENT",118,   54 },  // Façana del Naixement (brac dret)
  /* 6 FP */ { "FP", "F. PASSIO",    38,   54 },  // Façana de la Passió (brac esq.)
};

// NL i NR es desbloquegen junts (naus laterals simètriques)
const uint8_t LINKED_LATERALS[2] = { 3, 4 };

// ---------------------------------------------------------------------------
// Marker colors — warm tones for real-life limestone palette
// ---------------------------------------------------------------------------
const uint8_t SAG_COLOR_RING[3]      = { 245, 232, 210 };  // warm cream ring   #f5e8d2
const uint8_t SAG_COLOR_UNVISITED[3] = {  50,  40,  31 };  // warm dark center  #32281f
const uint8_t SAG_COLOR_VISITED[3]   = { 255, 210,  50 };  // warm gold         #ffd232
const uint8_t SAG_COLOR_LOCATION[3]  = { 220,  65,  56 };  // warm red          #dc4138

// ---------------------------------------------------------------------------
// Zone highlight overlay colors (for display systems that support per-zone
// colour illumination, e.g. a web preview layer or future LCD overlay mode).
// Matches the coloured zone shapes visible in the reference floor-plan image.
// ---------------------------------------------------------------------------
//  CU → #8b70c0  purple/violet  (apse + sacristies)
//  PO → #e08850  warm orange    (exterior NE / Nativity exterior)
//  TO → #5aaa6a  green          (crossing + central nave)
//  NL → #c87890  pink-salmon    (left lateral nave + porch)
//  NR → #c87890  pink-salmon    (right lateral nave + porch)
//  FN → #6888c0  periwinkle     (Nativity right arm)
//  FP → #50b8d0  cyan-blue      (Passion left arm)
const uint8_t SAG_ZONE_COLOR_CU[3] = { 139, 112, 192 };  // #8b70c0
const uint8_t SAG_ZONE_COLOR_PO[3] = { 224, 136,  80 };  // #e08850
const uint8_t SAG_ZONE_COLOR_TO[3] = {  90, 170, 106 };  // #5aaa6a
const uint8_t SAG_ZONE_COLOR_NL[3] = { 200, 120, 144 };  // #c87890
const uint8_t SAG_ZONE_COLOR_NR[3] = { 200, 120, 144 };  // #c87890
const uint8_t SAG_ZONE_COLOR_FN[3] = { 104, 136, 192 };  // #6888c0
const uint8_t SAG_ZONE_COLOR_FP[3] = {  80, 184, 208 };  // #50b8d0