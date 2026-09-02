# `model_module.py` — mètodes `get_kg_context()` i `generate_response()` pendents

**Estat**: ⏳ PENDENTS D'IMPLEMENTAR — els dos mètodes nous **no existeixen**
encara a `ModelRegistry`. El que sí existeix i funciona:
- `name_for(button_id)` ✅ — retorna `"artistic"` / `"technical"` / `"child"`
- `models_dir` ✅ (property)

**REGLA D'OR**: `name_for()` **NO es toca**. S'usa a `main.py` per etiquetar
gravacions i per deduir la Personalitat — ha de seguir funcionant exactament igual.

---

## Mètodes a afegir (dins `ModelRegistry`, sense tocar res existent)

```python
PERSONALITY_PROMPTS = {
    "artistic":   "Ets una guia artística apassionada...",
    "technical":  "Ets una guia tècnica i precisa...",
    "child":      "Ets una guia per a nens, parles senzill i divertit...",
}

class ModelRegistry:
    # ... codi existent intacte (name_for, _load_overrides, etc.) ...

    def get_kg_context(self, element: str) -> str:
        """Consulta el graf de coneixement de Gaudí per l'element detectat.
        Retorna un string de context (buit "" si l'element no es troba al KG).

        :param element: nom de l'element retornat per VisionClassifier.classify()
                        (p.ex. "drac", "xemeneia") -- ha de coincidir amb les
                        claus de gaudi_kg.json.
        """

    def generate_response(
        self,
        question: str,
        element: str | None,
        personality: str,
        kg_context: str,
    ) -> str:
        """Inferència amb el SLM (Qwen2.5 via llama-cpp-python).
        Retorna el text de la resposta generada.

        :param question:    text transcrit per Whisper (la pregunta del visitant)
        :param element:     element detectat per VisionClassifier, o None
        :param personality: "artistic" | "technical" | "child"
                            (el que retorna name_for(button_id))
        :param kg_context:  context factual del KG (el que retorna get_kg_context())
        """
```

---

## Implementació de `get_kg_context()`

```python
import json

def get_kg_context(self, element: str) -> str:
    if not hasattr(self, "_kg"):
        from config import KG_PATH
        try:
            with open(KG_PATH, "r", encoding="utf-8") as f:
                self._kg = json.load(f)
        except (OSError, ValueError) as exc:
            print(f"[WARN] No s'ha pogut llegir el KG ({KG_PATH}): {exc}")
            self._kg = {}
    entry = self._kg.get(element, {})
    if not entry:
        return ""
    # Converteix l'entrada a text pla per incloure al prompt
    return "\n".join(f"{k}: {v}" for k, v in entry.items() if k != "curiositats")
```

---

## Implementació de `generate_response()`

```python
def generate_response(
    self, question: str, element: str | None, personality: str, kg_context: str
) -> str:
    if not hasattr(self, "_llm"):
        from config import SLM_MODEL_PATH
        from llama_cpp import Llama
        self._llm = Llama(
            model_path=str(SLM_MODEL_PATH),
            n_ctx=2048,
            n_threads=4,
            verbose=False,
        )

    system_prompt = PERSONALITY_PROMPTS.get(personality, PERSONALITY_PROMPTS["artistic"])
    user_content = question
    if element:
        user_content += f"\n\n[Element detectat a la foto: {element}]"
    if kg_context:
        user_content += f"\n\n[Context factual:\n{kg_context}]"

    output = self._llm.create_chat_completion(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_tokens=256,
        temperature=0.7,
    )
    return output["choices"][0]["message"]["content"].strip()
```

---

## Constants a afegir a `config.py`

```python
SLM_MODEL_PATH = MODELS_DIR / "slm" / "qwen2.5-1.5b-instruct-q4_k_m.gguf"
KG_PATH        = MODELS_DIR / "knowledge" / "gaudi_kg.json"
```

Veure `models/README.md` per saber com obtenir els fitxers.

> ⚠️ **Si canvies de model SLM o de nom de fitxer**: actualitza `SLM_MODEL_PATH`
> a `config.py`. El model es carrega en lazy load la primera crida.
>
> ⚠️ **Si canvies els noms de Personalitat** a `models/models.json`
> (`"artistic"`, `"technical"`, `"child"`): actualitza les claus de
> `PERSONALITY_PROMPTS` aquí perquè coincideixin.
>
> ⚠️ **Si canvies les claus del KG** (`gaudi_kg.json`): les claus han de
> coincidir amb el que retorna `VisionClassifier.classify()` — coordina
> entre `vision_module.py` i el fitxer JSON.

---

## Com provar-ho de forma aïllada (PAS 4 del pla de migració)

```python
# test_model.py (executa-ho des de la carpeta python/)
from model_module import ModelRegistry

models = ModelRegistry()

# Prova get_kg_context
ctx = models.get_kg_context("drac")
print(f"Context KG: {ctx[:200] if ctx else '(buit)'}")

# Prova generate_response
resposta = models.generate_response(
    question="Qui va fer aquest drac?",
    element="drac",
    personality="artistic",
    kg_context=ctx,
)
print(f"Resposta: {resposta}")
```

```bash
cd python/
python test_model.py
```

---

## Com es crida des de `main.py` (quan estigui llest)

```python
# dins del loop, bloc is_recording_active:
question_text = microphone.transcribe(wav_path)
site          = location.current()
photo_path    = camera.last_photo_path
element       = vision.classify(site, photo_path) if photo_path else None
kg_context    = models.get_kg_context(element) if element else ""
answer        = models.generate_response(
                    question=question_text,
                    element=element,
                    personality=model_name,   # ja calculat: models.name_for(button_id)
                    kg_context=kg_context,
                )
player.synthesize_and_play(answer)
```
