# Do the guide personalities actually do anything?

The device offers three guide personalities — artistic, technical, child — on a
Modulino button. Nothing else in this repo shows that picking one changes what the
visitor hears, and the Ragas metrics next door structurally cannot: they score
whether an answer is factually right, and `AnswerCorrectness` scores it against
plain-register reference answers, which penalises the child and artistic voices
for doing exactly what they were asked to do.

This study asks two questions instead, both through a judge that never sees which
guide produced what.

1. **Can the guides be told apart?** The judge reads one answer and picks which of
   the three wrote it. Reported as a confusion matrix against a 33% chance
   baseline.
2. **Does a personality make the model invent things?** The judge reads the facts
   the model was given and the answer, and says whether every claim is supported.
   Reported as an unsupported rate per guide.

No board required — this runs entirely on the host through Ollama.

## Running it

```bash
ollama serve &
ollama pull qwen2.5:0.5b      # the model the device runs
ollama pull llama3.1:8b       # the judge

uv run python main.py personality
```

Useful flags:

| Flag | Why |
| --- | --- |
| `--no-judge` | Generate and diff only, zero judge calls. Fast iteration on the sheet. |
| `--reuse` | Re-judge saved answers instead of regenerating. |
| `--limit N` | First N probes only. |
| `--model` / `--judge-model` | Defaults are `qwen2.5:0.5b` and `llama3.1:8b`. |

Output lands in `results/`: `answers_<model>.json` (raw), plus
`personality_<model>.json` and `.html`. **Open the HTML** — the confusion matrix is
the headline but the side-by-side answers are what actually convince anyone.

## Design notes

**The prompts are imported, not copied.** `arms.py` pulls them from
`arduino/python/core/model_module.py` through `core/device_prompt.py`, so this
measures what ships and cannot drift from it.

**Unknown arm names are refused.** `build_system_prompt` resolves an unrecognised
personality by silently falling back to artistic, so a typo would generate a second
artistic arm and the study would compare it against itself and report a flawless
null. `resolve_arms` raises instead.

**The probes are open questions, and they are new.** The 38-question testset next
door is all closed factual items ("In which district is the Sagrada Família?"),
where three guides converge on one sentence whatever the prompt says — a floor
design for this question. `probes.json` asks one open question per element sheet
("Why does this look so strange?"), and each carries an `element_id`, so retrieval
goes through the direct-lookup path the device uses when vision names an element.
No item in the old testset has one, so that path had never been exercised.

**There are no reference answers,** deliberately. Grounding is judged against the
retrieved facts. Writing plain-register references and scoring against them is the
same mistake `AnswerCorrectness` makes.

**The judge is a different model family** from the candidate — `llama3.1:8b`
judging `qwen2.5:0.5b` — so we aren't asking a Qwen model to recognise its own
family's style. Its options are paraphrases ("an art-focused guide"), not the
shipped prompt text: handing over the prompts lets the judge match their vocabulary
against the answer's, which scores lexical overlap rather than style. Option order
is shuffled per item so a positional bias cannot beat chance.

**Persona echo is measured.** Small models often announce a persona ("As a friendly
guide for children…") rather than speaking in one, which would inflate judge
accuracy for the wrong reason. When any answer echoes its prompt, identification is
run a second time with those spans masked. A large gap between the two means the
model states its personality instead of enacting it.

**A warmup call precedes generation.** With a fixed seed the first call after a
cold model load differs from every later one, which then agree byte-for-byte.
Without the warmup the first probe would carry an anomaly the other 23 do not.

**Text similarity uses `difflib`, not embeddings.** The three answers are to the
same question about the same facts, so their embeddings sit at 0.85–0.95 no matter
what happens and the number says nothing. Near-identity is the thing worth knowing,
and a reader can check it by eye against the panels.

## What this cannot tell you

**Whether it matters to a visitor.** That needs human participants and the audio
path. An LLM preference judge measures an LLM's taste, so this study does not run
one.

**Why, if the guides turn out indistinguishable.** There is no positive control —
no deliberately loud persona run under the same constraints — so a null cannot
separate "the three prompts are too similar to each other" from "a 60-token cap and
'answer ONLY what the user asks' suppress any persona at all". Those have opposite
fixes. Report the null; don't pick a cause.

Worth knowing when reading a null: the three prompts are ~58 words each, of which
~28 are verbatim-identical across all three. Only about 30 words actually
distinguish a guide, and one of the shared sentences forbids the elaboration that
register normally lives in.
