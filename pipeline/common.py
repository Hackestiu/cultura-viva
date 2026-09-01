"""Shared Cultura Viva speech-to-text context and output cleanup."""

from __future__ import annotations

import re
from pathlib import Path


PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = PIPELINE_DIR.parent
MODELS_DIR = PROJECT_DIR / "models"

DOMAIN_PROMPT = (
    "Cultura Viva audio guide in Barcelona about Antoni Gaudí, Sagrada Família basilica, "
    "Nativity, Passion, and Glory facades, Catalan modernisme architecture, Casa Batlló, "
    "Casa Milà, Park Güell, dragon and salamander sculptures, and trencadís mosaics."
)

DOMAIN_KEYWORD_ALIASES = {
    "Antoni Gaudí": ("antoni gaudí", "antoni gaudi", "gaudí", "gaudi"),
    "Gaudí": ("gaudí", "gaudi", "antoni gaudí", "antoni gaudi"),
    "Barcelona": ("barcelona", "barcelona city"),
    "Passeig de Gràcia": ("passeig de gràcia", "passeig de gracia", "paseo de gracia"),
    "Temple Expiatori": ("temple expiatori", "expiatory temple", "expiatory church"),
    "Sagrada Família": ("sagrada família", "sagrada familia", "basilica of the sagrada familia"),
    "basilica": ("basilica", "basílica"),
    "facade": ("facade", "facades", "façade", "façades"),
    "Nativity facade": ("nativity facade", "nativity façade", "nativity"),
    "Passion facade": ("passion facade", "passion façade", "passion"),
    "Glory facade": ("glory facade", "glory façade", "glory"),
    "modernisme": ("modernisme", "modernism", "catalan modernisme"),
    "Catalan": ("catalan", "catalonia", "catalonian"),
    "Casa Batlló": ("casa batlló", "casa batllo", "batlló", "batllo"),
    "Casa Milà": ("casa milà", "casa mila", "la pedrera", "pedrera"),
    "La Pedrera": ("la pedrera", "pedrera", "the quarry"),
    "Park Güell": ("park güell", "park guell", "guell"),
    "Eixample": ("eixample", "eixample district", "example district"),
    "trencadís": ("trencadís", "trencadis", "broken tile mosaic"),
    "salamander": ("salamander", "el drac", "dragon salamander"),
    "dragon": ("dragon", "dragon-shaped", "dragon shaped", "dragon roof"),
    "catenary arch": ("catenary arch", "catenary arches", "parabolic arch"),
}

_CORRECTIONS = {
    r"\bgaudi\b": "Gaudí",
    r"\bgaudy\b": "Gaudí",
    r"\bcasa batl[óo]\b": "Casa Batlló",
    r"\bcasa batio\b": "Casa Batlló",
    r"\bcasa batlow\b": "Casa Batlló",
    r"\bcasa bortlow\b": "Casa Batlló",
    r"\bcasa mila\b": "Casa Milà",
    r"\bpark guell\b": "Park Güell",
    r"\bparkway\b": "Park Güell",
    r"\btrencadis\b": "trencadís",
    r"\btrincadis\b": "trencadís",
    r"\bmodernism\b": "modernisme",
    r"\bcatalonian\b": "Catalan",
    r"\bdrag on\b": "dragon",
}


def build_hotwords() -> str:
    """Return the shared domain vocabulary for faster-whisper hotword biasing."""
    return " ".join(DOMAIN_KEYWORD_ALIASES)


def canonicalize_domain_entities(text: str) -> str:
    """Normalize common ASR spellings without changing unrelated speech."""
    for pattern, replacement in _CORRECTIONS.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text.strip()


def transcribe_result(text: str) -> str:
    """Apply the same final cleanup used when scoring benchmark predictions."""
    return canonicalize_domain_entities(" ".join(text.split()))