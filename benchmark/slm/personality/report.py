"""Console summary and a self-contained HTML sheet for the personality study.

The HTML carries the confusion matrix and the grounding rates, then the answers
themselves side by side. The panels are the point: a matrix can say "these are
distinguishable" while the answers read identically to a person, and when those
two disagree the answers are right. Follows the layout discipline of
benchmark/stt/visualize.py:generate_html_report -- one f-string, inline CSS,
html.escape on everything interpolated, no external assets.
"""

from __future__ import annotations

import html
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Palette borrowed from benchmark/tts/visualize.py, where it is noted as
# CVD-validated across all pairs.
COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#4a3aa7"]
SURFACE, INK, INK_SOFT, GRID = "#ffffff", "#1a1a1a", "#5c5c5c", "#e4e4e7"


def _pct(n: int, d: int) -> str:
    return f"{100 * n / d:.0f}%" if d else "n/a"


def build_summary(*, model, judge_model, arms, rows, similarity, ident, ident_masked, facts,
                  judge_check=None) -> dict:
    n_probes = len({r["probe_id"] for r in rows})
    by_arm = defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)

    per_arm = {}
    for arm in arms:
        arm_rows = by_arm[arm]
        lengths = [len(r["answer"].split()) for r in arm_rows]
        per_arm[arm] = {
            "n": len(arm_rows),
            "median_words": statistics.median(lengths) if lengths else 0,
            "min_words": min(lengths, default=0),
            "max_words": max(lengths, default=0),
            "truncated": sum(1 for r in arm_rows if r.get("done_reason") == "length"),
            "echoed": sum(1 for r in arm_rows if r.get("echo_span")),
            "follows_format": sum(1 for r in arm_rows if r.get("follows_format")),
        }

    summary = {
        "model": model,
        "judge_model": judge_model,
        "arms": list(arms),
        "n_probes": n_probes,
        "n_answers": len(rows),
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "per_arm": per_arm,
        "similarity": {
            "probes_with_an_identical_pair": sum(1 for s in similarity if s["any_identical"]),
            "median_max_similarity": round(statistics.median(
                [s["max_similarity"] for s in similarity]), 3) if similarity else None,
            "per_probe": similarity,
        },
    }

    if judge_check is not None:
        summary["judge_self_test"] = judge_check
    if ident is not None:
        summary["identification"] = _identification_block(ident, arms)
        summary["identification_detail"] = [
            {"probe_id": r["probe_id"], "arm": r["arm"], "predicted": r["predicted"]}
            for r in ident
        ]
    if ident_masked is not None:
        summary["identification_echo_masked"] = _identification_block(ident_masked, arms)
    if facts is not None:
        g = {}
        for arm in arms:
            arm_f = [f for f in facts if f["arm"] == arm]
            unsupported = sum(1 for f in arm_f if f["verdict"] == "UNSUPPORTED")
            g[arm] = {"n": len(arm_f), "unsupported": unsupported,
                      "unjudged": sum(1 for f in arm_f if f["verdict"] is None)}
        summary["grounding"] = g
        # Per-answer verdicts, not just counts: an aggregate hallucination rate
        # nobody can audit is a number you have to take on trust.
        summary["grounding_detail"] = [
            {"probe_id": f["probe_id"], "arm": f["arm"], "verdict": f["verdict"]}
            for f in facts
        ]
    return summary


def _identification_block(ident: list[dict], arms: list[str]) -> dict:
    matrix = {t: {p: 0 for p in list(arms) + ["unparsed"]} for t in arms}
    for r in ident:
        matrix[r["arm"]][r["predicted"] or "unparsed"] += 1
    correct = sum(matrix[a][a] for a in arms)
    total = len(ident)
    return {
        "matrix": matrix,
        "correct": correct,
        "total": total,
        "accuracy": round(correct / total, 3) if total else None,
        "chance": round(1 / len(arms), 3),
        "per_arm_recall": {a: round(matrix[a][a] / max(1, sum(matrix[a].values())), 3) for a in arms},
        # A judge that answers one label for everything scores at chance and means
        # nothing; this is what to check before believing the accuracy number.
        "prediction_spread": dict(Counter(r["predicted"] or "unparsed" for r in ident)),
    }


def print_summary(s: dict) -> None:
    arms = s["arms"]
    w = 78
    print("\n" + "=" * w)
    print(f"  PERSONALITY STUDY -- {s['model']}  (judge: {s['judge_model']})")
    print("=" * w)
    print(f"  {s['n_probes']} probes x {len(arms)} guides = {s['n_answers']} answers\n")

    print(f"  {'Guide':<12} {'words (med)':>12} {'range':>12} {'truncated':>11} {'format ok':>10}")
    print("  " + "-" * (w - 4))
    for a in arms:
        p = s["per_arm"][a]
        rng = f"{p['min_words']}-{p['max_words']}"
        print(f"  {a:<12} {p['median_words']:>12.0f} {rng:>12} "
              f"{_pct(p['truncated'], p['n']):>11} {_pct(p['follows_format'], p['n']):>10}")

    sim = s["similarity"]
    print(f"\n  Probes where two guides gave an identical answer: "
          f"{sim['probes_with_an_identical_pair']}/{s['n_probes']}")
    print(f"  Median max text similarity between guides        : {sim['median_max_similarity']}")

    if "judge_self_test" in s:
        jc = s["judge_self_test"]
        print(f"\n  Judge self-test on hand-written distinct voices: "
              f"{jc['correct']}/{jc['total']} {'PASS' if jc['passed'] else 'FAIL'}")

    for key, title in (("identification", "IDENTIFICATION"),
                       ("identification_echo_masked", "IDENTIFICATION (persona echoes masked)")):
        if key not in s:
            continue
        b = s[key]
        print(f"\n  {title}: {b['correct']}/{b['total']} = {b['accuracy']:.0%} "
              f"(chance {b['chance']:.0%})")
        head = "".join(f"{p:>12}" for p in arms + ["unparsed"])
        print(f"    {'true \\ pred':<14}{head}")
        for t in arms:
            cells = "".join(f"{b['matrix'][t][p]:>12}" for p in arms + ["unparsed"])
            print(f"    {t:<14}{cells}")
        spread = b["prediction_spread"]
        if len(spread) == 1:
            print("    [!] judge predicted a single label throughout -- accuracy is meaningless")

    if "grounding" in s:
        print("\n  GROUNDING (claims unsupported by the retrieved facts)")
        for a in arms:
            g = s["grounding"][a]
            note = f"  ({g['unjudged']} unparsed)" if g["unjudged"] else ""
            print(f"    {a:<12} {g['unsupported']}/{g['n']} = {_pct(g['unsupported'], g['n'])}{note}")
    print("=" * w)


def render_html(s: dict, rows: list[dict], path: Path) -> None:
    arms = s["arms"]
    by_probe: dict[str, dict[str, dict]] = defaultdict(dict)
    for r in rows:
        by_probe[r["probe_id"]][r["arm"]] = r

    def esc(x) -> str:
        return html.escape(str(x))

    judge_check_html = ""
    if "judge_self_test" in s:
        jc = s["judge_self_test"]
        tone = "#1baf7a" if jc["passed"] else "#eb6834"
        msg = ("the judge identifies hand-written, obviously-distinct voices correctly, "
               "so a null below is about the guides, not the instrument"
               if jc["passed"] else
               "THE JUDGE FAILED this check -- a null below would be about the judge, "
               "not the guides")
        judge_check_html = (f"<p class='muted'><span style='color:{tone};font-weight:600'>"
                            f"Judge self-test {jc['correct']}/{jc['total']}</span> &mdash; {msg}.</p>")

    ident_html = "<p class='muted'>Judge not run.</p>"
    if "identification" in s:
        b = s["identification"]
        head = "".join(f"<th>{esc(p)}</th>" for p in arms + ["unparsed"])
        body = ""
        for t in arms:
            cells = "".join(
                f"<td class='{'hit' if p == t else ''}'>{b['matrix'][t][p]}</td>"
                for p in arms + ["unparsed"])
            body += f"<tr><th class='rowh'>{esc(t)}</th>{cells}</tr>"
        masked = ""
        if "identification_echo_masked" in s:
            m = s["identification_echo_masked"]
            masked = (f"<p class='muted'>With persona echoes masked: "
                      f"{m['correct']}/{m['total']} = {m['accuracy']:.0%}. "
                      f"A large drop would mean the model announces its persona rather "
                      f"than speaking in it.</p>")
        ident_html = f"""
        <p class="big">{b['correct']}/{b['total']} = {b['accuracy']:.0%}
           <span class="muted">(chance {b['chance']:.0%})</span></p>
        <table class="matrix"><tr><th class="rowh">true \\ predicted</th>{head}</tr>{body}</table>
        {masked}"""

    ground_html = "<p class='muted'>Judge not run.</p>"
    if "grounding" in s:
        ground_html = "<table class='matrix'><tr><th class='rowh'>guide</th><th>unsupported</th><th>of</th><th>rate</th></tr>"
        for a in arms:
            g = s["grounding"][a]
            ground_html += (f"<tr><th class='rowh'>{esc(a)}</th><td>{g['unsupported']}</td>"
                            f"<td>{g['n']}</td><td>{_pct(g['unsupported'], g['n'])}</td></tr>")
        ground_html += "</table>"

    arm_rows = ""
    for a in arms:
        p = s["per_arm"][a]
        arm_rows += (f"<tr><th class='rowh'>{esc(a)}</th><td>{p['median_words']:.0f}</td>"
                     f"<td>{p['min_words']}&ndash;{p['max_words']}</td>"
                     f"<td>{_pct(p['truncated'], p['n'])}</td>"
                     f"<td>{_pct(p['follows_format'], p['n'])}</td></tr>")

    panels = ""
    for probe_id, per_arm in by_probe.items():
        any_row = next(iter(per_arm.values()))
        cols = ""
        for i, a in enumerate(arms):
            r = per_arm.get(a)
            if not r:
                continue
            flags = []
            if r.get("done_reason") == "length":
                flags.append("<span class='flag'>cut off</span>")
            if r.get("echo_span"):
                flags.append("<span class='flag'>echoes prompt</span>")
            cols += (f"<div class='voice'><h4 style='color:{COLORS[i % len(COLORS)]}'>{esc(a)}</h4>"
                     f"<p>{esc(r['answer'])}</p><div class='flags'>{''.join(flags)}</div></div>")
        panels += (f"<section class='panel'><h3>{esc(any_row['question'])}"
                   f"<span class='muted'> &middot; {esc(probe_id)}</span></h3>"
                   f"<div class='voices'>{cols}</div></section>")

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Guide personalities &mdash; {esc(s['model'])}</title>
<style>
 body {{ background:{SURFACE}; color:{INK}; font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
        margin:0 auto; padding:40px 24px; max-width:1100px; }}
 h1 {{ font-size:26px; margin:0 0 4px; }}
 h2 {{ font-size:18px; margin:36px 0 10px; padding-bottom:6px; border-bottom:1px solid {GRID}; }}
 h3 {{ font-size:15px; font-weight:600; margin:0 0 10px; }}
 h4 {{ font-size:12px; text-transform:uppercase; letter-spacing:.06em; margin:0 0 6px; }}
 .muted {{ color:{INK_SOFT}; font-weight:400; }}
 .big {{ font-size:30px; font-weight:600; margin:6px 0 14px; }}
 table.matrix {{ border-collapse:collapse; margin:8px 0 4px; }}
 table.matrix th, table.matrix td {{ border:1px solid {GRID}; padding:7px 14px; text-align:right; }}
 table.matrix th {{ background:#fafafa; font-weight:600; }}
 th.rowh {{ text-align:left; }}
 td.hit {{ background:#eaf4ff; font-weight:700; }}
 .panel {{ border:1px solid {GRID}; border-radius:8px; padding:16px 18px; margin:14px 0; }}
 .voices {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:18px; }}
 .voice p {{ margin:0; font-size:14px; }}
 .flags {{ margin-top:8px; }}
 .flag {{ font-size:11px; background:#fdeee6; color:#8a3b12; border-radius:3px; padding:2px 6px; margin-right:5px; }}
 footer {{ margin-top:40px; color:{INK_SOFT}; font-size:13px; border-top:1px solid {GRID}; padding-top:14px; }}
 @media (prefers-color-scheme: dark) {{
   body {{ background:#161617; color:#f2f2f2; }}
   h2, footer {{ border-color:#333; }}
   table.matrix th {{ background:#1f1f21; }} table.matrix th, table.matrix td {{ border-color:#333; }}
   td.hit {{ background:#173049; }} .panel {{ border-color:#333; }}
   .flag {{ background:#3a2418; color:#f0b48a; }} .muted {{ color:#9a9a9a; }}
 }}
</style></head><body>
<h1>Do the guide personalities change the answer?</h1>
<p class="muted">{esc(s['model'])} &middot; judged by {esc(s['judge_model'])} &middot;
   {s['n_probes']} probes &times; {len(arms)} guides &middot; {esc(s['generated_utc'])}</p>

<h2>Can a blind judge tell the guides apart?</h2>
{judge_check_html}
{ident_html}

<h2>Does a personality make it invent things?</h2>
<p class="muted">Judged against the facts the model was given, not against a
  reference answer &mdash; scoring a child-register answer against a plain factual
  reference would penalise style and call it inaccuracy.</p>
{ground_html}

<h2>How different are the answers at all?</h2>
<p>Two guides produced an identical answer on
   <strong>{s['similarity']['probes_with_an_identical_pair']} of {s['n_probes']}</strong> probes.
   Median highest text similarity between two guides:
   <strong>{s['similarity']['median_max_similarity']}</strong>.</p>
<table class="matrix">
  <tr><th class="rowh">guide</th><th>median words</th><th>range</th><th>cut off</th><th>format obeyed</th></tr>
  {arm_rows}
</table>

<h2>The answers</h2>
<p class="muted">Read these. If the numbers above say the guides are distinguishable
  and these read the same to you, trust these.</p>
{panels}

<footer>Generated by <code>benchmark/slm/personality</code>.
  Prompts imported from <code>arduino/python/core/model_module.py</code>, so this
  measures what ships. Retrieval is by element id, the same path the device takes
  when vision names an element.</footer>
</body></html>"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc, encoding="utf-8")
