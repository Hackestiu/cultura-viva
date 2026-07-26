import wave

import torch

import pipeline


class _FakeSegment:
    def __init__(self, text):
        self.text = text


class _FakeWhisperModel:
    def __init__(self, model_path):
        self.model_path = model_path

    def transcribe(self, audio_path):
        return [_FakeSegment(" hello "), _FakeSegment("world ")]


def test_transcribe_joins_segments(monkeypatch):
    monkeypatch.setattr(pipeline, "WhisperModel", _FakeWhisperModel)
    assert pipeline.transcribe("input.wav") == "hello world"


class _FakeLlama:
    last_kwargs = None

    def __init__(self, **kwargs):
        _FakeLlama.last_kwargs = kwargs

    def __call__(self, prompt, max_tokens, stop):
        _FakeLlama.last_prompt = prompt
        return {"choices": [{"text": " a generated answer "}]}


def test_ask_slm_includes_vision_context_in_prompt(monkeypatch):
    monkeypatch.setattr(pipeline, "Llama", _FakeLlama)

    reply = pipeline.ask_slm(
        "When was it built?",
        image_labels=["sagrada família (95% confidence)"],
    )

    assert reply == "a generated answer"
    prompt = _FakeLlama.last_prompt
    assert "sagrada família (95% confidence)" in prompt
    assert "When was it built?" in prompt


def test_ask_slm_without_image_labels_omits_vision_context(monkeypatch):
    monkeypatch.setattr(pipeline, "Llama", _FakeLlama)

    pipeline.ask_slm("What is this?")

    prompt = _FakeLlama.last_prompt
    assert "The image shows" not in prompt


class _FakeImageProcessor:
    @staticmethod
    def from_pretrained(name):
        return _FakeImageProcessor()

    def __call__(self, images, return_tensors):
        return {}


class _FakeVisionModel:
    class _Config:
        id2label = {0: "sagrada família", 1: "casa batlló"}

    config = _Config()

    @staticmethod
    def from_pretrained(name):
        return _FakeVisionModel()

    def __call__(self, **inputs):
        logits = torch.tensor([[5.0, 0.1]])
        return type("Output", (), {"logits": logits})()


def test_classify_image_returns_labels_above_threshold(monkeypatch, tmp_path):
    from PIL import Image

    monkeypatch.setattr(pipeline, "AutoImageProcessor", _FakeImageProcessor)
    monkeypatch.setattr(pipeline, "MobileNetV2ForImageClassification", _FakeVisionModel)
    monkeypatch.setattr(Image, "open", lambda path: Image.new("RGB", (4, 4)))

    labels = pipeline.classify_image("fake.jpg", confidence_threshold=0.15, max_labels=2)

    assert len(labels) == 1
    assert labels[0].startswith("sagrada família")


class _FakeVoice:
    def __init__(self):
        self.synthesized = []

    def synthesize_wav(self, text, wav_file):
        self.synthesized.append(text)
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(16000)
        wav_file.writeframes(b"\x00\x00")


def test_synthesize_writes_wav_file(monkeypatch, tmp_path):
    fake_voice = _FakeVoice()
    monkeypatch.setattr(pipeline.PiperVoice, "load", staticmethod(lambda path: fake_voice))

    output_path = tmp_path / "out.wav"
    pipeline.synthesize("hello there", str(output_path))

    assert fake_voice.synthesized == ["hello there"]
    assert output_path.exists()
    with wave.open(str(output_path), "rb") as f:
        assert f.getnchannels() == 1
