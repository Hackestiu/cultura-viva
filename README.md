# Projecte Personalitat — Arduino UNO Q (+ integració Cultura Viva)

Aquest document és una referència completa de l'estat actual del projecte,
pensada per compartir amb altres persones (o altres IAs, com GitHub Copilot)
que hagin d'agafar el codi i seguir-hi treballant. Explica què fa cada
fitxer, com es comuniquen el sketch i el Python, i **què està fet de veritat
vs. què encara està pendent** — aquesta última part és important, no
assumeixis que tot el que es descriu aquí ja funciona de cap a cap.

> **Actualització:** aquesta versió incorpora dos fixes crítics fets
> després d'una sessió de depuració (gravació trencada + àudio Bluetooth
> mut) — veure la secció "Fixes aplicats" més avall, abans de "PENDENT".

## Maquinari

- **Arduino UNO Q**: placa amb dos processadors — un MCU (STM32, temps real,
  corre el sketch `.ino`) i un MPU Linux (Qualcomm QRB2210, corre el Python).
  Es comuniquen entre ells amb **Bridge (RPC)**, no per port sèrie.
- **LCD TFT ST7735S** 128x160, 1.8", nomès 3.3V — connectada per SPI de
  maquinari (pins CS=10, DC=8, RST=9, backlight=5).
- **Webcam Logitech Brio 105** per USB — fotos i vista en directe.
- **Micròfon**: el de la mateixa Brio 105 (ALSA `hw:0,0`), NO un micròfon
  Bluetooth.
- **Mòduls Qwiic (I2C per `Wire1`, NO `Wire`)**: Modulino Knob (control de volum dels auriculars 0-100%), Modulino Buttons (A/B/C), Modulino Buzzer.
- **Botó extern** a D7, **switch** a D6.
- **GPS NEO-6M** per `Serial1` (9600 baud) — només per triar automàticament
  entre dues ubicacions fixes per proximitat (veure més avall).
- **Sortida d'àudio**: auriculars connectats per **jack 3.5mm** (sortida directa ALSA `default`), amb volum regulable mitjançant el **Modulino Knob** — per reproduir la resposta de veu de la pipeline Cultura Viva.

## Estructura de carpetes

```
<carpeta del sketch>/
├── sketch.ino          # codi C++ del MCU (tot el hardware en temps real)
├── sketch.yaml          # dependencies de llibreries C++ (versions explicites)
├── landmarks.h           # dades del minimapa (Park Güell): landmarks
├── tilemap.h              # dades del minimapa (Park Güell): terreny/paleta
└── app.yaml               # manifest de l'app (nom, icona...)

python/
├── config.py                    # TOTA la configuracio centralitzada
├── main.py                       # bucle principal (App.run) -- veure "Fixes aplicats"
├── camera_module.py               # CameraManager: fotos 1080p + vista en directe
├── microphone_module.py            # MicrophoneManager: gravacio de la pregunta
├── model_module.py                  # ModelRegistry: Personalitat (A/B/C)
├── location_module.py                # LocationRegistry: Ubicacio per GPS
├── bluetooth_module.py                # connexio/emparellament Bluetooth auto -- veure "Fixes aplicats"
├── audio_playback_module.py            # AudioPlayer: reproduir la resposta TTS
├── requirements.txt
├── models/                              # fitxers de personalitat (opcional models.json)
├── minimapa/
│   ├── landmarks.json                    # font de veritat pel minimapa (mirall de landmarks.h)
│   ├── minimap_module.py                  # MinimapManager: marcar visitat / posicio
│   └── README.md                           # detall especific del minimapa
├── locations/                              # opcional locations.json (override coordenades GPS)
├── recordings/                              # .wav de preguntes gravades (es crea sol)
├── photos/                                   # fotos preses (es crea sol)
└── responses/                                 # .wav de respostes TTS (es crea sol -- veure nota mes avall)
```

## Com funciona: interacció física

El **switch D6** té dos modes, que canvien tant la pantalla LCD com el
significat del **botó D7**:

| Switch D6 | Pantalla LCD | Botó D7 fa... |
|---|---|---|
| **ON** (mode ENFOCAR/càmera) | Vista en directe de la webcam | Un click = fa una FOTO |
| **OFF** (mode MINIMAPA) | Minimapa de Park Güell | Click en TOGGLE = 1r click comença a gravar la pregunta, 2n click para |

Els **botons A/B/C** (Modulino Buttons) sempre fan la mateixa cosa,
independentment del switch: un click curt selecciona la **Personalitat**
(ARTISTIC/TECHNICAL/CHILD, index 0/1/2). Els LEDs de cada botó mostren quina
personalitat està seleccionada — excepte mentre s'està gravant una pregunta,
que parpellegen totes juntes com a feedback visual.

La **Ubicació** (Park Güell / Sagrada Família) NO es tria manualment: es
calcula sola per **proximitat GPS** — es compara la posició actual amb les
coordenades fixes de tots dos llocs i es tria la més propera. El sketch
només exposa el fix cru (`has_gps_fix`/`get_gps_lat`/`get_gps_lon`);
`location_module.py` és qui fa el càlcul de distància (Haversine).

⚠️ **Important**: el minimapa de la LCD només té dades de **Park Güell**
(`landmarks.h`/`tilemap.h`/`landmarks.json`). El GPS pot dir que estàs més a
prop de la Sagrada Família, però la LCD seguirà mostrant el mapa de Park
Güell igualment — el GPS només serveix per triar quin classificador de
visió / graf de coneixement fer servir a la pipeline de Cultura Viva, no
per canviar la pantalla. Fins que no es dissenyi un `tilemap.h` equivalent
per la Sagrada Família, la LCD és de Park Güell exclusivament.

## Interfície RPC (Bridge) — sketch ↔ Python

Totes aquestes funcions les **exposa el sketch** (`Bridge.provide(...)`) i
les **crida el Python** (`Bridge.call(...)`). Aquesta llista s'ha verificat
directament contra `sketch.ino` (línies `Bridge.provide(...)`) — és la font
de veritat, no assumeixis res que no hi surti:

| Funció RPC | Retorna | Què fa |
|---|---|---|
| `photo_trigger()` | bool | `True` un cop quan s'ha premut D7 en mode càmera (es consumeix en llegir-la) |
| `confirm_photo_saved()` | — | Python la crida quan ha desat la foto correctament -> sona el buzzer |
| `view_switch_state()` | bool | Estat debounced del switch D6 (`True`=càmera, `False`=minimapa) |
| `receive_camera_chunk(idx, total, data_b64)` | — | Un xec de la miniatura de la vista en directe (veure secció següent) |
| `get_personality_index()` | int (0/1/2) | Personalitat seleccionada actualment amb A/B/C |
| `is_recording_active()` | bool | `True` mentre s'està gravant la pregunta (toggle amb D7 en mode minimapa) |
| `has_gps_fix()` | bool | Si el GPS té fix vàlid ara mateix |
| `get_gps_lat()` / `get_gps_lon()` | float | Coordenades actuals (0.0 si no hi ha fix) |
| `mark_landmark_visited(id)` | bool | Marca un landmark del minimapa com a visitat |
| `set_location_by_id(id)` | bool | Mou el marcador "estàs aquí" a la posició d'un landmark |
| `set_location_xy(x, y)` | bool | Mou el marcador a una posició arbitrària |
| `reset_minimap()` | bool | Neteja tots els landmarks visitats i el marcador de posició |

> ⚠️ **`get_held_button()` NO existeix** al sketch actual — es va
> substituir per `get_personality_index()` + `is_recording_active()`. Si
> veus codi Python que encara la crida, és codi vell/trencat (veure
> "Fixes aplicats").

### Vista de la càmera, per paquets

El canal RPC té un límit de mida de missatge que salta amb miniatures
relativament petites en un sol missatge. Per això, `camera_module.py`
trosseja cada fotograma (reduït a `CAM_THUMB_W`x`CAM_THUMB_H` en RGB565) en
xecs de `CAM_CHUNK_PIXELS` píxels i els envia seqüencialment amb
`receive_camera_chunk`. **Aquestes tres constants han de coincidir
EXACTAMENT entre `config.py` i `sketch.ino`.**

## Mòduls Python, un per un

- **`camera_module.py`** — `CameraManager`: fotos a 1080p (amb verificació
  que la resolució s'ha aplicat de veritat) i vista en directe trossejada.
- **`microphone_module.py`** — `MicrophoneManager`: com que `Microphone`
  només exposa `record_wav(duration=X)` (sense start/stop de streaming), la
  gravació de durada variable es simula gravant trossos curts consecutius
  mentre una condició (`is_still_held`) segueixi sent certa. Ara aquesta
  condició és `is_recording_active()` (el toggle de D7) — ja connectat a
  `main.py`, veure "Fixes aplicats".
- **`model_module.py`** — `ModelRegistry`: nom assignat a cada botó A/B/C
  (per defecte `model_a`/`model_b`/`model_c`, sobreescrivible amb
  `models/models.json`). Amb la integració de Cultura Viva, aquests noms
  haurien de ser les Personalitats (`artistic`/`technical`/`child`).
  ✅ **Verificat**: `name_for()` espera una lletra ("A"/"B"/"C"), exactament
  el que li passa `main.py` (convertint l'índex de `get_personality_index()`
  amb `"ABC"[index]`) — la crida des de `main.py` és correcta.
- **`location_module.py`** — `LocationRegistry`: coordenades de referència
  de Park Güell i Sagrada Família, i `current()` que consulta el GPS via
  Bridge i retorna quin dels dos és més proper (Haversine).
- **`bluetooth_module.py`** — connexió automàtica a un dispositiu Bluetooth
  de sortida: reconnecta a l'última MAC coneguda, o escaneja/empareila/
  connecta un dispositiu pel nom (`TRUSTED_DEVICE_NAME`). Fa servir
  `bluetoothctl` per subprocess. **Fix aplicat a `get_playback_device()`**
  — veure "Fixes aplicats".
- **`audio_playback_module.py`** — `AudioPlayer`: reprodueix un `.wav`
  (bloquejant) amb `aplay`, fent servir el device Bluetooth resolt per
  `bluetooth_module.py` (o `PLAYBACK_DEVICE` de `config.py` si el vols
  forçar manualment).
- **`minimapa/minimap_module.py`** — `MinimapManager`: tradueix un codi de
  landmark humà (`"DR"`) a l'id numèric i crida les RPC del minimapa.

## Configuració (`config.py`)

Centralitza TOT — paths, dispositius, mides.

- `TRUSTED_DEVICE_NAME = "RZ-B100W"` — **ja confirmat i verificat**: els
  auriculars de sortida són uns Panasonic RZ-B100W, MAC
  `B4:6C:47:9B:49:1C`. Abans aquest valor era `None`, cosa que impedia
  qualsevol escaneig/connexió automàtica — era la causa principal de "no
  s'escolta l'àudio" (veure "Fixes aplicats").
- `PLAYBACK_DEVICE` — deixa'l a `None` per descoberta automàtica; només
  omple'l si la descoberta automàtica no funciona bé al teu entorn.

Punts que **ja estan verificats contra el maquinari real**:

- `MIC_DEVICE = "hw:0,0"` (Brio 105).
- `CAMERA_DEVICE_INDEX = 2`, `CAMERA_FOURCC = "MJPG"`.
- `TRUSTED_DEVICE_NAME = "RZ-B100W"` (Panasonic RZ-B100W, MAC
  `B4:6C:47:9B:49:1C`).

## Bluetooth: instal·lació de BlueALSA

Cal `bluez`, `bluealsa` i `alsa-utils` instal·lats, amb el perfil
`a2dp-sink` habilitat (és el que fa servir un dispositiu de sortida com
uns auriculars). Resum ràpid:

```bash
sudo apt update && sudo apt install -y bluez bluealsa alsa-utils
sudo systemctl enable --now bluetooth bluealsa
systemctl cat bluealsa   # comprova si ja hi ha --profile=a2dp-sink
```

Si falta el perfil, `sudo systemctl edit bluealsa` i afegir:
```
[Service]
ExecStart=
ExecStart=/usr/bin/bluealsa --profile=a2dp-sink
```
(la línia `ExecStart=` buida és imprescindible per netejar l'original).
Després `sudo systemctl daemon-reload && sudo systemctl restart bluealsa`.

⚠️ **Important, apres una sessió real de depuració**: `aplay -L | grep -i
blue` a la UNO Q **NOMÉS mostra una entrada genèrica** `bluealsa`
("Bluetooth Audio") — BlueALSA **no genera una entrada diferent per cada
MAC connectada**, a diferència del que assumia una versió anterior del
codi (veure "Fixes aplicats"). Per reproduir per un dispositiu concret cal
construir la cadena manualment:

```bash
aplay -D bluealsa:DEV=B4:6C:47:9B:49:1C,PROFILE=a2dp fitxer.wav
```

### Emparellament manual del RZ-B100W (procediment verificat)

Per emparellar els auriculars des de zero (o si mai es perd
l'emparellament):

1. Mantenir premut el botó d'encesa/Bluetooth dels RZ-B100W ~5-7s fins que
   el LED parpellegi (mode pairing) — **fer-ho immediatament abans** del
   pas 2, no abans, perquè el mode pairing es tanca sol al cap d'una
   estona.
2. Dins `bluetoothctl` (`bluetoothctl` sol, sense arguments, per entrar en
   mode interactiu):
   ```
   power on
   scan on
   ```
   Esperar fins veure `Device B4:6C:47:9B:49:1C RZ-B100W` a la sortida.
3. **Sense fer `scan off`**, emparellar mentre l'escaneig segueix actiu:
   ```
   pair B4:6C:47:9B:49:1C
   trust B4:6C:47:9B:49:1C
   connect B4:6C:47:9B:49:1C
   ```
   Si en algun punt diu `Device ... not available`, sol voler dir que el
   controlador ha perdut contacte amb el dispositiu (p.ex. per haver fet
   `scan off` massa aviat, o perquè el mode pairing dels auriculars ja
   s'havia tancat) — cal repetir el pas 1 (auriculars) i el pas 2 (scan)
   des de zero.
   - Si segueix fallant: `remove B4:6C:47:9B:49:1C`, `power off`,
     `power on`, i repetir tot el procediment.
   - Si els auriculars ja estan aparellats amb un altre dispositiu (mòbil)
     i **encès**, pot ser que no responguin al pairing request de la UNO
     Q — cal desactivar el Bluetooth d'aquell altre dispositiu abans.
4. Verificar: `devices Connected` hauria de mostrar la línia del
   RZ-B100W.
5. Provar la reproducció directament (fora de `bluetoothctl`):
   ```bash
   aplay -D bluealsa:DEV=B4:6C:47:9B:49:1C,PROFILE=a2dp /usr/share/sounds/alsa/Front_Center.wav
   ```

Un cop `TRUSTED_DEVICE_NAME = "RZ-B100W"` a `config.py`, i el dispositiu ja
emparellat/de confiança un cop de forma manual, `bluetooth_module.py` ha de
poder reconnectar-hi automàticament (via `BT_LAST_MAC_FILE`, la MAC
desada) als següents arrencaments sense repetir tot aquest procés.

## Fixes aplicats (sessió de depuració d'àudio i gravació)

Durant una sessió de depuració es van trobar i corregir dos bugs reals:

### 1. Gravació trencada — `main.py`

`main.py` encara cridava `Bridge.call("get_held_button")`, una RPC que
**ja no existeix** al sketch actual (substituïda per
`get_personality_index()` + `is_recording_active()`). Com que la crida
petava dins un `try/except`, mai arribava a `record_while_held` — no es
gravava res, sense donar cap error visible més enllà de la consola.

**Fix**: el bucle de `main.py` ara fa:
```python
if Bridge.call("is_recording_active"):
    personality_index = Bridge.call("get_personality_index")  # 0/1/2
    button_id = "ABC"[personality_index]
    model_name = models.name_for(button_id)
    audio = microphone.record_while_held(
        is_still_held=lambda: Bridge.call("is_recording_active")
    )
    if audio is not None:
        microphone.save(button_id, model_name, audio)
```
✅ **Verificat contra `model_module.py`**: `ModelRegistry.name_for()`
espera exactament una lletra ("A"/"B"/"C"), que és el que li passa aquest
codi. No cal cap canvi addicional aquí.

### 2. Àudio Bluetooth mut — `bluetooth_module.py`

`get_playback_device()` buscava la MAC del dispositiu connectat dins la
sortida d'`aplay -L`, assumint que BlueALSA hi generaria una entrada
específica per dispositiu. **Això no passa**: BlueALSA només exposa un PCM
genèric `bluealsa` ("Bluetooth Audio"), igual per tots els dispositius —
la cerca mai trobava res, `_resolve_device()` retornava `None`, i `aplay`
acabava sonant pel dispositiu per defecte del sistema (no per Bluetooth).

**Fix**: `get_playback_device()` ara construeix directament la cadena de
device en lloc de buscar-la:
```python
def get_playback_device():
    mac = ensure_connected()
    if mac is None:
        return None
    return f"bluealsa:DEV={mac},PROFILE=a2dp"
```

### 3. TRUSTED_DEVICE_NAME sense omplir — `config.py`

Encara que el fix #2 sigui correcte, sense `TRUSTED_DEVICE_NAME` omplert a
`config.py`, `bluetooth_module.ensure_connected()` mai pot escanejar ni
connectar res (surt directament amb un warning). **Ja identificat i
confirmat per escaneig manual**: els auriculars són uns **Panasonic
RZ-B100W** (MAC `B4:6C:47:9B:49:1C`) — cal:
```python
TRUSTED_DEVICE_NAME = "RZ-B100W"
```

## ⚠️ PENDENT — el que encara NO està fet

Això és important per no assumir que el projecte està complet:

1. ~~`main.py` desactualitzat/trencat (`get_held_button`)~~ — **corregit i
   verificat**, veure "Fixes aplicats" #1 (compatibilitat amb
   `model_module.name_for()` confirmada).
2. **La pipeline de Cultura Viva pròpiament dita (STT/visió/graf de
   coneixement/SLM) encara no s'ha portat a aquest projecte.** Només hi ha
   la infraestructura d'integració (mòduls de maquinari + config), no la
   IA en si — cal copiar/adaptar `speech/`, `vision/`, `knowledge/` del
   repo original de Cultura Viva. **Conseqüència pràctica**: `responses/`
   estarà buida fins que això existeixi — no hi ha res generat encara per
   reproduir per Bluetooth, per molt que la connexió i el codi de
   reproducció ja funcionin correctament (verificat amb un `.wav` de
   prova).
3. **`camera_module.py` no guarda encara el path de l'última foto presa**
   — caldrà per poder-la passar al classificador de visió quan es cridi
   la pipeline des de `main.py`.
4. **Minimapa de la Sagrada Família: no existeix.** Només hi ha dades de
   Park Güell.
5. **`sketch.yaml`: verifica el número de versió de `TinyGPSPlus`** — hi
   hem posat `1.0.3` com a valor habitual, sense poder confirmar-lo contra
   el teu entorn real.
6. **Pins de `Serial1` (GPS) no verificats** contra el pinout físic real
   de la UNO Q.