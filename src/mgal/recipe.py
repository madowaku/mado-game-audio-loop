from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


class RecipeError(ValueError):
    pass


@dataclass(frozen=True)
class Layer:
    source: str
    gain: float = 1.0
    offset_ms: int = 0


@dataclass(frozen=True)
class Recipe:
    recipe_version: str
    id: str
    intent: str
    layers: tuple[Layer, ...]
    normalize: bool = True
    fade_out_ms: int = 0


def _require(data: dict[str, Any], key: str, expected_type: type) -> Any:
    if key not in data:
        raise RecipeError(f"missing required field: {key}")
    value = data[key]
    if not isinstance(value, expected_type):
        raise RecipeError(f"{key} must be {expected_type.__name__}")
    return value


def load_recipe(path: str | Path) -> Recipe:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))

    version = _require(data, "recipe_version", str)
    recipe_id = _require(data, "id", str)
    intent = _require(data, "intent", str)
    raw_layers = _require(data, "layers", list)

    if version != "0.1":
        raise RecipeError(f"unsupported recipe_version: {version}")
    if not raw_layers:
        raise RecipeError("layers must not be empty")
    if len(raw_layers) > 4:
        raise RecipeError("M0.1 supports at most 4 layers")

    layers: list[Layer] = []
    for index, item in enumerate(raw_layers):
        if not isinstance(item, dict):
            raise RecipeError(f"layers[{index}] must be an object")
        source = _require(item, "source", str)
        gain = item.get("gain", 1.0)
        offset_ms = item.get("offset_ms", 0)
        if not isinstance(gain, (int, float)):
            raise RecipeError(f"layers[{index}].gain must be numeric")
        if not isinstance(offset_ms, int) or offset_ms < 0:
            raise RecipeError(f"layers[{index}].offset_ms must be a non-negative integer")
        layers.append(Layer(source=source, gain=float(gain), offset_ms=offset_ms))

    processing = data.get("processing", {})
    if not isinstance(processing, dict):
        raise RecipeError("processing must be an object")

    normalize = processing.get("normalize", True)
    fade_out_ms = processing.get("fade_out_ms", 0)
    if not isinstance(normalize, bool):
        raise RecipeError("processing.normalize must be boolean")
    if not isinstance(fade_out_ms, int) or fade_out_ms < 0:
        raise RecipeError("processing.fade_out_ms must be a non-negative integer")

    return Recipe(
        recipe_version=version,
        id=recipe_id,
        intent=intent,
        layers=tuple(layers),
        normalize=normalize,
        fade_out_ms=fade_out_ms,
    )
