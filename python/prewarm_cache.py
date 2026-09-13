#!/usr/bin/env python3
"""
Pre-computes the SLM prefix cache so no visitor pays a cold prefill.

warm_prefix() fills this cache lazily: the first person to photograph an element
waits out the ~30s prefill, everyone after them gets it back from disk in a
fraction of a second. This script does that first pass up front, offline.

One state per element, not per personality -- the cached block is the facts, which
are the same whichever guide is speaking (see core/model_module.build_facts_block).

MUST be run on the board, with the model file and llama.cpp build the app will use.
A KV state is only valid for the exact tokens and the exact model it was computed
from; the cache key covers that, so a state generated elsewhere is not wrong, it
is simply never read.

Usage (from python/ on the board):

    python3 prewarm_cache.py                    # every element, skipping cached ones
    python3 prewarm_cache.py --list             # show what is cached, compute nothing
    python3 prewarm_cache.py --element cupula   # just one (repeatable)
    python3 prewarm_cache.py --force            # recompute even if cached

Expect roughly 30s per element and 6-12 MB per state. Interrupting it is safe:
each state is written atomically, and a later run picks up the ones still missing.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from config import (  # noqa: E402
    SLM_MODEL_PATH,
    SLM_PREFIX_CACHE_DIR,
    SLM_PREFIX_CACHE_MAX_MB,
)
from core.model_module import ModelRegistry, build_facts_block  # noqa: E402
from logging_setup import logger, setup_logging  # noqa: E402


def cache_size_mb() -> float:
    """Returns the total size of the prefix cache on disk, in MB."""
    return sum(f.stat().st_size for f in SLM_PREFIX_CACHE_DIR.glob("prefix_*.pkl")) / 1e6


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pre-compute the SLM prefix cache (run this on the board)."
    )
    parser.add_argument(
        "--element",
        action="append",
        metavar="ID",
        help="Element id to warm; repeatable. Defaults to every element in the "
             "knowledge base.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute states that are already cached.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Report what is cached and exit without loading the model.",
    )
    args = parser.parse_args()

    setup_logging()

    models = ModelRegistry()
    models._load_kg()
    if not models._kg_index:
        print("No knowledge sheets loaded — nothing to warm.", file=sys.stderr)
        return 1

    unknown = [e for e in (args.element or []) if e not in models._kg_index]
    if unknown:
        print(f"Unknown element id(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Known: {', '.join(sorted(models._kg_index))}", file=sys.stderr)
        return 1

    elements = args.element or sorted(models._kg_index)

    # Rendering the facts needs only the knowledge base, so --list can answer
    # without paying the model load.
    plan = []
    for eid in elements:
        facts = build_facts_block(eid, models.get_kg_context(eid))
        if not facts:
            continue
        plan.append((eid, facts, models._prefix_state_path(facts)))

    if args.list:
        print(f"{'element':30}{'state':>10}  file")
        for eid, _, path in plan:
            mark = f"{path.stat().st_size / 1e6:.1f} MB" if path.exists() else "-"
            print(f"{eid:30}{mark:>10}  {path.name if path.exists() else ''}")
        cached = sum(1 for _, _, p in plan if p.exists())
        print(f"\n{cached}/{len(plan)} cached, {cache_size_mb():.0f} MB in "
              f"{SLM_PREFIX_CACHE_DIR}")
        return 0

    todo = [(e, f, p) for e, f, p in plan if args.force or not p.exists()]
    if not todo:
        print(f"All {len(plan)} element(s) already cached "
              f"({cache_size_mb():.0f} MB). Nothing to do.")
        return 0

    if not SLM_MODEL_PATH.exists():
        print(f"SLM model not found at {SLM_MODEL_PATH}.", file=sys.stderr)
        return 1

    print(f"Warming {len(todo)} of {len(plan)} element(s). "
          f"Roughly {len(todo) * 30 // 60} min. Ctrl-C is safe.\n")

    if not models.preload():
        print("Could not load the SLM — is llama-cpp-python installed?",
              file=sys.stderr)
        return 1

    failures = 0
    for n, (eid, facts, path) in enumerate(todo, 1):
        if args.force and path.exists():
            path.unlink()
        started = time.perf_counter()
        with models._llm_lock:
            models._store_prefix(facts)
            # The context now holds this element's facts, and the next iteration
            # evaluates a different element's. Keep the bookkeeping honest so a
            # ModelRegistry reused after this loop does not trust a stale flag.
            models._prefix_facts = facts
            models._warm_key = None
        if path.exists():
            print(f"  [{n}/{len(todo)}] {eid:28} {time.perf_counter() - started:6.1f}s"
                  f"  {path.stat().st_size / 1e6:5.1f} MB")
        else:
            failures += 1
            print(f"  [{n}/{len(todo)}] {eid:28}  FAILED (see the log above)")

    total = cache_size_mb()
    print(f"\n{len(todo) - failures}/{len(todo)} warmed. "
          f"Cache is {total:.0f} MB in {SLM_PREFIX_CACHE_DIR}")
    if total > 0.9 * SLM_PREFIX_CACHE_MAX_MB:
        print(f"WARNING: within 10% of SLM_PREFIX_CACHE_MAX_MB "
              f"({SLM_PREFIX_CACHE_MAX_MB} MB) — states warmed earliest are being "
              f"evicted as later ones are written. Raise the cap in config.py and "
              f"re-run, or warm only the site this board stands at.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
