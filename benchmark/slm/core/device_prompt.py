"""Bridge to the prompt construction the device actually ships.

This benchmark used to carry its own copy of the prompt: one flat string with a
generic "CulturaViva" persona. The device has since moved to chat messages whose
system turn puts the retrieved facts *first* and the personality instructions
second -- an ordering llama.cpp's prefix KV cache depends on. The two drifted,
and the benchmark ended up scoring a prompt that no longer shipped.

So rather than copy the prompt again, this imports it. `arduino/python` is a
sibling folder in this monorepo, and its prompt builders are pure functions over
(question, element, personality, kg_context). Importing them means a change to
the guide's wording shows up in the next benchmark run automatically.

Importing `core.model_module` pulls in the device's `config`, which probes for a
camera, microphone and speaker on import and logs a warning for each when run off
the board. Harmless here, and quietened below.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path

# benchmark/slm/core/device_prompt.py -> repo root is three levels up.
REPO_ROOT = Path(__file__).resolve().parents[3]
DEVICE_APP_DIR = REPO_ROOT / "arduino" / "python"

if not (DEVICE_APP_DIR / "core" / "model_module.py").exists():
    raise ImportError(
        f"Cannot find the device application at {DEVICE_APP_DIR}. The benchmark "
        "imports its prompt builders from there so the two cannot drift apart. "
        "Run this from a full checkout of the monorepo."
    )

if str(DEVICE_APP_DIR) not in sys.path:
    sys.path.insert(0, str(DEVICE_APP_DIR))

def _quieten_device_logging() -> None:
    """Keep the device's hardware-discovery warnings out of benchmark output.

    The device logs through loguru when it is installed and falls back to a
    stdlib shim on the "cultura" logger when it is not. This project does not
    depend on loguru, so the fallback is the path that actually runs here.
    """
    os.environ.setdefault("CULTURA_LOG_LEVEL", "ERROR")
    logging.getLogger("cultura").setLevel(logging.ERROR)
    try:
        from loguru import logger
    except ImportError:
        return
    logger.remove()
    logger.add(sys.stderr, level="ERROR")


_quieten_device_logging()


def _load_device_model_module():
    """Load arduino/python/core/model_module.py under its own module name.

    It cannot be imported as `core.model_module`: this project has its own
    top-level `core` package, which would shadow the device's. Loading by path
    sidesteps the collision. The device's own imports (`config`, `logging_setup`)
    are absolute and resolve through DEVICE_APP_DIR on sys.path.
    """
    path = DEVICE_APP_DIR / "core" / "model_module.py"
    spec = importlib.util.spec_from_file_location("cultura_device_model_module", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_device = _load_device_model_module()

PERSONALITY_PROMPTS: dict[str, str] = _device.PERSONALITY_PROMPTS
build_facts_block = _device.build_facts_block
build_messages = _device.build_messages
build_system_prompt = _device.build_system_prompt

PERSONALITIES: tuple[str, ...] = tuple(PERSONALITY_PROMPTS)

__all__ = [
    "PERSONALITIES",
    "PERSONALITY_PROMPTS",
    "build_facts_block",
    "build_messages",
    "build_system_prompt",
    "DEVICE_APP_DIR",
]
