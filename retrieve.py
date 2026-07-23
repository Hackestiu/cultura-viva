import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel
from typing import Any

EMBED_MODEL_NAME = "intfloat/e5-small-v2"

_tokenizer = None
_model = None


def _load_model() -> tuple[AutoTokenizer, AutoModel]:
    """Load the embedding model and tokenizer."""
    global _tokenizer, _model
    if _model is None:
        print(f"[RAG] Loading {EMBED_MODEL_NAME}...")
        _tokenizer = AutoTokenizer.from_pretrained(EMBED_MODEL_NAME)
        _model = AutoModel.from_pretrained(EMBED_MODEL_NAME)
        _model.eval()
    return _tokenizer, _model


def _mean_pooling(model_output: torch.Tensor, attention_mask: torch.Tensor) -> torch.Tensor:
    """Perform mean pooling on the model output."""
    token_embeddings = model_output[0]
    mask = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * mask, 1) / torch.clamp(mask.sum(1), min=1e-9)


def _embed_query(query: str) -> np.ndarray:
    """Embed the query using the embedding model."""
    tokenizer, model = _load_model()
    inputs = tokenizer(["query: " + query], padding=True, truncation=True,
                        max_length=512, return_tensors="pt")
    with torch.no_grad():
        output = model(**inputs)
    emb = _mean_pooling(output, inputs["attention_mask"])
    emb = torch.nn.functional.normalize(emb, p=2, dim=1)
    return emb.numpy()[0]


class RagIndex:
    def __init__(self, index_path: str="rag_index.npz") -> None:
        """Initialize the RAG index by loading embeddings and chunks from a .npz file."""
        data = np.load(index_path, allow_pickle=True)
        self.embeddings = data["embeddings"]
        self.chunks = data["chunks"]
        self.sources = data["sources"]
        print(f"[RAG] Index loaded: {len(self.chunks)} chunks")

    def retrieve(self, query: str, top_k: int = 3, min_score: float = 0.30) -> list[dict[str, Any]]:
        """Retrieve relevant chunks from the RAG index based on the query."""
        if len(self.chunks) == 0:
            return []
        query_emb = _embed_query(query)
        scores = self.embeddings @ query_emb  # normalized -> cos similarity
        top_idx = np.argsort(scores)[::-1][:top_k]
        results: list[dict[str, Any]] = []
        for i in top_idx:
            if scores[i] >= min_score:
                results.append({
                    "text": str(self.chunks[i]),
                    "source": str(self.sources[i]),
                    "score": float(scores[i]),
                })
        print(f"[RAG] Query: '{query[:60]}...' -> {len(results)} relevant chunks")
        return results