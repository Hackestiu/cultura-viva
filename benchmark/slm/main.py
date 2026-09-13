"""CulturaViva & SLM-Benchmark Unified CLI Entrypoint

Usage:
    uv run python main.py prepare --all              # Download models & build Arduino bundle
    uv run python main.py benchmark                  # Benchmark all SLMs over testset.json
    uv run python main.py benchmark --model qwen2.5:1.5b
    uv run python main.py eval --predictions <path>  # Score predictions with Ragas
"""

import sys
from scripts import prepare, benchmark
from eval.evaluate import main as run_evaluation


def main():
    if len(sys.argv) == 1:
        print(__doc__)
        sys.exit(0)

    command, *rest = sys.argv[1:]
    sys.argv = [sys.argv[0]] + rest

    if command == "prepare":
        prepare.main()
    elif command == "benchmark":
        benchmark.main()
    elif command in ("eval", "evaluate"):
        run_evaluation()
    else:
        print(f"Unknown command: '{command}'. Available commands: prepare, benchmark, eval")
        sys.exit(1)


if __name__ == "__main__":
    main()
