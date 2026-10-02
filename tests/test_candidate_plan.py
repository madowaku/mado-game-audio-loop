import json
from pathlib import Path

import pytest

from mgal.candidate_plan import (
    CandidatePlanError,
    compile_candidate_plan,
    create_candidate_plan,
    list_candidate_plans,
    validate_candidate_plan,
)
from mgal.variation_brief import (
    _sha256_json,
)


def _brief(
    *,
    action: str = "decrease",
    dimension: str = "gain",
    amount: float | int | None = 0.1,
    unit: str | None = "ratio",
) -> dict:
    payload = {
        "variation_brief_version": "0.1",
        "basis": {
            "delta_inspector_id": "delta:fixture",
            "context_pack_id": "context:fixture",
            "decision_memory_sha256": "a" * 64,
            "query": {
                "intent": "metallic slash",
                "normalized_intent": "metallic slash",
                "terms": [
                    "metallic",
                    "slash",
                ],
                "limit": 6,
            },
            "current_recipe": {
                "recipe_id": "current",
                "recipe_sha256": "b" * 64,
                "intent": "metallic slash",
                "layer_count": 2,
                "total_gain": 1.2,
                "earliest_offset_ms": 5,
                "latest_offset_ms": 30,
                "normalize": True,
                "fade_out_ms": 10,
                "source_ids": [
                    "sha256:x",
                    "sha256:y",
                ],
            },
            "reference": None,
        },
        "human_input": {
            "authorship": "human_explicit",
            "hypothesis": "A smaller gain may expose the attack.",
            "listening_for": "Sharper attack without losing body.",
            "planned_change": {
                "dimension": dimension,
                "action": action,
                "amount": amount,
                "unit": unit,
                "note": "One variable at a time.",
            },
            "preserve": [
                "source set",
                "layer count",
            ],
        },
        "authority": {
            "recipe_mutation": "none",
            "candidate_selection": "none",
            "candidate_generation": "none",
        },
    }
    payload["brief_id"] = (
        "brief:"
        + _sha256_json(
            payload
        )[:20]
    )
    return payload


def test_plan_compiles_control_hypothesis_and_contrast():
    plan = compile_candidate_plan(
        _brief()
    )

    assert [
        (
            item["slot"],
            item["role"],
        )
        for item in plan[
            "variants"
        ]
    ] == [
        ("A", "control"),
        ("B", "hypothesis"),
        ("C", "contrast"),
    ]

    control, hypothesis, contrast = plan[
        "variants"
    ]
    assert control[
        "change"
    ] is None
    assert hypothesis[
        "change"
    ]["action"] == "decrease"
    assert contrast[
        "change"
    ]["action"] == "increase"
    assert contrast[
        "change"
    ]["amount"] == 0.1
    assert plan[
        "ready_for_materialization"
    ] is True
    assert plan[
        "unresolved_slots"
    ] == []
    assert validate_candidate_plan(
        plan
    )["ok"] is True


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        (
            "increase",
            "decrease",
        ),
        (
            "decrease",
            "increase",
        ),
        (
            "add",
            "remove",
        ),
        (
            "remove",
            "add",
        ),
    ],
)
def test_contrast_only_inverts_safe_actions(
    action: str,
    expected: str,
):
    dimension = (
        "layers"
        if action in {
            "add",
            "remove",
        }
        else "gain"
    )
    amount = (
        1
        if dimension == "layers"
        else 0.1
    )
    unit = (
        "count"
        if dimension == "layers"
        else "ratio"
    )
    plan = compile_candidate_plan(
        _brief(
            action=action,
            dimension=dimension,
            amount=amount,
            unit=unit,
        )
    )

    assert plan[
        "variants"
    ][2]["change"][
        "action"
    ] == expected
    assert plan[
        "variants"
    ][2][
        "resolution"
    ] == "resolved"


@pytest.mark.parametrize(
    "action",
    [
        "hold",
        "replace",
        "toggle",
        "custom",
    ],
)
def test_noninvertible_contrast_stops_for_human(
    action: str,
):
    dimension = (
        "normalize"
        if action == "toggle"
        else "other"
    )
    plan = compile_candidate_plan(
        _brief(
            action=action,
            dimension=dimension,
            amount=None,
            unit=None,
        )
    )

    contrast = plan[
        "variants"
    ][2]
    assert contrast[
        "resolution"
    ] == "manual_required"
    assert contrast[
        "change"
    ] is None
    assert plan[
        "unresolved_slots"
    ] == ["C"]
    assert plan[
        "ready_for_materialization"
    ] is False


def test_plan_preserves_human_hypothesis_and_preserve_constraints():
    brief = _brief()
    plan = compile_candidate_plan(
        brief
    )

    assert plan[
        "experiment"
    ] == {
        "hypothesis": brief[
            "human_input"
        ]["hypothesis"],
        "listening_for": brief[
            "human_input"
        ]["listening_for"],
        "preserve": [
            "source set",
            "layer count",
        ],
    }
    assert plan[
        "variants"
    ][1]["hypothesis"] == brief[
        "human_input"
    ]["hypothesis"]


def test_candidate_plan_contains_no_recipe_materialization():
    plan = compile_candidate_plan(
        _brief()
    )
    raw = json.dumps(
        plan
    )

    for token in (
        "generated_recipe",
        "materialized_recipe",
        "selected_candidate_id",
        "recommended_candidate",
        "candidate_ranking",
        "preference_score",
        "auto_select",
        "apply_winner",
    ):
        assert token not in raw

    assert plan[
        "authority"
    ] == {
        "recipe_materialization": "none",
        "candidate_generation": "none",
        "candidate_selection": "none",
    }


def test_candidate_plan_is_content_addressed_and_idempotent(
    tmp_path: Path,
):
    first = create_candidate_plan(
        tmp_path,
        _brief(),
    )
    second = create_candidate_plan(
        tmp_path,
        _brief(),
    )

    assert first[
        "plan"
    ]["plan_id"] == second[
        "plan"
    ]["plan_id"]
    assert first[
        "saved"
    ]["reused"] is False
    assert second[
        "saved"
    ]["reused"] is True

    listing = list_candidate_plans(
        tmp_path
    )
    assert len(listing) == 1
    assert listing[0][
        "ready_for_materialization"
    ] is True


def test_candidate_plan_detects_tampered_readiness():
    plan = compile_candidate_plan(
        _brief(
            action="custom",
            dimension="other",
            amount=None,
            unit=None,
        )
    )
    plan[
        "ready_for_materialization"
    ] = True

    with pytest.raises(
        CandidatePlanError,
        match="readiness",
    ):
        validate_candidate_plan(
            plan
        )
