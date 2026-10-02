from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from .candidate_plan import (
    CandidatePlanError,
    load_candidate_plan,
    validate_candidate_plan,
)
from .delta_inspector import (
    DeltaInspectorError,
    summarize_current_recipe,
)
from .recipe import (
    RecipeError,
    parse_recipe,
)


MATERIALIZED_RECIPE_SET_VERSION = "0.1"
MATERIALIZATION_SEMANTICS = "whole-recipe-scalar-v1"

_SUPPORTED_DIMENSIONS = {
    "gain",
    "offset",
    "fade",
}

_SUPPORTED_ACTIONS = {
    "increase",
    "decrease",
}


class RecipeMaterializerError(ValueError):
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


def materialized_recipe_root(
    audio_root: str | Path,
) -> Path:
    return (
        Path(audio_root).resolve()
        / ".mgal"
        / "materialized-recipe-sets"
    )


def _validate_source_recipe(
    recipe: dict[str, Any],
) -> None:
    if not isinstance(recipe, dict):
        raise RecipeMaterializerError(
            "source Recipe must be an object"
        )
    try:
        parse_recipe(recipe)
    except RecipeError as exc:
        raise RecipeMaterializerError(
            f"source Recipe is invalid: {exc}"
        ) from exc


def _materializable_amount(
    change: dict[str, Any],
) -> float | int:
    amount = change.get("amount")
    dimension = change["dimension"]

    if amount is None:
        raise RecipeMaterializerError(
            f"{dimension} materialization requires an amount"
        )

    if dimension in {"offset", "fade"}:
        if isinstance(amount, bool):
            raise RecipeMaterializerError(
                f"{dimension} amount must be an integer"
            )
        numeric = float(amount)
        if not numeric.is_integer():
            raise RecipeMaterializerError(
                f"{dimension} amount must be an integer number of milliseconds"
            )
        return int(numeric)

    return float(amount)


def _validate_materializable_change(
    change: dict[str, Any],
) -> None:
    dimension = change.get("dimension")
    action = change.get("action")

    if dimension not in _SUPPORTED_DIMENSIONS:
        raise RecipeMaterializerError(
            f"materializer does not support dimension: {dimension}"
        )
    if action not in _SUPPORTED_ACTIONS:
        raise RecipeMaterializerError(
            f"materializer does not support {dimension} action: {action}"
        )
    _materializable_amount(change)


def _recipe_id(
    source_recipe: dict[str, Any],
    plan_id: str,
    slot: str,
) -> str:
    plan_slug = plan_id.split(":", 1)[-1][:10]
    return (
        f"{source_recipe['id']}-m25-"
        f"{slot.lower()}-{plan_slug}"
    )


def _apply_change(
    source_recipe: dict[str, Any],
    change: dict[str, Any],
    *,
    recipe_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _validate_materializable_change(
        change
    )
    amount = _materializable_amount(
        change
    )
    direction = (
        1
        if change["action"] == "increase"
        else -1
    )

    result = copy.deepcopy(
        source_recipe
    )
    result["id"] = recipe_id
    dimension = change["dimension"]

    if dimension == "gain":
        for layer in result["layers"]:
            layer["gain"] = round(
                float(
                    layer.get("gain", 1.0)
                )
                + direction * float(amount),
                6,
            )
        scope = "all_layers"

    elif dimension == "offset":
        delta = direction * int(amount)
        for layer in result["layers"]:
            current = int(
                layer.get("offset_ms", 0)
            )
            next_value = current + delta
            if next_value < 0:
                raise RecipeMaterializerError(
                    "offset materialization would create a negative offset"
                )
            layer["offset_ms"] = next_value
        scope = "all_layers"

    elif dimension == "fade":
        processing = result.setdefault(
            "processing",
            {},
        )
        current = int(
            processing.get(
                "fade_out_ms",
                0,
            )
        )
        next_value = (
            current
            + direction * int(amount)
        )
        if next_value < 0:
            raise RecipeMaterializerError(
                "fade materialization would create a negative fade_out_ms"
            )
        processing[
            "fade_out_ms"
        ] = next_value
        scope = "processing"

    else:
        raise RecipeMaterializerError(
            f"unsupported materialization dimension: {dimension}"
        )

    try:
        parse_recipe(result)
    except RecipeError as exc:
        raise RecipeMaterializerError(
            f"materialized Recipe is invalid: {exc}"
        ) from exc

    application = {
        "semantics": MATERIALIZATION_SEMANTICS,
        "scope": scope,
        "dimension": dimension,
        "action": change[
            "action"
        ],
        "amount": amount,
        "unit": change.get("unit"),
    }
    return result, application


def _materialize_variants(
    plan: dict[str, Any],
    source_recipe: dict[str, Any],
) -> list[dict[str, Any]]:
    variants: list[dict[str, Any]] = []

    for plan_variant in plan[
        "variants"
    ]:
        slot = plan_variant[
            "slot"
        ]
        role = plan_variant[
            "role"
        ]
        if (
            plan_variant[
                "resolution"
            ]
            != "resolved"
        ):
            raise RecipeMaterializerError(
                f"{slot}: Candidate Plan requires manual resolution"
            )

        recipe_id = _recipe_id(
            source_recipe,
            plan["plan_id"],
            slot,
        )

        if role == "control":
            recipe = copy.deepcopy(
                source_recipe
            )
            recipe["id"] = recipe_id
            application = None
            parse_recipe(recipe)
        else:
            change = plan_variant.get(
                "change"
            )
            if not isinstance(
                change,
                dict,
            ):
                raise RecipeMaterializerError(
                    f"{slot}: resolved variant must have a change"
                )
            recipe, application = _apply_change(
                source_recipe,
                change,
                recipe_id=recipe_id,
            )

        variants.append(
            {
                "slot": slot,
                "role": role,
                "plan_derivation": plan_variant[
                    "derivation"
                ],
                "application": application,
                "recipe_sha256": _sha256_json(
                    recipe
                ),
                "recipe": recipe,
            }
        )

    return variants


def build_materialized_recipe_set(
    audio_root: str | Path,
    plan: dict[str, Any],
    source_recipe: dict[str, Any],
) -> dict[str, Any]:
    try:
        report = validate_candidate_plan(
            plan
        )
    except CandidatePlanError as exc:
        raise RecipeMaterializerError(
            f"Candidate Plan is invalid: {exc}"
        ) from exc

    if not report[
        "ready_for_materialization"
    ]:
        raise RecipeMaterializerError(
            "Candidate Plan is not ready for materialization"
        )

    _validate_source_recipe(
        source_recipe
    )

    try:
        source_summary = summarize_current_recipe(
            source_recipe,
            audio_root,
        )
    except DeltaInspectorError as exc:
        raise RecipeMaterializerError(
            f"source Recipe cannot be fingerprinted: {exc}"
        ) from exc

    if source_summary != plan[
        "basis"
    ]["current_recipe"]:
        raise RecipeMaterializerError(
            "source Recipe does not match the Candidate Plan current Recipe snapshot"
        )

    variants = _materialize_variants(
        plan,
        source_recipe,
    )

    payload: dict[str, Any] = {
        "materialized_recipe_set_version": MATERIALIZED_RECIPE_SET_VERSION,
        "materialization_semantics": MATERIALIZATION_SEMANTICS,
        "candidate_plan": copy.deepcopy(
            plan
        ),
        "source_recipe": copy.deepcopy(
            source_recipe
        ),
        "source_recipe_summary": source_summary,
        "experiment": copy.deepcopy(
            plan["experiment"]
        ),
        "variants": variants,
        "authority": {
            "candidate_board_mutation": "none",
            "candidate_selection": "none",
            "source_generation": "none",
        },
    }
    payload[
        "materialization_id"
    ] = (
        "materialized:"
        + _sha256_json(payload)[:20]
    )
    return payload


def validate_materialized_recipe_set(
    data: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(
        data,
        dict,
    ):
        raise RecipeMaterializerError(
            "Materialized Recipe Set must be an object"
        )
    if (
        data.get(
            "materialized_recipe_set_version"
        )
        != MATERIALIZED_RECIPE_SET_VERSION
    ):
        raise RecipeMaterializerError(
            "unsupported materialized_recipe_set_version"
        )
    if (
        data.get(
            "materialization_semantics"
        )
        != MATERIALIZATION_SEMANTICS
    ):
        raise RecipeMaterializerError(
            "unsupported materialization semantics"
        )

    plan = data.get(
        "candidate_plan"
    )
    if not isinstance(plan, dict):
        raise RecipeMaterializerError(
            "Materialized Recipe Set candidate_plan must be an object"
        )
    try:
        plan_report = validate_candidate_plan(
            plan
        )
    except CandidatePlanError as exc:
        raise RecipeMaterializerError(
            f"embedded Candidate Plan is invalid: {exc}"
        ) from exc
    if not plan_report[
        "ready_for_materialization"
    ]:
        raise RecipeMaterializerError(
            "embedded Candidate Plan is not ready"
        )

    source_recipe = data.get(
        "source_recipe"
    )
    _validate_source_recipe(
        source_recipe
    )

    source_summary = data.get(
        "source_recipe_summary"
    )
    if not isinstance(
        source_summary,
        dict,
    ):
        raise RecipeMaterializerError(
            "source_recipe_summary must be an object"
        )
    if (
        source_summary.get(
            "recipe_sha256"
        )
        != _sha256_json(
            source_recipe
        )
    ):
        raise RecipeMaterializerError(
            "source Recipe fingerprint does not match source_recipe_summary"
        )
    if (
        source_summary
        != plan["basis"][
            "current_recipe"
        ]
    ):
        raise RecipeMaterializerError(
            "source Recipe summary does not match Candidate Plan basis"
        )

    if data.get(
        "experiment"
    ) != plan[
        "experiment"
    ]:
        raise RecipeMaterializerError(
            "Materialized Recipe Set experiment does not match Candidate Plan"
        )

    expected_variants = _materialize_variants(
        plan,
        source_recipe,
    )
    if data.get(
        "variants"
    ) != expected_variants:
        raise RecipeMaterializerError(
            "materialized variants do not recompute from Candidate Plan and source Recipe"
        )

    if data.get("authority") != {
        "candidate_board_mutation": "none",
        "candidate_selection": "none",
        "source_generation": "none",
    }:
        raise RecipeMaterializerError(
            "Materialized Recipe Set authority boundary is invalid"
        )

    forbidden = {
        "selected_candidate_id",
        "candidate_decision",
        "preference_score",
        "recommended_candidate",
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
                collect_keys(
                    child
                )
        elif isinstance(
            value,
            list,
        ):
            for child in value:
                collect_keys(
                    child
                )

    collect_keys(data)
    if forbidden & keys:
        raise RecipeMaterializerError(
            "Materialized Recipe Set contains a Candidate selection field"
        )

    materialization_id = data.get(
        "materialization_id"
    )
    if not isinstance(
        materialization_id,
        str,
    ):
        raise RecipeMaterializerError(
            "materialization_id must be a string"
        )
    payload = dict(data)
    payload.pop(
        "materialization_id",
        None,
    )
    expected_id = (
        "materialized:"
        + _sha256_json(payload)[:20]
    )
    if materialization_id != expected_id:
        raise RecipeMaterializerError(
            "materialization_id does not match payload"
        )

    return {
        "ok": True,
        "materialization_id": materialization_id,
        "candidate_plan_id": plan[
            "plan_id"
        ],
        "variant_count": 3,
    }


def verify_materialized_recipe_set(
    data: dict[str, Any],
    audio_root: str | Path,
) -> dict[str, Any]:
    report = validate_materialized_recipe_set(
        data
    )
    try:
        current_summary = summarize_current_recipe(
            data["source_recipe"],
            audio_root,
        )
    except DeltaInspectorError as exc:
        raise RecipeMaterializerError(
            f"source Recipe cannot be verified: {exc}"
        ) from exc
    if current_summary != data[
        "source_recipe_summary"
    ]:
        raise RecipeMaterializerError(
            "source Recipe files no longer match the materialization snapshot"
        )
    if current_summary != data[
        "candidate_plan"
    ]["basis"][
        "current_recipe"
    ]:
        raise RecipeMaterializerError(
            "source Recipe no longer matches Candidate Plan basis"
        )
    return {
        **report,
        "fresh": True,
    }


def _write_recipe_set_directory(
    directory: Path,
    recipe_set: dict[str, Any],
) -> None:
    directory.mkdir(
        parents=True,
        exist_ok=True,
    )
    (
        directory
        / "set.json"
    ).write_text(
        json.dumps(
            recipe_set,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    for variant in recipe_set[
        "variants"
    ]:
        filename = (
            f"{variant['slot']}-"
            f"{variant['role']}.json"
        )
        (
            directory
            / filename
        ).write_text(
            json.dumps(
                variant["recipe"],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )


def save_materialized_recipe_set(
    audio_root: str | Path,
    recipe_set: dict[str, Any],
) -> dict[str, Any]:
    validate_materialized_recipe_set(
        recipe_set
    )
    root = materialized_recipe_root(
        audio_root
    )
    slug = recipe_set[
        "materialization_id"
    ].split(":", 1)[1]
    directory = root / slug

    reused = False
    if directory.exists():
        set_path = (
            directory
            / "set.json"
        )
        if not set_path.is_file():
            raise RecipeMaterializerError(
                "materialization directory exists without set.json"
            )
        existing = load_materialized_recipe_set(
            directory
        )
        if existing != recipe_set:
            raise RecipeMaterializerError(
                "Materialized Recipe Set ID collision with different content"
            )
        reused = True
    else:
        temporary = root / (
            f".{slug}.tmp"
        )
        if temporary.exists():
            raise RecipeMaterializerError(
                "temporary materialization directory already exists"
            )
        root.mkdir(
            parents=True,
            exist_ok=True,
        )
        _write_recipe_set_directory(
            temporary,
            recipe_set,
        )
        temporary.replace(
            directory
        )

    return {
        "ok": True,
        "materialization_id": recipe_set[
            "materialization_id"
        ],
        "path": str(directory),
        "reused": reused,
    }


def materialize_candidate_plan(
    audio_root: str | Path,
    plan: dict[str, Any],
    source_recipe: dict[str, Any],
) -> dict[str, Any]:
    recipe_set = build_materialized_recipe_set(
        audio_root,
        plan,
        source_recipe,
    )
    saved = save_materialized_recipe_set(
        audio_root,
        recipe_set,
    )
    return {
        "recipe_set": recipe_set,
        "saved": saved,
    }


def _verify_split_recipe_files(
    directory: Path,
    recipe_set: dict[str, Any],
) -> None:
    for variant in recipe_set[
        "variants"
    ]:
        filename = (
            f"{variant['slot']}-"
            f"{variant['role']}.json"
        )
        path = directory / filename
        if not path.is_file():
            raise RecipeMaterializerError(
                f"materialized Recipe file is missing: {filename}"
            )
        try:
            recipe = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except json.JSONDecodeError as exc:
            raise RecipeMaterializerError(
                f"materialized Recipe file contains invalid JSON: {filename}"
            ) from exc
        if recipe != variant[
            "recipe"
        ]:
            raise RecipeMaterializerError(
                f"materialized Recipe file does not match set.json: {filename}"
            )


def load_materialized_recipe_set(
    path: str | Path,
) -> dict[str, Any]:
    path = Path(path)
    directory = (
        path
        if path.is_dir()
        else None
    )
    if directory is not None:
        path = directory / "set.json"
    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except json.JSONDecodeError as exc:
        raise RecipeMaterializerError(
            "Materialized Recipe Set contains invalid JSON"
        ) from exc
    if not isinstance(
        data,
        dict,
    ):
        raise RecipeMaterializerError(
            "Materialized Recipe Set must contain an object"
        )
    validate_materialized_recipe_set(
        data
    )
    if directory is not None:
        _verify_split_recipe_files(
            directory,
            data,
        )
    return data


def list_materialized_recipe_sets(
    audio_root: str | Path,
) -> list[dict[str, Any]]:
    root = materialized_recipe_root(
        audio_root
    )
    if not root.is_dir():
        return []

    result: list[dict[str, Any]] = []
    for directory in sorted(
        path
        for path in root.iterdir()
        if path.is_dir()
        and not path.name.startswith(".")
    ):
        try:
            recipe_set = load_materialized_recipe_set(
                directory
            )
        except (
            OSError,
            RecipeMaterializerError,
        ) as exc:
            result.append(
                {
                    "ok": False,
                    "path": str(
                        directory
                    ),
                    "error": str(exc),
                }
            )
            continue

        result.append(
            {
                "ok": True,
                "materialization_id": recipe_set[
                    "materialization_id"
                ],
                "candidate_plan_id": recipe_set[
                    "candidate_plan"
                ]["plan_id"],
                "variation_brief_id": recipe_set[
                    "candidate_plan"
                ]["variation_brief_id"],
                "hypothesis": recipe_set[
                    "experiment"
                ]["hypothesis"],
                "listening_for": recipe_set[
                    "experiment"
                ]["listening_for"],
                "source_recipe_id": recipe_set[
                    "source_recipe"
                ]["id"],
                "variants": [
                    {
                        "slot": item[
                            "slot"
                        ],
                        "role": item[
                            "role"
                        ],
                        "recipe_id": item[
                            "recipe"
                        ]["id"],
                        "application": item[
                            "application"
                        ],
                    }
                    for item in recipe_set[
                        "variants"
                    ]
                ],
                "path": str(
                    directory
                ),
            }
        )
    return result


def load_saved_candidate_plan(
    audio_root: str | Path,
    plan_id: str,
) -> dict[str, Any]:
    if (
        not isinstance(
            plan_id,
            str,
        )
        or not plan_id.startswith(
            "plan:"
        )
    ):
        raise RecipeMaterializerError(
            "plan_id must be a Candidate Plan ID"
        )
    slug = plan_id.split(
        ":",
        1,
    )[1]
    path = (
        Path(audio_root).resolve()
        / ".mgal"
        / "candidate-plans"
        / f"{slug}.json"
    )
    if not path.is_file():
        raise RecipeMaterializerError(
            f"Candidate Plan does not exist: {plan_id}"
        )
    try:
        plan = load_candidate_plan(
            path
        )
    except CandidatePlanError as exc:
        raise RecipeMaterializerError(
            f"Candidate Plan is invalid: {exc}"
        ) from exc
    if plan.get(
        "plan_id"
    ) != plan_id:
        raise RecipeMaterializerError(
            "Candidate Plan ID does not match stored content"
        )
    return plan


def materialize_saved_candidate_plan(
    audio_root: str | Path,
    plan_id: str,
    source_recipe: dict[str, Any],
) -> dict[str, Any]:
    plan = load_saved_candidate_plan(
        audio_root,
        plan_id,
    )
    return materialize_candidate_plan(
        audio_root,
        plan,
        source_recipe,
    )
