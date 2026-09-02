# Carpeta de models

Aquí hi van els fitxers dels teus models de veu/resposta (pesos,
prompts, configuracions...), un per "personalitat" associada a cada
botó Modulino (A/B/C).

L'única part que llegeix el codi és, opcionalment, `models.json` (a
aquesta mateixa carpeta), que assigna un nom a cada botó. Si no hi és,
es fan servir noms genèrics (`model_a`, `model_b`, `model_c`). Mira
`models.example.json` per veure el format — copia'l a `models.json` i
edita'l al teu gust.

Aquest nom s'utilitza per etiquetar els fitxers de gravació
(`python/recordings/recording_<timestamp>_<boto>-<nom_model>.wav`) i,
més endavant, per triar quin model carregar en processar l'àudio —
això últim encara està per fer, és responsabilitat teva connectar-hi
la lògica real (veure `python/model_module.py`).

---

## Integració Cultura Viva — fitxers PENDENTS DE POSAR

Quan implementis la pipeline completa (STT → visió → KG → SLM → TTS),
aquesta carpeta ha d'acollir dos elements nous:

### 1. Model SLM — `models/slm/<fitxer>.gguf`

El mètode `ModelRegistry.generate_response(...)` (pendent d'implementar
a `model_module.py`) necessita un fitxer GGUF. Model recomanat:
**Qwen2.5-1.5B-Instruct** quantitzat (q4_K_M) — és lleuger i cabà bé
a la UNO Q (~4 GB RAM al MPU).

```
models/
└── slm/
    └── qwen2.5-1.5b-instruct-q4_k_m.gguf
```

**Com descarregar-lo (des de la UNO Q):**
```bash
pip install huggingface-hub
huggingface-cli download Qwen/Qwen2.5-1.5B-Instruct-GGUF \
    qwen2.5-1.5b-instruct-q4_k_m.gguf \
    --local-dir python/models/slm/
```

**Llbibreria necessària** (afegir a `requirements.txt`):
```
llama-cpp-python>=0.2.0
```
En ARM/Linux cal compilar des de font:
```bash
CMAKE_ARGS="-DLLAMA_BLAS=ON" pip install llama-cpp-python
```

**Quan el tinguis**, afegeix a `config.py`:
```python
SLM_MODEL_PATH = MODELS_DIR / "slm" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
```

> ⚠️ **Si canvies de model o de nom de fitxer**: actualitza `SLM_MODEL_PATH`
> a `config.py`. El codi de `model_module.py` l'importarà des d'allà.
> Si canvies els noms de Personalitat a `models.json` (`"artistic"`,
> `"technical"`, `"child"`), actualitza també les claus del diccionari
> `PERSONALITY_PROMPTS` dins de `model_module.py`.

### 2. Graf de coneixement de Gaudí (KG) — `models/knowledge/gaudi_kg.json`

El mètode `ModelRegistry.get_kg_context(element)` (pendent d'implementar)
consulta un JSON amb informació factual sobre elements detectats per la
càmera (`"drac"`, `"xemeneia"`, `"nativity_facade"`, etc.) per enriquir
la resposta del SLM.

**Format esperat (JSON):**
```json
{
  "drac": {
    "nom_complet": "Drac de la porta de la Casa Güell",
    "ubicacio": "park_guell",
    "material": "ferro forjat",
    "any": 1885,
    "curiositats": ["..."]
  },
  "xemeneia": {
    "nom_complet": "Xemeneia de la Casa Milà (La Pedrera)",
    "ubicacio": "sagrada_familia"
  }
}
```

```
models/
└── knowledge/
    └── gaudi_kg.json
```

**Quan el tinguis**, afegeix a `config.py`:
```python
KG_PATH = MODELS_DIR / "knowledge" / "gaudi_kg.json"
```

> ⚠️ **Si canvies el nom del fitxer o les claus del JSON**: actualitza
> `KG_PATH` a `config.py` i revisa `ModelRegistry.get_kg_context()` a
> `model_module.py`, que fa el lookup per clau d'element.

---

## Resum de constants a afegir a `config.py` (totes PENDENTS)

| Constant | Valor d'exemple | Qui la fa servir |
|---|---|---|
| `SLM_MODEL_PATH` | `MODELS_DIR / "slm" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"` | `model_module.ModelRegistry.generate_response()` |
| `KG_PATH` | `MODELS_DIR / "knowledge" / "gaudi_kg.json"` | `model_module.ModelRegistry.get_kg_context()` |

Cap d'aquestes constants existeix encara a `config.py`.
