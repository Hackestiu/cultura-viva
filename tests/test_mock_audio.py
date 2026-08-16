import wave

from models import mock_audio


def test_generate_writes_valid_wav_file(tmp_path):
    output_path = tmp_path / "sample.wav"

    mock_audio.generate(str(output_path), duration_seconds=0.5)

    assert output_path.exists()
    with wave.open(str(output_path), "rb") as f:
        assert f.getnchannels() == 1
        assert f.getframerate() == mock_audio._SAMPLE_RATE
        assert f.getnframes() == int(mock_audio._SAMPLE_RATE * 0.5)
