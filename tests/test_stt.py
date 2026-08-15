from speech import stt


class _FakeSegment:
    def __init__(self, text):
        self.text = text


class _FakeWhisperModel:
    def __init__(self, model_path):
        self.model_path = model_path

    def transcribe(self, audio_path):
        return [_FakeSegment(" hello "), _FakeSegment("world ")]


def test_transcribe_joins_segments(monkeypatch):
    monkeypatch.setattr(stt, "WhisperModel", _FakeWhisperModel)
    assert stt.transcribe("input.wav") == "hello world"
