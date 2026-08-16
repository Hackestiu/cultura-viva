# Training per-monument, per-model classifiers

`train_classifier.py` trains one classifier for every combination of
**monument** x **model**, each as a fully separate run: separate dataset
split, separate model instance, separate output directory, separate W&B run.

With 4 monuments and 6 models in the default `config.yaml`, that's 24
trained versions from a single `python train_classifier.py`.

## config.yaml structure

```yaml
dataset:
  name: culturaviva/gaudi_image
  val_size: 0.15
  test_size: 0.15
  seed: 42

training_defaults:       # applied to every run unless overridden
  num_epochs: 100
  batch_size: 8
  learning_rate: 3e-5

wandb:
  project: cultura-viva

monuments:                # each is culturaviva/gaudi_image/<data_dir>
  - name: sagrada_familia
    data_dir: sagrada_familia
  - name: casa_batllo
    data_dir: casa_batllo
  - name: park_guell
    data_dir: park_guell
  - name: casa_mila
    data_dir: casa_mila

models:
  - name: mobilenetv2
    vision_model_name: google/mobilenet_v2_1.0_224
  - name: vit
    vision_model_name: google/vit-base-patch16-224
    learning_rate: 2e-5   # per-model override
```

Each monument's classes ("elements") are auto-detected from that monument's
own subfolders, so the number of classes can differ freely between
monuments -- the script doesn't assume they match.

## How it runs

For each monument, the dataset is loaded and split **once**, then every
model in `models:` is trained on that same split before moving to the next
monument. This avoids re-downloading/re-splitting the dataset once per
model.

Output directory and W&B run name both default to `<monument>-<model>`
(e.g. `sagrada_familia-vit`, `casa_mila-resnet50`), so nothing overwrites
anything else. You can override either per model with `output_dir:` /
`run_name:` if you want a custom naming scheme.

## Run it

```bash
export HF_TOKEN=hf_xxxx
python train_classifier.py
```

## Train a subset

Comment out entries from `monuments:` or `models:` to shrink the matrix, or
point at a smaller config file:

```bash
CONFIG_PATH=config_quick_test.yaml python train_classifier.py
```

## Add a monument or a model

Just add a new entry under `monuments:` (with its `data_dir`) or `models:`
(with its `vision_model_name`) -- the script automatically covers the full
cross product on the next run.