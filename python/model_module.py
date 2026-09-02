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

    # ------------------------------------------------------------------
    # Methods for the Cultura Viva pipeline.
    # name_for() and existing methods remain untouched.
    # ------------------------------------------------------------------

    def get_kg_context(self, element: str) -> str:
        """Queries the Gaudí knowledge graph for the detected element.
        Returns a string of factual context, or '' if the element is not found
        in the KG or if the KG file does not exist yet.

        The KG is loaded lazily on the first call.
        """
        from config import KG_PATH

        if not KG_PATH.exists():
            print(
                f"[WARN] Knowledge graph not found at {KG_PATH}. "
                "Create it following the instructions in models/README.md. "
                "Returning empty context string."
            )
            return ""

        if not hasattr(self, "_kg"):
            try:
                with open(KG_PATH, "r", encoding="utf-8") as f:
                    self._kg = json.load(f)
                print(f"[OK] Knowledge graph loaded: {len(self._kg)} elements")
            except (OSError, ValueError) as exc:
                print(f"[ERROR] Could not read KG ({KG_PATH}): {exc}")
                self._kg = {}

        entry = self._kg.get(element, {})
        if not entry:
            print(f"[WARN] Element '{element}' not found in knowledge graph.")
            return ""

        # Convert entry into plain text for inclusion in the SLM prompt
        lines = []
        for k, v in entry.items():
            if k == "curiosities" and isinstance(v, list):
                lines.append(f"curiosities: {'; '.join(str(c) for c in v)}")
            elif k == "curiositats" and isinstance(v, list):
                lines.append(f"curiosities: {'; '.join(str(c) for c in v)}")
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
        """Inference with SLM (Qwen2.5 via llama-cpp-python) using the
        system prompt of the selected Personality.
        Returns the generated response text, or a descriptive error message
        if the model is unavailable (no exception is raised).

        :param question:    transcribed text from Whisper (user question)
        :param element:     detected element from VisionClassifier, or None
        :param personality: 'artistic' | 'technical' | 'child' (name_for(button_id))
        :param kg_context:  factual context from KG (get_kg_context())
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
                    n_ctx=2048,
                    n_threads=4,
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
                max_tokens=256,
                temperature=0.7,
            )
            answer = output["choices"][0]["message"]["content"].strip()
            print(f"[OK] SLM response generated ({len(answer)} characters).")
            return answer
        except Exception as exc:
            print(f"[ERROR] SLM failed to generate response: {exc}")
            return "(error generating response)"
