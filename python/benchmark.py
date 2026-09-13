#!/usr/bin/env python3
"""
Latency benchmark for the Cultura Viva pipeline on the Arduino UNO Q.

Answers three questions before any optimisation work starts:

  1. Is the board configured the way we think? (CPU features, governor, thermal
     throttling, whether llama.cpp actually has a GPU backend compiled in)
  2. How long does each pipeline stage take — vision, STT, SLM prefill, SLM
     decode, TTS — and what share of total latency is each?
  3. How much of the SLM cost is the prompt (prefill) versus the answer (decode)?

Runs standalone on the MPU: no Bridge RPC, no App Lab, no microphone or camera.
It reuses the production modules so the numbers reflect the real code paths.

Usage (from python/ on the board):

    python3 benchmark.py                      # full run, 3 reps per stage
    python3 benchmark.py --reps 5
    python3 benchmark.py --stage slm          # iterate on one stage
    python3 benchmark.py --json before.json   # save for before/after diffing

Fixtures are auto-discovered: the newest file in data/photos/ and the newest
in data/recordings/. Override with --photo / --audio. Stages whose fixture or
model is missing are skipped with a reason rather than failing the whole run.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from config import (  # noqa: E402
    PHOTOS_DIR,
    RECORDINGS_DIR,
    SLM_MODEL_PATH,
    STT_MODEL_PATH,
    DEFAULT_LOCATION,
)

# Element used for the SLM/KG stages. Must exist in element_sheets.json (by id
# or alias) so the benchmark exercises a realistic, fully-populated prompt.
BENCH_ELEMENT = "sala_hipostila"
BENCH_SITE = DEFAULT_LOCATION if DEFAULT_LOCATION == "park_guell" else "park_guell"
BENCH_QUESTION = "What is this place and why did Gaudi build it like that?"
BENCH_PERSONALITIES = ("artistic", "technical", "child")

# Representative answer for the TTS stage: ~50 words, matching the length the
# personality prompts ask the SLM to produce.
BENCH_TTS_TEXT = (
    "This is the Hypostyle Room, held up by eighty-six columns that Gaudi shaped "
    "like a forest of stone. He designed it as a covered market for the residents "
    "of his garden city. Look up: the ceiling drains rainwater straight down "
    "through the columns into a cistern below."
)

STAGES = ("vision", "stt", "slm", "tts")


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------


def _read(path, default=None):
    """Reads and strips a sysfs/procfs file, returning default if unreadable."""
    try:
        return Path(path).read_text().strip()
    except Exception:
        return default


def _newest(directory: Path, patterns: tuple[str, ...]) -> Path | None:
    """Returns the most recently modified file in directory matching any glob pattern."""
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(p for p in directory.glob(pattern) if p.is_file())
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _cpu_freqs_mhz() -> list[int]:
    """Returns the current clock of every cpufreq policy, in MHz."""
    freqs = []
    for policy in sorted(Path("/sys/devices/system/cpu/cpufreq").glob("policy*")):
        cur = _read(policy / "scaling_cur_freq")
        if cur and cur.isdigit():
            freqs.append(int(cur) // 1000)
    return freqs


def _temps_c() -> list[float]:
    """Returns every readable thermal zone temperature, in degrees Celsius."""
    temps = []
    for zone in sorted(Path("/sys/class/thermal").glob("thermal_zone*")):
        raw = _read(zone / "temp")
        if raw and raw.lstrip("-").isdigit():
            value = int(raw)
            temps.append(value / 1000.0 if abs(value) > 1000 else float(value))
    return temps


def _fmt(seconds: float) -> str:
    return f"{seconds:7.3f}s"


class Timer:
    """Context manager recording a single wall-clock duration in perf-counter seconds."""

    def __enter__(self):
        self.elapsed = 0.0
        self._start = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.elapsed = time.perf_counter() - self._start
        return False


# --------------------------------------------------------------------------
# Section 0 — environment
# --------------------------------------------------------------------------


def report_environment() -> dict:
    """Prints and returns the hardware/runtime facts that determine what performance is even achievable on this board."""
    print("=" * 72)
    print(" 0. ENVIRONMENT")
    print("=" * 72)

    env: dict = {}

    import platform

    env["python"] = platform.python_version()
    env["machine"] = platform.machine()
    print(f"  python                 {env['python']}  ({env['machine']})")

    cpuinfo = _read("/proc/cpuinfo", "") or ""
    features = ""
    for line in cpuinfo.splitlines():
        if line.lower().startswith(("features", "flags")):
            features = line.split(":", 1)[1].strip()
            break
    env["cpu_features"] = features
    env["cores"] = cpuinfo.count("processor\t:") or cpuinfo.count("processor :")

    feature_set = set(features.split())
    # The decisive ISA question for quantised inference on ARM. Cortex-A53 is
    # ARMv8.0 and has none of these; every fast ARM LLM path assumes at least
    # asimddp. Their absence caps what any amount of tuning can achieve.
    for flag, label in (
        ("asimd", "NEON (asimd)"),
        ("asimddp", "dot product (asimddp)"),
        ("i8mm", "int8 matmul (i8mm)"),
        ("sve", "SVE"),
    ):
        present = flag in feature_set
        env[f"has_{flag}"] = present
        print(f"  {label:<22} {'yes' if present else 'NO'}")

    print(f"  cores                  {env['cores']}")

    governors = []
    max_freqs = []
    for policy in sorted(Path("/sys/devices/system/cpu/cpufreq").glob("policy*")):
        gov = _read(policy / "scaling_governor")
        mx = _read(policy / "scaling_max_freq")
        if gov:
            governors.append(gov)
        if mx and mx.isdigit():
            max_freqs.append(int(mx) // 1000)
    env["governors"] = governors
    env["max_freq_mhz"] = max_freqs
    env["freq_mhz_start"] = _cpu_freqs_mhz()
    env["temp_c_start"] = _temps_c()
    print(f"  governor               {', '.join(sorted(set(governors))) or 'unknown'}")
    print(f"  max freq (MHz)         {max_freqs or 'unknown'}")
    print(f"  cur freq (MHz)         {env['freq_mhz_start'] or 'unknown'}")
    print(
        f"  temperature (C)        "
        f"{[round(t, 1) for t in env['temp_c_start']] or 'unknown'}"
    )

    meminfo = _read("/proc/meminfo", "") or ""
    for line in meminfo.splitlines():
        if line.startswith(("MemTotal", "MemAvailable")):
            key, value = line.split(":", 1)
            mb = int(value.strip().split()[0]) // 1024
            env[key.lower()] = mb
            print(f"  {key.lower():<22} {mb} MB")

    # Container CPU quota: App Lab runs the Python side in a container, and a
    # quota here would silently cap inference below the core count.
    quota = _read("/sys/fs/cgroup/cpu.max")
    if quota:
        env["cgroup_cpu_max"] = quota
        print(f"  cgroup cpu.max         {quota}")

    # --- llama.cpp backend ---
    try:
        import llama_cpp

        env["llama_cpp_version"] = getattr(llama_cpp, "__version__", "unknown")
        gpu_offload = None
        try:
            gpu_offload = bool(llama_cpp.llama_supports_gpu_offload())
        except Exception:
            pass
        env["llama_supports_gpu_offload"] = gpu_offload
        print(f"  llama-cpp-python       {env['llama_cpp_version']}")
        print(
            f"  llama GPU offload      "
            f"{'yes' if gpu_offload else 'NO — CPU only, n_gpu_layers is ignored'}"
        )
    except ImportError:
        env["llama_cpp_version"] = None
        print("  llama-cpp-python       NOT INSTALLED")

    try:
        import onnxruntime as ort

        env["onnxruntime_version"] = ort.__version__
        env["onnxruntime_providers"] = ort.get_available_providers()
        print(f"  onnxruntime            {ort.__version__}")
        print(f"  onnx providers         {', '.join(env['onnxruntime_providers'])}")
    except ImportError:
        env["onnxruntime_version"] = None
        print("  onnxruntime            NOT INSTALLED")

    for label, path in (("SLM", SLM_MODEL_PATH), ("STT", Path(STT_MODEL_PATH))):
        if path.exists():
            size = (
                path.stat().st_size
                if path.is_file()
                else sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
            )
            print(f"  {label} model             {path.name}  ({size / 1e6:.0f} MB)")
        else:
            print(f"  {label} model             MISSING at {path}")

    print()
    return env


# --------------------------------------------------------------------------
# Section 1 — cold model load
# --------------------------------------------------------------------------


def measure_loads(stages: tuple[str, ...]) -> tuple[dict, dict]:
    """Times the one-off cost of loading each model into memory and returns the timings plus the loaded module instances for reuse by the stage benchmarks."""
    print("=" * 72)
    print(" 1. MODEL PRELOAD  (startup cost main.py pays up front, via preload())")
    print("=" * 72)

    loads: dict = {}
    instances: dict = {}

    def timed_preload(stage: str, label: str, build, preload):
        """Constructs a module and times its preload(), recording None if it reports failure."""
        try:
            instance = build()
        except Exception as exc:
            instances[stage] = None
            print(f"  {label:<18}skipped ({exc})")
            return
        instances[stage] = instance
        try:
            with Timer() as t:
                ok = bool(preload(instance))
        except Exception as exc:
            loads[stage] = None
            print(f"  {label:<18}failed ({exc})")
            return
        loads[stage] = t.elapsed if ok else None
        print(f"  {label:<18}{_fmt(t.elapsed) if ok else 'skipped (model unavailable)'}")

    def _vision():
        from core.vision_module import VisionClassifier

        return VisionClassifier()

    def _mic():
        from hw.microphone_module import MicrophoneManager

        return MicrophoneManager()

    def _slm():
        from core.model_module import ModelRegistry

        return ModelRegistry()

    def _tts():
        from hw.audio_playback_module import AudioPlayer

        return AudioPlayer()

    if "vision" in stages:
        timed_preload("vision", "vision (onnx)", _vision, lambda v: v.preload(BENCH_SITE))

    if "stt" in stages:
        timed_preload("stt", "stt (whisper)", _mic, lambda m: m.preload())

    if "slm" in stages:
        timed_preload("slm", "slm (llama.cpp)", _slm, lambda m: m.preload())

    if "tts" in stages:
        # preload() warms every voice in PERSONALITY_VOICE, matching what
        # main.py does at startup rather than just the one voice we benchmark.
        timed_preload("tts", "tts (piper)", _tts, lambda p: p.preload())

    print()
    return loads, instances


# --------------------------------------------------------------------------
# Section 2 — per-stage timing
# --------------------------------------------------------------------------


def bench_vision(vision, photo: Path, reps: int) -> dict:
    """Times ONNX classification of a real photo, warm session."""
    vision.classify(BENCH_SITE, photo)  # warm-up, excluded from timings
    samples = []
    for _ in range(reps):
        with Timer() as t:
            label = vision.classify(BENCH_SITE, photo)
        samples.append(t.elapsed)
    return {"samples": samples, "detail": {"label": label, "photo": photo.name}}


def bench_stt(mic, audio: Path, reps: int) -> dict:
    """Times faster-whisper transcription of a real recording, including the model load on the first (untimed) call."""
    import wave

    try:
        with wave.open(str(audio), "rb") as wf:
            duration = wf.getnframes() / float(wf.getframerate())
    except Exception:
        duration = None

    mic.transcribe(audio)  # warm-up, excluded from timings

    samples = []
    for _ in range(reps):
        with Timer() as t:
            text = mic.transcribe(audio)
        samples.append(t.elapsed)

    detail = {"audio": audio.name, "audio_seconds": duration, "text": text}
    if duration and samples:
        detail["realtime_factor"] = statistics.median(samples) / duration
    return {"samples": samples, "detail": detail}


def bench_slm(models, reps: int) -> dict:
    """Times SLM generation with prefill and decode separated.

    Prefill (time to first token) and decode (the rest) scale with completely
    different things — prompt length versus answer length — so a single
    end-to-end number cannot tell you which one to attack. The KV cache is
    reset before every repetition so prefill is measured cold; llama-cpp-python
    would otherwise reuse the shared prefix and report a misleadingly fast
    second run.
    """
    from core.model_module import build_messages

    # Preloaded in section 1; drive the Llama object directly so we can stream
    # token-by-token and time the first one, which generate_response does not expose.
    llm = models._ensure_llm() if hasattr(models, "_ensure_llm") else getattr(models, "_llm", None)
    if llm is None:
        return {"samples": [], "detail": {"error": "llama-cpp-python unavailable"}}

    per_personality: dict = {}
    all_totals: list[float] = []
    all_prefills: list[float] = []
    all_decodes: list[float] = []

    for personality in BENCH_PERSONALITIES:
        kg_context = models.get_kg_context(BENCH_ELEMENT, personality=personality)

        # The same builder generate_response uses, so the prompt measured here is the
        # prompt production sends — including which half of it is the cacheable prefix.
        messages = build_messages(
            BENCH_QUESTION, BENCH_ELEMENT, personality, kg_context
        )

        prefills, decodes, totals, prompt_tokens, decoded_counts = [], [], [], [], []

        for _ in range(reps):
            llm.reset()  # clear KV cache so prefill is measured cold
            start = time.perf_counter()
            ttft = None
            n_prompt = None

            stream = llm.create_chat_completion(
                messages=messages,
                max_tokens=60,
                temperature=0.1,
                repeat_penalty=1.1,
                stop=["\n\n", "<|im_end|>"],
                stream=True,
            )
            for chunk in stream:
                delta = chunk["choices"][0].get("delta", {})
                if not delta.get("content"):
                    continue
                if ttft is None:
                    ttft = time.perf_counter() - start
                    # llm.n_tokens is the KV cache fill. Sampled at the first
                    # token it is the prompt length (+/- 1 depending on whether
                    # that token has been evaluated back yet) — good enough to
                    # tell a 150-token prompt from a 700-token one. Counting
                    # stream chunks instead would undercount, because
                    # llama-cpp-python buffers for multi-byte UTF-8 and for
                    # stop-sequence lookahead.
                    n_prompt = getattr(llm, "n_tokens", None)
            total = time.perf_counter() - start

            if ttft is None:  # model emitted nothing
                continue

            # Exact, unlike chunk counting: the KV cache grew by one per token.
            ctx_end = getattr(llm, "n_tokens", None)
            n_decoded = (ctx_end - n_prompt) if (ctx_end and n_prompt) else 0

            prefills.append(ttft)
            decodes.append(total - ttft)
            totals.append(total)
            decoded_counts.append(n_decoded)
            if n_prompt:
                prompt_tokens.append(n_prompt)

        # Same prompt, but with the photo-dependent prefix already evaluated — what
        # production sees once warm_prefix() has run during the recording window. The
        # gap between this and the cold prefill above is what the overlap buys.
        warm_prefills: list[float] = []
        for _ in range(reps):
            llm.reset()
            models._warm_key = None
            if not models.warm_prefix(BENCH_ELEMENT, personality, kg_context):
                break
            start = time.perf_counter()
            stream = llm.create_chat_completion(
                messages=messages,
                max_tokens=60,
                temperature=0.1,
                repeat_penalty=1.1,
                stop=["\n\n", "<|im_end|>"],
                stream=True,
            )
            for chunk in stream:
                if chunk["choices"][0].get("delta", {}).get("content"):
                    warm_prefills.append(time.perf_counter() - start)
                    break
            # Only the time to first token matters here; the decode is unchanged by
            # warming, and letting it run would triple the benchmark's wall time.
            stream.close()

        if not totals:
            continue

        med_prefill = statistics.median(prefills)
        med_decode = statistics.median(decodes)
        med_prompt = statistics.median(prompt_tokens) if prompt_tokens else None
        med_decoded = statistics.median(decoded_counts)

        per_personality[personality] = {
            "kg_context_chars": len(kg_context),
            "prompt_tokens": med_prompt,
            "decoded_tokens": med_decoded,
            "prefill_s": med_prefill,
            "decode_s": med_decode,
            "total_s": statistics.median(totals),
            "warm_prefill_s": statistics.median(warm_prefills) if warm_prefills else None,
            "prefill_tok_s": (med_prompt / med_prefill) if med_prompt else None,
            "decode_tok_s": (med_decoded / med_decode) if med_decode else None,
        }
        all_totals.extend(totals)
        all_prefills.extend(prefills)
        all_decodes.extend(decodes)

    print(
        f"     {'personality':<12}{'prompt tok':>11}{'prefill':>10}{'tok/s':>8}"
        f"{'warm':>9}{'out tok':>9}{'decode':>9}{'tok/s':>8}"
    )
    for name, row in per_personality.items():
        warm = row.get("warm_prefill_s")
        print(
            f"     {name:<12}{row['prompt_tokens'] or 0:>11.0f}"
            f"{row['prefill_s']:>9.2f}s{row['prefill_tok_s'] or 0:>8.1f}"
            f"{(f'{warm:.2f}s' if warm is not None else '-'):>9}"
            f"{row['decoded_tokens']:>9.0f}{row['decode_s']:>8.2f}s"
            f"{row['decode_tok_s'] or 0:>8.1f}"
        )
    print(
        "     'prefill' is cold (empty KV cache); 'warm' is time to first token with\n"
        "     the prompt prefix already evaluated, as warm_prefix() leaves it in\n"
        "     production. The difference is what overlapping the prefill removes."
    )

    return {
        "samples": all_totals,
        "prefill_samples": all_prefills,
        "decode_samples": all_decodes,
        "detail": {"per_personality": per_personality, "element": BENCH_ELEMENT},
    }


def bench_tts(player, reps: int) -> dict:
    """Times Piper synthesis of a representative answer and reports the realtime factor."""
    import wave
    from hw.audio_playback_module import PERSONALITY_VOICE

    voice_key = PERSONALITY_VOICE.get("artistic")
    player._synthesize(BENCH_TTS_TEXT, voice_key)  # warm-up

    samples = []
    wav_bytes = None
    for _ in range(reps):
        with Timer() as t:
            wav_bytes = player._synthesize(BENCH_TTS_TEXT, voice_key)
        samples.append(t.elapsed)

    detail: dict = {"chars": len(BENCH_TTS_TEXT), "voice": voice_key}
    if wav_bytes:
        try:
            import io

            with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
                audio_seconds = wf.getnframes() / float(wf.getframerate())
            detail["audio_seconds"] = audio_seconds
            detail["realtime_factor"] = statistics.median(samples) / audio_seconds
        except Exception:
            pass
    return {"samples": samples, "detail": detail}


# --------------------------------------------------------------------------
# Summary
# --------------------------------------------------------------------------


def print_summary(results: dict, loads: dict, reps: int) -> None:
    """Prints the stage breakdown with each stage's share of total user-perceived latency."""
    print("=" * 72)
    print(f" 3. STAGE BREAKDOWN  (median of {reps} reps, models already warm)")
    print("=" * 72)

    rows: list[tuple[str, float, float, float]] = []
    for stage in STAGES:
        res = results.get(stage)
        if not res or not res.get("samples"):
            continue
        if stage == "slm":
            for sub, key in (("slm prefill", "prefill_samples"), ("slm decode", "decode_samples")):
                s = res.get(key) or []
                if s:
                    rows.append((sub, statistics.median(s), min(s), max(s)))
        else:
            s = res["samples"]
            rows.append((stage, statistics.median(s), min(s), max(s)))

    if not rows:
        print("  No stage produced a measurement — check the skip reasons above.\n")
        return

    total = sum(r[1] for r in rows)
    print(f"  {'stage':<14}{'median':>10}{'min':>10}{'max':>10}{'share':>9}")
    print("  " + "-" * 53)
    for name, med, lo, hi in rows:
        print(f"  {name:<14}{med:>9.2f}s{lo:>9.2f}s{hi:>9.2f}s{med / total:>8.1%}")
    print("  " + "-" * 53)
    print(f"  {'TOTAL':<14}{total:>9.2f}s")

    if loads:
        cold = sum(v for v in loads.values() if v)
        if cold:
            print(f"\n  + {cold:.2f}s of model preload at startup (not per request).")

    print("\n  Current temperature / clocks after the run:")
    print(f"    freq (MHz)  {_cpu_freqs_mhz() or 'unknown'}")
    print(f"    temp (C)    {[round(t, 1) for t in _temps_c()] or 'unknown'}")
    print()


# --------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--reps", type=int, default=3, help="repetitions per stage (default 3)")
    parser.add_argument(
        "--stage",
        action="append",
        choices=STAGES,
        help="benchmark only this stage (repeatable); default is all",
    )
    parser.add_argument("--photo", type=Path, help="photo for the vision stage")
    parser.add_argument("--audio", type=Path, help="WAV recording for the STT stage")
    parser.add_argument("--json", type=Path, help="write full results to this JSON file")
    args = parser.parse_args()

    stages: tuple[str, ...] = tuple(args.stage) if args.stage else STAGES
    reps = max(1, args.reps)

    env = report_environment()
    loads, instances = measure_loads(stages)

    print("=" * 72)
    print(f" 2. STAGE TIMING  ({reps} reps each)")
    print("=" * 72)

    results: dict = {}

    def run(stage: str, fn):
        """Runs one stage benchmark, keeping a failure local to that stage."""
        try:
            results[stage] = fn()
        except Exception as exc:
            print(f"     FAILED: {type(exc).__name__}: {exc}")

    if "vision" in stages:
        photo = args.photo or _newest(PHOTOS_DIR, ("*.jpg", "*.jpeg", "*.png"))
        print("  [vision]")
        if photo is None or not photo.exists():
            print(f"     skipped: no photo found in {PHOTOS_DIR} (pass --photo)")
        elif instances.get("vision") is None or loads.get("vision") is None:
            print("     skipped: ONNX model unavailable")
        else:
            run("vision", lambda: bench_vision(instances["vision"], photo, reps))
            if "vision" in results:
                print(f"     label={results['vision']['detail']['label']}")

    if "stt" in stages:
        audio = args.audio or _newest(RECORDINGS_DIR, ("*.wav",))
        print("  [stt]")
        if audio is None or not audio.exists():
            print(f"     skipped: no recording found in {RECORDINGS_DIR} (pass --audio)")
        elif instances.get("stt") is None:
            print("     skipped: MicrophoneManager unavailable")
        else:
            run("stt", lambda: bench_stt(instances["stt"], audio, reps))
            d = results.get("stt", {}).get("detail", {})
            if d.get("realtime_factor"):
                print(
                    f"     {d['audio_seconds']:.1f}s of audio, "
                    f"realtime factor {d['realtime_factor']:.2f}x"
                )

    if "slm" in stages:
        print("  [slm]")
        if instances.get("slm") is None:
            print("     skipped: ModelRegistry unavailable")
        elif not SLM_MODEL_PATH.exists():
            print(f"     skipped: GGUF not found at {SLM_MODEL_PATH}")
        else:
            run("slm", lambda: bench_slm(instances["slm"], reps))

    if "tts" in stages:
        print("  [tts]")
        if instances.get("tts") is None or loads.get("tts") is None:
            print("     skipped: Piper voice unavailable")
        else:
            run("tts", lambda: bench_tts(instances["tts"], reps))
            d = results.get("tts", {}).get("detail", {})
            if d.get("realtime_factor"):
                print(
                    f"     {d['audio_seconds']:.1f}s of speech, "
                    f"realtime factor {d['realtime_factor']:.2f}x"
                )

    print()
    print_summary(results, loads, reps)

    if args.json:
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "reps": reps,
            "environment": env,
            "cold_load_s": loads,
            "stages": {
                name: {
                    "samples": res.get("samples"),
                    "prefill_samples": res.get("prefill_samples"),
                    "decode_samples": res.get("decode_samples"),
                    "median_s": statistics.median(res["samples"]) if res.get("samples") else None,
                    "detail": res.get("detail"),
                }
                for name, res in results.items()
            },
        }
        args.json.write_text(json.dumps(payload, indent=2, default=str))
        print(f"  Results written to {args.json}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
