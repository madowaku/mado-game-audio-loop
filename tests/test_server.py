from array import array
from pathlib import Path
import wave

import pytest

from mgal.server import build_catalog, resolve_audio_path


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = array("h", [0] * 800)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(samples.tobytes())


def test_build_catalog_uses_relative_paths(tmp_path: Path):
    audio = tmp_path / "audio"
    _write_wav(audio / "swords" / "slash.wav")

    catalog = build_catalog(audio)

    assert len(catalog) == 1
    assert catalog[0]["relative_path"] == "swords/slash.wav"
    assert catalog[0]["duration_ms"] == 100
    assert catalog[0]["url"] == "/audio/swords/slash.wav"


def test_resolve_audio_path_rejects_escape(tmp_path: Path):
    audio = tmp_path / "audio"
    audio.mkdir()
    outside = tmp_path / "outside.wav"
    _write_wav(outside)

    with pytest.raises(PermissionError):
        resolve_audio_path(audio, "../outside.wav")
