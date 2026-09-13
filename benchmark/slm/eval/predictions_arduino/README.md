# On-device predictions (pre knowledge-store unification)

Six runs of `benchmark_arduino.py` on the Arduino UNO Q, one per candidate model,
kept as the record of real on-device latency. They used to live in
`arduino_export/`, which is now generated and gitignored, so they moved here.

**They are not comparable to `eval/predictions_*.json` from the PC, and never
were.** Three reasons, all fixed in `device_runtime/benchmark_arduino.py`:

- They carry **one** retrieved passage per question; the PC run retrieves three.
  Ragas scores `ContextPrecision` and `ContextRecall` per passage, so the two sets
  of context metrics measure different things.
- They were generated with a **flat completion prompt and no guide personality** —
  `"You are CulturaViva… Context: … Question: … Answer:"` — while the device and the
  PC benchmark both send chat messages with one of three personality prompts.
- Retrieval used the export bundle's own keyword scorer over its own prose
  renderer, which by then had drifted from the device's.

What remains valid in them is the timing: `elapsed_s` and `tokens` are genuine
Cortex-A53 measurements. Median latency for Qwen2.5-0.5B was 19.2 s against a
3 s target, which is the number that motivated the context-engineering work.

Regenerate with `python3 benchmark_arduino.py --personality technical` inside a
freshly built bundle.
