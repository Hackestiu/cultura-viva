import wave

from speech import tts


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
    monkeypatch.setattr(tts.PiperVoice, "load", staticmethod(lambda path: fake_voice))

    output_path = tmp_path / "out.wav"
    tts.synthesize("hello there", str(output_path))

    assert fake_voice.synthesized == ["hello there"]
    assert output_path.exists()
    with wave.open(str(output_path), "rb") as f:
        assert f.getnchannels() == 1
