from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import wave


SUPPORTED_SUFFIXES = {".wav"}


@dataclass(frozen=True)
class AudioMetadata:
    path: str
    duration_ms: int
    sample_rate: int
    channels: int
    sample_width: int
    frames: int


def read_wav_metadata(path: str | Path) -> AudioMetadata:
    path = Path(path)
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        sample_rate = wav.getframerate()
        duration_ms = round(frames / sample_rate * 1000) if sample_rate else 0
        return AudioMetadata(
            path=str(path),
            duration_ms=duration_ms,
            sample_rate=sample_rate,
            channels=wav.getnchannels(),
            sample_width=wav.getsampwidth(),
            frames=frames,
        )


def scan_audio(folder: str | Path) -> list[dict[str, object]]:
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(folder)

    rows: list[dict[str, object]] = []
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_SUFFIXES:
            rows.append(asdict(read_wav_metadata(path)))
    return rows
