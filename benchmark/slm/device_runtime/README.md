# `device_runtime/` — the scripts that run inside the Arduino export bundle

`scripts/prepare.py` copies these into `arduino_export/` alongside the device's
own `knowledge_store.py` and `guide_prompt.py`, the knowledge JSON and the GGUF.

They live here as **real files** rather than inside string literals in
`prepare.py`, which is where they used to live. Source-in-a-string is how the
bundle drifted: somebody improved `arduino_export/gaudi_knowledge_store.py`
directly — adding a stop-word list and title/body scoring — and the generator
never received it, so the next `prepare --export-arduino` would have silently
reverted the improvement. A file can be reviewed, diffed, grepped and linted; a
string literal cannot.

They import `knowledge_store` and `guide_prompt` flat, because the bundle is a
flat directory. That is the same import the device uses, and it is why those two
modules sit at the top level of `arduino/python/` rather than under `core/`.

**They carry no prompt of their own.** They used to: a flat completion
("You are CulturaViva… Context: … Visitor: … Guide:") with no personality concept
at all, at `max_tokens=150` and `temperature=0.2` against the device's 60 and 0.1.
Anything prompt-shaped belongs in `arduino/python/guide_prompt.py`.

Runtime parameters come from `bundle_config.json`, which `prepare.py` generates
from `config.yaml` — so the bundle cannot disagree with the benchmark about
sampling either.
