# Personality runs before the knowledge store was unified

These runs are **not comparable to current ones**, and the reason is the point of
the change that superseded them.

`personality/arms.py` says it builds "the exact chat messages the device would
send", and the prompt builders really were imported from the device. The *context*
was not. `study.py` fed them `GaudiKnowledgeStore.context_for_element` — a renderer
this project maintained separately, which the board has never run. So the study
measured a prompt that did not ship, which is exactly the failure
`core/device_prompt.py` was written to prevent, one layer down.

Concretely, every one of the 24 probe contexts in `answers_*.json` differs from
what the device produces:

| | old (benchmark renderer) | new (device renderer) |
| --- | --- | --- |
| shape | one prose paragraph | labeled lines (`Element:`, `Creator:`, `Timeline:`, `Purpose:` …) |
| `creator`, `timeline` | **dropped** | present |
| facts | uncapped | 2 technical + 2 artistic + 1 general |
| parent | `(part of park_guell)` — raw vision label | `Part of: Park Güell` |

Two graded hallucinations in `personality_qwen2.5_0.5b.json` trace straight to
that first row. Casa Batlló's context named only Josep Batlló, from `inspiration`,
because `creator` was dropped — and the model answered *"Casa Batlló is a modernist
building by Josep Batlló"*. Park Güell's context had no `timeline`, and the model
answered *"designed in the 1920s"* (it was built 1900–1914).

So the headline numbers here — identification 41.7% against a 33.3% baseline, and
22/72 answers with an unsupported claim — describe a prompt nobody ships. Whether
they hold against the real one is an open question, and re-measuring it is the
next step, not something this archive answers.

What does carry over: the format-compliance counts are a property of the
personality prompts and the 60-token cap, not of the renderer. The child guide
failed its closing-question requirement on 19 of 19 answers that terminated
normally, so that finding is not a truncation artefact.

Regenerate with `uv run python main.py personality`.
