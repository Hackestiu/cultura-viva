"""Entry point for the Gaudí ragas evaluation pipeline.

The RAG + SLM pipeline under test lives in a separate repo; run it there to produce a
predictions file (see eval/predictions.example.json for the schema), then run this.
"""

from eval.evaluate import main as run_evaluation

if __name__ == "__main__":
    run_evaluation()
