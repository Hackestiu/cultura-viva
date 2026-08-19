# slm-benchmark

A [Ragas](https://docs.ragas.io/) evaluation pipeline for a RAG + small-language-model (SLM)
system focused exclusively on the Catalan architect **Antoni Gaudí**.

The evaluation database comes from the `g2 rag` repository. The current 19-item testset is
curated open-question QA: each item contains an `id`, `question`, and reference answer.


This repo is **evaluation-only**. The RAG + SLM pipeline under test (retrieval + generation)
lives in a separate repo — run it there to produce a predictions file, then evaluate it here.
Every model used for evaluation is free and local (no paid or hosted APIs, no Groq):

| Role              | Model                                      | Notes                          |
|-------------------|---------------------------------------------|----------------------------------|
| Judge LLM          | Any Ollama model, e.g. `qwen2.5:7b`        | Local, free — prefer a stronger model than the SLM under test |
| Judge embeddings   | `sentence-transformers/all-MiniLM-L6-v2`   | Local, no API key                |

## Project layout

```
eval/testset.json              Curated Gaudí question / reference-answer pairs (with ids)
eval/predictions.example.json  Schema example for the predictions file the other repo must produce
eval/evaluate.py               Joins testset + predictions, scores with ragas
main.py                        Entry point: uv run python main.py
```

## Setup

1. Install dependencies (uses [uv](https://docs.astral.sh/uv/)):

   ```bash
   uv sync
   ```

2. Install and start [Ollama](https://ollama.com), then pull a judge model:

   ```bash
    ollama serve            # in one terminal (Windows: start the Ollama app instead)
    ollama pull qwen2.5:7b  # in another
   ```

   Prefer a larger/stronger model than whatever SLM is under test in the other repo —
   self-grading with the same small model is unreliable for nuanced metrics like faithfulness.

3. Copy `.env.example` to `.env` and adjust if needed:

   ```bash
   cp .env.example .env
   ```

## Producing predictions (in the other repo)

Run the RAG + SLM pipeline over every question in `eval/testset.json` and export a JSON file
matching `eval/predictions.example.json`. The production file must contain exactly one entry
for each of the 19 testset IDs:

```json
[
  {
    "id": "sagrada-interior-columns",
    "contexts": ["... retrieved chunk(s) used to answer ..."],
    "answer": "... the SLM's generated answer ..."
  }
]
```

- `id` must match the corresponding entry's `id` in `eval/testset.json`; IDs must be unique.
- `contexts` is the non-empty list of retrieved passages the generator was given.
- `answer` is the pipeline's final generated response.
- The evaluator rejects missing, duplicate, or unexpected IDs.

Copy or point the resulting file at this repo (default path: `eval/predictions.json`, override
with `PREDICTIONS_PATH` in `.env` or `--predictions`).

## Running the evaluation

```bash
uv run python main.py
# or equivalently
uv run python -m eval.evaluate --predictions path/to/predictions.json
```

This will:
1. Load `eval/testset.json` and the predictions file, joining them by `id`.
2. Score each sample with ragas metrics — `AnswerCorrectness`, `AnswerRelevancy`,
   `Faithfulness`, `ContextPrecision`, and `ContextRecall` — using a local Ollama model as
   the judge LLM and local Hugging Face embeddings for embedding-based metrics.
3. Print aggregate scores and save a per-question CSV under `eval/results/`.


## Notes on scope

- `eval/testset.json` is deliberately scoped to Gaudí only (biography, architectural
  style/techniques, and his major works). Add entries there (with a unique `id`) to extend
  coverage — the other repo's pipeline will then need a matching prediction for each new `id`.
- Swap `OLLAMA_JUDGE_MODEL` in `.env` to compare judge quality/consistency across models.
