"""
Voice/response model selector associated with Modulino buttons A/B/C.

The models/ folder is where your own model files (weights, prompts, configs...) reside;
this module is responsible for knowing WHICH model name corresponds to each button,
for tagging recordings and for selecting which model to load when processing audio.

By default, each button maps to a generic personality name:
    A -> "model_a", B -> "model_b", C -> "model_c"

This can be overridden by creating models/models.json (see models/models.example.json):
    {"A": "artistic", "B": "technical", "C": "child"}
"""

import json

try:
    from config import MODELS_CONFIG_FILE, MODELS_DIR, VISION_UNKNOWN_LABEL
except ImportError:
    from config import MODELS_CONFIG_FILE, MODELS_DIR
    VISION_UNKNOWN_LABEL = "unknown"

_DEFAULT_NAMES = {"A": "artistic", "B": "technical", "C": "child"}

# System prompts for each Personality (Cultura Viva pipeline).
# Keys must match the values in models/models.json ("artistic", "technical", "child").
PERSONALITY_PROMPTS: dict[str, str] = {
    "artistic": (
        "You are an enthusiastic tour guide passionate about art and symbolism. "
        "You explain Gaudí's works emphasizing beauty, organic shapes, and inspiration. "
        "Directly and strictly answer ONLY what the user asks—do not give unsolicited background or extra explanations. "
        "You speak with passion and use evocative metaphors. "
        "Keep your response strictly under 3 short sentences (maximum 50 words). "
        "Always respond in the same language as the user's question."
    ),
    "technical": (
        "You are a tour guide specialized in architecture and engineering. "
        "You explain Gaudí's works focusing on construction techniques, materials, "
        "Directly and strictly answer ONLY what the user asks—do not give unsolicited background or extra explanations. "
        "and structural innovations. You are precise, rigorous, and cite facts and dimensions. "
        "Keep your response strictly under 3 short sentences (maximum 50 words). "
        "Always respond in the same language as the user's question."
    ),
    "child": (
        "You are a friendly tour guide for children aged 6 to 12. "
        "You explain Gaudí's works in a simple, fun, and engaging way full of curious facts. "
        "Directly and strictly answer ONLY what the user asks—do not give unsolicited background or extra explanations. "
        "You use simple analogies and an animated tone. Avoid complicated words. "
        "Keep your response strictly under 3 short sentences (maximum 50 words). "
        "Always respond in the same language as the user's question."
    ),
}


class ModelRegistry:
    def __init__(self):
        self._names = dict(_DEFAULT_NAMES)
        self._load_overrides()

    def _load_overrides(self) -> None:
        if not MODELS_CONFIG_FILE.exists():
            return
        try:
            with open(MODELS_CONFIG_FILE, "r", encoding="utf-8") as f:
                overrides = json.load(f)
            for button, name in overrides.items():
                key = button.strip().upper()
                if key in self._names and isinstance(name, str) and name.strip():
                    self._names[key] = name.strip()
        except (OSError, ValueError) as exc:
            print(f"[WARN] Could not read {MODELS_CONFIG_FILE}: {exc}")

    def name_for(self, button_id: str) -> str:
        """Name of the model assigned to this button ('A'/'B'/'C'). If the
        button is not recognized, returns the identifier itself."""
        return self._names.get(button_id.strip().upper(), button_id)

    @property
    def models_dir(self):
        return MODELS_DIR

    def _load_kg(self) -> None:
        """Lazily loads element_sheets.json and builds id and alias indices."""
        if hasattr(self, "_kg_index"):
            return
        from config import KG_PATH

        self._kg_index: dict = {}
        self._kg_alias_index: dict = {}  # alias.lower() -> id

        if not KG_PATH.exists():
            print(
                f"[WARN] element_sheets.json not found at {KG_PATH}. "
                "Returning empty KG context."
            )
            return

        try:
            with open(KG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            sheets = data.get("sheets", [])
            for sheet in sheets:
                sid = sheet.get("id", "")
                if sid:
                    self._kg_index[sid] = sheet
                    # Index by name and all aliases
                    for alias in [sheet.get("name", "")] + sheet.get("aliases", []):
                        if alias:
                            self._kg_alias_index[alias.lower()] = sid
            print(f"[OK] Knowledge sheets loaded: {len(self._kg_index)} elements")
        except (OSError, ValueError) as exc:
            print(f"[ERROR] Could not read element_sheets.json: {exc}")

    def _load_kg_base(self) -> dict:
        """Lazily loads knowledge_base.json. Returns {} on error."""
        if hasattr(self, "_kg_base"):
            return self._kg_base
        from config import KG_BASE_PATH

        self._kg_base: dict = {}
        if not KG_BASE_PATH.exists():
            return self._kg_base
        try:
            with open(KG_BASE_PATH, "r", encoding="utf-8") as f:
                self._kg_base = json.load(f)
            print(f"[OK] Knowledge base loaded.")
        except (OSError, ValueError) as exc:
            print(f"[ERROR] Could not read knowledge_base.json: {exc}")
        return self._kg_base

    def get_kg_context(self, element: str, personality: str = "artistic") -> str:
        """Returns a factual context string for *element* from the Gaudí knowledge sheets.

        Looks up element by id or alias (case-insensitive). If not found, tries
        knowledge_base.json. Returns '' if nothing is found.

        Mirrors the structure of GaudiKnowledgeStore.context_for_element() from
        slm-benchmark: own sheet + a short parent summary (if the element belongs
        to a larger monument) + top related elements. Kept deliberately compact
        (no full parent fact-dump) because the on-device SLM only has a 2048-token
        context window and the response budget is 128 tokens.

        :param element:     Element id or name from the vision module
                            (e.g. 'drac_park_guell', 'El Drac').
        :param personality: 'artistic' | 'technical' | 'child' — selects which
                            fact fields to prioritise in the returned string.
        """
        if not element or element == VISION_UNKNOWN_LABEL:
            return ""

        self._load_kg()

        # --- look up sheet by id, then by alias ---
        sheet = self._kg_index.get(element)
        if sheet is None:
            sid = self._kg_alias_index.get(element.lower())
            if sid:
                sheet = self._kg_index.get(sid)

        # --- fallback: monument level from knowledge_base.json ---
        if sheet is None:
            base = self._load_kg_base()
            entry = base.get(element, {})
            if entry:
                print(f"[INFO] KG: element '{element}' served from knowledge_base.json")
                return self._render_kb_entry(entry)
            print(f"[WARN] KG: element '{element}' not found in any knowledge file.")
            return ""

        return self._build_element_context(sheet, personality)

    def _build_element_context(self, sheet: dict, personality: str) -> str:
        """Assembles the full context for a sheet: own facts + parent summary
        + related elements, following the shape of benchmark.py's
        context_for_element() but trimmed for the on-device SLM's small
        context window."""
        parts = [self._format_sheet(sheet, personality)]

        parent_id = sheet.get("parent")
        if parent_id and parent_id != sheet.get("id"):
            parent_sheet = self._kg_index.get(parent_id)
            if parent_sheet is not None:
                parts.append(self._render_parent_summary(parent_sheet))

        related = sheet.get("similarities", [])[:2]
        for note in related:
            parts.append(f"Related: {note}")

        return "\n---\n".join(p for p in parts if p)

    def _render_parent_summary(self, parent_sheet: dict) -> str:
        """Compact 2-3 line summary of the parent monument/area a sub-element
        belongs to (e.g. the Dragon Stairway's parent is Park Güell). Unlike
        benchmark.py's _render_sheet (which dumps the full sheet for offline
        eval grounding), this stays short since it's extra context riding
        alongside the element's own facts."""
        name = parent_sheet.get("name", "")
        lines = [f"Part of: {name}"] if name else []
        if parent_sheet.get("creator"):
            lines.append(f"Creator: {parent_sheet['creator']}")
        if parent_sheet.get("inspiration"):
            lines.append(f"Context: {parent_sheet['inspiration']}")
        return "\n".join(lines)

    def _format_sheet(self, sheet: dict, personality: str) -> str:
        """Formats a knowledge sheet into a compact factual string for the SLM prompt."""
        lines: list[str] = []
        name = sheet.get("name", "")
        if name:
            lines.append(f"Element: {name}")

        # Fields shared by all personalities
        if sheet.get("creator"):
            lines.append(f"Creator: {sheet['creator']}")
        if sheet.get("timeline"):
            lines.append(f"Timeline: {sheet['timeline']}")

        if personality == "technical":
            for key in ("materials", "construction_process", "technical_figures"):
                val = sheet.get(key)
                if val:
                    if isinstance(val, list):
                        lines.append(f"{key}: {'; '.join(str(v) for v in val)}")
                    elif isinstance(val, dict) and val:
                        for k2, v2 in val.items():
                            lines.append(f"{k2}: {v2}")
                    else:
                        lines.append(f"{key}: {val}")
            for fact in sheet.get("technical_facts", []):
                lines.append(f"- {fact}")

        elif personality == "child":
            if sheet.get("inspiration"):
                lines.append(f"Inspiration: {sheet['inspiration']}")
            for fact in sheet.get("artistic_facts", [])[:3]:
                lines.append(f"- {fact}")
            for fact in sheet.get("general_knowledge_facts", [])[:2]:
                lines.append(f"- {fact}")

        else:  # artistic (default)
            if sheet.get("inspiration"):
                lines.append(f"Inspiration: {sheet['inspiration']}")
            for fact in sheet.get("artistic_facts", []):
                lines.append(f"- {fact}")
            for fact in sheet.get("general_knowledge_facts", []):
                lines.append(f"- {fact}")
            sims = sheet.get("similarities", [])
            if sims:
                lines.append(f"Connections: {'; '.join(sims)}")

        return "\n".join(lines)

    def _render_kb_entry(self, entry: dict) -> str:
        """Formats a knowledge_base.json (monument-level) entry into a compact,
        labeled string.

        Labels are derived from the JSON keys themselves ('unesco_status' ->
        'Unesco Status') rather than a hardcoded key/label table, so adding a
        new field to knowledge_base.json (e.g. 'restoration_year') shows up
        here automatically — no code change needed. 'name' is pulled to the
        top since every entry has one; list-of-strings fields (like
        'notable_facts') render as bullets, nested dicts are flattened one
        level, everything else is a single 'Label: value' line. Empty/falsy
        values are skipped.
        """
        lines: list[str] = []
        if name := entry.get("name"):
            lines.append(f"Name: {name}")

        for key, val in entry.items():
            if key == "name" or not val:
                continue
            label = key.replace("_", " ").title()

            if isinstance(val, list):
                if all(isinstance(v, str) for v in val):
                    lines.append(f"{label}:\n- " + "\n- ".join(val))
                else:
                    lines.append(f"{label}: {'; '.join(str(v) for v in val)}")
            elif isinstance(val, dict):
                for k2, v2 in val.items():
                    lines.append(f"{k2.replace('_', ' ').title()}: {v2}")
            else:
                lines.append(f"{label}: {val}")

        return "\n".join(lines).strip()

    def generate_response(
        self,
        question: str,
        element: str | None,
        personality: str,
        kg_context: str,
    ) -> str:
        """Generates a spoken response to question, adopting the tone defined by personality
        and grounded in kg_context and element when provided.
        Returns the generated text, or a descriptive error string if the model is unavailable
        (no exception is raised).

        :param question:    The user's transcribed question.
        :param element:     Gaudí element detected in the last photo, or None.
        :param personality: 'artistic' | 'technical' | 'child' (from name_for(button_id)).
        :param kg_context:  Factual context string from get_kg_context(), or ''.
        """
        from config import SLM_MODEL_PATH

        if not SLM_MODEL_PATH.exists():
            print(
                f"[WARN] SLM model not found at {SLM_MODEL_PATH}. "
                "Download it following the instructions in models/README.md. "
                "Response will be an error fallback."
            )
            return "(model not available — download the SLM to get responses)"

        if not hasattr(self, "_llm"):
            try:
                from llama_cpp import Llama
                self._llm = Llama(
                    model_path=str(SLM_MODEL_PATH),
                    n_ctx=512,           # context window (matches README; Qwen2.5-1.5B default)
                    n_threads=4,          # Cortex-A53 has 4 cores; use all for CPU layers
                    n_threads_batch=4,    # parallelise prefill on CPU layers
                    n_batch=128,          # larger prefill batches are faster on Adreno GPU path
                    n_gpu_layers=-1,      # offload ALL layers to Adreno GPU (-1 = auto-max)
                    use_mlock=True,       # lock weights in RAM; avoids paging under load
                    flash_attn=True,      # enabled: reduces memory bandwidth on GPU path
                    verbose=False,
                )
                print(f"[OK] SLM model loaded: {SLM_MODEL_PATH.name}")
            except ImportError:
                print(
                    "[WARN] llama-cpp-python is not installed. "
                    "Add 'llama-cpp-python' to requirements.txt and reinstall. "
                    "Response will be an error fallback."
                )
                self._llm = None

        if self._llm is None:
            return "(llama-cpp-python not installed — install it to get responses)"

        system_prompt = PERSONALITY_PROMPTS.get(
            personality, PERSONALITY_PROMPTS.get("artistic", "You are a tour guide.")
        )

        user_content = question or "(no question provided)"
        if element == VISION_UNKNOWN_LABEL:
            user_content += (
                "\n\n[Visual recognition: The photo does not match any architectural element of this monument. "
                "Politely and concisely tell the user (in your assigned guide personality) that the photo does not seem "
                "to show a recognized monument element, and invite them to capture an architectural element if they'd like details.]"
            )
        elif element:
            user_content += f"\n\n[Detected element in photo: {element}]"
        if kg_context:
            user_content += f"\n\n[Factual information about the element:\n{kg_context}]"

        try:
            output = self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=60,        # fewer decode steps → faster; prompt instructs ≤50 words
                temperature=0.1,      # low temperature = more factual, less hallucination
                repeat_penalty=1.1,   # slight penalty helps model hit <eos> sooner
                stop=["\n\n", "<|im_end|>"],  # early-stop on double newline or chat end token
            )
            answer = output["choices"][0]["message"]["content"].strip()
            print(f"[OK] SLM response generated ({len(answer)} characters).")
            return answer
        except Exception as exc:
            print(f"[ERROR] SLM failed to generate response: {exc}")
            return "(error generating response)"
