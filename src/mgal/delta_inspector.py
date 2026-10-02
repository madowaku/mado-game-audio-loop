from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .context_pack import (
    DecisionContextError,
    load_decision_context_pack,
    validate_decision_context_pack,
)
from .decision_memory import load_decision_memory
from .recipe import RecipeError, parse_recipe


DELTA_INSPECTOR_VERSION = "0.1"


class DeltaInspectorError(ValueError):
    pass


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        _canonical_json_bytes(value)
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_source(
    audio_root: Path,
    source: str,
) -> Path:
    logical = Path(source)
    if logical.is_absolute():
        raise DeltaInspectorError(
            f"current Recipe source must be relative: {source}"
        )
    candidate = (audio_root / logical).resolve()
    try:
        candidate.relative_to(audio_root)
    except ValueError as exc:
        raise DeltaInspectorError(
            f"current Recipe source escapes audio root: {source}"
        ) from exc
    if not candidate.is_file():
        raise DeltaInspectorError(
            f"current Recipe source is missing: {source}"
        )
    return candidate


def summarize_current_recipe(
    recipe_data: dict[str, Any],
    audio_root: str | Path,
) -> dict[str, Any]:
    if not isinstance(recipe_data, dict):
        raise DeltaInspectorError(
            "current Recipe must be an object"
        )
    try:
        recipe = parse_recipe(recipe_data)
    except RecipeError as exc:
        raise DeltaInspectorError(
            f"current Recipe is invalid: {exc}"
        ) from exc

    root = Path(audio_root).resolve()
    if not root.is_dir():
        raise DeltaInspectorError(
            f"audio root does not exist: {root}"
        )

    source_ids: list[str] = []
    gains: list[float] = []
    offsets: list[int] = []

    for layer in recipe.layers:
        path = _resolve_source(
            root,
            layer.source,
        )
        source_ids.append(
            "sha256:" + _sha256_file(path)
        )
        gains.append(layer.gain)
        offsets.append(layer.offset_ms)

    return {
        "recipe_id": recipe.id,
        "recipe_sha256": _sha256_json(
            recipe_data
        ),
        "intent": recipe.intent,
        "layer_count": len(recipe.layers),
        "total_gain": round(
            sum(gains),
            6,
        ),
        "earliest_offset_ms": (
            min(offsets)
            if offsets
            else 0
        ),
        "latest_offset_ms": (
            max(offsets)
            if offsets
            else 0
        ),
        "normalize": recipe.normalize,
        "fade_out_ms": recipe.fade_out_ms,
        "source_ids": sorted(source_ids),
    }


def _validate_summary(
    summary: dict[str, Any],
    *,
    label: str,
) -> None:
    if not isinstance(summary, dict):
        raise DeltaInspectorError(
            f"{label} Recipe summary must be an object"
        )

    scalar_types = {
        "recipe_sha256": str,
        "layer_count": int,
        "total_gain": (int, float),
        "earliest_offset_ms": int,
        "latest_offset_ms": int,
        "normalize": bool,
        "fade_out_ms": int,
    }
    for field, expected in scalar_types.items():
        value = summary.get(field)
        if not isinstance(value, expected):
            raise DeltaInspectorError(
                f"{label} Recipe summary {field} is invalid"
            )

    source_ids = summary.get("source_ids")
    if (
        not isinstance(source_ids, list)
        or not all(
            isinstance(item, str)
            and item.startswith("sha256:")
            for item in source_ids
        )
    ):
        raise DeltaInspectorError(
            f"{label} Recipe summary source_ids are invalid"
        )


def recipe_delta(
    current: dict[str, Any],
    reference: dict[str, Any],
) -> dict[str, Any]:
    _validate_summary(
        current,
        label="current",
    )
    _validate_summary(
        reference,
        label="reference",
    )

    current_sources = set(
        current["source_ids"]
    )
    reference_sources = set(
        reference["source_ids"]
    )

    return {
        "direction": "current_minus_reference",
        "layer_count_delta": (
            current["layer_count"]
            - reference["layer_count"]
        ),
        "total_gain_delta": round(
            float(current["total_gain"])
            - float(reference["total_gain"]),
            6,
        ),
        "earliest_offset_ms_delta": (
            current["earliest_offset_ms"]
            - reference["earliest_offset_ms"]
        ),
        "latest_offset_ms_delta": (
            current["latest_offset_ms"]
            - reference["latest_offset_ms"]
        ),
        "fade_out_ms_delta": (
            current["fade_out_ms"]
            - reference["fade_out_ms"]
        ),
        "normalize_changed": (
            current["normalize"]
            != reference["normalize"]
        ),
        "shared_source_count": len(
            current_sources & reference_sources
        ),
        "current_only_source_count": len(
            current_sources - reference_sources
        ),
        "reference_only_source_count": len(
            reference_sources - current_sources
        ),
    }


def _memory_sha256(
    audio_root: str | Path,
) -> str:
    memory = load_decision_memory(
        audio_root
    )
    return _sha256_json(memory)


def _validate_context_freshness(
    context_pack: dict[str, Any],
    audio_root: str | Path,
) -> None:
    try:
        validate_decision_context_pack(
            context_pack
        )
    except DecisionContextError as exc:
        raise DeltaInspectorError(
            f"Decision Context Pack is invalid: {exc}"
        ) from exc

    current_memory_hash = _memory_sha256(
        audio_root
    )
    if (
        context_pack[
            "decision_memory_sha256"
        ]
        != current_memory_hash
    ):
        raise DeltaInspectorError(
            "Decision Context Pack is stale: Decision Memory fingerprint changed"
        )


def build_delta_inspector_pack(
    audio_root: str | Path,
    context_pack: dict[str, Any],
    current_recipe: dict[str, Any],
) -> dict[str, Any]:
    _validate_context_freshness(
        context_pack,
        audio_root,
    )
    current_summary = summarize_current_recipe(
        current_recipe,
        audio_root,
    )

    inspections: list[dict[str, Any]] = []
    for observation in context_pack[
        "observations"
    ]:
        winner = observation[
            "winner_recipe"
        ]
        loser = observation[
            "loser_recipe"
        ]
        inspections.append(
            {
                "entry_id": observation[
                    "entry_id"
                ],
                "archive_id": observation[
                    "archive_id"
                ],
                "source_intent": observation[
                    "source_intent"
                ],
                "pair_index": observation[
                    "pair_index"
                ],
                "winner_candidate_id": observation[
                    "winner_candidate_id"
                ],
                "loser_candidate_id": observation[
                    "loser_candidate_id"
                ],
                "past_observed_differences": observation[
                    "observed_differences"
                ],
                "current_vs_winner": {
                    "reference_role": "past_winner",
                    "reference_recipe": winner,
                    "delta": recipe_delta(
                        current_summary,
                        winner,
                    ),
                },
                "current_vs_loser": {
                    "reference_role": "past_loser",
                    "reference_recipe": loser,
                    "delta": recipe_delta(
                        current_summary,
                        loser,
                    ),
                },
            }
        )

    payload: dict[str, Any] = {
        "delta_inspector_version": DELTA_INSPECTOR_VERSION,
        "context_pack_id": context_pack[
            "context_pack_id"
        ],
        "decision_memory_sha256": context_pack[
            "decision_memory_sha256"
        ],
        "query": context_pack["query"],
        "current_recipe": current_summary,
        "inspection_count": len(
            inspections
        ),
        "inspections": inspections,
        "usage": {
            "role": "observation_only",
            "selection_effect": "none",
            "mutation_effect": "none",
        },
    }
    payload["delta_inspector_id"] = (
        "delta:" + _sha256_json(payload)[:20]
    )
    return payload


def validate_delta_inspector_pack(
    data: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise DeltaInspectorError(
            "Delta Inspector Pack must be an object"
        )
    if (
        data.get("delta_inspector_version")
        != DELTA_INSPECTOR_VERSION
    ):
        raise DeltaInspectorError(
            "unsupported delta_inspector_version"
        )

    if data.get("usage") != {
        "role": "observation_only",
        "selection_effect": "none",
        "mutation_effect": "none",
    }:
        raise DeltaInspectorError(
            "Delta Inspector usage boundary is invalid"
        )

    forbidden = {
        "recommended_candidate",
        "auto_select",
        "preference_score",
        "candidate_ranking",
        "closer_to",
        "similarity_score",
        "apply_winner",
    }
    keys: set[str] = set()

    def collect_keys(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                keys.add(str(key))
                collect_keys(child)
        elif isinstance(value, list):
            for child in value:
                collect_keys(child)

    collect_keys(data)
    if forbidden & keys:
        raise DeltaInspectorError(
            "Delta Inspector contains an automatic-evaluation field"
        )

    current = data.get(
        "current_recipe"
    )
    _validate_summary(
        current,
        label="current",
    )

    inspections = data.get(
        "inspections"
    )
    if not isinstance(inspections, list):
        raise DeltaInspectorError(
            "Delta Inspector inspections must be a list"
        )
    if data.get("inspection_count") != len(
        inspections
    ):
        raise DeltaInspectorError(
            "Delta Inspector inspection_count does not match inspections"
        )

    seen: set[str] = set()
    for item in inspections:
        if not isinstance(item, dict):
            raise DeltaInspectorError(
                "Delta Inspector inspection must be an object"
            )
        entry_id = item.get("entry_id")
        if (
            not isinstance(entry_id, str)
            or not entry_id
        ):
            raise DeltaInspectorError(
                "Delta Inspector entry_id must be a string"
            )
        if entry_id in seen:
            raise DeltaInspectorError(
                f"duplicate Delta Inspector entry: {entry_id}"
            )
        seen.add(entry_id)

        for field, role in (
            (
                "current_vs_winner",
                "past_winner",
            ),
            (
                "current_vs_loser",
                "past_loser",
            ),
        ):
            comparison = item.get(field)
            if not isinstance(
                comparison,
                dict,
            ):
                raise DeltaInspectorError(
                    f"{entry_id}: {field} must be an object"
                )
            if (
                comparison.get(
                    "reference_role"
                )
                != role
            ):
                raise DeltaInspectorError(
                    f"{entry_id}: {field} reference role is invalid"
                )
            reference = comparison.get(
                "reference_recipe"
            )
            _validate_summary(
                reference,
                label=role,
            )
            expected = recipe_delta(
                current,
                reference,
            )
            if comparison.get(
                "delta"
            ) != expected:
                raise DeltaInspectorError(
                    f"{entry_id}: {field} delta does not recompute"
                )

    inspector_id = data.get(
        "delta_inspector_id"
    )
    if not isinstance(
        inspector_id,
        str,
    ):
        raise DeltaInspectorError(
            "delta_inspector_id must be a string"
        )
    payload = dict(data)
    payload.pop(
        "delta_inspector_id",
        None,
    )
    expected_id = (
        "delta:" + _sha256_json(payload)[:20]
    )
    if inspector_id != expected_id:
        raise DeltaInspectorError(
            "delta_inspector_id does not match payload"
        )

    return {
        "ok": True,
        "delta_inspector_id": inspector_id,
        "inspections": len(
            inspections
        ),
    }


def write_delta_inspector_pack(
    audio_root: str | Path,
    context_pack_path: str | Path,
    recipe_path: str | Path,
    output_path: str | Path,
) -> Path:
    context_pack = load_decision_context_pack(
        context_pack_path
    )

    recipe_path = Path(recipe_path)
    try:
        recipe_data = json.loads(
            recipe_path.read_text(
                encoding="utf-8"
            )
        )
    except json.JSONDecodeError as exc:
        raise DeltaInspectorError(
            "current Recipe contains invalid JSON"
        ) from exc
    if not isinstance(recipe_data, dict):
        raise DeltaInspectorError(
            "current Recipe must contain an object"
        )

    pack = build_delta_inspector_pack(
        audio_root,
        context_pack,
        recipe_data,
    )
    validate_delta_inspector_pack(pack)

    output = Path(output_path).resolve()
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output.write_text(
        json.dumps(
            pack,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def load_delta_inspector_pack(
    path: str | Path,
) -> dict[str, Any]:
    try:
        data = json.loads(
            Path(path).read_text(
                encoding="utf-8"
            )
        )
    except json.JSONDecodeError as exc:
        raise DeltaInspectorError(
            "Delta Inspector Pack contains invalid JSON"
        ) from exc
    if not isinstance(data, dict):
        raise DeltaInspectorError(
            "Delta Inspector Pack must contain an object"
        )
    validate_delta_inspector_pack(
        data
    )
    return data
