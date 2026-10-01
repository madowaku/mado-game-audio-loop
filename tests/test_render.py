from array import array
from pathlib import Path
import json
import wave

from mgal.recipe import load_recipe
from mgal.render import render_recipe


def _write_tone(path: Path, samples: list[int]) -> None:
    data = array("h", samples)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(data.tobytes())


def test_render_two_layers(tmp_path: Path):
    a = tmp_path / "a.wav"
    b = tmp_path / "b.wav"
    _write_tone(a, [1000] * 80)
    _write_tone(b, [500] * 80)

    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(
        json.dumps({
            "recipe_version": "0.1",
            "id": "test",
            "intent": "test",
            "layers": [
                {"source": "a.wav", "gain": 1.0, "offset_ms": 0},
                {"source": "b.wav", "gain": 1.0, "offset_ms": 0}
            ],
            "processing": {"normalize": False, "fade_out_ms": 0}
        }),
        encoding="utf-8",
    )

    recipe = load_recipe(recipe_path)
    output = tmp_path / "out.wav"
    render_recipe(recipe, recipe_path, output)

    assert output.exists()
    with wave.open(str(output), "rb") as wav:
        assert wav.getnframes() == 80
        assert wav.getframerate() == 8000


def test_render_can_resolve_sources_from_audio_root(tmp_path: Path):
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    source = audio_root / "slash.wav"
    _write_tone(source, [900] * 40)

    downloads = tmp_path / "downloads"
    downloads.mkdir()
    recipe_path = downloads / "recipe.json"
    recipe_path.write_text(
        json.dumps({
            "recipe_version": "0.1",
            "id": "downloaded",
            "intent": "downloaded browser recipe",
            "layers": [{"source": "slash.wav", "gain": 0.5, "offset_ms": 0}],
            "processing": {"normalize": False, "fade_out_ms": 0}
        }),
        encoding="utf-8",
    )

    output = tmp_path / "out.wav"
    render_recipe(
        load_recipe(recipe_path),
        recipe_path,
        output,
        source_root=audio_root,
    )

    assert output.exists()
