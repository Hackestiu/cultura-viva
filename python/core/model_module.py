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

from config import MODELS_CONFIG_FILE, MODELS_DIR

_DEFAULT_NAMES = {"A": "artistic", "B": "technical", "C": "child"}

# System prompts for each Personality (Cultura Viva pipeline).
# Keys must match the values in models/models.json ("artistic", "technical", "child").
PERSONALITY_PROMPTS: dict[str, str] = {
    "artistic": (
        "You are an enthusiastic tour guide passionate about art and symbolism. "
        "You explain Gaudí's works emphasizing beauty, organic shapes, and inspiration. "
        "You speak with passion and use evocative metaphors. "
        "Always respond in the same language as the user's question."
    ),
    "technical": (
        "You are a tour guide specialized in architecture and engineering. "
        "You explain Gaudí's works focusing on construction techniques, materials, "
        "and structural innovations. You are precise, rigorous, and cite facts and dimensions. "
        "Always respond in the same language as the user's question."
    ),
    "child": (
        "You are a friendly tour guide for children aged 6 to 12. "
        "You explain Gaudí's works in a simple, fun, and engaging way full of curious facts. "
        "You use simple analogies and an animated tone. Avoid complicated words. "
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

        :param element:     Element id or name from the vision module
                            (e.g. 'drac_park_guell', 'El Drac').
        :param personality: 'artistic' | 'technical' | 'child' — selects which
                            fact fields to prioritise in the returned string.
        """
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
                return self._format_base_entry(entry)
            print(f"[WARN] KG: element '{element}' not found in any knowledge file.")
            return ""

        return self._format_sheet(sheet, personality)

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

    def _format_base_entry(self, entry: dict) -> str:
        """Formats a knowledge_base.json entry into a compact string."""
        lines: list[str] = []
        for k, v in entry.items():
            if isinstance(v, list):
                lines.append(f"{k}: {'; '.join(str(i) for i in v)}")
            elif isinstance(v, dict):
                for k2, v2 in v.items():
                    lines.append(f"{k2}: {v2}")
            else:
                lines.append(f"{k}: {v}")
        return "\n".join(lines)

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
                    n_ctx=2048,      # context_window
                    n_threads=4,     # threads (Cortex-A53 has 4 cores)
                    n_batch=256,     # batch_size for prompt processing
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
        if element:
            user_content += f"\n\n[Detected element in photo: {element}]"
        if kg_context:
            user_content += f"\n\n[Factual information about the element:\n{kg_context}]"

        try:
            output = self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                max_tokens=128,   # max_tokens: keeps responses concise for TTS
                temperature=0.1,  # low temperature = more factual, less hallucination
            )
            answer = output["choices"][0]["message"]["content"].strip()
            print(f"[OK] SLM response generated ({len(answer)} characters).")
            return answer
        except Exception as exc:
            print(f"[ERROR] SLM failed to generate response: {exc}")
            return "(error generating response)"
