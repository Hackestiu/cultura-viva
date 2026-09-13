#include "minimap.h"
#include "tilemap_guell.h"
#include "tilemap_sagrada.h"
#include "tilemap_batllo.h"
#include "tilemap_mila.h"
#include "landmarks_sagrada.h"
#include "landmarks_batllo.h"
#include "landmarks_mila.h"
#include "ui_manager.h"
#include "../core/app_state.h"
#include "../input/controls.h"

// Active map: 0 = Park Guell, 1 = Sagrada Familia, 2 = Casa Batllo, 3 = Casa Mila
static uint8_t activeMapId = 1;

bool visited[NUM_LANDMARKS] = { false };
int8_t lastVisitedId = -1;
bool hasLocation = false;
int16_t locX = 0, locY = 0;

bool mapCompletionCelebrationActive = false;
unsigned long mapCompletionCelebrationStart = 0;
static bool mapCompletionNotified = false;

static uint16_t C_VOID[2], C_BLOCK[2], C_BLOCKD[2], C_FORESTDD[2], C_FOREST[2], C_FORESTL[2],
                C_SCRUB[2], C_SCRUBL[2], C_PATH[2], C_PATHD[2], C_SAND[2], C_SANDD[2],
                C_STONE[2], C_STONED[2], C_ROOF[2], C_ROOFL[2], C_TILE[2], C_TILEL[2],
                C_ROCK[2], C_ROCKD[2];
static uint16_t C_INK, C_RING, C_UNVISITED, C_VISITED, C_LOCATION;

static const Landmark* activeLandmarks() {
  if (activeMapId == 3) return LANDMARKS_MILA;
  if (activeMapId == 2) return LANDMARKS_BATLLO;
  if (activeMapId == 1) return LANDMARKS_SAGRADA;
  return LANDMARKS;
}

static uint8_t activeLandmarkCount() {
  if (activeMapId == 3) return NUM_LANDMARKS_MILA;
  if (activeMapId == 2) return NUM_LANDMARKS_BATLLO;
  if (activeMapId == 1) return NUM_LANDMARKS_SAGRADA;
  return NUM_LANDMARKS;
}

static const char* const* activeMapRows() {
  if (activeMapId == 3) return MAP_ROWS_MILA;
  if (activeMapId == 2) return MAP_ROWS_BATLLO;
  if (activeMapId == 1) return MAP_ROWS_SAGRADA;
  return MAP_ROWS;
}

static uint8_t activeMapRowCount() {
  if (activeMapId == 3) return MAP_ROW_COUNT_MILA;
  if (activeMapId == 2) return MAP_ROW_COUNT_BATLLO;
  if (activeMapId == 1) return MAP_ROW_COUNT_SAGRADA;
  return MAP_ROW_COUNT;
}

static uint8_t grayOf(const ParkColor& c) {
  return (uint8_t)(((uint16_t)c.r * 77 + (uint16_t)c.g * 151 + (uint16_t)c.b * 28) >> 8);
}

static void setPair(uint16_t out[2], const ParkColor& c) {
  out[0] = tft.color565(c.r, c.g, c.b);
  uint8_t g = grayOf(c);
  out[1] = tft.color565(g, g, g);
}

void initMinimapColors() {
  if (activeMapId == 3) {
    // Casa Milà palette — map the 10 shared C_* slots to facade tile colors
    setPair(C_VOID,    MILA_PAL_VOID);      // ' ' = sky
    setPair(C_BLOCK,   MILA_PAL_PARAPET);   // 'w' = wavy cornice
    setPair(C_BLOCKD,  MILA_PAL_OCULUS);    // 'o' = oculus window
    setPair(C_FOREST,  MILA_PAL_CHIMNEY);   // 'c' = chimney
    setPair(C_FORESTL, MILA_PAL_STONE);     // 's' = undulating stone facade
    setPair(C_FORESTDD,MILA_PAL_RECEDE);    // 'r' = receding wing stone
    setPair(C_SCRUB,   MILA_PAL_WINDOW);    // 'i' = window
    setPair(C_SCRUBL,  MILA_PAL_BALCONY);   // 'b' = wrought-iron balcony
    setPair(C_PATH,    MILA_PAL_DIVIDER);   // 'd' = floor cornice divider
    setPair(C_PATHD,   MILA_PAL_GROUND);    // 'a' = ground floor stone
    setPair(C_SAND,    MILA_PAL_PORTAL);    // 'p' = portal shadow
    setPair(C_SANDD,   MILA_PAL_NEIGHBOR);  // 'j' = neighbour building
    setPair(C_STONE,   MILA_PAL_TREE);      // 't' = street tree
    setPair(C_STONED,  MILA_PAL_SIDEWALK);  // 'g' = sidewalk
    setPair(C_ROOF,    MILA_PAL_LAMP);      // 'l' = lamp post
    C_INK      = tft.color565(MILA_PAL_INK.r,            MILA_PAL_INK.g,            MILA_PAL_INK.b);
    C_RING     = tft.color565(MILA_COLOR_RING[0],        MILA_COLOR_RING[1],        MILA_COLOR_RING[2]);
    C_UNVISITED= tft.color565(MILA_COLOR_UNVISITED[0],   MILA_COLOR_UNVISITED[1],   MILA_COLOR_UNVISITED[2]);
    C_VISITED  = tft.color565(MILA_COLOR_VISITED[0],     MILA_COLOR_VISITED[1],     MILA_COLOR_VISITED[2]);
    C_LOCATION = tft.color565(MILA_COLOR_LOCATION[0],    MILA_COLOR_LOCATION[1],    MILA_COLOR_LOCATION[2]);
    return;
  }
  if (activeMapId == 2) {
    // Casa Batlló palette: reuse the 10 shared C_* slots for the facade tiles
    setPair(C_VOID,    BAT_PAL_VOID);           // ' ' = sky
    setPair(C_BLOCK,   BAT_PAL_ROOF_TEAL);      // 'u' = cupula teal light
    setPair(C_BLOCKD,  BAT_PAL_ROOF_TEAL_D);    // 'U' = cupula teal dark
    setPair(C_FOREST,  BAT_PAL_ROOF_PINK);      // 'v' = left wing pink light
    setPair(C_FORESTL, BAT_PAL_ROOF_PINK_D);    // 'V' = left wing pink dark
    setPair(C_FORESTDD,BAT_PAL_ROOF_GREEN);     // 't' = right wing green light
    setPair(C_SCRUB,   BAT_PAL_ROOF_GREEN_D);   // 'T' = right wing green dark
    setPair(C_PATH,    BAT_PAL_TOWER);          // 'z' = tower stone light
    setPair(C_PATHD,   BAT_PAL_TOWER_D);        // 'Z' = tower stone dark
    setPair(C_SAND,    BAT_PAL_CORNICE);        // 'e' = cornice ochre
    setPair(C_SANDD,   BAT_PAL_MOSAIC);         // 'm' = trencadis gold
    setPair(C_STONE,   BAT_PAL_MOSAIC_TEAL);    // 'M' = trencadis teal dot
    setPair(C_STONED,  BAT_PAL_MOSAIC_CREAM);   // 'c' = trencadis cream dot
    setPair(C_ROOF,    BAT_PAL_FRAME);          // 'f' = bone window frame
    setPair(C_ROOFL,   BAT_PAL_GLASS);          // 'h' = blue window glass
    setPair(C_TILE,    BAT_PAL_BONE);           // 'k' = bone balcony / balustrade
    setPair(C_TILEL,   BAT_PAL_BONE_SHADOW);    // 'b' = bone balcony dark tip
    setPair(C_ROCK,    BAT_PAL_STONE);          // 'a' = ground floor stone light
    setPair(C_ROCKD,   BAT_PAL_STONE_D);        // 'A' = ground floor stone dark
    C_INK      = tft.color565(BAT_PAL_INK.r,          BAT_PAL_INK.g,          BAT_PAL_INK.b);
    C_RING     = tft.color565(BAT_COLOR_RING[0],      BAT_COLOR_RING[1],      BAT_COLOR_RING[2]);
    C_UNVISITED= tft.color565(BAT_COLOR_UNVISITED[0], BAT_COLOR_UNVISITED[1], BAT_COLOR_UNVISITED[2]);
    C_VISITED  = tft.color565(BAT_COLOR_VISITED[0],   BAT_COLOR_VISITED[1],   BAT_COLOR_VISITED[2]);
    C_LOCATION = tft.color565(BAT_COLOR_LOCATION[0],  BAT_COLOR_LOCATION[1],  BAT_COLOR_LOCATION[2]);
    return;
  }
  if (activeMapId == 0) {
    setPair(C_VOID, PAL_VOID);
    setPair(C_BLOCK, PAL_BLOCK);
    setPair(C_BLOCKD, PAL_BLOCK_D);
    setPair(C_FORESTDD, PAL_FOREST_DD);
    setPair(C_FOREST, PAL_FOREST);
    setPair(C_FORESTL, PAL_FOREST_L);
    setPair(C_SCRUB, PAL_SCRUB);
    setPair(C_SCRUBL, PAL_SCRUB_L);
    setPair(C_PATH, PAL_PATH);
    setPair(C_PATHD, PAL_PATH_D);
    setPair(C_SAND, PAL_SAND);
    setPair(C_SANDD, PAL_SAND_D);
    setPair(C_STONE, PAL_STONE);
    setPair(C_STONED, PAL_STONE_D);
    setPair(C_ROOF, PAL_ROOF);
    setPair(C_ROOFL, PAL_ROOF_L);
    setPair(C_TILE, PAL_TILE);
    setPair(C_TILEL, PAL_TILE_L);
    setPair(C_ROCK, PAL_ROCK);
    setPair(C_ROCKD, PAL_ROCK_D);
    C_INK = tft.color565(PAL_INK.r, PAL_INK.g, PAL_INK.b);
    C_RING = tft.color565(COLOR_RING[0], COLOR_RING[1], COLOR_RING[2]);
    C_UNVISITED = tft.color565(COLOR_UNVISITED[0], COLOR_UNVISITED[1], COLOR_UNVISITED[2]);
    C_VISITED = tft.color565(COLOR_VISITED[0], COLOR_VISITED[1], COLOR_VISITED[2]);
    C_LOCATION = tft.color565(COLOR_LOCATION[0], COLOR_LOCATION[1], COLOR_LOCATION[2]);
    return;
  }

  setPair(C_VOID, SAG_PAL_VOID);
  setPair(C_BLOCK, SAG_PAL_WALL_FILL);
  setPair(C_BLOCKD, SAG_PAL_WALL_EDGE);
  setPair(C_FORESTDD, SAG_PAL_TORRES);
  setPair(C_FOREST, SAG_PAL_TORRES);
  setPair(C_FORESTL, SAG_PAL_TORRES);
  setPair(C_SCRUB, SAG_PAL_SACRISTY);
  setPair(C_SCRUBL, SAG_PAL_SACRISTY);
  setPair(C_PATH, SAG_PAL_LATERAL);
  setPair(C_PATHD, SAG_PAL_LATERAL_L);
  setPair(C_SAND, SAG_PAL_CRUCERO);
  setPair(C_SANDD, SAG_PAL_CRUCERO_L);
  setPair(C_STONE, SAG_PAL_APSE);
  setPair(C_STONED, SAG_PAL_APSE_L);
  setPair(C_ROOF, SAG_PAL_NAVE);
  setPair(C_ROOFL, SAG_PAL_NAVE_L);
  setPair(C_TILE, SAG_PAL_SACRISTY);
  setPair(C_TILEL, SAG_PAL_SACRISTY_L);
  setPair(C_ROCK, SAG_PAL_PORCH);
  setPair(C_ROCKD, SAG_PAL_PORCH_L);
  C_INK = tft.color565(50, 40, 31);
  C_RING = tft.color565(SAG_COLOR_RING[0], SAG_COLOR_RING[1], SAG_COLOR_RING[2]);
  C_UNVISITED = tft.color565(SAG_COLOR_UNVISITED[0], SAG_COLOR_UNVISITED[1], SAG_COLOR_UNVISITED[2]);
  C_VISITED = tft.color565(SAG_COLOR_VISITED[0], SAG_COLOR_VISITED[1], SAG_COLOR_VISITED[2]);
  C_LOCATION = tft.color565(SAG_COLOR_LOCATION[0], SAG_COLOR_LOCATION[1], SAG_COLOR_LOCATION[2]);
}

uint8_t nearestLandmarkId(int16_t x, int16_t y) {
  const Landmark* landmarks = activeLandmarks();
  uint8_t landmarkCount = activeLandmarkCount();
  uint8_t best = 0;
  long dx0 = landmarks[0].x - x, dy0 = landmarks[0].y - y;
  long bestDist = dx0 * dx0 + dy0 * dy0;
  for (uint8_t i = 1; i < landmarkCount; i++) {
    long dx = landmarks[i].x - x, dy = landmarks[i].y - y;
    long d = dx * dx + dy * dy;
    if (d < bestDist) { bestDist = d; best = i; }
  }
  return best;
}

static bool isRevealed(int16_t px, int16_t py) {
  return visited[nearestLandmarkId(px + 2, py + 2)];
}

// Milà doesn't need extra bonus colors — all 15 tile chars fit in the 10 C_* slots.
// Batlló-specific colours for tiles that don't fit in the 10 shared C_ slots
static uint16_t BAT_C_SHADOW, BAT_C_CONE, BAT_C_ONION, BAT_C_CROSS, BAT_C_OCULUS;
static uint16_t BAT_C_AMA_GABLE, BAT_C_AMA_GABLE_D, BAT_C_AMA_WALL, BAT_C_AMA_WALL_D;
static uint16_t BAT_C_AMA_GLASS, BAT_C_AMA_PLINTH;
static uint16_t BAT_C_EIX_WALL, BAT_C_EIX_WALL_D, BAT_C_EIX_ROOF;
static uint16_t BAT_C_NEIGHBOR, BAT_C_TREE;

static void initBatlloBonusColors() {
  BAT_C_SHADOW    = tft.color565(BAT_PAL_SHADOW.r,       BAT_PAL_SHADOW.g,       BAT_PAL_SHADOW.b);
  BAT_C_CONE      = tft.color565(BAT_PAL_CONE.r,         BAT_PAL_CONE.g,         BAT_PAL_CONE.b);
  BAT_C_ONION     = tft.color565(BAT_PAL_ONION.r,        BAT_PAL_ONION.g,        BAT_PAL_ONION.b);
  BAT_C_CROSS     = tft.color565(BAT_PAL_CROSS.r,        BAT_PAL_CROSS.g,        BAT_PAL_CROSS.b);
  BAT_C_OCULUS    = tft.color565(BAT_PAL_OCULUS.r,       BAT_PAL_OCULUS.g,       BAT_PAL_OCULUS.b);
  BAT_C_AMA_GABLE = tft.color565(BAT_PAL_AMA_GABLE.r,   BAT_PAL_AMA_GABLE.g,   BAT_PAL_AMA_GABLE.b);
  BAT_C_AMA_GABLE_D=tft.color565(BAT_PAL_AMA_GABLE_D.r, BAT_PAL_AMA_GABLE_D.g, BAT_PAL_AMA_GABLE_D.b);
  BAT_C_AMA_WALL  = tft.color565(BAT_PAL_AMA_WALL.r,    BAT_PAL_AMA_WALL.g,    BAT_PAL_AMA_WALL.b);
  BAT_C_AMA_WALL_D= tft.color565(BAT_PAL_AMA_WALL_D.r,  BAT_PAL_AMA_WALL_D.g,  BAT_PAL_AMA_WALL_D.b);
  BAT_C_AMA_GLASS = tft.color565(BAT_PAL_AMA_GLASS.r,   BAT_PAL_AMA_GLASS.g,   BAT_PAL_AMA_GLASS.b);
  BAT_C_AMA_PLINTH= tft.color565(BAT_PAL_AMA_PLINTH.r,  BAT_PAL_AMA_PLINTH.g,  BAT_PAL_AMA_PLINTH.b);
  BAT_C_EIX_WALL  = tft.color565(BAT_PAL_EIX_WALL.r,    BAT_PAL_EIX_WALL.g,    BAT_PAL_EIX_WALL.b);
  BAT_C_EIX_WALL_D= tft.color565(BAT_PAL_EIX_WALL_D.r,  BAT_PAL_EIX_WALL_D.g,  BAT_PAL_EIX_WALL_D.b);
  BAT_C_EIX_ROOF  = tft.color565(BAT_PAL_EIX_ROOF.r,    BAT_PAL_EIX_ROOF.g,    BAT_PAL_EIX_ROOF.b);
  BAT_C_NEIGHBOR  = tft.color565(BAT_PAL_NEIGHBOR.r,     BAT_PAL_NEIGHBOR.g,     BAT_PAL_NEIGHBOR.b);
  BAT_C_TREE      = tft.color565(BAT_PAL_TREE.r,         BAT_PAL_TREE.g,         BAT_PAL_TREE.b);
}

static void paintTile(char ch, int16_t px, int16_t py, bool revealed) {
  if (activeMapId == 3) {
    // Casa Milà facade tileset — all chars map to C_* slots set in initMinimapColors
    uint8_t r = revealed ? 0 : 1;
    switch (ch) {
      case ' ': tft.fillRect(px,py,4,4,C_VOID[r]);     break;  // sky
      case 'w': tft.fillRect(px,py,4,4,C_BLOCK[r]);    break;  // wavy cornice
      case 'o': tft.fillRect(px,py,4,4,C_BLOCKD[r]);   break;  // oculus
      case 'c': tft.fillRect(px,py,4,4,C_FOREST[r]);   break;  // chimney
      case 's': tft.fillRect(px,py,4,4,C_FORESTL[r]);  break;  // stone facade
      case 'r': tft.fillRect(px,py,4,4,C_FORESTDD[r]); break;  // receding wing
      case 'i': tft.fillRect(px,py,4,4,C_SCRUB[r]);    break;  // window
      case 'b': tft.fillRect(px,py,4,4,C_SCRUBL[r]);   break;  // balcony iron
      case 'd': tft.fillRect(px,py,4,4,C_PATH[r]);     break;  // floor divider
      case 'a': tft.fillRect(px,py,4,4,C_PATHD[r]);    break;  // ground floor
      case 'p': tft.fillRect(px,py,4,4,C_SAND[r]);     break;  // portal shadow
      case 'j': tft.fillRect(px,py,4,4,C_SANDD[r]);    break;  // neighbour
      case 't': tft.fillRect(px,py,4,4,C_STONE[r]);    break;  // tree
      case 'g': tft.fillRect(px,py,4,4,C_STONED[r]);   break;  // sidewalk
      case 'l': tft.fillRect(px,py,4,4,C_ROOF[r]);     break;  // lamp post
      default:  tft.fillRect(px,py,4,4,C_VOID[r]);     break;
    }
    return;
  }
  if (activeMapId == 2) {
    // Casa Batlló facade tileset
    // Unrevealed tiles are greyed out using [1] palette entries (desaturated).
    uint8_t r = revealed ? 0 : 1;
    switch (ch) {
      // Sky
      case ' ': tft.fillRect(px,py,4,4,C_VOID[r]); break;
      // Tower / cross / onion
      case 'x': tft.fillRect(px,py,4,4,revealed ? BAT_C_CROSS   : C_VOID[1]); break;
      case 'n': tft.fillRect(px,py,4,4,revealed ? BAT_C_ONION   : C_VOID[1]); break;
      case 'y': tft.fillRect(px,py,4,4,revealed ? BAT_C_CONE    : C_VOID[1]); break;
      case 'z': tft.fillRect(px,py,4,4,C_PATH[r]);  break;  // tower stone light
      case 'Z': tft.fillRect(px,py,4,4,C_PATHD[r]); break;  // tower stone dark
      // Roof scales left wing (pink)
      case 'v': tft.fillRect(px,py,4,4,C_FOREST[r]);  break;
      case 'V': tft.fillRect(px,py,4,4,C_FORESTL[r]); break;
      // Roof scales main cupola (teal)
      case 'u': tft.fillRect(px,py,4,4,C_BLOCK[r]);  break;
      case 'U': tft.fillRect(px,py,4,4,C_BLOCKD[r]); break;
      // Roof scales right wing (green)
      case 't': tft.fillRect(px,py,4,4,C_FORESTDD[r]); break;
      case 'T': tft.fillRect(px,py,4,4,C_SCRUB[r]);    break;
      // Cornice
      case 'e': tft.fillRect(px,py,4,4,C_SAND[r]); break;
      // Trencadis mosaic
      case 'm': tft.fillRect(px,py,4,4,C_SANDD[r]); break;
      case 'M': tft.fillRect(px,py,4,4,C_STONE[r]); break;
      case 'c': tft.fillRect(px,py,4,4,C_STONED[r]); break;
      // Windows / bone
      case 'f': tft.fillRect(px,py,4,4,C_ROOF[r]);  break;  // bone frame
      case 'h': tft.fillRect(px,py,4,4,C_ROOFL[r]); break;  // blue glass
      case 'k': tft.fillRect(px,py,4,4,C_TILE[r]);  break;  // bone balcony / balustrade
      case 'b': tft.fillRect(px,py,4,4,C_TILEL[r]); break;  // balcony dark tip
      case 'o': tft.fillRect(px,py,4,4,revealed ? BAT_C_OCULUS : C_VOID[1]); break;  // oculus
      // Ground floor stone
      case 'a': tft.fillRect(px,py,4,4,C_ROCK[r]);  break;
      case 'A': tft.fillRect(px,py,4,4,C_ROCKD[r]); break;
      // Shadow / party wall
      case 'q': tft.fillRect(px,py,4,4,revealed ? BAT_C_SHADOW : C_VOID[1]); break;
      // Street trees
      case 'g': tft.fillRect(px,py,4,4,revealed ? BAT_C_TREE : C_VOID[1]); break;
      // Amatller neighbour (left)
      case 'i': tft.fillRect(px,py,4,4,revealed ? BAT_C_AMA_GABLE   : C_VOID[1]); break;
      case 'I': tft.fillRect(px,py,4,4,revealed ? BAT_C_AMA_GABLE_D : C_VOID[1]); break;
      case 'p': tft.fillRect(px,py,4,4,revealed ? BAT_C_AMA_WALL    : C_VOID[1]); break;
      case 'P': tft.fillRect(px,py,4,4,revealed ? BAT_C_AMA_WALL_D  : C_VOID[1]); break;
      case 'l': tft.fillRect(px,py,4,4,revealed ? BAT_C_AMA_GLASS   : C_VOID[1]); break;
      case 'r': tft.fillRect(px,py,4,4,revealed ? BAT_C_AMA_PLINTH  : C_VOID[1]); break;
      // Eixample neighbour (right)
      case 'B': tft.fillRect(px,py,4,4,revealed ? BAT_C_EIX_WALL   : C_VOID[1]); break;
      case 'C': tft.fillRect(px,py,4,4,revealed ? BAT_C_EIX_WALL_D : C_VOID[1]); break;
      case 'D': tft.fillRect(px,py,4,4,revealed ? BAT_C_EIX_ROOF   : C_VOID[1]); break;
      default:  tft.fillRect(px,py,4,4,C_VOID[r]); break;
    }
    return;
  }
  if (activeMapId == 1) {
    uint8_t r = revealed ? 0 : 1;
    switch (ch) {
      case '#': tft.fillRect(px, py, 4, 4, C_BLOCK[r]); break;
      case 'w': tft.fillRect(px, py, 4, 4, C_BLOCK[r]); break;
      case 'a': tft.fillRect(px, py, 4, 4, C_STONE[r]); break;
      case 'y': tft.fillRect(px, py, 4, 4, C_TILE[r]); break;
      case 'x': tft.fillRect(px, py, 4, 4, C_SAND[r]); break;
      case 't': tft.fillRect(px, py, 4, 4, C_FOREST[r]); break;
      case 'n': tft.fillRect(px, py, 4, 4, C_ROOF[r]); break;
      case 'l': tft.fillRect(px, py, 4, 4, C_PATH[r]); break;
      case 'c': tft.fillRect(px, py, 4, 4, C_ROCK[r]); break;
      default: tft.fillRect(px, py, 4, 4, C_VOID[r]); break;
    }
    return;
  }
  // activeMapId == 0: Park Guell
  uint8_t r = revealed ? 0 : 1;

  switch (ch) {
    case ' ':
      tft.fillRect(px, py, 4, 4, C_VOID[r]);
      tft.drawPixel(px, py, C_BLOCKD[r]);
      tft.drawPixel(px + 2, py + 2, C_BLOCKD[r]);
      break;
    case '#':
      tft.fillRect(px, py, 4, 4, C_BLOCK[r]);
      tft.drawPixel(px, py, C_BLOCKD[r]);
      tft.drawPixel(px + 1, py, C_BLOCKD[r]);
      tft.drawPixel(px + 2, py, C_BLOCKD[r]);
      tft.drawPixel(px + 3, py, C_BLOCKD[r]);
      tft.drawPixel(px, py + 3, C_BLOCKD[r]);
      tft.drawPixel(px + 3, py + 3, C_BLOCKD[r]);
      break;
    case 'F':
      tft.fillRect(px, py, 4, 4, C_FORESTDD[r]);
      tft.drawPixel(px + 1, py, C_FOREST[r]);
      tft.drawPixel(px + 2, py + 1, C_FOREST[r]);
      tft.drawPixel(px, py + 2, C_FOREST[r]);
      tft.drawPixel(px + 3, py + 2, C_FOREST[r]);
      tft.drawPixel(px + 1, py + 3, C_FOREST[r]);
      break;
    case 'f':
      tft.fillRect(px, py, 4, 4, C_FOREST[r]);
      tft.drawPixel(px, py + 1, C_FORESTL[r]);
      tft.drawPixel(px + 2, py, C_FORESTL[r]);
      tft.drawPixel(px + 3, py + 2, C_FORESTL[r]);
      tft.drawPixel(px + 1, py + 3, C_FORESTL[r]);
      break;
    case 'g':
      tft.fillRect(px, py, 4, 4, C_SCRUB[r]);
      tft.drawPixel(px, py, C_SCRUBL[r]);
      tft.drawPixel(px + 2, py + 1, C_SCRUBL[r]);
      tft.drawPixel(px + 1, py + 2, C_SCRUBL[r]);
      tft.drawPixel(px + 3, py + 3, C_SCRUBL[r]);
      break;
    case 'p':
      tft.fillRect(px, py, 4, 4, C_PATH[r]);
      tft.drawPixel(px + 1, py + 1, C_PATHD[r]);
      tft.drawPixel(px + 3, py + 2, C_PATHD[r]);
      break;
    case 'S':
      tft.fillRect(px, py, 4, 4, C_SAND[r]);
      tft.drawPixel(px, py + 2, C_SANDD[r]);
      tft.drawPixel(px + 2, py, C_SANDD[r]);
      break;
    case 'w':
      tft.fillRect(px, py, 4, 4, C_STONE[r]);
      tft.drawPixel(px, py, C_STONED[r]);
      tft.drawPixel(px + 1, py, C_STONED[r]);
      tft.drawPixel(px + 2, py, C_STONED[r]);
      tft.drawPixel(px + 3, py, C_STONED[r]);
      tft.drawPixel(px, py + 2, C_STONED[r]);
      tft.drawPixel(px + 1, py + 2, C_STONED[r]);
      tft.drawPixel(px + 2, py + 2, C_STONED[r]);
      tft.drawPixel(px + 3, py + 2, C_STONED[r]);
      break;
    case 'b':
      tft.fillRect(px, py, 4, 4, C_ROOF[r]);
      tft.drawPixel(px, py, C_ROOFL[r]);
      tft.drawPixel(px + 1, py, C_ROOFL[r]);
      tft.drawPixel(px + 2, py, C_ROOFL[r]);
      tft.drawPixel(px + 3, py, C_ROOFL[r]);
      break;
    case 'c':
      tft.fillRect(px, py, 4, 4, C_TILE[r]);
      tft.drawPixel(px, py, C_TILEL[r]);
      tft.drawPixel(px + 2, py + 1, C_TILEL[r]);
      tft.drawPixel(px + 1, py + 2, C_TILEL[r]);
      tft.drawPixel(px + 3, py + 3, C_TILEL[r]);
      break;
    case 'r':
      tft.fillRect(px, py, 4, 4, C_ROCK[r]);
      tft.drawPixel(px, py + 3, C_ROCKD[r]);
      tft.drawPixel(px + 1, py + 3, C_ROCKD[r]);
      tft.drawPixel(px + 3, py + 1, C_ROCKD[r]);
      break;
    default:
      tft.fillRect(px, py, 4, 4, C_VOID[r]);
      break;
  }
}

static void drawTerrain() {
  const char* const* mapRows = activeMapRows();
  for (uint8_t row = 0; row < activeMapRowCount(); row++) {
    const char* rowPtr = mapRows[row];
    for (uint8_t col = 0; col < MAP_COL_COUNT; col++) {
      char ch = rowPtr[col];
      int16_t px = col * 4, py = row * 4;
      paintTile(ch, px, py, isRevealed(px, py));
    }
  }
}

static void drawLandmarkPin(const Landmark& lm, bool isVisited) {
  uint16_t dot = isVisited ? C_VISITED : C_UNVISITED;
  tft.fillCircle(lm.x, lm.y, 4, C_RING);
  tft.drawCircle(lm.x, lm.y, 4, C_INK);
  tft.fillCircle(lm.x, lm.y, 2, dot);
}

static void drawLocationMarker() {
  if (!hasLocation) return;
  tft.fillCircle(locX, locY, 2, C_LOCATION);
  tft.drawCircle(locX, locY, 5, C_LOCATION);
}

uint8_t getActiveLandmarkTotal() {
  return activeLandmarkCount();
}

uint8_t getVisitedLandmarkCount() {
  uint8_t count = 0;
  uint8_t total = activeLandmarkCount();
  for (uint8_t i = 0; i < total; i++) {
    if (visited[i]) count++;
  }
  return count;
}

bool isMapCompleted() {
  uint8_t total = activeLandmarkCount();
  if (total == 0) return false;
  for (uint8_t i = 0; i < total; i++) {
    if (!visited[i]) return false;
  }
  return true;
}

void drawMapCompletedOverlay() {
  const int16_t x = 8;
  const int16_t y = 14;
  const int16_t w = 144;
  const int16_t h = 88;

  // Solid dark container
  tft.fillRoundRect(x, y, w, h, 6, 0x0000);
  // Double gold accent border
  tft.drawRoundRect(x, y, w, h, 6, 0xFFE0);
  tft.drawRoundRect(x + 1, y + 1, w - 2, h - 2, 5, 0xFFE0);

  // Top banner (gold background, dark text)
  tft.fillRoundRect(x + 4, y + 4, w - 8, 16, 3, 0xFFE0);
  tft.setTextSize(1);
  tft.setTextColor(0x0000); // Black text
  tft.setCursor(x + 14, y + 8);
  tft.print(F("COMPLETED MAP!"));

  // Subtitle / congratulations
  tft.setTextColor(0xFFFF); // White
  tft.setCursor(x + 38, y + 26);
  tft.print(F("Congratulations!"));

  // Message body
  tft.setTextColor(tft.color565(255, 215, 60)); // Warm gold
  tft.setCursor(x + 12, y + 40);
  tft.print(F("You have discovered all the"));
  tft.setCursor(x + 20, y + 51);
  tft.print(F("landmarks!"));

  // Badge capsule at the bottom
  uint8_t count = getVisitedLandmarkCount();
  uint8_t total = getActiveLandmarkTotal();
  tft.fillRoundRect(x + 16, y + 66, w - 32, 14, 3, tft.color565(20, 60, 30));
  tft.drawRoundRect(x + 16, y + 66, w - 32, 14, 3, 0x07E0);
  tft.setTextColor(0x07E0); // Bright green
  tft.setCursor(x + 22, y + 69);
  tft.print(F("[ "));
  tft.print(count);
  tft.print(F("/"));
  tft.print(total);
  tft.print(F(" Discovered ]"));
}

static void drawMinimapStatusBar() {
  tft.fillRect(0, 112, 160, 16, C_INK);
  tft.drawFastHLine(0, 112, 160, C_BLOCKD[0]);

  uint8_t count = getVisitedLandmarkCount();
  uint8_t total = getActiveLandmarkTotal();
  const Landmark* landmarks = activeLandmarks();

  bool completed = (count >= total && total > 0);

  if (completed) {
    // Golden celebration badge for counter
    tft.fillRect(3, 115, 11, 11, 0xFFE0);
    tft.setTextSize(1);
    tft.setTextColor(0x0000); // Black text on gold
    tft.setCursor(count < 10 ? 6 : 4, 118);
    tft.print(count);

    // Celebration status text
    tft.setTextColor(0xFFE0);
    tft.setCursor(19, 118);
    tft.print(F("COMPLETED MAP!"));
  } else {
    tft.fillRect(3, 115, 11, 11, C_RING);
    tft.setTextSize(1);
    tft.setTextColor(C_INK);
    tft.setCursor(count < 10 ? 6 : 4, 118);
    tft.print(count);

    const char* label;
    if (hasLocation) {
      label = landmarks[nearestLandmarkId(locX, locY)].screen;
    } else if (lastVisitedId >= 0) {
      label = landmarks[lastVisitedId].screen;
    } else {
      if (activeMapId == 3)      label = "CASA MILA";
      else if (activeMapId == 2) label = "CASA BATLLO";
      else if (activeMapId == 1) label = "SAGRADA FAMILIA";
      else                       label = "PARK GUELL";
    }
    tft.setTextColor(C_RING);
    tft.setCursor(19, 118);
    tft.print(label);
  }
}

void drawParkMap() {
  const Landmark* landmarks = activeLandmarks();
  uint8_t landmarkCount = activeLandmarkCount();
  drawTerrain();
  for (uint8_t i = 0; i < landmarkCount; i++) {
    drawLandmarkPin(landmarks[i], visited[i]);
  }
  drawLocationMarker();
  drawMinimapStatusBar();
  if (mapCompletionCelebrationActive) {
    drawMapCompletedOverlay();
  }
}

void markVisited(uint8_t id) {
  if (id >= activeLandmarkCount()) return;
  visited[id] = true;
  if (activeMapId == 1 && (id == LINKED_LATERALS[0] || id == LINKED_LATERALS[1])) {
    visited[LINKED_LATERALS[0]] = true;
    visited[LINKED_LATERALS[1]] = true;
  }
  lastVisitedId = id;

  bool wasCompleted = isMapCompleted();
  if (wasCompleted && !mapCompletionNotified) {
    mapCompletionNotified = true;
    mapCompletionCelebrationActive = true;
    mapCompletionCelebrationStart = millis();

    // Celebratory victory fanfare on Modulino Buzzer
    buzzer.tone(1318, 90); delay(95);
    buzzer.tone(1567, 90); delay(95);
    buzzer.tone(2093, 110); delay(115);
    buzzer.tone(2637, 250);
  }

  if (!viewSwitchDebounced) {
    drawParkMap();
    UiOverlayType overlay = getCurrentOverlayType();
    if (overlay != UI_OVERLAY_NONE) {
      drawAssistantOverlay(overlay, 0, true);
    }
    if (volumeOverlayVisible) {
      drawVolumeBar(currentVolume);
    }
  }
}

void setLocation(int16_t x, int16_t y) {
  locX = constrain(x, 0, 159);
  locY = constrain(y, 0, 111);
  hasLocation = true;
  if (!viewSwitchDebounced) {
    drawParkMap();
    UiOverlayType overlay = getCurrentOverlayType();
    if (overlay != UI_OVERLAY_NONE) {
      drawAssistantOverlay(overlay, 0, true);
    }
    if (volumeOverlayVisible) {
      drawVolumeBar(currentVolume);
    }
  }
}

void resetMinimapState() {
  uint8_t total = activeLandmarkCount();
  for (uint8_t i = 0; i < total; i++) visited[i] = false;
  lastVisitedId = -1;
  hasLocation = false;
  mapCompletionNotified = false;
  mapCompletionCelebrationActive = false;
  if (!viewSwitchDebounced) {
    drawParkMap();
    UiOverlayType overlay = getCurrentOverlayType();
    if (overlay != UI_OVERLAY_NONE) {
      drawAssistantOverlay(overlay, 0, true);
    }
    if (volumeOverlayVisible) {
      drawVolumeBar(currentVolume);
    }
  }
}

bool set_minimap_location(int location) {
  if (location < 0 || location > 3) return false;
  if ((uint8_t)location == activeMapId) return true;
  activeMapId = (uint8_t)location;
  mapCompletionNotified = false;
  mapCompletionCelebrationActive = false;
  if (activeMapId == 2) initBatlloBonusColors();
  initMinimapColors();
  resetMinimapState();
  return true;
}

bool mark_landmark_visited(int id) {
  if (id < 0 || id >= activeLandmarkCount()) return false;
  markVisited((uint8_t)id);
  return true;
}

bool set_location_by_id(int id) {
  if (id < 0 || id >= activeLandmarkCount()) return false;
  setLocation(activeLandmarks()[id].x, activeLandmarks()[id].y);
  return true;
}

bool set_location_xy(int x, int y) {
  setLocation((int16_t)x, (int16_t)y);
  return true;
}

bool reset_minimap() {
  resetMinimapState();
  return true;
}

bool is_map_completed() {
  return isMapCompleted();
}
