from __future__ import annotations

from array import array
from pathlib import Path
import wave

from .recipe import Recipe


class RenderError(ValueError):
    pass


def _read_pcm16_mono(path: Path) -> tuple[int, array]:
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 2:
            raise RenderError(f"{path}: only 16-bit PCM WAV is supported in v0.x")
        if wav.getnchannels() != 1:
            raise RenderError(f"{path}: only mono WAV is supported in v0.x")
        sample_rate = wav.getframerate()
        samples = array("h")
        samples.frombytes(wav.readframes(wav.getnframes()))
        return sample_rate, samples


def render_recipe(
    recipe: Recipe,
    recipe_path: Path,
    output_path: Path,
    source_root: Path | None = None,
) -> Path:
    loaded: list[tuple[int, int, float, array]] = []
    base_root = source_root.resolve() if source_root is not None else recipe_path.parent.resolve()
    common_rate: int | None = None
    total_frames = 0

    for layer in recipe.layers:
        source = Path(layer.source)
        if not source.is_absolute():
            source = (base_root / source).resolve()

        rate, samples = _read_pcm16_mono(source)
        if common_rate is None:
            common_rate = rate
        elif rate != common_rate:
            raise RenderError("all v0.x layers must share one sample rate")

        offset_frames = round(layer.offset_ms * rate / 1000)
        total_frames = max(total_frames, offset_frames + len(samples))
        loaded.append((rate, offset_frames, layer.gain, samples))

    if common_rate is None:
        raise RenderError("recipe has no layers")

    mixed = [0.0] * total_frames
    for _rate, offset_frames, gain, samples in loaded:
        for i, sample in enumerate(samples):
            mixed[offset_frames + i] += sample * gain

    if recipe.fade_out_ms > 0 and mixed:
        fade_frames = min(len(mixed), round(recipe.fade_out_ms * common_rate / 1000))
        start = len(mixed) - fade_frames
        for i in range(fade_frames):
            factor = 1.0 - (i / max(1, fade_frames - 1))
            mixed[start + i] *= factor

    peak = max((abs(value) for value in mixed), default=0.0)
    scale = (32767.0 / peak) if recipe.normalize and peak > 32767 else 1.0

    pcm = array("h")
    for value in mixed:
        clipped = max(-32768, min(32767, round(value * scale)))
        pcm.append(clipped)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(common_rate)
        wav.writeframes(pcm.tobytes())

    return output_path
