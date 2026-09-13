# Baseline: the original tone-instruction prompts

Results from the personality prompts as they were before format constraints were
introduced, kept so the change is measurable rather than asserted.

Those prompts told each guide *how to sound* — "you speak with passion and use
evocative metaphors", "you are precise, rigorous", "you use simple analogies and
an animated tone". Measured against a `llama3.1:8b` judge on `qwen2.5:0.5b`:

| | value |
| --- | --- |
| Blind identification | 28/72 = 38.9% (chance 33.3%, binomial p = 0.19) |
| child guide recall | 1/24 = 4% |
| Judge self-test | 3/3 — the instrument works; the guides sounded alike |

Regenerate the current numbers with `uv run python main.py personality`.
