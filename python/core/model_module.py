"""
Personality selection and response generation.

Maps the three Modulino buttons (A/B/C) to named "guide personalities"
(artistic, technical, child by default, overridable via models/models.json),
retrieves factual context for a detected element from the knowledge base
files, and generates the spoken response using a local SLM (Qwen2.5-1.5B via
llama-cpp-python).
"""

import hashlib
import json
import os
import pickle
import re
import threading
import time

try:
    from logging_setup import logger
except ImportError:  # module used standalone, without the app root on sys.path
    from loguru import logger

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
        "Keep your response strictly under 3 short sentences (maximum 50 words)."
    ),
    "technical": (
        "You are a tour guide specialized in architecture and engineering. "
        "You explain Gaudí's works focusing on construction techniques, materials, "
        "Directly and strictly answer ONLY what the user asks—do not give unsolicited background or extra explanations. "
        "and structural innovations. You are precise, rigorous, and cite facts and dimensions. "
        "Keep your response strictly under 3 short sentences (maximum 50 words)."
    ),
    "child": (
        "You are a friendly tour guide for children aged 6 to 12. "
        "You explain Gaudí's works in a simple, fun, and engaging way full of curious facts. "
        "Directly and strictly answer ONLY what the user asks—do not give unsolicited background or extra explanations. "
        "You use simple analogies and an animated tone. Avoid complicated words. "
        "Keep your response strictly under 3 short sentences (maximum 50 words)."
    ),
}


# Sentence boundary: terminal punctuation followed by whitespace or end of text.
# The lookahead keeps "1.5 metres" and "Gaudi's" from splitting, which matters
# because every emitted chunk is spoken aloud immediately.
_SENTENCE_END = re.compile(r"""[.!?…]['"\)\]]*(?=\s|$)""")

# Below this, a chunk is too short to be worth a separate Piper invocation and
# its prosody sounds clipped; it is held back and merged into the next one.
MIN_SENTENCE_CHARS = 12


def build_facts_block(element: str | None, kg_context: str) -> str:
    """Renders the photo-dependent head of the system prompt: what vision detected and
    the facts retrieved for it.

    This block is deliberately free of anything personality-specific, and
    build_system_prompt puts it first, because it is the part that gets cached. llama.cpp
    reuses the longest common *prefix* of its KV cache and nothing else, so a block can
    only be restored from disk if it sits at the very front of the prompt -- see
    ModelRegistry.warm_prefix.

    Returns an empty string when there is nothing photo-dependent to say, in which case
    there is also nothing worth caching.
    """
    parts: list[str] = []

    if element == VISION_UNKNOWN_LABEL:
        parts.append(
            "[Visual recognition: The photo does not match any architectural element of this monument. "
            "Politely and concisely tell the user (in your assigned guide personality) that the photo does not seem "
            "to show a recognized monument element, and invite them to capture an architectural element if they'd like details.]"
        )
    elif element:
        parts.append(f"[Detected element in photo: {element}]")

    if kg_context:
        parts.append(f"[Factual information about the element:\n{kg_context}]")

    return "\n\n".join(parts)


def build_system_prompt(
    element: str | None, personality: str, kg_context: str
) -> str:
    """Assembles the system message: what vision detected and the retrieved facts first,
    the personality instructions second.

    That order is what makes the prefix cache possible -- the facts are identical for
    every personality, so one cached KV state per element serves all three, and editing a
    personality prompt invalidates none of them. It also puts the instructions closer to
    the question, which small models tend to follow better.

    The rendered prompt up to the user turn is identical for every question asked about
    the same photo with the same personality, so llama.cpp treats it as a cache hit once
    warm_prefix() has evaluated it.
    """
    instructions = PERSONALITY_PROMPTS.get(
        personality, PERSONALITY_PROMPTS.get("artistic", "You are a tour guide.")
    )
    facts = build_facts_block(element, kg_context)
    return f"{facts}\n\n{instructions}" if facts else instructions


def build_messages(
    question: str, element: str | None, personality: str, kg_context: str
) -> list[dict]:
    """Builds the chat messages for one question. The user turn holds nothing but the
    question, so it is the only part of the rendered prompt that changes between
    questions about the same photo."""
    return [
        {
            "role": "system",
            "content": build_system_prompt(element, personality, kg_context),
        },
        {"role": "user", "content": question or "(no question provided)"},
    ]


class ModelRegistry:
    def __init__(self):
        """Initializes the button-to-personality mapping from defaults, then applies any overrides found in models/models.json."""
        self._names = dict(_DEFAULT_NAMES)
        self._load_overrides()
        # llama.cpp holds one KV cache per context and is not reentrant, so the
        # background prefill thread and the foreground generation must never be
        # inside it at once. Whichever starts first runs to completion; the other
        # waits, which is no worse than doing the prefill inline.
        self._llm_lock = threading.RLock()
        self._warm_key: tuple | None = None
        # The facts block currently sitting at the front of llama.cpp's KV cache. Used to
        # tell "the cache already starts with these facts" from "it starts with another
        # element's", so a second question about the same photo is not answered by
        # throwing away a warmer in-memory cache to reload a colder one from disk.
        self._prefix_facts: str | None = None

    def _load_overrides(self) -> None:
        """Applies personality-name overrides from models/models.json onto the default A/B/C mapping, ignoring unrecognized keys or malformed entries and leaving defaults untouched if the file is absent or unreadable."""
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
            logger.warning("Could not read {}: {}", MODELS_CONFIG_FILE, exc)

    def name_for(self, button_id: str) -> str:
        """Returns the personality name assigned to a hardware button ('A', 'B', or 'C'), or the button id itself if it has no mapping."""
        return self._names.get(button_id.strip().upper(), button_id)

    @property
    def models_dir(self):
        """Exposes the root directory containing model weights, prompts, and configuration files."""
        return MODELS_DIR

    def _load_kg(self) -> None:
        """Lazily loads element_sheets.json into an index by element id and an alias index (alias, lowercased, mapped to id); a no-op once already loaded, and leaves both indices empty if the file is missing."""
        if hasattr(self, "_kg_index"):
            return
        from config import KG_PATH

        self._kg_index: dict = {}
        self._kg_alias_index: dict = {}  # alias.lower() -> id

        if not KG_PATH.exists():
            logger.warning(
                "element_sheets.json not found at {}. Returning empty KG context.",
                KG_PATH,
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
                    for alias in [sheet.get("name", "")] + sheet.get("aliases", []):
                        if alias:
                            self._kg_alias_index[alias.lower()] = sid
            logger.success(
                "Knowledge sheets loaded: {} elements", len(self._kg_index)
            )
        except (OSError, ValueError) as exc:
            logger.exception("Could not read element_sheets.json: {}", exc)

    def _load_kg_base(self) -> dict:
        """Lazily loads and caches knowledge_base.json, which provides monument-level overview context used as a fallback when a specific element sheet is unavailable."""
        if hasattr(self, "_kg_base"):
            return self._kg_base
        from config import KG_BASE_PATH

        self._kg_base: dict = {}
        if not KG_BASE_PATH.exists():
            return self._kg_base
        try:
            with open(KG_BASE_PATH, "r", encoding="utf-8") as f:
                self._kg_base = json.load(f)
            logger.success("Knowledge base loaded.")
        except (OSError, ValueError) as exc:
            logger.exception("Could not read knowledge_base.json: {}", exc)
        return self._kg_base

    def get_kg_context(self, element: str) -> str:
        """Retrieves and formats factual context for an architectural element. Falls back
        to monument-level overview data if no specific element sheet is found, and returns
        an empty string if the element is empty, unknown, or absent from both knowledge
        files.

        The result deliberately does not depend on the personality. The three guides differ
        in how they speak, not in what is true, and one rendering shared by all of them is
        what lets a single cached KV state per element serve every button -- see
        warm_prefix(). Personality selects the *voice* in PERSONALITY_PROMPTS, which sits
        after this block in the prompt and is prefilled live.
        """
        if not element or element == VISION_UNKNOWN_LABEL:
            return ""

        self._load_kg()

        # look up sheet by id, then by alias
        sheet = self._kg_index.get(element)
        if sheet is None:
            sid = self._kg_alias_index.get(element.lower())
            if sid:
                sheet = self._kg_index.get(sid)

        # fallback: monument level from knowledge_base.json
        if sheet is None:
            base = self._load_kg_base()
            entry = base.get(element, {})
            if entry:
                logger.info(
                    "KG: element {!r} served from knowledge_base.json", element
                )
                return self._render_kb_entry(entry)
            logger.warning(
                "KG: element {!r} not found in any knowledge file.", element
            )
            return ""

        return self._build_element_context(sheet)

    def _build_element_context(self, sheet: dict) -> str:
        """Assembles the full context block for an element sheet: its own facts, a short
        summary of its parent monument if any, and up to two related-element notes,
        following the shape used by benchmark.py's context builder but trimmed for the
        on-device SLM's small context window."""
        parts = [self._format_sheet(sheet)]

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
        """Produces a compact 2-3 line summary of the parent monument or area a sub-element belongs to (e.g. Park Güell for the Dragon Stairway). Unlike benchmark.py's full-sheet renderer used for offline eval grounding, this stays short since it rides alongside the element's own facts."""
        name = parent_sheet.get("name", "")
        lines = [f"Part of: {name}"] if name else []
        if parent_sheet.get("creator"):
            lines.append(f"Creator: {parent_sheet['creator']}")
        if parent_sheet.get("inspiration"):
            lines.append(f"Context: {parent_sheet['inspiration']}")
        return "\n".join(lines)

    def _format_sheet(self, sheet: dict) -> str:
        """Formats a knowledge sheet into a compact factual string for the SLM prompt.

        One rendering serves all three personalities. The per-personality field selection
        this replaced saved perhaps forty tokens of prompt, and cost a separate cached KV
        state per personality -- a bad trade once the prefix is read from disk rather than
        prefilled. The per-kind caps keep the block near the size the artistic rendering
        used to be, which matters for a 0.5B model's attention even though the prefill is
        now free.
        """
        lines: list[str] = []
        name = sheet.get("name", "")
        if name:
            lines.append(f"Element: {name}")

        if sheet.get("creator"):
            lines.append(f"Creator: {sheet['creator']}")
        if sheet.get("timeline"):
            lines.append(f"Timeline: {sheet['timeline']}")
        if sheet.get("inspiration"):
            lines.append(f"Inspiration: {sheet['inspiration']}")

        for key in ("materials", "construction_process", "technical_figures"):
            val = sheet.get(key)
            if not val:
                continue
            if isinstance(val, list):
                lines.append(f"{key}: {'; '.join(str(v) for v in val)}")
            elif isinstance(val, dict):
                for k2, v2 in val.items():
                    lines.append(f"{k2}: {v2}")
            else:
                lines.append(f"{key}: {val}")

        for fact in sheet.get("technical_facts", [])[:2]:
            lines.append(f"- {fact}")
        for fact in sheet.get("artistic_facts", [])[:2]:
            lines.append(f"- {fact}")
        for fact in sheet.get("general_knowledge_facts", [])[:1]:
            lines.append(f"- {fact}")

        # similarities are deliberately not rendered here: _build_element_context
        # already appends the first two as "Related:" lines. Emitting them in both
        # places, as the artistic rendering used to, spent tokens saying the same
        # thing twice to a model with 1024 of them.

        return "\n".join(lines)

    def _render_kb_entry(self, entry: dict) -> str:
        """Formats a monument-level knowledge_base.json entry into a labeled string, deriving each label from its JSON key so new fields appear automatically without code changes. The 'name' field is surfaced first; list-of-strings fields render as bullets, nested dicts are flattened one level, and empty or falsy values are skipped."""
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

    def _ensure_llm(self):
        """Loads and caches the Llama instance on first call, returning it (or None if the
        model file is missing or llama-cpp-python is not installed). Subsequent calls are
        a no-op, so this is safe to call both from preload() and from generate_response()."""
        if hasattr(self, "_llm"):
            return self._llm

        from config import SLM_MODEL_PATH

        if not SLM_MODEL_PATH.exists():
            logger.warning(
                "SLM model not found at {}. Download it following the instructions "
                "in models/README.md.",
                SLM_MODEL_PATH,
            )
            self._llm = None
            return None

        try:
            from llama_cpp import Llama  # type: ignore[import]

            self._llm = Llama(
                model_path=str(SLM_MODEL_PATH),
                # Headroom for the largest knowledge sheet. The facts block is restored
                # from disk rather than prefilled (see warm_prefix), so a longer context
                # costs KV cache memory -- about 25 MB here -- and no latency.
                n_ctx=2048,  # context window
                n_threads=4,  # Cortex-A53 has 4 cores
                n_threads_batch=4,  # parallelise prefill across the 4 cores
                n_batch=128,  # larger prefill batches amortise per-batch overhead
                # No n_gpu_layers: llama-cpp-python is built CPU-only here (the build in
                # models/README.md passes no GGML_OPENCL/GGML_VULKAN backend flag), so
                # requesting GPU offload was silently ignored. Inference runs on the
                # Cortex-A53 cores; add a backend at build time before offloading.
                use_mlock=True,  # lock weights in RAM
                flash_attn=True,  # reduces memory bandwidth during attention
                verbose=False,
            )
            logger.success("SLM model loaded: {}", SLM_MODEL_PATH.name)
        except ImportError:
            logger.warning(
                "llama-cpp-python is not installed. Add 'llama-cpp-python' to "
                "requirements.txt and reinstall. Response will be an error fallback."
            )
            self._llm = None
        except Exception as exc:
            logger.exception("Could not load SLM model: {}", exc)
            self._llm = None

        return self._llm

    def preload(self) -> bool:
        """Eagerly loads the SLM weights and the knowledge-base indices so the first user
        question does not pay the cold-start cost. Returns True if the SLM is ready.

        Safe to call more than once and safe to skip entirely: generate_response() still
        falls back to loading on demand if this was never called or failed.
        """
        self._load_kg()
        self._load_kg_base()
        return self._ensure_llm() is not None

    def _prefix_state_path(self, facts: str):
        """Returns the on-disk path of the cached KV state for a facts block.

        Keyed by the model filename and the facts text, so swapping the GGUF or editing a
        knowledge sheet lands on a different filename rather than restoring a state whose
        tokens no longer match. Personality is deliberately absent: the facts block is the
        same for all three, which is the whole point of caching only that much.
        """
        from config import SLM_MODEL_PATH, SLM_PREFIX_CACHE_DIR

        digest = hashlib.sha256(
            f"{SLM_MODEL_PATH.name}\x00{facts}".encode("utf-8")
        ).hexdigest()[:32]
        return SLM_PREFIX_CACHE_DIR / f"prefix_{digest}.pkl"

    def _restore_prefix(self, facts: str) -> bool:
        """Loads the cached KV state for a facts block into the live context, if there is
        one. Returns True if the prefill of those tokens can now be skipped.

        Caller must hold _llm_lock. A miss, a corrupt file or a state from another build
        all return False and cost nothing but the normal prefill -- llama.cpp compares the
        restored tokens against the ones it is about to evaluate and truncates the cache
        wherever they diverge, so a stale state can make the answer slow, never wrong.
        """
        path = self._prefix_state_path(facts)
        if not path.exists():
            return False
        try:
            started = time.perf_counter()
            with open(path, "rb") as f:
                self._llm.load_state(pickle.load(f))
            os.utime(path, None)  # mark as recently used for _prune_prefix_cache
            logger.info(
                "SLM prefix restored from cache in {:.2f}s ({})",
                time.perf_counter() - started,
                path.name,
            )
            return True
        except Exception as exc:
            logger.warning("Could not restore prefix cache {}: {}", path.name, exc)
            try:
                path.unlink()
            except OSError:
                pass
            return False

    def _store_prefix(self, facts: str) -> None:
        """Evaluates the facts block on its own and writes the resulting KV state to disk.

        Caller must hold _llm_lock, and must call this *before* anything personality- or
        question-specific has been evaluated: what gets saved is whatever is in the cache,
        and the point is to save the facts and nothing after them.

        Writing is best-effort throughout. The cache is an optimisation; a full disk or a
        pickle that chokes on this llama-cpp-python's LlamaState must cost a slow prefill,
        not an answer.
        """
        path = self._prefix_state_path(facts)
        try:
            self._llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": facts},
                    {"role": "user", "content": "(no question provided)"},
                ],
                max_tokens=1,
                temperature=0.1,
            )
            tmp = path.with_suffix(".tmp")
            with open(tmp, "wb") as f:
                pickle.dump(self._llm.save_state(), f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, path)
            logger.info(
                "SLM prefix cached: {} ({:.1f} MB)",
                path.name,
                path.stat().st_size / 1e6,
            )
            self._prune_prefix_cache()
        except Exception as exc:
            logger.warning("Could not cache SLM prefix: {}", exc)

    @staticmethod
    def _prune_prefix_cache() -> None:
        """Drops least-recently-used states until the cache fits SLM_PREFIX_CACHE_MAX_MB,
        so adding locations cannot quietly fill the board's eMMC."""
        from config import SLM_PREFIX_CACHE_DIR, SLM_PREFIX_CACHE_MAX_MB

        try:
            files = sorted(
                SLM_PREFIX_CACHE_DIR.glob("prefix_*.pkl"),
                key=lambda f: f.stat().st_mtime,
            )
            total = sum(f.stat().st_size for f in files)
            budget = SLM_PREFIX_CACHE_MAX_MB * 1_000_000
            while files and total > budget:
                victim = files.pop(0)
                total -= victim.stat().st_size
                victim.unlink()
                logger.info("Evicted prefix cache entry {}", victim.name)
        except OSError as exc:
            logger.warning("Could not prune the prefix cache: {}", exc)

    def warm_prefix(
        self, element: str | None, personality: str, kg_context: str | None = None
    ) -> bool:
        """Gets the photo-dependent part of the prompt into llama.cpp's KV cache before
        the question exists, so generate_response only has to prefill the question itself.

        On the UNO Q's Cortex-A53 cores a ~400-token prompt costs upwards of 25 seconds to
        prefill, and it would otherwise be prefilled after the visitor has finished
        speaking -- dead time they sit through. The element is known the moment the photo
        is validated, several seconds before recording even starts, so doing it there makes
        it free. Except that "several seconds" was never reliably 25 of them: warm_prefix
        holds _llm_lock, and a visitor who asked a short question waited out the remainder.

        So the facts are no longer prefilled at all after the first time. The KV cache for
        a block of tokens is a pure function of the model and those tokens, so it is saved
        to disk on first use and restored on every later one, which takes a fraction of a
        second. Only the ~94-token personality tail is still evaluated live, and *that*
        does fit in the overlap.

        Returns True if the cache was warmed. Retrieves the KG context itself when not
        supplied, so callers can fire this off knowing only the element and personality.
        """
        llm = self._ensure_llm()
        if llm is None:
            return False

        if kg_context is None:
            kg_context = self.get_kg_context(element) if element else ""

        key = (element, personality)
        facts = build_facts_block(element, kg_context)

        with self._llm_lock:
            if self._warm_key == key:
                return True
            try:
                started = time.perf_counter()

                # Skipped when the cache already opens with these facts -- a second
                # question about the same photo, or a personality switch. Restoring then
                # would replace a cache that covers the whole prompt with one that covers
                # only its head, and charge for the difference.
                if facts and self._prefix_facts != facts:
                    if not self._restore_prefix(facts):
                        self._store_prefix(facts)
                    self._prefix_facts = facts

                # An empty question: the rendered prompt then shares every token up to
                # the user turn with the real call, which is all of the expensive part.
                # max_tokens=1 is the cheapest way to make llama.cpp evaluate it.
                llm.create_chat_completion(
                    messages=build_messages("", element, personality, kg_context),
                    max_tokens=1,
                    temperature=0.1,
                )
                self._warm_key = key
                logger.info(
                    "SLM prefix warmed for element={!r} personality={!r} in {:.1f}s",
                    element,
                    personality,
                    time.perf_counter() - started,
                )
                return True
            except Exception as exc:
                # Warming is an optimisation: a failure here must not stop the answer,
                # it only means generate_response pays the full prefill as before.
                logger.warning("SLM prefix warm-up failed: {}", exc)
                self._prefix_facts = None
                return False

    def warm_prefix_async(
        self, element: str | None, personality: str
    ) -> "threading.Thread | None":
        """Runs warm_prefix() on a daemon thread and returns immediately, so the caller
        can keep serving the UI loop while the prompt prefills. Returns the thread, or
        None if there is nothing to warm."""
        if not element:
            return None
        thread = threading.Thread(
            target=self.warm_prefix,
            args=(element, personality),
            name="slm-prefill",
            daemon=True,
        )
        thread.start()
        return thread

    def generate_response(
        self,
        question: str,
        element: str | None,
        personality: str,
        kg_context: str,
        is_active_fn=None,
        on_sentence=None,
    ) -> str | None:
        """Generates a spoken audio-guide reply from the on-device SLM using token streaming,
        adopting the given personality and conditioning on the user's question, the detected
        element (if any), and retrieved factual context. Lazily loads and caches the Llama model
        on first call.

        If is_active_fn is provided, it is called between each generated token: if it returns
        False the generation loop is interrupted immediately and None is returned, allowing the
        caller to skip TTS and reset the pipeline without waiting for the full response.

        If on_sentence is provided, it is called with each complete sentence as soon as that
        sentence is finished rather than only at the end, so the caller can start speaking the
        first sentence while the rest is still decoding. Decode runs at roughly three tokens a
        second on this board, so waiting for all of them before any sound comes out costs the
        user most of the perceived latency. The trailing fragment, if the model stops without
        terminal punctuation, is emitted as a final chunk.

        Returns the generated answer string, None if cancelled mid-generation, or a descriptive
        fallback string if the model file or the llama-cpp-python dependency is missing, or if
        inference fails.
        """
        from config import SLM_MODEL_PATH

        if not SLM_MODEL_PATH.exists():
            logger.warning(
                "SLM model not found at {}. Download it following the instructions "
                "in models/README.md. Response will be an error fallback.",
                SLM_MODEL_PATH,
            )
            return "(model not available — download the SLM to get responses)"

        if self._ensure_llm() is None:
            return "(llama-cpp-python not installed — install it to get responses)"

        messages = build_messages(question, element, personality, kg_context)

        try:
            # The lock makes a still-running warm_prefix finish first; the prompt it
            # left in the KV cache is this call's prefix, so llama.cpp re-evaluates
            # only the question.
            with self._llm_lock:
                # stream=True lets us check for cancellation between each token so the
                # generation loop can be interrupted immediately when the user presses
                # the cancel button, instead of blocking for the full synchronous call,
                # and lets us hand finished sentences to TTS while decoding continues.
                stream = self._llm.create_chat_completion(
                    messages=messages,
                    max_tokens=60,  # fewer decode steps → faster
                    temperature=0.1,  # low temperature = more factual
                    repeat_penalty=1.1,  # slight penalty helps model hit <eos> sooner
                    stop=[
                        "\n\n",
                        "<|im_end|>",
                    ],  # early-stop on double newline or chat end token
                    stream=True,
                )

                tokens: list[str] = []
                pending = ""  # text generated but not yet handed to on_sentence
                # Whatever happens below — completion, cancellation, an exception —
                # the KV cache no longer ends at the warmed prefix, so the next
                # question must warm again rather than trust a stale flag. The facts
                # do still sit at the front of it, though, and recording that is what
                # keeps a follow-up question about the same photo from reloading a
                # cached prefix it is already past.
                self._warm_key = None
                self._prefix_facts = build_facts_block(element, kg_context) or None
                for chunk in stream:
                    # Check cancellation between every generated token
                    if is_active_fn is not None and not is_active_fn():
                        logger.info(
                            "SLM generation cancelled by user after {} token(s).",
                            len(tokens),
                        )
                        return None

                    delta = chunk["choices"][0].get("delta", {})
                    token_text = delta.get("content", "")
                    if not token_text:
                        continue

                    tokens.append(token_text)
                    if on_sentence is None:
                        continue

                    pending += token_text
                    ready, pending = _split_ready_sentences(pending)
                    for sentence in ready:
                        on_sentence(sentence)

            answer = "".join(tokens).strip()

            if on_sentence is not None and pending.strip():
                on_sentence(pending.strip())

            logger.success(
                "SLM response generated ({} characters).", len(answer)
            )
            return answer
        except Exception as exc:
            logger.exception("SLM failed to generate response: {}", exc)
            return "(error generating response)"


def _split_ready_sentences(text: str) -> tuple[list[str], str]:
    """Splits off every complete sentence at the front of text, returning them along with
    the unterminated remainder to carry into the next token.

    A boundary that would produce a chunk shorter than MIN_SENTENCE_CHARS is skipped
    rather than abandoned, so a brief opener ("Yes.") is merged into the sentence after
    it instead of stalling every later split behind it.
    """
    sentences: list[str] = []
    last_cut = 0
    for match in _SENTENCE_END.finditer(text):
        cut = match.end()
        candidate = text[last_cut:cut].strip()
        if len(candidate) < MIN_SENTENCE_CHARS:
            continue
        sentences.append(candidate)
        last_cut = cut
    return sentences, text[last_cut:].lstrip()
