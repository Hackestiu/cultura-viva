#pragma once

#include <stdint.h>

/**
 * 40x28 grid tilemap representation of the Casa Batlló facade.
 *
 * Unlike the Park Güell / Sagrada Família maps (aerial-style terrain), this
 * one is a stylized front ELEVATION of the facade on Passeig de Gràcia,
 * traced from the annotated reference photo (esquema_casa_batllo.png).
 *
 * v3: la façana de Batlló ocupa només les columnes 8-31 (24 de 40), en lloc
 * de gairebé tota l'amplada del mapa. A banda i banda hi ha edificis veïns
 * de l'Eixample (esquerra: un frontó esglaonat a la Amatller, dreta: un bloc
 * senzill amb un petit ràfec de pissarra), separats de Batlló per una franja
 * fosca (columnes 7 i 32) que suggereix la paret mitgera entre finques.
 * Amb la façana més estreta, l'edifici es llegeix més VERTICAL i es
 * reconeix millor: la torre amb creu i la teulada del drac ara sobresurten
 * clarament per damunt dels veïns, que són plans.
 *   rows 0-9   -> teulada del drac + torre amb creu (només al cos central)
 *   row  10    -> cornisa amb merlets, compartida per les tres finques
 *   rows 11-19 -> planta noble (Batlló: oculus + 2 pisos de finestres i
 *                 balcons d'os; veïns: la seva pròpia façana)
 *   row  20    -> franja de TRENCADÍS decoratiu que travessa tota l'amplada
 *                 (el "marc" de mosaic que unifica la composició)
 *   row  21    -> balustrada de pedra (Batlló) / cornisa dels veïns
 *   rows 22-27 -> planta baixa: arcs parabòlics (Batlló) i portals/sòcol
 *                 dels veïns, amb un arbre de vorera a cada cantonada
 *
 * Cada superfície plana continua fent servir un dither de 2-3 tons per
 * suggerir la textura real sense augmentar la resolució: escates de drac al
 * teulat, trencadís pigallat al mur, finestres amb marc d'os + vidre blau
 * flanquejades per balcons en forma de càpsula ("els ossos" — els famosos
 * balcons-calavera de Batlló), esgrafiat rosat a la casa veïna de
 * l'esquerra i parament més sobri a la de la dreta.
 *
 * v4: el contrast clar/fosc de cada parella de color (teulades, torre,
 * trencadís, pedra, veïns) s'ha suavitzat una mica, i paintTile() ara pinta
 * cada tile de 4x4 amb el seu to base MÉS un estampat de 4 píxels de la
 * parella oposada (vegeu minimap.cpp), en lloc d'un fillRect pla. Això
 * aprofita els píxels que ja hi ha dins de cada tile perquè el dithering
 * es llegeixi com una textura contínua en comptes d'un escaquer dur entre
 * tiles veïnes — sense canviar la resolució real de la pantalla (160x128).
 */

#define MAP_ROW_COUNT_BATLLO 28
// MAP_COL_COUNT (40) is shared globally, defined in tilemap_guell.h

const char* const MAP_ROWS_BATLLO[MAP_ROW_COUNT_BATLLO] = {
  "             x     uUu                  ",
  "            nnn    UuUu                 ",
  "            yZy   UuUuUU                ",
  "            zZZ   uUuUuu                ",
  "           VzZZ  uUuUuUUuUt             ",
  "           vzZZtUUuUuUuuUuTtT           ",
  "   i      vVzZZTuuUuUuUUuUtTt           ",
  "  iIi    VVvzZZtUUuUuUuuUuTtTt          ",
  " iIIIi   vvVzZZTuuUuUuUUuUtTtTT         ",
  "iIIIIIi vVVvzZZtUUuUuUuuUuTtTtt  DDDDDDD",
  "MeecMeecMeecMeecMeecMeecMeecMeecMeecMeec",  // cornisa amb merlets, tota l'amplada
  "pPpPpPpqcMMmfhhhfmoooomfhhhfcMMmqBCBCBCB",  // oculus central; veïns: esgrafiat
  "ppflfppqmMcmfhhhfmMcmMcfhhhfmMcmqBBfhfBB",  // planta noble, pis superior: finestres
  "pPpPpPpqcMmcfhhhfcMmcMmfhhhfcMmcqBCBCBCB",
  "PpPpPpPqmMcmbkkkbmMcmMcbkkkbmMcmqCBCBCBC",  // balco d'os sota finestres
  "pPpPpPpqmMmMmMmMmMmMmMmMmMmMmMmMqBCBCBCB",  // mur de trencadis pigallat entre pisos
  "PpPpPpPqcmMmcmMmcmMmcmMmcmMmcmMmqCBCBCBC",
  "ppflfppqmMcmfhhhfmMcmMcfhhhfmMcmqBBfhfBB",  // planta noble, pis inferior: finestres
  "pPpPpPpqcMmcfhhhfcMmcMmfhhhfcMmcqBCBCBCB",
  "PpPpPpPqmMcmbkkkbmMcmMcbkkkbmMcmqCBCBCBC",  // balco d'os sota finestres (fi zona SUPERIOR)
  "mMcMmMcMmMcMmMcMmMcMmMcMmMcMmMcMmMcMmMcM",  // franja de trencadis, tota l'amplada (marc)
  "aAaAaAaqkkkkkkkkkkkkkkkkkkkkkkkkqAaAaAaA",  // balustrada de pedra sobre els arcs
  "rrqqqrrqaaAaaAqqaaAaaAqqaaAaaAqqqAAqqqAA",  // arcs parabolics (oberts) / portals veins
  "rrqqqrrqaAaaAaqqaAaaAaqqaAaaAaqqqAAqqqAA",
  "rrqqqrrqAaaAaaqqAaaAaaqqAaaAaaqqqAAqqqAA",
  "rrqqqrrqaaAaaAaqaaAaaAaqaaAaaAaqqAAqqqAA",  // arcs tancant-se (base parabolica)
  "rrqqqrrqaAaaAaaqaAaaAaaqaAaaAaaqqAAqqqAA",
  "grqqqrrqqqqqqqqqqqqqqqqqqqqqqqqqqAAqqqAg",  // vorera: arbrat a cada cantonada
};

// Tile legend:
//  ' ' cel                             'x' creu del cim de la torre
//  'n' bulb daurat sota la creu         'y' teulada conica (faldó) de la torre
//  'v'/'V' escates teulada rosa (ala esquerra, clar/fosc)
//  'u'/'U' escates teulada blau/verd (gran cupula, clar/fosc)
//  't'/'T' escates teulada verda (ala dreta, clar/fosc)
//  'z'/'Z' cos de pedra de la torre (bandes clar/fosc)
//  'e' cornisa amb merlets ocres        'o' oculus / mascaro central
//  'm' trencadis (to daurat base)       'M' trencadis (pigall blau/verd)
//  'c' trencadis (pigall crema clar)    'q' ombra / escletxa mitgera
//  'f' marc d'os al voltant la finestra 'h' vidre de la finestra (blau)
//  'k' balco d'os (capsula, clar) / balustrada  'b' extrem fosc de la capsula d'os
//  'a'/'A' pedra de la planta baixa (clar/fosc)
//  'g' arbrat de vorera
//  --- Casa Amatller (veï esquerre) ---
//  'i'/'I' fronto esglaonat, teula (clar/fosc)  'p'/'P' esgrafiat rosat del mur (clar/fosc)
//  'l' vidre daurat de la finestra       'r' socol de pedra / portal
//  --- Edifici de l'Eixample (veí dret) ---
//  'B'/'C' parament clar/fosc del mur    'D' ràfec de pissarra

// Color palette, sampled from the real facade (reuses the shared ParkColor
// struct defined in tilemap_guell.h). Each textured surface (roof scales,
// trencadis, stone) now carries a light/dark pair so paintTile() can dither
// it into a two-tone pattern instead of a single flat fill.
const ParkColor BAT_PAL_VOID         = { 58,  143, 217 };  // cel
const ParkColor BAT_PAL_ROOF_PINK    = { 202, 146, 158 };  // teulada rosa/malva, clar
const ParkColor BAT_PAL_ROOF_PINK_D  = { 186, 126, 140 };  // teulada rosa/malva, fosc
const ParkColor BAT_PAL_ROOF_TEAL    = { 88,  151, 167 };  // gran cupula blau/verd, clar
const ParkColor BAT_PAL_ROOF_TEAL_D  = { 70,  127, 143 };  // gran cupula blau/verd, fosc
const ParkColor BAT_PAL_ROOF_GREEN   = { 100, 167, 110 };  // teulada verda (ala dreta), clar
const ParkColor BAT_PAL_ROOF_GREEN_D = { 82,  145, 94  };  // teulada verda (ala dreta), fosc
const ParkColor BAT_PAL_TOWER        = { 158, 148, 130 };  // pedra de la torre, clar
const ParkColor BAT_PAL_TOWER_D      = { 142, 132, 114 };  // pedra de la torre, fosc
const ParkColor BAT_PAL_CONE         = { 179, 87,  46  };  // teulada conica terracota (faldó)
const ParkColor BAT_PAL_ONION        = { 216, 178, 96  };  // bulb daurat sota la creu
const ParkColor BAT_PAL_CROSS        = { 232, 226, 208 };  // creu
const ParkColor BAT_PAL_CORNICE      = { 201, 143, 74  };  // merlets ocres sota l'ràfec
const ParkColor BAT_PAL_MOSAIC       = { 182, 162, 118 };  // trencadis, to daurat base
const ParkColor BAT_PAL_MOSAIC_TEAL  = { 130, 152, 140 };  // trencadis, pigall blau/verd
const ParkColor BAT_PAL_MOSAIC_CREAM = { 211, 198, 159 };  // trencadis, pigall crema
const ParkColor BAT_PAL_FRAME        = { 230, 224, 202 };  // marc d'os de la finestra
const ParkColor BAT_PAL_GLASS        = { 86,  132, 168 };  // vidre de la finestra (blau)
const ParkColor BAT_PAL_BONE         = { 215, 209, 192 };  // balco d'os, capsula clara / balustrada
const ParkColor BAT_PAL_BONE_SHADOW  = { 121, 109, 88  };  // balco d'os, extrem fosc
const ParkColor BAT_PAL_OCULUS       = { 224, 217, 196 };  // mascaro central
const ParkColor BAT_PAL_DIVIDER      = { 140, 120, 90  };  // cornisa divisoria (llegat, sense us directe)
const ParkColor BAT_PAL_STONE        = { 175, 162, 137 };  // pedra planta baixa, clar
const ParkColor BAT_PAL_STONE_D      = { 161, 149, 125 };  // pedra planta baixa, fosc
const ParkColor BAT_PAL_SHADOW       = { 60,  52,  42  };  // ombra dels arcs / escletxa mitgera
const ParkColor BAT_PAL_NEIGHBOR     = { 150, 60,  45  };  // llegat, sense us directe
const ParkColor BAT_PAL_TREE         = { 63,  122, 69  };  // arbrat
const ParkColor BAT_PAL_INK          = { 26,  22,  18  };  // contorn / detall fosc

// --- Nova paleta pels edificis veïns (Eixample) ---
const ParkColor BAT_PAL_AMA_GABLE    = { 203, 139, 115 };  // fronto esglaonat Amatller, teula clara
const ParkColor BAT_PAL_AMA_GABLE_D  = { 180, 115, 91  };  // fronto esglaonat Amatller, teula fosca
const ParkColor BAT_PAL_AMA_WALL     = { 228, 209, 192 };  // esgrafiat rosat, clar
const ParkColor BAT_PAL_AMA_WALL_D   = { 210, 186, 165 };  // esgrafiat rosat, fosc
const ParkColor BAT_PAL_AMA_GLASS    = { 207, 154, 78  };  // vidre daurat de la finestra veina
const ParkColor BAT_PAL_AMA_PLINTH   = { 140, 121, 95  };  // socol de pedra / portal veí esquerre
const ParkColor BAT_PAL_EIX_WALL     = { 219, 206, 174 };  // parament clar, edifici Eixample dret
const ParkColor BAT_PAL_EIX_WALL_D   = { 201, 187, 154 };  // parament fosc, edifici Eixample dret
const ParkColor BAT_PAL_EIX_ROOF     = { 109, 111, 116 };  // rafec de pissarra, edifici dret