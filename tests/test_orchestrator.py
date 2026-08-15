import pytest

import main
from main import Personality
from vision.classifiers import Location


def _patch_common(monkeypatch, transcript="What is this?"):
    monkeypatch.setattr(main, "transcribe", lambda audio_path: transcript)
    monkeypatch.setattr(main, "synthesize", lambda text, output_path: None)

    calls = {}

    def fake_ask_slm(prompt_text, image_labels=None, system_prompt=None, kg_context=None):
        calls["prompt_text"] = prompt_text
        calls["image_labels"] = image_labels
        calls["system_prompt"] = system_prompt
        calls["kg_context"] = kg_context
        return "a generated answer"

    monkeypatch.setattr(main, "ask_slm", fake_ask_slm)
    return calls


def test_run_routes_pedrera_classifier(monkeypatch):
    calls = _patch_common(monkeypatch)
    monkeypatch.setattr(main, "classify_for_location", lambda location, image_path: "chimney")

    result = main.run(Location.PEDRERA, Personality.TECHNICAL, "input.wav", "photo.jpg")

    assert result.element == "chimney"
    assert calls["image_labels"] == ["chimney"]


def test_run_routes_park_guell_classifier(monkeypatch):
    calls = _patch_common(monkeypatch)
    monkeypatch.setattr(main, "classify_for_location", lambda location, image_path: "dragon")

    result = main.run(Location.PARK_GUELL, Personality.TECHNICAL, "input.wav", "photo.jpg")

    assert result.element == "dragon"
    assert calls["image_labels"] == ["dragon"]


def test_run_without_image_has_no_element_or_context(monkeypatch):
    calls = _patch_common(monkeypatch)
    monkeypatch.setattr(main, "classify_for_location", lambda location, image_path: None)

    result = main.run(Location.PEDRERA, Personality.ARTISTIC, "input.wav", image_path=None)

    assert result.element is None
    assert calls["image_labels"] is None
    assert calls["kg_context"] is None


def test_run_with_image_attaches_knowledge_graph_context(monkeypatch):
    calls = _patch_common(monkeypatch)
    monkeypatch.setattr(main, "classify_for_location", lambda location, image_path: "chimney")

    main.run(Location.PEDRERA, Personality.ARTISTIC, "input.wav", "photo.jpg")

    assert calls["kg_context"] is not None
    assert "Pedrera" in calls["kg_context"]


@pytest.mark.parametrize("personality", list(Personality))
def test_run_selects_system_prompt_for_personality(monkeypatch, personality):
    calls = _patch_common(monkeypatch)
    monkeypatch.setattr(main, "classify_for_location", lambda location, image_path: None)

    main.run(Location.PEDRERA, personality, "input.wav")

    assert calls["system_prompt"] == main.SYSTEM_PROMPTS[personality]


def test_run_raises_on_empty_transcript(monkeypatch):
    _patch_common(monkeypatch, transcript="   ")
    monkeypatch.setattr(main, "classify_for_location", lambda location, image_path: None)

    with pytest.raises(ValueError):
        main.run(Location.PEDRERA, Personality.CHILD, "input.wav")
