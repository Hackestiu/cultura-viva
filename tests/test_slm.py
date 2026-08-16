from speech import slm


class _FakeLlama:
    last_kwargs = None

    def __init__(self, **kwargs):
        _FakeLlama.last_kwargs = kwargs

    def __call__(self, prompt, max_tokens, stop):
        _FakeLlama.last_prompt = prompt
        return {"choices": [{"text": " a generated answer "}]}


def _use_real_backend(monkeypatch):
    monkeypatch.setattr(slm, "MOCK_MODELS", False)
    monkeypatch.setattr(slm, "Llama", _FakeLlama)


def test_ask_slm_includes_vision_context_in_prompt(monkeypatch):
    _use_real_backend(monkeypatch)

    reply = slm.ask_slm(
        "When was it built?",
        image_labels=["sagrada família (95% confidence)"],
    )

    assert reply == "a generated answer"
    prompt = _FakeLlama.last_prompt
    assert "sagrada família (95% confidence)" in prompt
    assert "When was it built?" in prompt


def test_ask_slm_without_image_labels_omits_vision_context(monkeypatch):
    _use_real_backend(monkeypatch)

    slm.ask_slm("What is this?")

    prompt = _FakeLlama.last_prompt
    assert "The image shows" not in prompt


def test_ask_slm_uses_default_system_prompt_when_none_given(monkeypatch):
    _use_real_backend(monkeypatch)

    slm.ask_slm("What is this?")

    prompt = _FakeLlama.last_prompt
    assert slm.DEFAULT_SYSTEM_PROMPT in prompt


def test_ask_slm_includes_custom_system_prompt_and_kg_context(monkeypatch):
    _use_real_backend(monkeypatch)

    slm.ask_slm(
        "What is this?",
        system_prompt="You are a playful guide for children.",
        kg_context="The dragon was built around 1904-1905.",
    )

    prompt = _FakeLlama.last_prompt
    assert "You are a playful guide for children." in prompt
    assert "The dragon was built around 1904-1905." in prompt
    assert slm.DEFAULT_SYSTEM_PROMPT not in prompt


def test_ask_slm_uses_mock_backend_when_mock_models_enabled(monkeypatch):
    monkeypatch.setattr(slm, "MOCK_MODELS", True)

    reply = slm.ask_slm(
        "What is this?",
        image_labels=["dragon"],
        kg_context="Located at: Park Güell.",
    )

    assert "dragon" in reply
    assert "Park Güell" in reply
