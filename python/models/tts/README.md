# models/tts — Piper voice model files

Place the downloaded voice model pairs here before running `AudioPlayer` from `hw.audio_playback_module`.

```
python/models/tts/
├── en_US-libritts_r-medium.onnx
├── en_US-libritts_r-medium.onnx.json
├── en_GB-semaine-medium.onnx
└── en_GB-semaine-medium.onnx.json
```

---

## Voice index

| Voice key (`hw/audio_playback_module.py`) | Personality | Language | Description | ONNX stem |
|---|---|---|---|---|
| `libriTTS_r_medium` | `artistic` | en-US | LibriTTS-R medium — clean, neutral American English | `en_US-libritts_r-medium` |
| `semaine_spike` | `technical` | en-GB | Semaine medium — Spike (male British English) | `en_GB-semaine-medium` |
| `semaine_prudence` | `child` | en-GB | Semaine medium — Prudence (female British English) | `en_GB-semaine-medium` |

> **Semaine note**: Spike and Prudence share the **same ONNX pair**. The
> module uses `speaker_id` 0 for Prudence and 1 for Spike, matching the
> downloaded `en_GB-semaine-medium.onnx.json` configuration.


## Download instructions
All voices are hosted in the [`rhasspy/piper-voices`](https://huggingface.co/rhasspy/piper-voices)
repository on Hugging Face.

### Option A — `huggingface_hub` (recommended, works on the board)

```bash
pip install huggingface-hub   # skip if already installed

python - <<'EOF'
from huggingface_hub import hf_hub_download
from pathlib import Path
import shutil

DEST = Path("python/models/tts")
DEST.mkdir(parents=True, exist_ok=True)
REPO = "rhasspy/piper-voices"

files = [
    # en-US LibriTTS-R medium
    "en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx",
    "en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx.json",
    # en-GB Semaine medium (covers both Spike and Prudence)
    "en/en_GB/semaine/medium/en_GB-semaine-medium.onnx",
    "en/en_GB/semaine/medium/en_GB-semaine-medium.onnx.json",
]

for remote_path in files:
    local = hf_hub_download(repo_id=REPO, filename=remote_path)
    target = DEST / Path(remote_path).name
    shutil.copy2(local, target)
    print(f"  OK  {target.name}")
EOF
```

### Option B — Direct download links

Download each file from these Hugging Face links and save it in
`python/models/tts/`:

- [en_US-libritts_r-medium.onnx](https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx)
- [en_US-libritts_r-medium.onnx.json](https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/libritts_r/medium/en_US-libritts_r-medium.onnx.json)
- [en_GB-semaine-medium.onnx](https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/semaine/medium/en_GB-semaine-medium.onnx)
- [en_GB-semaine-medium.onnx.json](https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_GB/semaine/medium/en_GB-semaine-medium.onnx.json)

## .gitignore reminder

Add `*.onnx` to `.gitignore` — large binary files should not be committed.

