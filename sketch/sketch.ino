/*
  PROJECTE PERSONALITAT — Arduino UNO Q
  =======================================
  - LCD TFT ST7735S (128x160 SPI, 1.8", nomes 3.3V)
  - Modulino Knob (potenciometre, encara sense us assignat)
  - Modulino Buttons (A/B/C, click curt) -> trien la PERSONALITAT
    (ARTISTIC/TECHNICAL/CHILD -- veure python/model_module.py). Es
    poden prémer independentment del mode (switch D6).
  - Boto extern D7 -> el seu comportament depen del switch D6:
      ON  (mode ENFOCAR/camera): click -> fa una FOTO (webcam Brio
           105, 1080p, processada pel costat Python)
      OFF (mode MINIMAPA): click en TOGGLE -> grava la pregunta de
           l'usuari (1r click comença, 2n click para -- no cal
           mantenir-lo premut; veure is_recording_active() mes avall
           i python/microphone_module.py)
  - GPS (NEO-6M, per Serial1 + TinyGPSPlus) -> NOMES per triar
    automaticament la Ubicacio entre dos punts fixos coneguts (Park
    Güell i la Sagrada Família), per proximitat -- es tria la mes
    propera a la posicio actual. Aquest sketch NOMES exposa el fix
    (has_gps_fix/get_gps_lat/get_gps_lon) -- el calcul de "quin dels
    dos es mes proper" es fa a Python (veure location_module.py), que
    es on viuen les coordenades de referencia dels dos llocs. La LCD
    (minimapa, switch OFF) continua mostrant NOMES Park Güell -- no
    tenim encara dades de tile-map/landmarks per la Sagrada Família;
    la Ubicacio triada pel GPS s'usa nomes per la pipeline de Cultura
    Viva (quin classificador de visio / graf de coneixement fer
    servir), no per canviar la pantalla.
  - Modulino Buzzer -> so curt en arrencar, so de "clic" quan una FOTO
    s'ha desat correctament (confirmat pel costat Python), i sons
    curts en començar/parar una gravacio de pregunta.
  - Switch D6 -> a mes de triar el mode de D7 (veure a dalt), tambe
    tria que es mostra a la LCD: OFF -> minimapa de Park Güell (veure
    python/minimapa/minimap_module.py), ON -> vista de la webcam
    rebuda per PAQUETS (veure recepcio de fotogrames mes avall).

  MINIMAPA (Park Güell): landmarks.h i tilemap.h (aquesta mateixa
  carpeta) contenen el terreny i els punts d'interes -- son el mirall
  en C++ de python/minimapa/landmarks.json (font de veritat). El
  costat Python NO parla per port serie per aixo (a diferencia de la
  versio standalone original d'aquest sketch): fa servir el mateix
  Bridge RPC que la resta del projecte, cridant mark_landmark_visited/
  set_location_by_id/set_location_xy/reset_minimap (veure
  python/minimapa/minimap_module.py).

  NOTES IMPORTANTS D'AQUEST CORE (arduino:zephyr, UNO Q):
  - El connector Qwiic va per Wire1, NO per Wire.
  - Cal Modulino.begin(Wire1) explicit abans de knob/buttons/buzzer.begin(),
    o es pengen indefinidament.
  - LCD: INITR_GREENTAB (BLACKTAB sortia desplaçat en aquest panell).
  - Arduino_RouterBridge ja ve inclosa a la plataforma, no cal sketch.yaml.
  - D12 NO es pot fer servir com a GPIO lliure: es el MISO de l'SPI
    de maquinari que ja fa servir la LCD.
  - tilemap.h NO fa servir PROGMEM/pgm_read_* (son macros AVR-especifiques
    que poden no existir en aquest core) -- el mapa viu en RAM normal,
    de sobres per aquesta placa.
  - El struct de color es diu ParkColor, no RGB -- "RGB" xocava amb un
    tipus/macro ja definit per la plataforma (probablement
    Arduino_LTR381RGB).
  - GPS: cal afegir la llibreria TinyGPSPlus a sketch.yaml (veure
    fitxer a part) -- verifica el numero de versio disponible amb
    "arduino-cli lib search TinyGPSPlus" al teu entorn, ja que
    sketch.yaml exigeix versio explicita entre parentesis.
  - GPS: aquest sketch fa servir Serial1 pel modul NEO-6M a 9600 baud
    (baud rate estandard d'aquest modul). Comprova al pinout de la UNO
    Q quins pins fisics corresponen a Serial1 al teu core -- no son
    seleccionables per software.
*/

#include <Arduino_RouterBridge.h>
#include <SPI.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ST7735.h>
#include <Arduino_Modulino.h>
#include <TinyGPSPlus.h>
#include "landmarks.h"
#include "tilemap.h"
#include "ui_screens.h"

// ---------- Pins LCD (SPI per maquinari) ----------
#define TFT_CS   10
#define TFT_DC    8
#define TFT_RST   9
#define TFT_BL    5   // Backlight

Adafruit_ST7735 tft = Adafruit_ST7735(TFT_CS, TFT_DC, TFT_RST);

// ---------- Botó extern (foto) ----------
#define EXT_BUTTON_PIN 7

// ---------- Switch (minimapa / vista camera) ----------
#define VIEW_SWITCH_PIN 6
// D12 NO es fa servir: sol ser el MISO del bus SPI de maquinari, que
// la LCD ja ocupa per sota -- per aixo no funcionava com a switch.
// LOW (connectat a GND via pull-up) = "off" = minimapa
// HIGH (obert) = "on" = vista de la camera
// Si en la teva placa el switch fisic fa el contrari, nomes cal
// invertir aquesta condicio (canviar == LOW per == HIGH) mes avall.

// ---------- Modulinos (Qwiic / I2C -> Wire1) ----------
ModulinoKnob    knob;
ModulinoButtons buttons;
ModulinoBuzzer  buzzer;

// ---------- GPS (NEO-6M per Serial1 + TinyGPSPlus) ----------
// Nomes per triar la Ubicacio (Park Güell / Sagrada Família) per
// proximitat -- el calcul de quina es mes propera es fa a Python
// (location_module.py), aqui nomes exposem el fix cru per RPC.
TinyGPSPlus gps;
#define GPS_BAUD 9600

bool has_gps_fix() {
  return gps.location.isValid();
}

float get_gps_lat() {
  return gps.location.isValid() ? (float)gps.location.lat() : 0.0f;
}

float get_gps_lon() {
  return gps.location.isValid() ? (float)gps.location.lng() : 0.0f;
}

// ---------- Estat pel debounce del boto extern ----------
bool lastExtBtnState = false;

// ---------- Filtre pel Modulino Knob ----------
// El knob de vegades fa salts espuris grans (p.ex. 0 -> -112) per un
// glitch de lectura I2C. Rebutgem salts mes grans que KNOB_MAX_JUMP en
// una sola lectura -- si veus que et talla girades rapides legitimes,
// puja aquest valor.
const int16_t KNOB_MAX_JUMP = 15;
int16_t knobFiltered = 0;
bool knobFilteredInit = false;

int16_t readKnobFiltered() {
  int16_t raw = knob.get();
  if (!knobFilteredInit) {
    knobFiltered = raw;
    knobFilteredInit = true;
    return knobFiltered;
  }
  int16_t diff = raw - knobFiltered;
  if (diff > KNOB_MAX_JUMP || diff < -KNOB_MAX_JUMP) {
    // Salt sospitos -- el descartem, mantenim l'ultim valor bo
    return knobFiltered;
  }
  knobFiltered = raw;
  return knobFiltered;
}

// ---------- Modulino Knob: Volum dels auriculars (0 - 100%) ----------
int16_t currentVolume = 70;
int16_t lastKnobPos = 0;
bool knobVolumeInit = false;

int get_volume() {
  return (int)currentVolume;
}

// ---------- UI State Machine ----------
// UI_BOOT_INTRO  : Logo displayed, blinking "PRESS ANY BUTTON" prompt
// UI_OPTIONS     : "Get Started" screen -- [A] Tutorial or [C] Skip
// UI_TUTORIAL_1  : Controls page (Switch / Push button / Knob)
// UI_TUTORIAL_2  : How it works (3 steps)
// UI_TUTORIAL_3  : Personality intro
// UI_VOICE_SELECT: Personality selection (A/B/C)
// UI_ACTIVE      : Full normal app mode
enum AppUiState {
  UI_BOOT_INTRO,
  UI_OPTIONS,
  UI_TUTORIAL_1,
  UI_TUTORIAL_2,
  UI_TUTORIAL_3,
  UI_VOICE_SELECT,
  UI_ACTIVE
};

AppUiState currentUiState = UI_BOOT_INTRO;

// ---------- Botons A/B/C: seleccio de Personalitat (click curt) ----------
// Nomes s'actualitzen dins loop() (unica funcio que toca I2C per
// aquests); les funcions RPC nomes LLEGEIXEN aquestes variables, mai
// criden buttons.update()/isPressed() elles mateixes -- aixi evitem
// accedir a l'I2C des del context de la crida RPC.
//
// A diferencia de la versio anterior (boto MANTINGUT premut = gravar
// amb aquell model), ara A/B/C nomes SELECCIONEN la Personalitat
// (index 0/1/2) amb un click curt, independentment del mode (switch
// D6) -- la Ubicacio ja no es tria amb botons, ve del GPS (veure mes
// amunt).
bool btnAHeld = false, btnBHeld = false, btnCHeld = false;
bool btnAHeldPrev = false, btnBHeldPrev = false, btnCHeldPrev = false;

uint8_t personalityIndex = 0;   // 0=A, 1=B, 2=C -- veure python/model_module.py

uint8_t get_personality_index() {
  return personalityIndex;
}

// ---------- Boto D7 en mode MINIMAPA: gravar en TOGGLE (no cal mantenir) ----------
// 1r click -> comença a gravar (recordingActive = true)
// 2n click -> para de gravar (recordingActive = false)
// Python llegeix aquest estat cada iteracio del seu bucle amb
// is_recording_active() (el mateix patro que abans feia servir amb
// "boto mantingut", nomes que ara la font de veritat es aquest toggle
// en lloc de "esta el boto fisicament premut ara mateix").
bool recordingActive = false;

bool is_recording_active() {
  return recordingActive;
}

// ---------- Flag de foto (boto D7, nomes en mode ENFOCAR/camera) ----------
bool photoTriggerFlag = false;  // consumit pel costat Python (fa la foto)

bool photo_trigger() {
  bool result = photoTriggerFlag;
  photoTriggerFlag = false;
  return result;
}

// Cridat per Python DESPRES de desar la foto correctament -- nomes
// llavors sona el buzzer (no en prémer el boto), per confirmar que la
// foto s'ha fet de veritat.
bool playShutterSoundFlag = false;

void confirm_photo_saved() {
  playShutterSoundFlag = true;
}

// ---------- Switch D6: estat debounced ----------
// Un interruptor mecanic sol "rebotar" uns mil·lisegons en commutar --
// sense aixo es podien disparar canvis de pantalla/RPC espuris.
// S'actualitza nomes al loop(); tothom (LCD i aquesta funcio RPC)
// llegeix aquesta variable, mai un digitalRead() directe.
bool viewSwitchDebounced = true;
bool viewSwitchRawLast = true;
unsigned long viewSwitchLastChangeTime = 0;
const unsigned long VIEW_SWITCH_DEBOUNCE_MS = 50;

bool view_switch_state() {
  return viewSwitchDebounced;
}

// ---------- Recepcio de la vista de camera, PER PAQUETS ----------
// El canal RPC te un limit de mida per missatge que, en proves, s'ha
// vist que salta ja amb miniatures relativament petites (32x24 en un
// sol missatge falla amb "message size exceeds the limit"). En lloc de
// lluitar contra aquest limit reduint la imatge, la trossegem: el
// costat Python envia la miniatura sencera com una serie de xecs
// petits i consecutius (receive_camera_chunk), cadascun molt per sota
// del limit, i aqui els anem encaixant en un buffer fins tenir-los
// tots.
//
// IMPORTANT: CAM_THUMB_W/CAM_THUMB_H/CAM_CHUNK_PIXELS han de coincidir
// EXACTAMENT amb els mateixos noms a python/config.py.
#define CAM_THUMB_W 48
#define CAM_THUMB_H 36
#define CAM_CHUNK_PIXELS 72  // mida de xec conservadora (~96B/xec en cru)
#define CAM_TOTAL_PIXELS (CAM_THUMB_W * CAM_THUMB_H)
#define CAM_TOTAL_CHUNKS ((CAM_TOTAL_PIXELS + CAM_CHUNK_PIXELS - 1) / CAM_CHUNK_PIXELS)

uint8_t camFrameBuf[CAM_TOTAL_PIXELS * 2];  // RGB565 = 2 bytes/pixel
int camExpectedChunk = 0;
unsigned long camLastChunkMillis = 0;
const unsigned long CAM_CHUNK_TIMEOUT_MS = 3000;  // si triga mes, descartem el frame a mitges
bool newCameraFrameFlag = false;

// Decodificador base64 minim (evitem afegir una llibreria extra nomes
// per aixo). Ignora salts de linia/padding, no valida estrictament.
int base64Value(char c) {
  if (c >= 'A' && c <= 'Z') return c - 'A';
  if (c >= 'a' && c <= 'z') return c - 'a' + 26;
  if (c >= '0' && c <= '9') return c - '0' + 52;
  if (c == '+') return 62;
  if (c == '/') return 63;
  return -1;
}

int base64Decode(const String &input, uint8_t *output, int maxOutputLen) {
  int outLen = 0;
  int val = 0, valb = -8;
  for (unsigned int i = 0; i < input.length(); i++) {
    int d = base64Value(input[i]);
    if (d == -1) continue;
    val = (val << 6) + d;
    valb += 6;
    if (valb >= 0) {
      if (outLen >= maxOutputLen) break;
      output[outLen++] = (uint8_t)((val >> valb) & 0xFF);
      valb -= 8;
    }
  }
  return outLen;
}

// Cridat per Python (Bridge.call) un cop per xec, en ordre, per cada
// fotograma de la vista en directe. Nomes desa dades i marca flags --
// el dibuix real es fa al loop(), mai aqui, per no barrejar l'SPI de
// la LCD amb la crida RPC.
void receive_camera_chunk(int chunkIndex, int totalChunks, String data) {
  unsigned long now = millis();

  // Si portem massa temps esperant el seguent xec, el frame a mitges
  // es dona per espatllat -- nomes acceptem tornar a comencar pel xec 0.
  if (camExpectedChunk > 0 && (now - camLastChunkMillis) > CAM_CHUNK_TIMEOUT_MS) {
    camExpectedChunk = 0;
  }

  if (totalChunks != CAM_TOTAL_CHUNKS || chunkIndex != camExpectedChunk) {
    if (chunkIndex == 0) {
      camExpectedChunk = 0;  // comencem un frame nou
    } else {
      return;  // xec orfe/fora d'ordre -- l'ignorem
    }
  }

  int byteOffset = chunkIndex * CAM_CHUNK_PIXELS * 2;
  int maxBytesThisChunk = (int)sizeof(camFrameBuf) - byteOffset;
  if (maxBytesThisChunk > CAM_CHUNK_PIXELS * 2) {
    maxBytesThisChunk = CAM_CHUNK_PIXELS * 2;
  }
  if (maxBytesThisChunk <= 0) return;

  base64Decode(data, camFrameBuf + byteOffset, maxBytesThisChunk);

  camLastChunkMillis = now;
  camExpectedChunk = chunkIndex + 1;

  if (chunkIndex == totalChunks - 1) {
    newCameraFrameFlag = true;
    camExpectedChunk = 0;  // preparats per rebre el seguent frame
  }
}

// ---------- Minimapa Park Güell (switch D6 OFF) ----------
// Estat i logica de dibuix adaptats de la versio standalone
// (park_guell_map.ino). La diferencia principal amb l'original: aqui
// NO es llegeix per Serial -- l'estat es modifica nomes via les
// funcions RPC mark_landmark_visited/set_location_by_id/
// set_location_xy/reset_minimap, cridades pel costat Python
// (python/minimapa/minimap_module.py).
bool visited[NUM_LANDMARKS] = { false };
int8_t lastVisitedId = -1;
bool hasLocation = false;
int16_t locX = 0, locY = 0;

// Every terrain color exists as a full-saturation version (index 0) and a
// desaturated "unexplored" version (index 1). Tiles render gray until a
// nearby landmark is visited, then switch to color for good -- see
// isRevealed().
uint16_t C_VOID[2], C_BLOCK[2], C_BLOCKD[2], C_FORESTDD[2], C_FOREST[2], C_FORESTL[2],
         C_SCRUB[2], C_SCRUBL[2], C_PATH[2], C_PATHD[2], C_SAND[2], C_SANDD[2],
         C_STONE[2], C_STONED[2], C_ROOF[2], C_ROOFL[2], C_TILE[2], C_TILEL[2],
         C_ROCK[2], C_ROCKD[2];
uint16_t C_INK, C_RING, C_UNVISITED, C_VISITED, C_LOCATION;

// Approximates luminance (0.30R + 0.59G + 0.11B) without floating point.
uint8_t grayOf(const ParkColor& c) {
  return (uint8_t)(((uint16_t)c.r * 77 + (uint16_t)c.g * 151 + (uint16_t)c.b * 28) >> 8);
}

void setPair(uint16_t out[2], const ParkColor& c) {
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

// Nearest landmark by straight-line distance -- every point on the map
// belongs to exactly one landmark's territory (a Voronoi partition), so
// once all landmarks are visited the whole map is revealed with no gaps.
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

// True once the tile's territory-owning landmark has been visited.
bool isRevealed(int16_t px, int16_t py) {
  return visited[nearestLandmarkId(px + 2, py + 2)];
}

// Paints one 4x4 tile at (px,py): a base fill plus a handful of accent
// pixels, giving each terrain type a dithered, hand-painted texture.
// `revealed` selects the full-color or desaturated version of each color.
void paintTile(char ch, int16_t px, int16_t py, bool revealed) {
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

void drawTerrain() {
  for (uint8_t row = 0; row < MAP_ROW_COUNT; row++) {
    const char* rowPtr = MAP_ROWS[row];
    for (uint8_t col = 0; col < MAP_COL_COUNT; col++) {
      char ch = rowPtr[col];
      int16_t px = col * 4, py = row * 4;
      paintTile(ch, px, py, isRevealed(px, py));
    }
  }
}

void drawLandmarkPin(const Landmark& lm, bool isVisited) {
  uint16_t dot = isVisited ? C_VISITED : C_UNVISITED;
  tft.fillCircle(lm.x, lm.y, 4, C_RING);
  tft.drawCircle(lm.x, lm.y, 4, C_INK);
  tft.fillCircle(lm.x, lm.y, 2, dot);
}

void drawLocationMarker() {
  if (!hasLocation) return;
  tft.fillCircle(locX, locY, 2, C_LOCATION);
  tft.drawCircle(locX, locY, 5, C_LOCATION);
}

void drawMinimapStatusBar() {
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

// Nomes redibuixem si el minimapa es realment el que s'esta veient ara
// (switch OFF) -- si esta ON (vista camera), l'estat es queda actualitzat
// i es dibuixara sol la propera vegada que es torni a commutar el switch
// (drawCurrentView() ja crida drawParkMap() en aquell moment).
void markVisited(uint8_t id) {
  if (id >= NUM_LANDMARKS) return;
  visited[id] = true;
  lastVisitedId = id;
  if (!viewSwitchDebounced) drawParkMap();
}

void setLocation(int16_t x, int16_t y) {
  locX = constrain(x, 0, 159);
  locY = constrain(y, 0, 111); // stay above the HUD status bar
  hasLocation = true;
  if (!viewSwitchDebounced) drawParkMap();
}

void resetMinimapState() {
  for (uint8_t i = 0; i < NUM_LANDMARKS; i++) visited[i] = false;
  lastVisitedId = -1;
  hasLocation = false;
  if (!viewSwitchDebounced) drawParkMap();
}

// ---------- RPC del minimapa, cridades pel costat Python ----------
// (veure python/minimapa/minimap_module.py) -- substitueixen el
// protocol de text per Serial ("V3", "P40,90", "R"...) de la versio
// standalone original.
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

unsigned long lastStatusPrint = 0;

void setup() {
  Bridge.begin();
  Monitor.begin();
  delay(3000);

  Monitor.println("==================================");
  Monitor.println(" PROJECTE PERSONALITAT — Arduino UNO Q");
  Monitor.println("==================================");
  delay(100);

  // RPC cap a Python
  Monitor.println("[..] Registrant RPC...");
  delay(100);
  Bridge.provide("photo_trigger", photo_trigger);
  Bridge.provide("confirm_photo_saved", confirm_photo_saved);
  Bridge.provide("view_switch_state", view_switch_state);
  Bridge.provide("receive_camera_chunk", receive_camera_chunk);
  Bridge.provide("get_personality_index", get_personality_index);
  Bridge.provide("is_recording_active", is_recording_active);
  Bridge.provide("get_volume", get_volume);
  Bridge.provide("has_gps_fix", has_gps_fix);
  Bridge.provide("get_gps_lat", get_gps_lat);
  Bridge.provide("get_gps_lon", get_gps_lon);
  Bridge.provide("mark_landmark_visited", mark_landmark_visited);
  Bridge.provide("set_location_by_id", set_location_by_id);
  Bridge.provide("set_location_xy", set_location_xy);
  Bridge.provide("reset_minimap", reset_minimap);
  Monitor.println("[OK] RPC registrats");
  delay(100);

  // Botó extern
  Monitor.println("[..] Configurant boto extern (D7)...");
  delay(100);
  pinMode(EXT_BUTTON_PIN, INPUT_PULLUP);
  Monitor.println("[OK] Boto extern (D7) configurat amb pull-up intern");
  delay(100);

  // Switch minimapa/vista camera
  Monitor.println("[..] Configurant switch (D6)...");
  delay(100);
  pinMode(VIEW_SWITCH_PIN, INPUT_PULLUP);
  Monitor.println("[OK] Switch (D6) configurat amb pull-up intern");
  delay(100);

  // LCD
  Monitor.println("[..] Inicialitzant LCD (tft.initR)...");
  delay(100);
  pinMode(TFT_BL, OUTPUT);
  digitalWrite(TFT_BL, HIGH);
  tft.initR(INITR_GREENTAB);
  tft.setRotation(1);
  tft.fillScreen(ST77XX_BLACK);
  tft.setTextColor(ST77XX_WHITE);
  tft.setTextSize(1);
  tft.setCursor(0, 0);
  tft.println("Projecte Personalitat");
  tft.println("UNO Q");
  Monitor.println("[OK] LCD ST7735S inicialitzada");
  delay(100);

  // Colors del minimapa (depenen de tft, cal fer-ho despres de tft.initR())
  Monitor.println("[..] Inicialitzant colors del minimapa...");
  delay(100);
  initMinimapColors();
  Monitor.println("[OK] Colors del minimapa inicialitzats");
  delay(100);

  // Bus I2C Wire1 (connector Qwiic) + Modulinos
  Monitor.println("[..] Inicialitzant bus I2C Wire1 (connector Qwiic)...");
  delay(100);
  Wire1.begin();
#if defined(WIRE_HAS_TIMEOUT) || defined(ARDUINO_ARCH_AVR) || defined(ARDUINO_ARCH_SAMD) || defined(ARDUINO_ARCH_RENESAS)
  Wire1.setWireTimeout(50000, true);
#endif
  Modulino.begin(Wire1);  // *** CRUCIAL: sense aixo knob/buttons/buzzer.begin() es pengen ***
  Monitor.println("[OK] Bus I2C Wire1 + Modulino.begin(Wire1) fets");
  delay(100);

  Monitor.println("[..] Inicialitzant Modulino Knob...");
  delay(100);
  knob.begin();
  Monitor.println("[OK] Knob inicialitzat");
  delay(100);

  Monitor.println("[..] Inicialitzant Modulino Buttons...");
  delay(100);
  buttons.begin();
  Monitor.println("[OK] Buttons inicialitzat (A/B/C = personalitat en mode camera, ubicacio en mode minimapa)");
  delay(100);

  Monitor.println("[..] Inicialitzant Modulino Buzzer...");
  delay(100);
  buzzer.begin();
  Monitor.println("[OK] Buzzer inicialitzat");
  delay(100);

  buzzer.tone(1000, 150);
  delay(200);

  // GPS (NEO-6M) per Serial1
  Monitor.println("[..] Inicialitzant GPS (Serial1)...");
  delay(100);
  Serial1.begin(GPS_BAUD);
  Monitor.println("[OK] Serial1 (GPS) inicialitzat -- esperant fix...");
  delay(100);

  Monitor.println("==================================");
  Monitor.println("Iniciant bucle...");
  Monitor.println("==================================");

  // Display the intro splash screen with the logo on boot
  drawScreenIntro();
}

// Old inline UI drawing functions removed -- now in sketch/ui_screens.h.

void drawMinimap() {
  drawParkMap();
}

#define CAM_SCALE 4  // factor d'ampliacio en dibuixar (32x24 -> 128x96 px)

void drawCameraViewPlaceholder() {
  tft.fillScreen(ST77XX_BLACK);
  tft.setTextColor(ST77XX_WHITE);
  tft.setTextSize(1);
  tft.setCursor(0, 0);
  tft.println("VISTA CAMERA");
  tft.println("(switch ON)");
  tft.println("");
  tft.println("Esperant imatge...");
  int x = (160 - CAM_THUMB_W * CAM_SCALE) / 2;
  int y = (128 - CAM_THUMB_H * CAM_SCALE) / 2;
  tft.drawRect(x - 2, y - 2, CAM_THUMB_W * CAM_SCALE + 4, CAM_THUMB_H * CAM_SCALE + 4, ST77XX_WHITE);
}

void drawCameraFrame() {
  int x0 = (160 - CAM_THUMB_W * CAM_SCALE) / 2;
  int y0 = (128 - CAM_THUMB_H * CAM_SCALE) / 2;
  uint16_t *pixels = (uint16_t *)camFrameBuf;
  for (int row = 0; row < CAM_THUMB_H; row++) {
    for (int col = 0; col < CAM_THUMB_W; col++) {
      uint16_t color = pixels[row * CAM_THUMB_W + col];
      tft.fillRect(x0 + col * CAM_SCALE, y0 + row * CAM_SCALE, CAM_SCALE, CAM_SCALE, color);
    }
  }
}

void drawCurrentView() {
  if (viewSwitchDebounced) {
    drawCameraViewPlaceholder();
  } else {
    drawMinimap();
  }
}

void loop() {
  // --- GPS: llegeix tots els bytes disponibles de Serial1 cada volta ---
  // (nomes actualitza l'estat intern de TinyGPSPlus -- no bloqueja si
  // no hi ha dades noves, i no cal fix per continuar la resta del bucle)
  while (Serial1.available() > 0) {
    gps.encode(Serial1.read());
  }

  // --- Switch D6: minimapa (off) / vista camera-enfocar (on), amb debounce ---
  // (el llegim ABANS de D7 i dels botons perque el seu significat depen d'aquest mode)
  bool viewSwitchRaw = (digitalRead(VIEW_SWITCH_PIN) == HIGH);
  if (viewSwitchRaw != viewSwitchRawLast) {
    viewSwitchLastChangeTime = millis();
    viewSwitchRawLast = viewSwitchRaw;
  }
  if ((millis() - viewSwitchLastChangeTime) > VIEW_SWITCH_DEBOUNCE_MS
      && viewSwitchRaw != viewSwitchDebounced) {
    viewSwitchDebounced = viewSwitchRaw;
    Monitor.print("[EVENT] Switch D6 canviat -> ");
    Monitor.println(viewSwitchDebounced ? "ON (enfocar/camera)" : "OFF (minimapa)");

    // Si sortim del mode minimapa amb una gravacio a mitges, la parem
    // forçosament -- no te sentit deixar-la "penjada" en mode camera.
    if (viewSwitchDebounced && recordingActive) {
      recordingActive = false;
      buzzer.tone(600, 150);
      Monitor.println("[EVENT] Gravacio aturada forçosament (canvi a mode camera)");
    }

    if (currentUiState == UI_ACTIVE) {
      drawCurrentView();
    }
  }
  bool viewSwitchOn = viewSwitchDebounced;

  // --- Botó extern D7: significat segons mode (actiu nomes en UI_ACTIVE) ---
  bool extBtnPressed = (digitalRead(EXT_BUTTON_PIN) == LOW);
  if (extBtnPressed && !lastExtBtnState && currentUiState == UI_ACTIVE) {
    if (viewSwitchOn) {
      // Mode ENFOCAR/camera -> foto (el buzzer sona quan Python confirma que s'ha desat)
      photoTriggerFlag = true;
      Monitor.println("[EVENT] Boto D7 premut -> foto");
    } else {
      // Mode MINIMAPA -> toggle de gravacio de la pregunta
      recordingActive = !recordingActive;
      if (recordingActive) {
        buzzer.tone(1400, 90);
        Monitor.println("[EVENT] Boto D7 premut -> comença a gravar pregunta");
      } else {
        buzzer.tone(900, 90);
        Monitor.println("[EVENT] Boto D7 premut -> para de gravar pregunta");
      }
    }
  }
  lastExtBtnState = extBtnPressed;

  if (playShutterSoundFlag) {
    playShutterSoundFlag = false;
    buzzer.tone(2000, 100);
  }

  // Frame de camera complet (tots els xecs rebuts) -- nomes el
  // dibuixem si estem en mode "vista camera" i UI activa.
  if (newCameraFrameFlag) {
    newCameraFrameFlag = false;
    if (viewSwitchOn && currentUiState == UI_ACTIVE) {
      drawCameraFrame();
    }
  }

  // --- Modulino Buttons: Gestio segons l'estat d'UI ---
  buttons.update();
  btnAHeld = (buttons.isPressed('A') == HIGH);
  btnBHeld = (buttons.isPressed('B') == HIGH);
  btnCHeld = (buttons.isPressed('C') == HIGH);

  bool btnAPressedEdge = btnAHeld && !btnAHeldPrev;
  bool btnBPressedEdge = btnBHeld && !btnBHeldPrev;
  bool btnCPressedEdge = btnCHeld && !btnCHeldPrev;
  btnAHeldPrev = btnAHeld;
  btnBHeldPrev = btnBHeld;
  btnCHeldPrev = btnCHeld;

  // State machine for onboarding and tutorial screens
  if (currentUiState == UI_BOOT_INTRO) {
    blinkIntroPrompt();
    if (btnAPressedEdge || btnBPressedEdge || btnCPressedEdge) {
      currentUiState = UI_OPTIONS;
      drawScreenOptions();
      buzzer.tone(1400, 50);
    }
  } else if (currentUiState == UI_OPTIONS) {
    if (btnAPressedEdge) {
      currentUiState = UI_TUTORIAL_1;
      drawScreenTutorial1();
      buzzer.tone(1500, 60);
    } else if (btnCPressedEdge) {
      currentUiState = UI_VOICE_SELECT;
      drawScreenPersonalitySelect();
      buzzer.tone(1500, 60);
    }
  } else if (currentUiState == UI_TUTORIAL_1) {
    if (btnAPressedEdge) {
      currentUiState = UI_TUTORIAL_2;
      drawScreenTutorial2();
      buzzer.tone(1500, 60);
    } else if (btnCPressedEdge) {
      currentUiState = UI_VOICE_SELECT;
      drawScreenPersonalitySelect();
      buzzer.tone(1500, 60);
    }
  } else if (currentUiState == UI_TUTORIAL_2) {
    if (btnAPressedEdge) {
      currentUiState = UI_TUTORIAL_3;
      drawScreenTutorial3();
      buzzer.tone(1500, 60);
    } else if (btnCPressedEdge) {
      currentUiState = UI_VOICE_SELECT;
      drawScreenPersonalitySelect();
      buzzer.tone(1500, 60);
    }
  } else if (currentUiState == UI_TUTORIAL_3) {
    if (btnAPressedEdge || btnCPressedEdge) {
      currentUiState = UI_VOICE_SELECT;
      drawScreenPersonalitySelect();
      buzzer.tone(1500, 60);
    }
  } else if (currentUiState == UI_VOICE_SELECT) {
    if (btnAPressedEdge || btnBPressedEdge || btnCPressedEdge) {
      personalityIndex = btnAPressedEdge ? 0 : (btnBPressedEdge ? 1 : 2);
      currentUiState = UI_ACTIVE;
      Monitor.print("[EVENT] Personality selected: index ");
      Monitor.println(personalityIndex);
      buzzer.tone(1800, 100);
      drawCurrentView();
    }
  } else if (currentUiState == UI_ACTIVE) {
    // Normal mode: A/B/C changes personality on the fly
    if (btnAPressedEdge || btnBPressedEdge || btnCPressedEdge) {
      personalityIndex = btnAPressedEdge ? 0 : (btnBPressedEdge ? 1 : 2);
      Monitor.print("[EVENT] Personalitat seleccionada: index ");
      Monitor.println(personalityIndex);
      buzzer.tone(1800, 40);
    }
  }

  // LEDs: visual feedback according to UI state
  if (currentUiState == UI_BOOT_INTRO || currentUiState == UI_OPTIONS) {
    buttons.setLeds(true, false, true);   // A and C lit
  } else if (currentUiState == UI_TUTORIAL_1 || currentUiState == UI_TUTORIAL_2) {
    buttons.setLeds(true, false, true);   // A and C lit (Next / Skip)
  } else if (currentUiState == UI_TUTORIAL_3) {
    buttons.setLeds(true, false, false);  // only A lit (Choose Personality)
  } else if (currentUiState == UI_VOICE_SELECT) {
    buttons.setLeds(true, true, true);    // A, B and C all lit
  } else if (currentUiState == UI_ACTIVE) {
    if (recordingActive) {
      bool blink = ((millis() / 300) % 2) == 0;
      buttons.setLeds(blink, blink, blink);
    } else {
      buttons.setLeds(personalityIndex == 0, personalityIndex == 1, personalityIndex == 2);
    }
  }

  // --- Knob (filtrat): Control de Volum (0 - 100%) ---
  int16_t currentKnobPos = readKnobFiltered();
  if (!knobVolumeInit) {
    lastKnobPos = currentKnobPos;
    knobVolumeInit = true;
  } else {
    int16_t diff = currentKnobPos - lastKnobPos;
    if (diff != 0) {
      lastKnobPos = currentKnobPos;
      currentVolume += diff * 2;
      if (currentVolume < 0) currentVolume = 0;
      if (currentVolume > 100) currentVolume = 100;
      Monitor.print("[EVENT] Volum canviat -> ");
      Monitor.print(currentVolume);
      Monitor.println("%");
    }
  }

  // --- Estat cada 2s (nomes debug) ---
  if (millis() - lastStatusPrint >= 2000) {
    lastStatusPrint = millis();
    Monitor.print("Estat | D7: ");
    Monitor.print(extBtnPressed ? "premut" : "lliure");
    Monitor.print(" | Switch D6: ");
    Monitor.print(viewSwitchOn ? "ON (camera)" : "OFF (minimapa)");
    Monitor.print(" | Volum: ");
    Monitor.print(currentVolume);
    Monitor.print("%");
    Monitor.print(" | Personalitat idx: ");
    Monitor.print(personalityIndex);
    Monitor.print(" | Gravant: ");
    Monitor.print(recordingActive ? "SI" : "no");
    Monitor.print(" | GPS fix: ");
    if (gps.location.isValid()) {
      Monitor.print(gps.location.lat(), 6);
      Monitor.print(",");
      Monitor.println(gps.location.lng(), 6);
    } else {
      Monitor.println("sense fix");
    }
  }

  delay(20);
}
