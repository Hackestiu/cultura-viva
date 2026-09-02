"""
vision_module.py — Vision classifier for Gaudí architectural elements.

Given the path of a photo taken by CameraManager and the location name
returned by LocationRegistry.current(), returns the name of the Gaudí
element detected in the photo (or None if none is detected with sufficient confidence).

CURRENT MODELS (ONNX, exported from the training pipeline):
  - Sagrada Família: models/vision/sagrada_familia/model.onnx + labels.json
    Classes: cupula, facana_naixement, facana_passio, laterals, posterior, torres
  - Park Güell:      models/vision/park_guell/model.onnx + labels.json
    Classes: 3_viaductes, casa_museu, escalinata_drac, pavellons_consergeria,
             placa_natura, sala_hipostila, turo_3_creus

Runtime dependencies: onnxruntime, Pillow, numpy  (no torch / transformers needed)
  pip install onnxruntime pillow numpy

DO NOT modify the signature of classify() or the class name — main.py
already imports and uses them.
"""

import json
from pathlib import Path

import numpy as np

# -----------------------------------------------------------------------
# Root directory for vision model subfolders.
# NOTE: If you move or rename the folder, update VISION_MODEL_DIR in
# config.py (or this constant below).
# -----------------------------------------------------------------------
try:
    from config import MODELS_DIR
    VISION_MODEL_DIR = MODELS_DIR / "vision"
except ImportError:
    VISION_MODEL_DIR = Path(__file__).parent / "models" / "vision"

# Minimum softmax probability to accept a prediction as valid.
# Increase if the model produces false positives; decrease if it fails to detect.
CONFIDENCE_THRESHOLD = 0.5

# Recognized location folder names — each must contain model.onnx + labels.json.
LOCATION_MODEL_DIRS: dict[str, Path] = {
    "sagrada_familia": VISION_MODEL_DIR / "sagrada_familia",
    "park_guell":      VISION_MODEL_DIR / "park_guell",
}


# ---------------------------------------------------------------------------
# Preprocessing helpers (matches the val/test transforms used during training)
# ---------------------------------------------------------------------------

def _preprocess(image_path: Path, size: int, mean: list, std: list) -> np.ndarray:
    """Resize (shortest side to `size`), center-crop (size x size),
    normalize, and convert HWC -> NCHW float32 for ONNX Runtime."""
    from PIL import Image

    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    scale = size / min(w, h)
    img = img.resize((round(w * scale), round(h * scale)), Image.BILINEAR)
    w, h = img.size
    left = (w - size) // 2
    top  = (h - size) // 2
    img  = img.crop((left, top, left + size, top + size))

    arr = np.asarray(img).astype(np.float32) / 255.0            # HWC  [0, 1]
    arr = (arr - np.array(mean, dtype=np.float32)) \
               / np.array(std,  dtype=np.float32)                # normalize
    arr = arr.transpose(2, 0, 1)                                 # CHW
    return np.expand_dims(arr, 0).astype(np.float32)             # NCHW


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - np.max(x))
    return e / e.sum()


# ---------------------------------------------------------------------------
# Main classifier class
# ---------------------------------------------------------------------------

class VisionClassifier:
    """Classifies a photo to detect which Gaudí element is present.

    Called from main.py:
        element = vision.classify(site, camera.last_photo_path)

    Returns a string such as 'torres' or 'escalinata_drac', or None if no
    element is detected with sufficient confidence (or if the model is unavailable).

    Models are loaded lazily on the first call for each location and reused
    thereafter (ONNX Runtime session + metadata dict).
    """

    def __init__(self):
        # { location_name: (ort.InferenceSession, meta_dict) | None }
        self._sessions: dict = {}

    def classify(self, location: str, photo_path) -> str | None:
        """Returns the Gaudí element detected in the photo, or None.

        :param location:   'park_guell' or 'sagrada_familia'
                           (returned by location_module.LocationRegistry.current())
        :param photo_path: path to the .jpg file (Path or str) of the last captured photo
        """
        if photo_path is None:
            return None

        path = Path(photo_path)
        if not path.exists():
            print(f"[WARN] vision_module: photo not found: {path}")
            return None

        session_meta = self._load_session(location)
        if session_meta is None:
            return None

        session, meta = session_meta
        return self._run_inference(session, meta, path, location)

    # -----------------------------------------------------------------------
    # Internals
    # -----------------------------------------------------------------------

    def _load_session(self, location: str):
        """Lazily loads the ONNX Runtime session for the given location.
        Returns (InferenceSession, meta_dict) or None if the model is missing.
        """
        if location in self._sessions:
            return self._sessions[location]

        model_dir = LOCATION_MODEL_DIRS.get(location)
        if model_dir is None:
            print(f"[WARN] vision_module: unknown location '{location}'. Returning None.")
            self._sessions[location] = None
            return None

        onnx_path   = model_dir / "model.onnx"
        labels_path = model_dir / "labels.json"

        if not onnx_path.exists():
            print(
                f"[WARN] vision_module: ONNX model not found at {onnx_path}. "
                "Ensure model.onnx and labels.json are in the model folder. Returning None."
            )
            self._sessions[location] = None
            return None

        if not labels_path.exists():
            print(
                f"[WARN] vision_module: labels.json not found at {labels_path}. "
                "Returning None."
            )
            self._sessions[location] = None
            return None

        try:
            import onnxruntime as ort

            with open(labels_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

            session = ort.InferenceSession(
                str(onnx_path),
                providers=["CPUExecutionProvider"],
            )
            self._sessions[location] = (session, meta)
            print(f"[OK] vision_module: ONNX model loaded for '{location}' from {model_dir}")
            return self._sessions[location]

        except ImportError:
            print(
                "[WARN] vision_module: 'onnxruntime' is not installed. "
                "Run: pip install onnxruntime pillow numpy. Returning None."
            )
            self._sessions[location] = None
            return None
        except Exception as exc:
            print(f"[ERROR] vision_module: error loading model for '{location}': {exc}")
            self._sessions[location] = None
            return None

    def _run_inference(self, session, meta: dict, photo_path: Path, location: str) -> str | None:
        """Runs ONNX inference on the photo.
        Returns the winning class label if it exceeds CONFIDENCE_THRESHOLD, or None.
        """
        try:
            pixel_values = _preprocess(
                photo_path,
                size=meta["image_size"],
                mean=meta["image_mean"],
                std=meta["image_std"],
            )

            outputs = session.run(["logits"], {"pixel_values": pixel_values})
            logits  = outputs[0][0]
            probs   = _softmax(logits)

            top_idx    = int(np.argmax(probs))
            confidence = float(probs[top_idx])
            id2label   = meta["id2label"]
            label      = id2label.get(str(top_idx), str(top_idx))

            print(
                f"[OK] vision_module: '{label}' "
                f"(confidence: {confidence:.1%}, location: {location})"
            )

            if confidence < CONFIDENCE_THRESHOLD:
                print(
                    f"[WARN] vision_module: confidence {confidence:.1%} < "
                    f"threshold {CONFIDENCE_THRESHOLD:.0%} — returning None."
                )
                return None

            return label

        except ImportError:
            print(
                "[WARN] vision_module: 'Pillow' is not installed. "
                "Run: pip install pillow. Returning None."
            )
            return None
        except Exception as exc:
            print(f"[ERROR] vision_module: error during inference: {exc}")
            return None
