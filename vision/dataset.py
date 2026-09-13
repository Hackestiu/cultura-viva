"""Loading and splitting of the per-monument Hugging Face datasets.

Both train_classifier.py and calibrate_thresholds.py go through
`load_monument_dataset` so that calibration always sees exactly the split the
model was trained on -- if the two drifted, thresholds would be calibrated on
images the model had already been fit to.
"""

from __future__ import annotations

import os
import time

from datasets import ClassLabel, DatasetDict, load_dataset

MAX_RETRIES = 5
BACKOFF_SECONDS = 30


def _is_offline_error(err: Exception) -> bool:
    """True when the Hub was unreachable or the requested subset is not cached."""
    text = str(err).lower()
    return (
        "couldn't find cache" in text
        or "offlinemodeisenabled" in text
        or ("couldn't reach" in text and "offline" in text)
    )


def _is_rate_limit_error(err: Exception) -> bool:
    text = str(err).lower()
    return "429" in text or "too many requests" in text or "rate limit" in text


def _load_with_retry(hf_dataset_name: str, **load_kwargs) -> DatasetDict:
    """load_dataset with backoff on Hub rate limits.

    Offline/cache-miss errors are re-raised at once so the caller can fall back
    to filtering the full cached dataset.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return load_dataset(hf_dataset_name, **load_kwargs)
        except Exception as err:
            if _is_offline_error(err) or not _is_rate_limit_error(err) or attempt == MAX_RETRIES:
                raise
            wait = attempt * BACKOFF_SECONDS
            print(f"\n[Warning] Hugging Face rate limit (429), attempt {attempt}/{MAX_RETRIES}.")
            print(f"Waiting {wait}s before retrying...")
            time.sleep(wait)


def _filter_to_monument(full_dataset: DatasetDict, monument_name: str, data_dir: str) -> DatasetDict:
    """Cut the full cached dataset down to one monument, relabelled 0..N-1.

    Label names in the full dataset encode the subfolder path (e.g.
    "park_guell/escalinata_drac"), so the monument is the leading segment.
    """
    all_label_names = full_dataset["train"].features["label"].names
    indices = [
        i for i, name in enumerate(all_label_names)
        if name.split("/")[0] == data_dir
    ]
    if not indices:
        raise ValueError(
            f"No labels for monument '{monument_name}' (data_dir='{data_dir}') in the "
            f"full cached dataset. Available labels: {all_label_names}"
        )

    local_names = [all_label_names[i].split("/")[-1] for i in indices]
    old_to_new = {old: new for new, old in enumerate(indices)}
    keep = set(indices)

    def remap(split):
        filtered = split.filter(lambda ex: ex["label"] in keep)
        filtered = filtered.map(lambda ex: {"label": old_to_new[ex["label"]]})
        features = filtered.features.copy()
        features["label"] = ClassLabel(names=local_names)
        return filtered.cast(features)

    print(f"[Info] Filtered to {len(indices)} classes for '{monument_name}': {local_names}")
    return DatasetDict({name: remap(split) for name, split in full_dataset.items()})


def load_monument_dataset(cfg: dict, monument_name: str, data_dir: str) -> DatasetDict:
    """Load one monument's dataset as a train/validation/test DatasetDict.

    Tries the per-monument HF subset first; if only the full dataset is cached
    (offline runs), falls back to loading it whole and filtering. Splits are
    stratified by label and seeded from config.yaml, so repeated calls for the
    same monument return identical splits.
    """
    hf_dataset_name = cfg["dataset"]["name"]
    val_size = cfg["dataset"]["val_size"]
    test_size = cfg["dataset"]["test_size"]
    seed = cfg["dataset"]["seed"]

    # export HF_TOKEN=hf_xxxx, or rely on huggingface-cli login
    token_kwargs = {}
    hf_token = os.environ.get("HF_TOKEN")
    if hf_token:
        token_kwargs["token"] = hf_token

    try:
        raw = _load_with_retry(hf_dataset_name, data_dir=data_dir, **token_kwargs)
    except Exception as err:
        if not _is_offline_error(err):
            print(f"\n[Error] Failed to load dataset: {err}")
            print("\nTip: to use an already-cached copy, set HF_DATASETS_OFFLINE=1")
            raise
        print(f"\n[Info] Per-monument cache not found for '{data_dir}'.")
        print(f"[Info] Loading the full cached dataset and filtering for '{monument_name}'...")
        full = _load_with_retry(hf_dataset_name, **token_kwargs)
        raw = _filter_to_monument(full, monument_name, data_dir)

    if "test" in raw or "validation" in raw:
        return raw

    # No upstream splits: carve train -> train/validation/test ourselves.
    train_rest = raw["train"].train_test_split(
        test_size=val_size + test_size, seed=seed, stratify_by_column="label"
    )
    val_test = train_rest["test"].train_test_split(
        test_size=test_size / (val_size + test_size), seed=seed, stratify_by_column="label"
    )
    return DatasetDict({
        "train": train_rest["train"],
        "validation": val_test["train"],
        "test": val_test["test"],
    })


def validation_split(cfg: dict, monument_name: str, data_dir: str):
    """The split calibration runs on: the monument's validation images."""
    dataset = load_monument_dataset(cfg, monument_name, data_dir)
    return dataset["validation"]
