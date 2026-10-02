from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .variation_brief import (
    VariationBriefError,
    load_variation_brief,
    validate_variation_brief,
    variation_brief_root,
)


CANDIDATE_PLAN_VERSION = "0.1"

_CONTRAST_ACTIONS = {
    "increase": "decrease",
    "decrease": "increase",
    "add": "remove",
    "remove": "add",
}


class CandidatePlanError(ValueError):
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


def candidate_plan_root(
    audio_root: str | Path,
) -> Path:
    return (
        Path(audio_root).resolve()
        / ".mgal"
        / "candidate-plans"
    )


def load_saved_variation_brief(
    audio_root: str | Path,
    brief_id: str,
) -> dict[str, Any]:
    if not isinstance(brief_id, str) or not brief_id.startswith("brief:"):
        raise CandidatePlanError(
            "brief_id must be a content-addressed Variation Brief ID"
        )
    slug = brief_id.split(":", 1)[1]
    if (
        not slug
        or any(
            character not in "0123456789abcdef"
            for character in slug
        )
    ):
        raise CandidatePlanError(
            "brief_id contains an invalid hash suffix"
        )

    path = variation_brief_root(
        audio_root
    ) / f"{slug}.json"
    if not path.is_file():
        raise CandidatePlanError(
            f"Variation Brief does not exist: {brief_id}"
        )

    try:
        brief = load_variation_brief(
            path
        )
    except VariationBriefError as exc:
        raise CandidatePlanError(
            f"Variation Brief is invalid: {exc}"
        ) from exc

    if brief.get("brief_id") != brief_id:
        raise CandidatePlanError(
            "Variation Brief ID does not match stored content"
        )
    return brief


def _contrast_change(
    change: dict[str, Any],
) -> tuple[str, dict[str, Any] | None, str]:
    action = change["action"]
    inverse = _CONTRAST_ACTIONS.get(
        action
    )
    if inverse is None:
        return (
            "manual_required",
            None,
            "non_invertible_human_change",
        )

    contrast = dict(change)
    contrast["action"] = inverse
    note = contrast.get("note")
    contrast["note"] = (
        f"Deterministic contrast of human action '{action}'."
        + (
            f" Human note: {note}"
            if note
            else ""
        )
    )
    return (
        "resolved",
        contrast,
        "deterministic_inverse_v1",
    )


def compile_candidate_plan(
    brief: dict[str, Any],
) -> dict[str, Any]:
    try:
        validate_variation_brief(
            brief
        )
    except VariationBriefError as exc:
        raise CandidatePlanError(
            f"Variation Brief is invalid: {exc}"
        ) from exc

    human = brief["human_input"]
    basis = brief["basis"]
    planned_change = human[
        "planned_change"
    ]
    (
        contrast_resolution,
        contrast_change,
        contrast_derivation,
    ) = _contrast_change(
        planned_change
    )

    variants: list[dict[str, Any]] = [
        {
            "slot": "A",
            "role": "control",
            "resolution": "resolved",
            "derivation": "preserve_current_recipe",
            "change": None,
            "hypothesis": None,
            "listening_for": human[
                "listening_for"
            ],
        },
        {
            "slot": "B",
            "role": "hypothesis",
            "resolution": "resolved",
            "derivation": "human_variation_brief",
            "change": dict(planned_change),
            "hypothesis": human[
                "hypothesis"
            ],
            "listening_for": human[
                "listening_for"
            ],
        },
        {
            "slot": "C",
            "role": "contrast",
            "resolution": contrast_resolution,
            "derivation": contrast_derivation,
            "change": contrast_change,
            "hypothesis": None,
            "listening_for": human[
                "listening_for"
            ],
        },
    ]

    unresolved_slots = [
        item["slot"]
        for item in variants
        if item["resolution"]
        != "resolved"
    ]

    payload: dict[str, Any] = {
        "candidate_plan_version": CANDIDATE_PLAN_VERSION,
        "variation_brief_id": brief[
            "brief_id"
        ],
        "basis": {
            "delta_inspector_id": basis[
                "delta_inspector_id"
            ],
            "context_pack_id": basis[
                "context_pack_id"
            ],
            "decision_memory_sha256": basis[
                "decision_memory_sha256"
            ],
            "current_recipe": basis[
                "current_recipe"
            ],
            "reference": basis[
                "reference"
            ],
        },
        "experiment": {
            "hypothesis": human[
                "hypothesis"
            ],
            "listening_for": human[
                "listening_for"
            ],
            "planned_change": dict(planned_change),
            "preserve": human[
                "preserve"
            ],
        },
        "variants": variants,
        "unresolved_slots": unresolved_slots,
        "ready_for_materialization": (
            len(unresolved_slots) == 0
        ),
        "authority": {
            "recipe_materialization": "none",
            "candidate_generation": "none",
            "candidate_selection": "none",
        },
    }
    payload["plan_id"] = (
        "plan:" + _sha256_json(payload)[:20]
    )
    return payload


def validate_candidate_plan(
    data: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise CandidatePlanError(
            "Candidate Plan must be an object"
        )
    if (
        data.get("candidate_plan_version")
        != CANDIDATE_PLAN_VERSION
    ):
        raise CandidatePlanError(
            "unsupported candidate_plan_version"
        )

    variation_brief_id = data.get(
        "variation_brief_id"
    )
    if (
        not isinstance(
            variation_brief_id,
            str,
        )
        or not variation_brief_id.startswith(
            "brief:"
        )
    ):
        raise CandidatePlanError(
            "variation_brief_id must be a Variation Brief ID"
        )

    basis = data.get("basis")
    if not isinstance(basis, dict):
        raise CandidatePlanError(
            "Candidate Plan basis must be an object"
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
            raise CandidatePlanError(
                f"Candidate Plan basis {field} must be a string"
            )
    if not isinstance(
        basis.get("current_recipe"),
        dict,
    ):
        raise CandidatePlanError(
            "Candidate Plan basis current_recipe must be an object"
        )

    experiment = data.get(
        "experiment"
    )
    if not isinstance(
        experiment,
        dict,
    ):
        raise CandidatePlanError(
            "Candidate Plan experiment must be an object"
        )
    for field in (
        "hypothesis",
        "listening_for",
    ):
        if (
            not isinstance(
                experiment.get(field),
                str,
            )
            or not experiment[field].strip()
        ):
            raise CandidatePlanError(
                f"Candidate Plan experiment {field} must be non-empty"
            )
    planned_change = experiment.get(
        "planned_change"
    )
    if not isinstance(
        planned_change,
        dict,
    ):
        raise CandidatePlanError(
            "Candidate Plan experiment planned_change must be an object"
        )

    preserve = experiment.get(
        "preserve"
    )
    if (
        not isinstance(
            preserve,
            list,
        )
        or not all(
            isinstance(item, str)
            and item
            for item in preserve
        )
    ):
        raise CandidatePlanError(
            "Candidate Plan preserve must be a list of strings"
        )

    variants = data.get(
        "variants"
    )
    if (
        not isinstance(
            variants,
            list,
        )
        or len(variants) != 3
    ):
        raise CandidatePlanError(
            "Candidate Plan must contain exactly three variants"
        )

    expected = [
        ("A", "control"),
        ("B", "hypothesis"),
        ("C", "contrast"),
    ]
    unresolved: list[str] = []

    for item, (
        expected_slot,
        expected_role,
    ) in zip(variants, expected):
        if not isinstance(
            item,
            dict,
        ):
            raise CandidatePlanError(
                "Candidate Plan variant must be an object"
            )
        if (
            item.get("slot")
            != expected_slot
            or item.get("role")
            != expected_role
        ):
            raise CandidatePlanError(
                "Candidate Plan variant slots/roles must be A-control, B-hypothesis, C-contrast"
            )
        resolution = item.get(
            "resolution"
        )
        if resolution not in {
            "resolved",
            "manual_required",
        }:
            raise CandidatePlanError(
                f"{expected_slot}: invalid resolution"
            )

        change = item.get(
            "change"
        )
        if expected_slot == "A":
            if (
                resolution != "resolved"
                or change is not None
                or item.get("derivation")
                != "preserve_current_recipe"
            ):
                raise CandidatePlanError(
                    "A control must preserve the current Recipe without a change"
                )
        elif expected_slot == "B":
            if (
                resolution != "resolved"
                or not isinstance(
                    change,
                    dict,
                )
                or item.get("derivation")
                != "human_variation_brief"
            ):
                raise CandidatePlanError(
                    "B hypothesis must contain the human planned change"
                )
            if change != planned_change:
                raise CandidatePlanError(
                    "B hypothesis change must match the Variation Brief planned change"
                )
            if item.get(
                "hypothesis"
            ) != experiment[
                "hypothesis"
            ]:
                raise CandidatePlanError(
                    "B hypothesis text must match the experiment hypothesis"
                )
        else:
            (
                expected_resolution,
                expected_change,
                expected_derivation,
            ) = _contrast_change(
                planned_change
            )
            if (
                resolution
                != expected_resolution
                or change
                != expected_change
                or item.get(
                    "derivation"
                )
                != expected_derivation
            ):
                raise CandidatePlanError(
                    "C contrast does not match deterministic contrast derivation"
                )
            if (
                resolution
                == "manual_required"
            ):
                unresolved.append(
                    expected_slot
                )

        listening_for = item.get(
            "listening_for"
        )
        if listening_for != experiment[
            "listening_for"
        ]:
            raise CandidatePlanError(
                f"{expected_slot}: listening target must match experiment"
            )

    if data.get(
        "unresolved_slots"
    ) != unresolved:
        raise CandidatePlanError(
            "Candidate Plan unresolved_slots does not match variants"
        )
    if data.get(
        "ready_for_materialization"
    ) is not (
        len(unresolved) == 0
    ):
        raise CandidatePlanError(
            "Candidate Plan materialization readiness is inconsistent"
        )

    if data.get("authority") != {
        "recipe_materialization": "none",
        "candidate_generation": "none",
        "candidate_selection": "none",
    }:
        raise CandidatePlanError(
            "Candidate Plan authority boundary is invalid"
        )

    forbidden = {
        "generated_recipe",
        "materialized_recipe",
        "selected_candidate_id",
        "recommended_candidate",
        "candidate_ranking",
        "preference_score",
        "auto_select",
        "apply_winner",
    }
    keys: set[str] = set()

    def collect_keys(
        value: object,
    ) -> None:
        if isinstance(
            value,
            dict,
        ):
            for key, child in value.items():
                keys.add(str(key))
                collect_keys(child)
        elif isinstance(
            value,
            list,
        ):
            for child in value:
                collect_keys(child)

    collect_keys(data)
    if forbidden & keys:
        raise CandidatePlanError(
            "Candidate Plan contains a materialization or selection field"
        )

    plan_id = data.get(
        "plan_id"
    )
    if not isinstance(
        plan_id,
        str,
    ):
        raise CandidatePlanError(
            "Candidate Plan plan_id must be a string"
        )
    payload = dict(data)
    payload.pop(
        "plan_id",
        None,
    )
    expected_id = (
        "plan:" + _sha256_json(payload)[:20]
    )
    if plan_id != expected_id:
        raise CandidatePlanError(
            "Candidate Plan plan_id does not match payload"
        )

    return {
        "ok": True,
        "plan_id": plan_id,
        "ready_for_materialization": data[
            "ready_for_materialization"
        ],
        "unresolved_slots": unresolved,
    }


def save_candidate_plan(
    audio_root: str | Path,
    plan: dict[str, Any],
) -> dict[str, Any]:
    validate_candidate_plan(
        plan
    )
    root = candidate_plan_root(
        audio_root
    )
    root.mkdir(
        parents=True,
        exist_ok=True,
    )
    slug = plan[
        "plan_id"
    ].split(":", 1)[1]
    path = root / f"{slug}.json"
    content = (
        json.dumps(
            plan,
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
        if existing != plan:
            raise CandidatePlanError(
                "Candidate Plan ID collision with different content"
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
        temporary.replace(
            path
        )

    return {
        "ok": True,
        "plan_id": plan[
            "plan_id"
        ],
        "path": str(path),
        "reused": reused,
    }


def create_candidate_plan(
    audio_root: str | Path,
    brief: dict[str, Any],
) -> dict[str, Any]:
    plan = compile_candidate_plan(
        brief
    )
    saved = save_candidate_plan(
        audio_root,
        plan,
    )
    return {
        "plan": plan,
        "saved": saved,
    }


def create_candidate_plan_from_brief_id(
    audio_root: str | Path,
    brief_id: str,
) -> dict[str, Any]:
    brief = load_saved_variation_brief(
        audio_root,
        brief_id,
    )
    return create_candidate_plan(
        audio_root,
        brief,
    )


def load_candidate_plan(
    path: str | Path,
) -> dict[str, Any]:
    try:
        data = json.loads(
            Path(path).read_text(
                encoding="utf-8"
            )
        )
    except json.JSONDecodeError as exc:
        raise CandidatePlanError(
            "Candidate Plan contains invalid JSON"
        ) from exc
    if not isinstance(
        data,
        dict,
    ):
        raise CandidatePlanError(
            "Candidate Plan must contain an object"
        )
    validate_candidate_plan(
        data
    )
    return data


def list_candidate_plans(
    audio_root: str | Path,
) -> list[dict[str, Any]]:
    root = candidate_plan_root(
        audio_root
    )
    if not root.is_dir():
        return []

    result: list[dict[str, Any]] = []
    for path in sorted(
        root.glob("*.json")
    ):
        try:
            plan = load_candidate_plan(
                path
            )
        except (
            OSError,
            CandidatePlanError,
        ) as exc:
            result.append(
                {
                    "ok": False,
                    "path": str(path),
                    "error": str(exc),
                }
            )
            continue

        experiment = plan[
            "experiment"
        ]
        result.append(
            {
                "ok": True,
                "plan_id": plan[
                    "plan_id"
                ],
                "variation_brief_id": plan[
                    "variation_brief_id"
                ],
                "hypothesis": experiment[
                    "hypothesis"
                ],
                "listening_for": experiment[
                    "listening_for"
                ],
                "ready_for_materialization": plan[
                    "ready_for_materialization"
                ],
                "unresolved_slots": plan[
                    "unresolved_slots"
                ],
                "variants": [
                    {
                        "slot": item[
                            "slot"
                        ],
                        "role": item[
                            "role"
                        ],
                        "resolution": item[
                            "resolution"
                        ],
                        "change": item[
                            "change"
                        ],
                    }
                    for item in plan[
                        "variants"
                    ]
                ],
                "path": str(path),
            }
        )
    return result
