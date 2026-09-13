# gaudi-vision

Trains the element classifiers that let the device recognise *what* a visitor
photographed, and exports them to ONNX for the Arduino UNO Q.

One classifier is trained per **(monument, model)** pair — each monument has its
own element classes, so they can't share a head. Every run gets its own dataset
split, model instance, output directory, and W&B run.

## The four scripts

| Script | Does |
| --- | --- |
| `train_classifier.py` | Fine-tunes every (monument, model) combination in `config.yaml`. |
| `export_to_onnx.py` | Turns one finetuned checkpoint into `model.onnx` + `labels.json` for the board. |
| `calibrate_thresholds.py` | Sweeps the validation split to suggest OOD thresholds for a checkpoint. |
| `inference.py` | Runs an exported checkpoint on one image, with the OOD gate applied. Also importable as `MonumentClassifier`. |

`common.py` (config + processor helpers) and `dataset.py` (HF loading and
splitting) are shared internals, not entry points. `dataset.py` matters:
training and calibration both go through it, so calibration is guaranteed to run
on images the model was never fit to.

## Pipeline

```bash
export HF_TOKEN=hf_xxxx

# 1. Train. Omit the filters to run the full cross product.
uv run python train_classifier.py --monuments sagrada_familia --models vit

# 2. Export the checkpoint the board will run.
uv run python export_to_onnx.py \
    ./outputs/sagrada_familia-vit-finetuned ./onnx_export/sagrada_familia-vit

# 3. Pick OOD thresholds from the validation split.
uv run python calibrate_thresholds.py ./onnx_export/sagrada_familia-vit sagrada_familia

# 4. Spot-check a photo.
uv run python inference.py ./onnx_export/sagrada_familia-vit photo.jpg --verbose
```

Step 3 prints an `inference:` snippet to paste under the matching monument or
model entry in `config.yaml`. Step 2's two output files are what get copied to
the board, under `models/vision/<location>/`.

## config.yaml

Currently 4 monuments x 2 models = **8 runs** per full pass.

```yaml
dataset:
  name: culturaviva/image_1080
  val_size: 0.15
  test_size: 0.15
  seed: 42

training_defaults:        # applied to every run unless a model overrides it
  num_epochs: 8
  batch_size: 16
  learning_rate: 2e-5

monuments:                # each is culturaviva/image_1080/<data_dir>
  - name: casa_batllo     #   2 classes
    data_dir: casa_batllo
  - name: park_guell      #   7 classes
    data_dir: park_guell
  - name: pedrera         #   3 classes
    data_dir: pedrera
  - name: sagrada_familia #   6 classes
    data_dir: sagrada_familia

models:
  - name: mobilenetv2
    vision_model_name: google/mobilenet_v2_1.0_224
  - name: vit
    vision_model_name: google/vit-base-patch16-224
    learning_rate: 2e-5   # per-model override
```

Element classes are auto-detected from each monument's own subfolders, so class
counts differ freely between monuments — nothing assumes they match. Adding a
monument or a model extends the cross product on the next run; no code changes.

Output directory and W&B run name both default to `<monument>-<model>`
(e.g. `sagrada_familia-vit`), so runs never overwrite each other. Override per
model with `output_dir:` / `run_name:`.

## OOD detection

A visitor will point the camera at a tree, a tourist, or the sky. The gate
rejects a prediction as `not_sure` when either signal says the input is
off-distribution:

- **entropy** `H(p) = -Σ p·ln(p)` exceeds `entropy_threshold`
  (default `0.5 · ln(N)`, auto-scaled to the monument's class count), or
- **confidence** `max(p)` falls below `confidence_threshold` (default `0.50`).

Thresholds merge global → monument → model → CLI flag, highest wins, so a
backbone that runs less confident can be loosened on its own without touching
the others. `calibrate_thresholds.py --recall-target` sets how much
in-distribution recall to preserve when suggesting values (default 95%).

## Offline runs

If the per-monument subset isn't cached but the full dataset is,
`dataset.py` loads the whole thing and filters it down by label prefix:

```bash
export HF_DATASETS_OFFLINE=1
uv run python train_classifier.py
```

## Setup

```bash
uv sync
```

Requires Python >= 3.10. Training wants a GPU; `inference.py` and
`export_to_onnx.py` run fine on CPU.
