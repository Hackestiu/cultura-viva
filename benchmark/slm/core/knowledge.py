"""Semantic retrieval layered on the device's knowledge store.

The device looks an element up by the id vision gives it. The testset has no
element ids and asks architect-level and cross-monument questions that no single
sheet answers, so passages are retrieved semantically here. That is the one
deliberate difference from the board, and it is why this subclass exists.

Everything else is inherited. `context_for_element`, `display_name` and the sheet
renderers come from `KnowledgeStore` in `arduino/python/knowledge_store.py`, so the
id path renders exactly what the board renders. This project used to maintain its
own renderer, which produced a prose blob the device has never emitted -- the
personality study, whose 24 probes all carry an `element_id`, was scoring it.

A sheet gets three different text projections and they are not interchangeable:

- **prompt text** -- `render_sheet`, labeled and capped. Frozen: it is the KV
  prefix cache key on the board.
- **search text** -- `_search_text`, flat and uncapped, for keyword scoring only.
- **chunk text** -- `_build_chunks` below, one or two sentences. Short on purpose:
  a 1900-character labeled block is a poor embedding unit, and using the prompt
  renderer here would collapse this index from 62 chunks to 28.
"""

from __future__ import annotations

from core.config import cfg
from core.device_prompt import KnowledgeStore


class SemanticKnowledgeStore(KnowledgeStore):
    """KnowledgeStore plus a dense vector index over granular passages.

    The embedder is built on first use rather than in __init__. The personality
    study inherits this class but only ever calls `context_for_element`, and it was
    paying for a SentenceTransformer load and 62 encodes on every run to reach a
    code path that touches neither.
    """

    def __init__(self, embedding_model: str | None = None, sheets_path=None, kb_path=None):
        super().__init__(
            sheets_path=sheets_path or cfg.element_sheets_path,
            kb_path=kb_path or cfg.knowledge_base_path,
        )
        self._embedding_model = embedding_model or cfg.embedding_model
        self._embedder = None
        self._chunks: list[dict] | None = None
        self._chunk_embeddings = None

    def _ensure_index(self) -> None:
        if self._embedder is not None:
            return
        # Imported here, not at module scope: this is the only code path that needs
        # torch, and keeping it local is what makes the lazy load actually lazy.
        import numpy as np
        from sentence_transformers import SentenceTransformer

        print(f"Initializing semantic retriever with {self._embedding_model}...")
        self._embedder = SentenceTransformer(self._embedding_model)
        self._chunks = self._build_chunks()
        self._chunk_embeddings = self._embedder.encode(
            [c["text"] for c in self._chunks], normalize_embeddings=True
        )
        self._np = np
        print(f"Indexed {len(self._chunks)} semantic knowledge chunks.")

    def _build_chunks(self) -> list[dict]:
        """Granular passages to embed: one overview and one per notable fact for each
        knowledge-base entry, and one condensed passage per element sheet."""
        chunks: list[dict] = []

        # 1. Knowledge Base entries: overview chunk + per-fact chunks
        for k, v in self.kb.items():
            name = v.get("name", k)
            overview = (
                f"{name}. Location: {v.get('location', '')}. "
                f"Architect: {v.get('architect', '')}. Style: {v.get('style', '')}. "
                f"Status: {v.get('status', '')}. UNESCO: {v.get('unesco_status', '')}."
            )
            chunks.append({"id": f"{k}_overview", "title": name, "text": overview.strip()})
            for i, fact in enumerate(v.get("notable_facts", [])):
                chunks.append({"id": f"{k}_fact_{i}", "title": name, "text": f"{name}: {fact}"})

        # 2. Element sheets
        for sheet in self.sheets_by_id.values():
            s_name = sheet.get("name")
            # The parent's display name, not its raw id. These chunks are handed to the
            # model as retrieved context, and interpolating the id put
            # "Serpentine Bench (part of park_guell)" in the prompt -- the snake_case
            # leak that made the model read identifiers aloud and invent around them.
            parent_id = sheet.get("parent")
            parent = self.display_name(parent_id) if parent_id else None
            mats = ", ".join(sheet.get("materials", []))
            tech = " ".join(sheet.get("technical_facts", []))
            art = " ".join(sheet.get("artistic_facts", []))
            text = (
                f"{s_name} (part of {parent or s_name}). Materials: {mats}. "
                f"{sheet.get('inspiration', '')} {tech} {art}"
            ).strip()
            chunks.append({"id": sheet.get("id"), "title": s_name, "text": text})

        return chunks

    def retrieve_top_k(self, query: str, k: int = 3) -> list[str]:
        """The k most semantically relevant passages, as a list.

        A list, not a joined string: Ragas scores ContextPrecision and ContextRecall
        per retrieved passage, so collapsing these into one would make precision
        trivially 1.0.
        """
        self._ensure_index()
        q_emb = self._embedder.encode([query], normalize_embeddings=True)
        sims = self._np.dot(self._chunk_embeddings, q_emb.T).squeeze()
        top_idx = self._np.argsort(-sims)[:k]
        return [self._chunks[i]["text"] for i in top_idx]

    def context_for_topic(self, query: str, k: int = 3) -> str:
        """Semantic override of the base class's keyword search.

        The board keeps the keyword implementation -- it cannot run
        sentence-transformers. Here the embeddings are available, so use them.
        """
        return "\n\n---\n\n".join(self.retrieve_top_k(query, k=k))
