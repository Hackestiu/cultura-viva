"""Where the device application lives, and putting it on sys.path.

A leaf module on purpose: it imports nothing from the device and nothing from this
project's config, so anything that needs the device's modules can depend on it
without pulling in what the *other* importer needed.

That matters because the two importers want very different things.
`core.device_prompt` wants the prompt builders and is happy to pay for them;
`core.knowledge` wants the knowledge store and must not pay for `config`, which
probes for a camera, microphone and speaker on import. Splitting the path lookup
out is what lets the second one exist.
"""

from __future__ import annotations

import sys
from pathlib import Path

# benchmark/slm/core/device_paths.py -> repo root is three levels up.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEVICE_APP_DIR = REPO_ROOT / "arduino" / "python"

if not (DEVICE_APP_DIR / "knowledge_store.py").exists():
    raise ImportError(
        f"Cannot find the device application at {DEVICE_APP_DIR}. This benchmark "
        "imports the board's knowledge store and prompt builders from there so the "
        "two cannot drift apart. Run this from a full checkout of the monorepo."
    )

if str(DEVICE_APP_DIR) not in sys.path:
    sys.path.insert(0, str(DEVICE_APP_DIR))

__all__ = ["DEVICE_APP_DIR", "REPO_ROOT"]
