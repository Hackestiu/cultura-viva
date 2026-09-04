#include "minimap.h"
#include "tilemap.h"
#include "ui_manager.h"
#include "../core/app_state.h"

bool visited[NUM_LANDMARKS] = { false };
int8_t lastVisitedId = -1;
bool hasLocation = false;
int16_t locX = 0, locY = 0;

static uint16_t C_VOID[2], C_BLOCK[2], C_BLOCKD[2], C_FORESTDD[2], C_FOREST[2], C_FORESTL[2],
                C_SCRUB[2], C_SCRUBL[2], C_PATH[2], C_PATHD[2], C_SAND[2], C_SANDD[2],
                C_STONE[2], C_STONED[2], C_ROOF[2], C_ROOFL[2], C_TILE[2], C_TILEL[2],
                C_ROCK[2], C_ROCKD[2];
static uint16_t C_INK, C_RING, C_UNVISITED, C_VISITED, C_LOCATION;

static uint8_t grayOf(const ParkColor& c) {
  return (uint8_t)(((uint16_t)c.r * 77 + (uint16_t)c.g * 151 + (uint16_t)c.b * 28) >> 8);
}

static void setPair(uint16_t out[2], const ParkColor& c) {
  out[0] = tft.color565(c.r, c.g, c.b);
  uint8_t g = grayOf(c);
  out[1] = tft.color565(g, g, g);
}

void initMinimapColors() {
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

  C_RING      = tft.color565(COLOR_RING[0], COLOR_RING[1], COLOR_RING[2]);
  C_UNVISITED = tft.color565(COLOR_UNVISITED[0], COLOR_UNVISITED[1], COLOR_UNVISITED[2]);
  C_VISITED   = tft.color565(COLOR_VISITED[0], COLOR_VISITED[1], COLOR_VISITED[2]);
  C_LOCATION  = tft.color565(COLOR_LOCATION[0], COLOR_LOCATION[1], COLOR_LOCATION[2]);
}

uint8_t nearestLandmarkId(int16_t x, int16_t y) {
  uint8_t best = 0;
  long dx0 = LANDMARKS[0].x - x, dy0 = LANDMARKS[0].y - y;
  long bestDist = dx0 * dx0 + dy0 * dy0;
  for (uint8_t i = 1; i < NUM_LANDMARKS; i++) {
    long dx = LANDMARKS[i].x - x, dy = LANDMARKS[i].y - y;
    long d = dx * dx + dy * dy;
    if (d < bestDist) { bestDist = d; best = i; }
  }
  return best;
}

static bool isRevealed(int16_t px, int16_t py) {
  return visited[nearestLandmarkId(px + 2, py + 2)];
}

static void paintTile(char ch, int16_t px, int16_t py, bool revealed) {
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
  for (uint8_t row = 0; row < MAP_ROW_COUNT; row++) {
    const char* rowPtr = MAP_ROWS[row];
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

static void drawMinimapStatusBar() {
  tft.fillRect(0, 112, 160, 16, C_INK);
  tft.drawFastHLine(0, 112, 160, C_BLOCKD[0]);

  uint8_t count = 0;
  for (uint8_t i = 0; i < NUM_LANDMARKS; i++) if (visited[i]) count++;

  tft.fillRect(3, 115, 11, 11, C_RING);
  tft.setTextSize(1);
  tft.setTextColor(C_INK);
  tft.setCursor(count < 10 ? 6 : 4, 118);
  tft.print(count);

  const char* label;
  if (hasLocation) {
    label = LANDMARKS[nearestLandmarkId(locX, locY)].screen;
  } else if (lastVisitedId >= 0) {
    label = LANDMARKS[lastVisitedId].screen;
  } else {
    label = "PARK GUELL";
  }
  tft.setTextColor(C_RING);
  tft.setCursor(19, 118);
  tft.print(label);
}

void drawParkMap() {
  drawTerrain();
  for (uint8_t i = 0; i < NUM_LANDMARKS; i++) {
    drawLandmarkPin(LANDMARKS[i], visited[i]);
  }
  drawLocationMarker();
  drawMinimapStatusBar();
}

void markVisited(uint8_t id) {
  if (id >= NUM_LANDMARKS) return;
  visited[id] = true;
  lastVisitedId = id;
  if (!viewSwitchDebounced) {
    drawParkMap();
    if (processingActive) {
      drawGeneratingAnswerOverlay(0, true);
    }
  }
}

void setLocation(int16_t x, int16_t y) {
  locX = constrain(x, 0, 159);
  locY = constrain(y, 0, 111);
  hasLocation = true;
  if (!viewSwitchDebounced) {
    drawParkMap();
    if (processingActive) {
      drawGeneratingAnswerOverlay(0, true);
    }
  }
}

void resetMinimapState() {
  for (uint8_t i = 0; i < NUM_LANDMARKS; i++) visited[i] = false;
  lastVisitedId = -1;
  hasLocation = false;
  if (!viewSwitchDebounced) {
    drawParkMap();
    if (processingActive) {
      drawGeneratingAnswerOverlay(0, true);
    }
  }
}

bool mark_landmark_visited(int id) {
  if (id < 0 || id >= NUM_LANDMARKS) return false;
  markVisited((uint8_t)id);
  return true;
}

bool set_location_by_id(int id) {
  if (id < 0 || id >= NUM_LANDMARKS) return false;
  setLocation(LANDMARKS[id].x, LANDMARKS[id].y);
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
