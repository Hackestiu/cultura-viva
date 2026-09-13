"""
OOD-aware inference wrapper for gaudi-vision ONNX checkpoints.

For any exported (monument, model) ONNX checkpoint this module:
  1. Loads model.onnx + labels.json (id2label, num_classes, image_size, mean, std).
  2. Preprocesses the input image identically to eval-time transforms:
       Resize (shortest edge -> image_size) -> CenterCrop -> Normalize.
  3. Runs inference through onnxruntime.
  4. Computes Shannon entropy  H(p) = -sum p_i * ln(p_i).
  5. Flags the prediction as OOD ("not_sure") when:
         entropy   >  entropy_threshold            (default: 0.5 * ln(N))
       OR
         max(p)    <  confidence_threshold         (default: 0.50)

Threshold priority (highest wins):
    CLI flag  >  model-level config.yaml  >  monument-level config.yaml  >  global config.yaml  >  auto

Usage (standalone):
    python inference.py <onnx_export_dir> <image_path> [options]

    Examples:
    python inference.py onnx_export/sagrada_familia-vit photo.jpg
    python inference.py onnx_export/sagrada_familia-vit photo.jpg --verbose
    python inference.py onnx_export/park_guell-vit tree.jpg --entropy-threshold 0.85

Programmatic usage:
    from inference import MonumentClassifier
    clf = MonumentClassifier("onnx_export/sagrada_familia-vit")
    result = clf.predict_path("photo.jpg")
    print(result.label, result.is_ood)
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
import onnxruntime as ort
from PIL import Image

# -- Constants -----------------------------------------------------------------

DEFAULT_CONFIDENCE_THRESHOLD = 0.50
CONFIG_PATH = os.environ.get("CONFIG_PATH", "config.yaml")

# -- Data types ----------------------------------------------------------------


@dataclass
class PredictionResult:
    """Structured output of a single MonumentClassifier.predict() call."""

    label: str
    """Top predicted class name, or not_sure_label when is_ood is True."""

    confidence: float
    """max(softmax) of the raw logits."""

    entropy: float
    """Shannon entropy H(p) = -sum p_i * ln(p_i), base-e."""

    entropy_threshold: float
    """Effective entropy threshold used for this prediction."""

    confidence_threshold: float
    """Effective confidence threshold used for this prediction."""

    is_ood: bool
    """True when entropy > entropy_threshold OR confidence < confidence_threshold."""

    probabilities: dict = field(default_factory=dict)
    """Per-class softmax probabilities keyed by class name."""


# -- Math helpers --------------------------------------------------------------


def softmax(logits: np.ndarray) -> np.ndarray:
    """Numerically stable row-wise softmax."""
    shifted = logits - logits.max()
    exp = np.exp(shifted)
    return exp / exp.sum()


def shannon_entropy(probs: np.ndarray) -> float:
    """Shannon entropy H(p) = -sum p_i * ln(p_i), base-e, in nats."""
    clipped = np.clip(probs, 1e-12, 1.0)
    return float(-np.sum(clipped * np.log(clipped)))


# -- Config helpers ------------------------------------------------------------


def _load_config(config_path: str = CONFIG_PATH) -> dict:
    """Load config.yaml; return empty dict if file is missing."""
    try:
        import yaml
        with open(config_path) as fh:
            return yaml.safe_load(fh) or {}
    except FileNotFoundError:
        return {}


def _resolve_thresholds(
    config_path: str,
    monument_name: Optional[str],
    model_name: Optional[str],
    cli_entropy: Optional[float],
    cli_confidence: Optional[float],
    num_classes: int,
) -> tuple:
    """
    Merge inference thresholds following the priority chain:
        global config.yaml -> monument -> model -> CLI flag  (highest wins)

    Returns (entropy_threshold, confidence_threshold, not_sure_label).
    """
    cfg = _load_config(config_path)

    # 1 -- global defaults
    global_inf = cfg.get("inference", {})
    entropy_thresh = global_inf.get("entropy_threshold")       # None = auto
    confidence_thresh = float(global_inf.get("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD))
    not_sure_label = global_inf.get("not_sure_label", "not_sure")

    # 2 -- monument-level override
    if monument_name:
        for m in cfg.get("monuments", []):
            if m.get("name") == monument_name:
                m_inf = m.get("inference", {})
                if "entropy_threshold" in m_inf:
                    entropy_thresh = m_inf["entropy_threshold"]
                if "confidence_threshold" in m_inf:
                    confidence_thresh = float(m_inf["confidence_threshold"])
                if "not_sure_label" in m_inf:
                    not_sure_label = m_inf["not_sure_label"]
                break

    # 3 -- model-level override
    if model_name:
        for m in cfg.get("models", []):
            if m.get("name") == model_name:
                m_inf = m.get("inference", {})
                if "entropy_threshold" in m_inf:
                    entropy_thresh = m_inf["entropy_threshold"]
                if "confidence_threshold" in m_inf:
                    confidence_thresh = float(m_inf["confidence_threshold"])
                if "not_sure_label" in m_inf:
                    not_sure_label = m_inf["not_sure_label"]
                break

    # 4 -- CLI flag (highest priority)
    if cli_entropy is not None:
        entropy_thresh = cli_entropy
    if cli_confidence is not None:
        confidence_thresh = float(cli_confidence)

    # 5 -- auto-formula if still None after all overrides
    if entropy_thresh is None:
        entropy_thresh = 0.5 * math.log(num_classes)

    return float(entropy_thresh), float(confidence_thresh), str(not_sure_label)


# -- Main class ----------------------------------------------------------------


class MonumentClassifier:
    """
    OOD-aware ONNX image classifier for a single (monument, model) checkpoint.

    Parameters
    ----------
    checkpoint_dir : str or Path
        Directory produced by export_to_onnx.py, containing:
          - model.onnx
          - labels.json   (keys: id2label, num_classes, image_size, image_mean, image_std)
    entropy_threshold : float or None
        Hard-override the entropy threshold. None = use auto (0.5 * ln(N)) or
        whatever config.yaml specifies for this monument/model.
    confidence_threshold : float or None
        Hard-override the confidence threshold. None = use config.yaml or default (0.50).
    not_sure_label : str or None
        Label emitted for OOD inputs. None = use config.yaml value or "not_sure".
    monument_name : str or None
        If provided, reads monument-level inference overrides from config.yaml.
    model_name : str or None
        If provided, reads model-level inference overrides from config.yaml.
    config_path : str
        Path to config.yaml (default: CONFIG_PATH env var or "config.yaml").
    """

    def __init__(
        self,
        checkpoint_dir,
        entropy_threshold: Optional[float] = None,
        confidence_threshold: Optional[float] = None,
        not_sure_label: Optional[str] = None,
        monument_name: Optional[str] = None,
        model_name: Optional[str] = None,
        config_path: str = CONFIG_PATH,
    ):
        checkpoint_dir = Path(checkpoint_dir)
        meta_path = checkpoint_dir / "labels.json"
        onnx_path = checkpoint_dir / "model.onnx"

        if not meta_path.exists():
            raise FileNotFoundError(f"labels.json not found in: {checkpoint_dir}")
        if not onnx_path.exists():
            raise FileNotFoundError(f"model.onnx not found in: {checkpoint_dir}")

        with open(meta_path) as fh:
            meta = json.load(fh)

        self.id2label: dict = {int(k): v for k, v in meta["id2label"].items()}
        self.num_classes: int = meta.get("num_classes", len(self.id2label))
        self.image_size: int = meta.get("image_size", 224)
        self.image_mean: list = meta.get("image_mean", [0.485, 0.456, 0.406])
        self.image_std: list = meta.get("image_std", [0.229, 0.224, 0.225])

        # Resolve thresholds through the full priority chain
        resolved_entropy, resolved_confidence, resolved_label = _resolve_thresholds(
            config_path=config_path,
            monument_name=monument_name,
            model_name=model_name,
            cli_entropy=entropy_threshold,
            cli_confidence=confidence_threshold,
            num_classes=self.num_classes,
        )
        self.entropy_threshold: float = resolved_entropy
        self.confidence_threshold: float = resolved_confidence
        self.not_sure_label: str = not_sure_label if not_sure_label is not None else resolved_label

        # ONNX Runtime session -- prefer CUDA, fall back to CPU silently
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        self._session = ort.InferenceSession(str(onnx_path), providers=providers)
        self._input_name: str = self._session.get_inputs()[0].name

    # -- Preprocessing ---------------------------------------------------------

    def _preprocess(self, image: Image.Image) -> np.ndarray:
        """
        Replicate the eval-time torchvision pipeline in pure numpy/Pillow:
            Resize (shortest edge -> image_size) -> CenterCrop -> ToTensor -> Normalize
        Returns a float32 array of shape (1, C, H, W).
        """
        s = self.image_size
        w, h = image.size

        # Resize so the shortest edge equals s (preserving aspect ratio)
        if w <= h:
            new_w, new_h = s, max(s, int(round(h * s / w)))
        else:
            new_w, new_h = max(s, int(round(w * s / h))), s
        image = image.resize((new_w, new_h), Image.BILINEAR)

        # Center crop to (s, s)
        left = (new_w - s) // 2
        top  = (new_h - s) // 2
        image = image.crop((left, top, left + s, top + s))

        # PIL -> float32 array in [0, 1], shape H x W x C
        arr = np.array(image, dtype=np.float32) / 255.0

        # Channel-wise normalisation
        mean = np.array(self.image_mean, dtype=np.float32)
        std  = np.array(self.image_std,  dtype=np.float32)
        arr = (arr - mean) / std

        # H x W x C -> 1 x C x H x W (NCHW batch of size 1)
        return arr.transpose(2, 0, 1)[np.newaxis, ...]

    # -- Inference -------------------------------------------------------------

    def predict(self, image: Image.Image) -> PredictionResult:
        """
        Run OOD-aware inference on a single PIL image.

        Parameters
        ----------
        image : PIL.Image.Image
            Input image in any mode; converted to RGB internally.

        Returns
        -------
        PredictionResult
        """
        arr = self._preprocess(image.convert("RGB"))
        logits: np.ndarray = self._session.run(None, {self._input_name: arr})[0][0]

        probs      = softmax(logits)
        entropy    = shannon_entropy(probs)
        confidence = float(probs.max())
        top_idx    = int(probs.argmax())
        top_label  = self.id2label[top_idx]

        is_ood = entropy > self.entropy_threshold or confidence < self.confidence_threshold
        label  = self.not_sure_label if is_ood else top_label

        probabilities = {self.id2label[i]: float(p) for i, p in enumerate(probs)}

        return PredictionResult(
            label=label,
            confidence=confidence,
            entropy=entropy,
            entropy_threshold=self.entropy_threshold,
            confidence_threshold=self.confidence_threshold,
            is_ood=is_ood,
            probabilities=probabilities,
        )

    def predict_path(self, image_path) -> PredictionResult:
        """Convenience wrapper: open image from a filesystem path and call predict()."""
        return self.predict(Image.open(image_path))


# -- CLI -----------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="inference.py",
        description="OOD-aware inference on a gaudi-vision ONNX checkpoint.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("checkpoint_dir", help="Path to the onnx_export/<monument-model>/ directory.")
    p.add_argument("image", help="Path to the input image file.")
    p.add_argument(
        "--entropy-threshold", type=float, default=None, metavar="H",
        help="Override entropy threshold. Default: 0.5 * ln(N) (auto).",
    )
    p.add_argument(
        "--confidence-threshold", type=float, default=None, metavar="P",
        help="Override confidence threshold. Default: from config.yaml or 0.50.",
    )
    p.add_argument(
        "--monument", default=None, metavar="NAME",
        help="Monument name (e.g. sagrada_familia) to load monument-level thresholds.",
    )
    p.add_argument(
        "--model", default=None, metavar="NAME",
        help="Model name (e.g. vit) to load model-level thresholds from config.yaml.",
    )
    p.add_argument(
        "--config", default=CONFIG_PATH, metavar="PATH",
        help="Path to config.yaml.",
    )
    p.add_argument("--verbose", action="store_true", help="Print per-class probability bars.")
    return p


def main() -> None:
    args = _build_parser().parse_args()

    classifier = MonumentClassifier(
        checkpoint_dir=args.checkpoint_dir,
        entropy_threshold=args.entropy_threshold,
        confidence_threshold=args.confidence_threshold,
        monument_name=args.monument,
        model_name=args.model,
        config_path=args.config,
    )

    result = classifier.predict_path(args.image)

    # Pretty-print result
    width = 54
    print(f"\n{'=' * width}")
    print(f"  Image      : {Path(args.image).name}")
    print(f"  Prediction : {result.label}")
    ood_tag = "YES -> not_sure" if result.is_ood else "NO  -> in-distribution"
    print(f"  OOD flag   : {ood_tag}")
    print(f"  {'-' * (width - 2)}")
    c_ok = "OK" if result.confidence >= result.confidence_threshold else "FAIL"
    e_ok = "OK" if result.entropy    <= result.entropy_threshold    else "FAIL"
    print(f"  Confidence : {result.confidence:.4f}  (>= {result.confidence_threshold:.4f})  [{c_ok}]")
    print(f"  Entropy    : {result.entropy:.4f}  (<= {result.entropy_threshold:.4f})  [{e_ok}]")

    if args.verbose:
        print(f"  {'-' * (width - 2)}")
        print("  Class probabilities:")
        bar_max = width - 40
        for cls, p in sorted(result.probabilities.items(), key=lambda x: -x[1]):
            bar = "#" * max(1, int(p * bar_max))
            print(f"    {cls:<28} {p:.4f}  {bar}")

    print(f"{'=' * width}\n")


if __name__ == "__main__":
    main()
