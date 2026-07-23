"""
It builds the vector index for the RAG system from text documents (.txt / .md).

Usage:
    python3 build_index.py ./knowledge_base ./rag_index.npz
"""
import sys
import glob
import os
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel

EMBED_MODEL_NAME = "intfloat/e5-small-v2"  
CHUNK_SIZE_WORDS = 180
CHUNK_OVERLAP_WORDS = 40
BATCH_SIZE = 16


def load_documents(folder) -> list[tuple[str, str]]:
    """Load all .txt and .md documents from the given folder."""
    docs: list[tuple[str, str]] = []
    patterns = ["**/*.txt", "**/*.md"]
    for pattern in patterns:
        for path in glob.glob(os.path.join(folder, pattern), recursive=True):
            with open(path, "r", encoding="utf-8") as f:
                docs.append((path, f.read()))
    return docs


def chunk_text(text: str, size: int = CHUNK_SIZE_WORDS, overlap: int = CHUNK_OVERLAP_WORDS) -> list[str]:
    """Split the text into overlapping chunks of words."""
    words = text.split()
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = start + size
        chunk = " ".join(words[start:end])
        if chunk.strip():
            chunks.append(chunk)
        start += size - overlap
    return chunks


def mean_pooling(model_output, attention_mask) -> torch.Tensor:
    """Perform mean pooling on the model output."""
    token_embeddings = model_output[0]
    mask = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return torch.sum(token_embeddings * mask, 1) / torch.clamp(mask.sum(1), min=1e-9)


def embed_texts(texts: list[str], tokenizer: AutoTokenizer, model: AutoModel, prefix: str = "passage: ") -> np.ndarray:
    """Embed a list of texts using the embedding model."""
    inputs = tokenizer([prefix + t for t in texts], padding=True, truncation=True,
                        max_length=512, return_tensors="pt")
    with torch.no_grad():
        output = model(**inputs)
    embeddings = mean_pooling(output, inputs["attention_mask"])
    embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
    return embeddings.numpy()


def main() -> None:
    """Main function to build the RAG index from documents."""
    if len(sys.argv) < 2:
        print("Usage: python3 build_index.py <documents_folder> [output.npz]")
        sys.exit(1)

    folder = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else "rag_index.npz"

    print(f"[RAG] Loading embedding model {EMBED_MODEL_NAME}...")
    tokenizer = AutoTokenizer.from_pretrained(EMBED_MODEL_NAME)
    model = AutoModel.from_pretrained(EMBED_MODEL_NAME)
    model.eval()

    docs = load_documents(folder)
    print(f"[RAG] {len(docs)} documents found in {folder}")
    if not docs:
        print("[RAG] No .txt/.md documents found. Aborting.")
        sys.exit(1)

    all_chunks: list[str] = []
    all_sources: list[str] = []
    for path, text in docs:
        for chunk in chunk_text(text):
            all_chunks.append(chunk)
            all_sources.append(os.path.basename(path))

    print(f"[RAG] {len(all_chunks)} fragments generated. Calculating embeddings...")

    all_embeddings: list[np.ndarray] = []
    for i in range(0, len(all_chunks), BATCH_SIZE):
        batch = all_chunks[i:i + BATCH_SIZE]
        all_embeddings.append(embed_texts(batch, tokenizer, model))
        print(f"[RAG]   {min(i + BATCH_SIZE, len(all_chunks))}/{len(all_chunks)}")

    embeddings = np.vstack(all_embeddings)

    np.savez(out_path,
             embeddings=embeddings,
             chunks=np.array(all_chunks, dtype=object),
             sources=np.array(all_sources, dtype=object))
    print(f"[RAG] Index saved in {out_path} ({embeddings.shape[0]} fragments, dim={embeddings.shape[1]})")


if __name__ == "__main__":
    main()