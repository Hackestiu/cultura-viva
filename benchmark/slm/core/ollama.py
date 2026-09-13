"""One Ollama /api/chat call, shared by the benchmark, the study and the judge.

It lived in scripts/benchmark.py, which meant personality/study.py imported the
whole benchmark module -- sentence-transformers, numpy and all -- to reach an
eighty-line urllib block. It has nothing to do with benchmarking.
"""

from __future__ import annotations

import json
import time
import urllib.request

from core.config import cfg


def ollama_chat(
    model_tag: str,
    messages: list[dict],
    base_url: str | None = None,
    options: dict | None = None,
) -> dict:
    """One /api/chat call. Returns answer, wall-clock, and why generation stopped.

    /api/chat rather than /api/generate: the device calls llama.cpp's
    create_chat_completion, which applies the model's chat template to a system
    and a user turn. Flattening that into one completion prompt, as this script
    used to, measures a prompt shape the device never sends.

    `base_url` and `options` default to the candidate model's endpoint and the
    device's sampling parameters. They are overridable so a judge can be driven
    through the same function rather than a second copy of this urllib block.

    done_reason matters: at max_tokens=60 an answer can be cut off mid-sentence,
    and a caller that only looks at the text cannot tell a finished answer from a
    truncated one.
    """
    opts = {
        "temperature": cfg.inference_temperature,
        "num_predict": cfg.inference_max_tokens,
        "repeat_penalty": cfg.inference_repeat_penalty,
        "num_ctx": cfg.inference_context_window,
        "stop": list(cfg.inference_stop),
        # Ollama picks a random seed when none is given, so without this a rerun
        # is not reproducible and a same-prompt control could not be measured.
        "seed": cfg.inference_seed,
    }
    if options:
        opts.update(options)

    payload = json.dumps({
        "model": model_tag,
        "messages": messages,
        "stream": False,
        "options": opts,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{(base_url or cfg.ollama_base_url).rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    start = time.time()
    result: dict = {}
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            answer = (result.get("message") or {}).get("content", "").strip()
            error = None
    except Exception as e:
        answer = f"Error during inference: {e}"
        error = str(e)

    return {
        "answer": answer,
        "elapsed_s": round(time.time() - start, 3),
        "done_reason": result.get("done_reason"),
        "eval_count": result.get("eval_count"),
        "prompt_eval_count": result.get("prompt_eval_count"),
        "error": error,
    }
