from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .delta_inspector import (
    DeltaInspectorError,
    validate_delta_inspector_pack,
)


VARIATION_BRIEF_VERSION = "0.1"

DIMENSIONS = {
    "layers",
    "gain",
    "offset",
    "fade",
    "normalize",
    "sources",
    "other",
}

ACTIONS = {
    "increase",
    "decrease",
    "hold",
    "add",
    "remove",
    "replace",
    "toggle",
    "custom",
}

REFERENCE_ROLES = {
    "past_winner",
    "past_loser",
}


class VariationBriefError(ValueError):
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


def variation_brief_root(
    audio_root: str | Path,
) -> Path:
    return (
        Path(audio_root).resolve()
        / ".mgal"
        / "variation-briefs"
    )


def _clean_text(
    value: object,
    *,
    field: str,
    required: bool = True,
    max_length: int = 2000,
) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str):
        raise VariationBriefError(
            f"{field} must be a string"
        )
    cleaned = value.strip()
    if required and not cleaned:
        raise VariationBriefError(
            f"{field} must not be empty"
        )
    if len(cleaned) > max_length:
        raise VariationBriefError(
            f"{field} is too long"
        )
    return cleaned or None


def _validate_change(
    change: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(change, dict):
        raise VariationBriefError(
            "planned_change must be an object"
        )

    dimension = change.get("dimension")
    action = change.get("action")
    amount = change.get("amount")
    unit = change.get("unit")
    note = change.get("note")

    if dimension not in DIMENSIONS:
        raise VariationBriefError(
            "planned_change.dimension is unsupported"
        )
    if action not in ACTIONS:
        raise VariationBriefError(
            "planned_change.action is unsupported"
        )
    if amount is not None and (
        not isinstance(amount, (int, float))
        or isinstance(amount, bool)
    ):
        raise VariationBriefError(
            "planned_change.amount must be numeric or null"
        )
    if isinstance(amount, float):
        amount = round(amount, 6)
    if unit is not None:
        unit = _clean_text(
            unit,
            field="planned_change.unit",
            required=False,
            max_length=40,
        )
    note = _clean_text(
        note,
        field="planned_change.note",
        required=False,
        max_length=1000,
    )

    if dimension in {"offset", "fade"}:
        if amount is not None and unit not in {"ms"}:
            raise VariationBriefError(
                f"{dimension} amount must use unit 'ms'"
            )
    elif dimension == "gain":
        if amount is not None and unit not in {"ratio"}:
            raise VariationBriefError(
                "gain amount must use unit 'ratio'"
            )
    elif dimension == "layers":
        if amount is not None:
            if (
                not isinstance(amount, int)
                or amount < 0
                or unit != "count"
            ):
                raise VariationBriefError(
                    "layers amount must be a non-negative integer with unit 'count'"
                )
    elif dimension == "normalize":
        if amount is not None or unit is not None:
            raise VariationBriefError(
                "normalize change does not accept amount/unit"
            )
    elif dimension in {"sources", "other"}:
        if amount is not None:
            raise VariationBriefError(
                f"{dimension} change does not accept numeric amount"
            )

    return {
        "dimension": dimension,
        "action": action,
        "amount": amount,
        "unit": unit,
        "note": note,
    }


def validate_planned_change(
    change: dict[str, Any],
) -> dict[str, Any]:
    """Validate and normalize a Variation Brief planned change."""
    return _validate_change(change)


def _reference_from_inspector(
    inspector: dict[str, Any],
    reference: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if reference is None:
        return None
    if not isinstance(reference, dict):
        raise VariationBriefError(
            "reference must be an object or null"
        )

    entry_id = reference.get("entry_id")
    role = reference.get("role")
    if not isinstance(entry_id, str) or not entry_id:
        raise VariationBriefError(
            "reference.entry_id must be a string"
        )
    if role not in REFERENCE_ROLES:
        raise VariationBriefError(
            "reference.role must be past_winner or past_loser"
        )

    inspection = next(
        (
            item
            for item in inspector["inspections"]
            if item.get("entry_id") == entry_id
        ),
        None,
    )
    if inspection is None:
        raise VariationBriefError(
            "reference entry is absent from Delta Inspector"
        )

    field = (
        "current_vs_winner"
        if role == "past_winner"
        else "current_vs_loser"
    )
    comparison = inspection[field]
    candidate_field = (
        "winner_candidate_id"
        if role == "past_winner"
        else "loser_candidate_id"
    )

    return {
        "entry_id": entry_id,
        "archive_id": inspection[
            "archive_id"
        ],
        "source_intent": inspection[
            "source_intent"
        ],
        "pair_index": inspection[
            "pair_index"
        ],
        "role": role,
        "candidate_id": inspection[
            candidate_field
        ],
        "reference_recipe": comparison[
            "reference_recipe"
        ],
        "current_minus_reference": comparison[
            "delta"
        ],
    }


def build_variation_brief(
    inspector: dict[str, Any],
    human_input: dict[str, Any],
) -> dict[str, Any]:
    try:
        validate_delta_inspector_pack(
            inspector
        )
    except DeltaInspectorError as exc:
        raise VariationBriefError(
            f"Delta Inspector is invalid: {exc}"
        ) from exc

    if not isinstance(human_input, dict):
        raise VariationBriefError(
            "human_input must be an object"
        )

    hypothesis = _clean_text(
        human_input.get("hypothesis"),
        field="hypothesis",
    )
    listening_for = _clean_text(
        human_input.get("listening_for"),
        field="listening_for",
    )
    change = _validate_change(
        human_input.get("planned_change")
    )

    raw_preserve = human_input.get(
        "preserve",
        [],
    )
    if not isinstance(raw_preserve, list):
        raise VariationBriefError(
            "preserve must be a list"
        )
    preserve: list[str] = []
    for index, item in enumerate(
        raw_preserve
    ):
        cleaned = _clean_text(
            item,
            field=f"preserve[{index}]",
            max_length=200,
        )
        if cleaned not in preserve:
            preserve.append(cleaned)

    reference = _reference_from_inspector(
        inspector,
        human_input.get("reference"),
    )

    payload: dict[str, Any] = {
        "variation_brief_version": VARIATION_BRIEF_VERSION,
        "basis": {
            "delta_inspector_id": inspector[
                "delta_inspector_id"
            ],
            "context_pack_id": inspector[
                "context_pack_id"
            ],
            "decision_memory_sha256": inspector[
                "decision_memory_sha256"
            ],
            "query": inspector["query"],
            "current_recipe": inspector[
                "current_recipe"
            ],
            "reference": reference,
        },
        "human_input": {
            "authorship": "human_explicit",
            "hypothesis": hypothesis,
            "listening_for": listening_for,
            "planned_change": change,
            "preserve": preserve,
        },
        "authority": {
            "recipe_mutation": "none",
            "candidate_selection": "none",
            "candidate_generation": "none",
        },
    }
    payload["brief_id"] = (
        "brief:" + _sha256_json(payload)[:20]
    )
    return payload


def validate_variation_brief(
    data: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise VariationBriefError(
            "Variation Brief must be an object"
        )
    if (
        data.get("variation_brief_version")
        != VARIATION_BRIEF_VERSION
    ):
        raise VariationBriefError(
            "unsupported variation_brief_version"
        )

    basis = data.get("basis")
    if not isinstance(basis, dict):
        raise VariationBriefError(
            "Variation Brief basis must be an object"
        )
    for field in (
        "delta_inspector_id",
        "context_pack_id",
        "decision_memory_sha256",
    ):
        if (
            not isinstance(
                basis.get(field),
                str,
            )
            or not basis[field]
        ):
            raise VariationBriefError(
                f"Variation Brief basis {field} must be a string"
            )
    if not isinstance(
        basis.get("query"),
        dict,
    ):
        raise VariationBriefError(
            "Variation Brief basis query must be an object"
        )
    if not isinstance(
        basis.get("current_recipe"),
        dict,
    ):
        raise VariationBriefError(
            "Variation Brief basis current_recipe must be an object"
        )

    reference = basis.get("reference")
    if reference is not None:
        if not isinstance(reference, dict):
            raise VariationBriefError(
                "Variation Brief reference must be an object or null"
            )
        if (
            reference.get("role")
            not in REFERENCE_ROLES
        ):
            raise VariationBriefError(
                "Variation Brief reference role is invalid"
            )
        for field in (
            "entry_id",
            "archive_id",
            "candidate_id",
        ):
            if (
                not isinstance(
                    reference.get(field),
                    str,
                )
                or not reference[field]
            ):
                raise VariationBriefError(
                    f"Variation Brief reference {field} is invalid"
                )
        if not isinstance(
            reference.get(
                "reference_recipe"
            ),
            dict,
        ):
            raise VariationBriefError(
                "Variation Brief reference_recipe must be an object"
            )
        if not isinstance(
            reference.get(
                "current_minus_reference"
            ),
            dict,
        ):
            raise VariationBriefError(
                "Variation Brief current_minus_reference must be an object"
            )

    human_input = data.get(
        "human_input"
    )
    if not isinstance(human_input, dict):
        raise VariationBriefError(
            "Variation Brief human_input must be an object"
        )
    if (
        human_input.get("authorship")
        != "human_explicit"
    ):
        raise VariationBriefError(
            "Variation Brief must record human_explicit authorship"
        )
    _clean_text(
        human_input.get("hypothesis"),
        field="hypothesis",
    )
    _clean_text(
        human_input.get("listening_for"),
        field="listening_for",
    )
    normalized_change = _validate_change(
        human_input.get(
            "planned_change"
        )
    )
    if normalized_change != human_input.get(
        "planned_change"
    ):
        raise VariationBriefError(
            "Variation Brief planned_change is not normalized"
        )

    preserve = human_input.get(
        "preserve"
    )
    if (
        not isinstance(preserve, list)
        or not all(
            isinstance(item, str)
            and item.strip() == item
            and item
            for item in preserve
        )
        or len(set(preserve)) != len(
            preserve
        )
    ):
        raise VariationBriefError(
            "Variation Brief preserve list is invalid"
        )

    if data.get("authority") != {
        "recipe_mutation": "none",
        "candidate_selection": "none",
        "candidate_generation": "none",
    }:
        raise VariationBriefError(
            "Variation Brief authority boundary is invalid"
        )

    forbidden = {
        "generated_recipe",
        "recommended_candidate",
        "auto_select",
        "candidate_ranking",
        "preference_score",
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
        raise VariationBriefError(
            "Variation Brief contains an automatic-action field"
        )

    brief_id = data.get("brief_id")
    if not isinstance(brief_id, str):
        raise VariationBriefError(
            "Variation Brief brief_id must be a string"
        )
    payload = dict(data)
    payload.pop("brief_id", None)
    expected_id = (
        "brief:" + _sha256_json(payload)[:20]
    )
    if brief_id != expected_id:
        raise VariationBriefError(
            "Variation Brief brief_id does not match payload"
        )

    return {
        "ok": True,
        "brief_id": brief_id,
        "referenced_entry": (
            reference["entry_id"]
            if reference is not None
            else None
        ),
    }


def save_variation_brief(
    audio_root: str | Path,
    brief: dict[str, Any],
) -> dict[str, Any]:
    validate_variation_brief(brief)
    root = variation_brief_root(
        audio_root
    )
    root.mkdir(
        parents=True,
        exist_ok=True,
    )
    brief_id = brief["brief_id"]
    slug = brief_id.split(
        ":",
        1,
    )[-1]
    path = root / f"{slug}.json"

    content = (
        json.dumps(
            brief,
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    reused = False
    if path.is_file():
        existing = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
        if existing != brief:
            raise VariationBriefError(
                "Variation Brief ID collision with different content"
            )
        reused = True
    else:
        temporary = path.with_suffix(
            ".tmp"
        )
        temporary.write_text(
            content,
            encoding="utf-8",
        )
        temporary.replace(path)

    return {
        "ok": True,
        "brief_id": brief_id,
        "path": str(path),
        "reused": reused,
    }


def create_variation_brief(
    audio_root: str | Path,
    inspector: dict[str, Any],
    human_input: dict[str, Any],
) -> dict[str, Any]:
    brief = build_variation_brief(
        inspector,
        human_input,
    )
    saved = save_variation_brief(
        audio_root,
        brief,
    )
    return {
        "brief": brief,
        "saved": saved,
    }


def load_variation_brief(
    path: str | Path,
) -> dict[str, Any]:
    try:
        data = json.loads(
            Path(path).read_text(
                encoding="utf-8"
            )
        )
    except json.JSONDecodeError as exc:
        raise VariationBriefError(
            "Variation Brief contains invalid JSON"
        ) from exc
    if not isinstance(data, dict):
        raise VariationBriefError(
            "Variation Brief must contain an object"
        )
    validate_variation_brief(data)
    return data


def list_variation_briefs(
    audio_root: str | Path,
) -> list[dict[str, Any]]:
    root = variation_brief_root(
        audio_root
    )
    if not root.is_dir():
        return []

    result: list[dict[str, Any]] = []
    for path in sorted(
        root.glob("*.json")
    ):
        try:
            brief = load_variation_brief(
                path
            )
        except (
            OSError,
            VariationBriefError,
        ) as exc:
            result.append(
                {
                    "ok": False,
                    "path": str(path),
                    "error": str(exc),
                }
            )
            continue

        human = brief["human_input"]
        reference = brief[
            "basis"
        ]["reference"]
        result.append(
            {
                "ok": True,
                "brief_id": brief[
                    "brief_id"
                ],
                "hypothesis": human[
                    "hypothesis"
                ],
                "listening_for": human[
                    "listening_for"
                ],
                "dimension": human[
                    "planned_change"
                ]["dimension"],
                "action": human[
                    "planned_change"
                ]["action"],
                "referenced_entry": (
                    reference["entry_id"]
                    if reference is not None
                    else None
                ),
                "reference_role": (
                    reference["role"]
                    if reference is not None
                    else None
                ),
                "path": str(path),
            }
        )
    return result
