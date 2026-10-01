from pathlib import Path
import wave

from mgal.audio import read_wav_metadata


def test_read_wav_metadata(tmp_path: Path):
    path = tmp_path / "sample.wav"
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 800)

    metadata = read_wav_metadata(path)
    assert metadata.duration_ms == 100
    assert metadata.sample_rate == 8000
    assert metadata.channels == 1
