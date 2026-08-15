from enum import Enum
from typing import Callable, Optional


class Location(Enum):
    """Physical site the visitor is standing at."""

    PEDRERA = "pedrera"
    PARK_GUELL = "park_guell"


def classify_pedrera(image_path: Optional[str]) -> Optional[str]:
    """Mock classifier for La Pedrera. Replace with a trained per-location
    MobileNetV2 model (see train_classifier.py) once one exists."""
    if not image_path:
        return None
    print(f"[VISION][pedrera] (mock) classifying {image_path}...")
    return "chimney"


def classify_park_guell(image_path: Optional[str]) -> Optional[str]:
    """Mock classifier for Park Güell. Replace with a trained per-location
    MobileNetV2 model (see train_classifier.py) once one exists."""
    if not image_path:
        return None
    print(f"[VISION][park_guell] (mock) classifying {image_path}...")
    return "dragon"


ClassifierFn = Callable[[Optional[str]], Optional[str]]

CLASSIFIERS: dict[Location, ClassifierFn] = {
    Location.PEDRERA: classify_pedrera,
    Location.PARK_GUELL: classify_park_guell,
}


def classify_for_location(location: Location, image_path: Optional[str]) -> Optional[str]:
    """Route to the classifier registered for the given location."""
    classifier = CLASSIFIERS[location]
    return classifier(image_path)
