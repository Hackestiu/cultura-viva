"""Does the guide personality a visitor picks actually change what they hear?

Two questions, both answered by an LLM judge that never sees which guide produced
what:

  1. Can the guides be told apart?  The judge reads one answer and picks which of
     the three guides wrote it.  Reported as a confusion matrix against a 33%
     chance baseline.
  2. Does a personality make the model invent things?  The judge reads the
     retrieved facts and the answer and says whether every claim is supported.
     Reported as an unsupported rate per guide.

Deliberately not measured: reading grade, word lists, figurative-language rates
and the rest.  Those quantify differences a judge can already detect, and a
hand-written "artistic-sounding words" list mostly tests whether the model agrees
with the list-writer's guess.

Usage:
    uv run python main.py personality
    uv run python main.py personality --no-judge        # generate + diff only
    uv run python main.py personality --model qwen2.5:1.5b
    uv run python main.py personality --judge-model llama3.1:8b
    uv run python main.py personality --reuse           # re-judge saved answers
"""

from __future__ import annotations

import argparse
import difflib
import json
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from core.config import cfg
from core.device_prompt import PERSONALITY_PROMPTS
from personality import report
from personality.arms import (
    FORMAT_REQUIREMENT,
    assert_arms_distinct,
    follows_format,
    messages_for,
    resolve_arms,
)
from core.knowledge import SemanticKnowledgeStore
from core.ollama import ollama_chat

HERE = Path(__file__).resolve().parent
PROBES_PATH = HERE / "probes.json"
RESULTS_DIR = HERE / "results"

# Chance level for the identification task, stated once so the report cannot
# drift from the number of arms actually run.
def chance(n_arms: int) -> float:
    return 1.0 / n_arms


# What the judge is offered as options. Paraphrases, NOT the shipped prompts:
# handing over the prompt text lets the judge match its vocabulary against the
# answer's, which scores lexical overlap rather than style.
JUDGE_LABELS: dict[str, str] = {
    "artistic": "an art-focused guide, who talks about beauty, shapes and symbolism",
    "technical": "an engineering-focused guide, who talks about construction, materials and structure",
    "child": "a children's guide, who explains things simply and playfully",
}


# --------------------------------------------------------------------------
# Generation
# --------------------------------------------------------------------------

def load_probes() -> list[dict]:
    with open(PROBES_PATH, encoding="utf-8") as fh:
        return json.load(fh)["probes"]


def warmup(model_tag: str) -> None:
    """Burn one throwaway call so the model is loaded before real generation.

    Measured, not assumed: with a fixed seed the first call after a cold load
    differs from every later one, which then agree byte-for-byte. Without this
    the first probe of a run would carry an anomaly the other 23 do not, and it
    would silently land in arm order, hitting whichever guide happens to go first.
    """
    ollama_chat(model_tag, [{"role": "user", "content": "hello"}],
                options={"num_predict": 1})


def generate(model_tag: str, arms: list[str], probes: list[dict], store: SemanticKnowledgeStore) -> list[dict]:
    """Answer every probe as every guide. Facts are retrieved once per probe and
    shared across arms, so the only thing that varies is the personality text."""
    warmup(model_tag)
    rows = []
    for i, probe in enumerate(probes, 1):
        element_id = probe["element_id"]
        kg_context = store.context_for_element(element_id)

        # Pre-flight on the first probe: if two arms render the same system
        # prompt, the run is meaningless and it is better to find out now.
        if i == 1:
            assert_arms_distinct(arms, element_id, kg_context)

        for arm in arms:
            messages = messages_for(probe["question"], arm, element_id, kg_context)
            result = ollama_chat(model_tag, messages)
            print(f"  [{i}/{len(probes)}] {probe['id']:<28} {arm:<10} "
                  f"{result['elapsed_s']:>5.2f}s  {result['done_reason'] or '?'}")
            rows.append({
                "probe_id": probe["id"],
                "element_id": element_id,
                "kind": probe["kind"],
                "question": probe["question"],
                "arm": arm,
                "answer": result["answer"],
                "context": kg_context,
                "elapsed_s": result["elapsed_s"],
                "done_reason": result["done_reason"],
                "eval_count": result["eval_count"],
                "follows_format": follows_format(arm, result["answer"]),
            })
    return rows


# --------------------------------------------------------------------------
# Free diagnostics -- no model calls
# --------------------------------------------------------------------------

def echo_span(row: dict) -> str | None:
    """Longest run of words the answer lifted verbatim from its own personality
    prompt.

    A small model often announces its persona ("As a friendly guide for children
    ...") instead of speaking in it. That inflates judge accuracy for the wrong
    reason: the judge reads the label off the text rather than recognising a
    voice. Measured so the identification result can be re-read with those spans
    masked.
    """
    instructions = PERSONALITY_PROMPTS[row["arm"]].lower()
    words = re.findall(r"[a-z']+", row["answer"].lower())
    best = ""
    for start in range(len(words)):
        for end in range(start + 4, len(words) + 1):  # 4+ words, shorter is coincidence
            span = " ".join(words[start:end])
            if span in instructions:
                if len(span) > len(best):
                    best = span
            else:
                break
    return best or None


def mask_echo(answer: str, span: str | None) -> str:
    if not span:
        return answer
    pattern = re.compile(re.escape(span).replace(r"\ ", r"\s+"), re.IGNORECASE)
    return pattern.sub("[...]", answer)


def agreement(rows: list[dict], arms: list[str]) -> list[dict]:
    """Per probe, how similar the arms' answers are to each other.

    difflib rather than embedding cosine: the three answers are to the same
    question about the same facts, so their embeddings sit at 0.85-0.95 whatever
    happens and the number says nothing. Near-identity is the thing worth
    knowing, and a reader can check it by eye against the panels.
    """
    by_probe: dict[str, dict[str, str]] = {}
    for r in rows:
        by_probe.setdefault(r["probe_id"], {})[r["arm"]] = r["answer"]

    out = []
    for probe_id, answers in by_probe.items():
        ratios = []
        for i, a in enumerate(arms):
            for b in arms[i + 1:]:
                if a in answers and b in answers:
                    ratios.append(difflib.SequenceMatcher(None, answers[a], answers[b]).ratio())
        if ratios:
            out.append({
                "probe_id": probe_id,
                "max_similarity": round(max(ratios), 3),
                "mean_similarity": round(sum(ratios) / len(ratios), 3),
                "any_identical": max(ratios) == 1.0,
            })
    return out


# --------------------------------------------------------------------------
# Judge
# --------------------------------------------------------------------------

def _judge_call(judge_model: str, prompt: str) -> str:
    result = ollama_chat(
        judge_model,
        [{"role": "user", "content": prompt}],
        options={"temperature": 0.0, "num_predict": 24, "stop": [], "seed": cfg.inference_seed},
    )
    return result["answer"].strip()


def identify(rows: list[dict], arms: list[str], judge_model: str, seed: int, mask: bool) -> list[dict]:
    """Blind 3-way identification, one call per answer.

    Option order is shuffled per item so a judge with a positional bias cannot
    score above chance by always picking the first option.
    """
    rng = random.Random(seed)
    out = []
    for i, row in enumerate(rows, 1):
        options = list(arms)
        rng.shuffle(options)
        letters = "ABC"[:len(options)]
        menu = "\n".join(f"{L}. {JUDGE_LABELS[o]}" for L, o in zip(letters, options))

        answer = mask_echo(row["answer"], row.get("echo_span")) if mask else row["answer"]
        prompt = (
            "Three tour guides at a Gaudi monument each answer visitors in their own style.\n"
            f"{menu}\n\n"
            "Read the answer below and decide which guide gave it, judging only by "
            "the style and tone of the writing.\n\n"
            f"Visitor question: {row['question']}\n"
            f"Answer: {answer}\n\n"
            f"Reply with a single letter ({'/'.join(letters)}) and nothing else."
        )
        raw = _judge_call(judge_model, prompt)
        m = re.search(rf"\b([{letters}])\b", raw.upper())
        predicted = options[letters.index(m.group(1))] if m else None
        print(f"  [{i}/{len(rows)}] id   {row['probe_id']:<28} true={row['arm']:<10} "
              f"pred={predicted or '?':<10} {'' if predicted == row['arm'] else 'x'}")
        out.append({
            "probe_id": row["probe_id"], "arm": row["arm"],
            "predicted": predicted, "raw": raw, "options": options,
        })
    return out


# Hand-written texts that are unmistakably one voice each. They exist to check the
# judge, not the guides: if identification comes back at chance, the first question
# is whether the instrument works at all, and this answers it without adding an arm
# to the study. Written by hand rather than generated, so they are independent of
# anything the candidate model produces.
HARNESS_FIXTURES: list[tuple[str, str]] = [
    ("child",
     "Imagine a giant stone forest! Gaudi made 86 fat columns that hold up the roof "
     "like tree trunks. And guess what? When it rains, the water sneaks down inside "
     "them into a secret tank below!"),
    ("technical",
     "The hall employs 86 Doric-inspired columns on a 6-metre grid. Each is hollow, "
     "functioning as a downpipe that channels roof runoff to a 1,200 cubic metre "
     "cistern beneath the slab."),
    ("artistic",
     "Step into a petrified grove, where light falls between trunks of pale stone "
     "like sun through leaves. Gaudi shaped the ceiling in swirling mosaic, so the "
     "whole room seems to breathe."),
]


def check_judge(arms: list[str], judge_model: str, seed: int) -> dict:
    """Can the judge identify voices that genuinely are different?

    A null identification result has two possible causes -- the guides sound alike,
    or the judge cannot tell voices apart at all -- and they are not the same
    finding. This separates them.
    """
    rows = [{"probe_id": f"fixture_{i}", "arm": arm, "question": "What is this room?",
             "answer": text, "echo_span": None}
            for i, (arm, text) in enumerate(HARNESS_FIXTURES) if arm in arms]
    res = identify(rows, arms, judge_model, seed, mask=False)
    correct = sum(1 for r in res if r["predicted"] == r["arm"])
    return {"correct": correct, "total": len(res),
            "passed": correct == len(res),
            "detail": [{"true": r["arm"], "predicted": r["predicted"]} for r in res]}


def grounding(rows: list[dict], judge_model: str) -> list[dict]:
    """Is every claim in the answer supported by the facts the model was given?

    Reference-free on purpose. Scoring against the plain-register reference
    answers in eval/testset.json would mark the child guide down for sounding
    like a child, which is a style penalty wearing an accuracy label.
    """
    out = []
    for i, row in enumerate(rows, 1):
        prompt = (
            "You are checking a tour guide's answer for invented information.\n\n"
            f"FACTS THE GUIDE WAS GIVEN:\n{row['context']}\n\n"
            f"VISITOR QUESTION: {row['question']}\n"
            f"GUIDE'S ANSWER: {row['answer']}\n\n"
            "Is every factual claim in the answer supported by the facts above? "
            "Ignore differences of tone, style or wording; judge only the facts. "
            "General knowledge that is clearly true and uncontroversial counts as supported.\n"
            "Reply with exactly one word: SUPPORTED or UNSUPPORTED."
        )
        raw = _judge_call(judge_model, prompt)
        verdict = "UNSUPPORTED" if "UNSUPPORTED" in raw.upper() else (
            "SUPPORTED" if "SUPPORTED" in raw.upper() else None)
        print(f"  [{i}/{len(rows)}] fact {row['probe_id']:<28} {row['arm']:<10} {verdict or '?'}")
        out.append({"probe_id": row["probe_id"], "arm": row["arm"], "verdict": verdict, "raw": raw})
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="main.py personality",
        description="Measure whether the three guide personalities change the model's output.",
    )
    parser.add_argument("--model", default="qwen2.5:1.5b",
                        help="Candidate model to study (default: the model the device runs).")
    parser.add_argument("--judge-model", default="llama3.1:8b",
                        help="Judge model. Deliberately a different family from the candidate.")
    parser.add_argument("--arms", nargs="+", default=None,
                        help=f"Personalities to run (default: all of {list(PERSONALITY_PROMPTS)}).")
    parser.add_argument("--skip-judge-check", action="store_true",
                        help="Skip the judge self-test on hand-written distinct voices.")
    parser.add_argument("--no-judge", action="store_true",
                        help="Generate and diff only; no judge calls.")
    parser.add_argument("--reuse", action="store_true",
                        help="Re-judge the saved answers instead of regenerating.")
    parser.add_argument("--seed", type=int, default=0, help="Seed for judge option shuffling.")
    parser.add_argument("--limit", type=int, default=None, help="Only the first N probes.")
    args = parser.parse_args()

    arms = resolve_arms(args.arms)
    probes = load_probes()
    if args.limit:
        probes = probes[:args.limit]

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    slug = args.model.replace(":", "_")
    raw_path = RESULTS_DIR / f"answers_{slug}.json"

    print(f"Model      : {args.model}")
    print(f"Judge      : {args.judge_model}")
    print(f"Arms       : {arms}")
    print(f"Probes     : {len(probes)}")

    if args.reuse:
        if not raw_path.exists():
            sys.exit(f"[Error] --reuse needs {raw_path}, which does not exist. Run without it first.")
        saved = json.loads(raw_path.read_text(encoding="utf-8"))
        rows = saved["answers"]
        for r in rows:
            r.setdefault("context", saved["contexts"][r["probe_id"]])
            r["follows_format"] = follows_format(r["arm"], r["answer"])
        print(f"Reusing {len(rows)} saved answers from {raw_path.name}\n")
    else:
        print(f"\nGenerating {len(probes) * len(arms)} answers...")
        store = SemanticKnowledgeStore()
        rows = generate(args.model, arms, probes, store)
        for row in rows:
            row["echo_span"] = echo_span(row)
        # The retrieved facts are identical across arms by construction, so they are
        # stored once per probe rather than repeated on all three rows.
        contexts = {r["probe_id"]: r.pop("context") for r in rows}
        raw_path.write_text(json.dumps({
            "model": args.model, "arms": arms,
            "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "inference": {
                "temperature": cfg.inference_temperature,
                "max_tokens": cfg.inference_max_tokens,
                "repeat_penalty": cfg.inference_repeat_penalty,
                "stop": list(cfg.inference_stop),
                "seed": cfg.inference_seed,
            },
            "contexts": contexts,
            "answers": rows,
        }, indent=2, ensure_ascii=False), encoding="utf-8")
        for r in rows:
            r["context"] = contexts[r["probe_id"]]
        print(f"Saved answers -> {raw_path.name}")

    similarity = agreement(rows, arms)
    ident = ident_masked = facts = judge_check = None
    if not args.no_judge:
        if not args.skip_judge_check:
            print("\nJudge self-test on hand-written distinct voices...")
            judge_check = check_judge(arms, args.judge_model, args.seed)
            verdict = "PASS" if judge_check["passed"] else "FAIL"
            print(f"  {verdict}: {judge_check['correct']}/{judge_check['total']}")
            if not judge_check["passed"]:
                print("  [!] The judge cannot identify voices that are obviously distinct. "
                      "A null result below would be about the judge, not the guides.")
        print(f"\nIdentification ({len(rows)} calls)...")
        ident = identify(rows, arms, args.judge_model, args.seed, mask=False)
        if any(r.get("echo_span") for r in rows):
            print("\nIdentification again, persona echoes masked...")
            ident_masked = identify(rows, arms, args.judge_model, args.seed, mask=True)
        print(f"\nGrounding ({len(rows)} calls)...")
        facts = grounding(rows, args.judge_model)

    summary = report.build_summary(
        model=args.model, judge_model=args.judge_model, arms=arms, rows=rows,
        similarity=similarity, ident=ident, ident_masked=ident_masked, facts=facts,
        judge_check=judge_check,
    )
    report.print_summary(summary)
    json_path = RESULTS_DIR / f"personality_{slug}.json"
    html_path = RESULTS_DIR / f"personality_{slug}.html"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    report.render_html(summary, rows, html_path)
    print(f"\nSummary  -> {json_path}")
    print(f"Sheet    -> {html_path}")


if __name__ == "__main__":
    main()
