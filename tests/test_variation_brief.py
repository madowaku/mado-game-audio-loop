import copy
import json
from pathlib import Path

import pytest

from mgal.cli import main
from mgal.variation_brief import (
    VariationBriefError,
    build_variation_brief,
    create_variation_brief,
    list_variation_briefs,
    validate_variation_brief,
)


def _inspector() -> dict:
    current = {
        "recipe_id": "current",
        "recipe_sha256": "a" * 64,
        "intent": "metallic slash",
        "layer_count": 2,
        "total_gain": 1.2,
        "earliest_offset_ms": 5,
        "latest_offset_ms": 30,
        "normalize": True,
        "fade_out_ms": 10,
        "source_ids": [
            "sha256:current-a",
            "sha256:shared",
        ],
    }
    winner = {
        "recipe_id": "past-b",
        "recipe_sha256": "b" * 64,
        "layer_count": 1,
        "total_gain": 0.8,
        "earliest_offset_ms": 25,
        "latest_offset_ms": 25,
        "normalize": True,
        "fade_out_ms": 20,
        "source_ids": [
            "sha256:shared",
        ],
    }
    loser = {
        "recipe_id": "past-a",
        "recipe_sha256": "c" * 64,
        "layer_count": 1,
        "total_gain": 0.5,
        "earliest_offset_ms": 0,
        "latest_offset_ms": 0,
        "normalize": True,
        "fade_out_ms": 20,
        "source_ids": [
            "sha256:loser",
        ],
    }
    return {
        "delta_inspector_version": "0.1",
        "delta_inspector_id": "",
        "context_pack_id": "context:fixture",
        "decision_memory_sha256": "d" * 64,
        "query": {
            "intent": "metallic slash",
            "normalized_intent": "metallic slash",
            "terms": [
                "metallic",
                "slash",
            ],
            "limit": 6,
        },
        "current_recipe_document": {
            "recipe_version": "0.1",
            "id": "current",
            "intent": "metallic slash",
            "layers": [
                {
                    "source": "current.wav",
                    "gain": 1.2,
                    "offset_ms": 5,
                }
            ],
            "processing": {
                "normalize": True,
                "fade_out_ms": 10,
            },
        },
        "current_recipe": current,
        "inspection_count": 1,
        "inspections": [
            {
                "entry_id": "decision:fixture",
                "archive_id": "archive-one",
                "source_intent": "crisp metallic slash",
                "pair_index": 0,
                "winner_candidate_id": "past-b",
                "loser_candidate_id": "past-a",
                "past_observed_differences": {
                    "layer_count_delta": 0,
                    "total_gain_delta": 0.3,
                    "earliest_offset_ms_delta": 25,
                    "latest_offset_ms_delta": 25,
                    "fade_out_ms_delta": 0,
                    "normalize_changed": False,
                    "shared_source_count": 0,
                    "winner_only_source_count": 1,
                    "loser_only_source_count": 1,
                },
                "current_vs_winner": {
                    "reference_role": "past_winner",
                    "reference_recipe": winner,
                    "delta": {
                        "direction": "current_minus_reference",
                        "layer_count_delta": 1,
                        "total_gain_delta": 0.4,
                        "earliest_offset_ms_delta": -20,
                        "latest_offset_ms_delta": 5,
                        "fade_out_ms_delta": -10,
                        "normalize_changed": False,
                        "shared_source_count": 1,
                        "current_only_source_count": 1,
                        "reference_only_source_count": 0,
                    },
                },
                "current_vs_loser": {
                    "reference_role": "past_loser",
                    "reference_recipe": loser,
                    "delta": {
                        "direction": "current_minus_reference",
                        "layer_count_delta": 1,
                        "total_gain_delta": 0.7,
                        "earliest_offset_ms_delta": 5,
                        "latest_offset_ms_delta": 30,
                        "fade_out_ms_delta": -10,
                        "normalize_changed": False,
                        "shared_source_count": 0,
                        "current_only_source_count": 2,
                        "reference_only_source_count": 1,
                    },
                },
            }
        ],
        "usage": {
            "role": "observation_only",
            "selection_effect": "none",
            "mutation_effect": "none",
        },
    }


def _valid_inspector() -> dict:
    from mgal.delta_inspector import (
        _sha256_json,
    )

    inspector = _inspector()
    inspector["current_recipe"][
        "recipe_sha256"
    ] = _sha256_json(
        inspector[
            "current_recipe_document"
        ]
    )
    payload = dict(inspector)
    payload.pop(
        "delta_inspector_id",
        None,
    )
    inspector[
        "delta_inspector_id"
    ] = (
        "delta:"
        + _sha256_json(payload)[:20]
    )
    return inspector


def _human_input() -> dict:
    return {
        "hypothesis": "Reducing gain may leave more room for the transient.",
        "listening_for": "A clearer attack without losing metallic weight.",
        "planned_change": {
            "dimension": "gain",
            "action": "decrease",
            "amount": 0.1,
            "unit": "ratio",
            "note": "Change gain only.",
        },
        "preserve": [
            "source set",
            "layer count",
        ],
        "reference": {
            "entry_id": "decision:fixture",
            "role": "past_winner",
        },
    }


def test_build_brief_records_explicit_human_hypothesis():
    brief = build_variation_brief(
        _valid_inspector(),
        _human_input(),
    )

    assert brief[
        "human_input"
    ]["authorship"] == "human_explicit"
    assert brief[
        "human_input"
    ]["planned_change"] == {
        "dimension": "gain",
        "action": "decrease",
        "amount": 0.1,
        "unit": "ratio",
        "note": "Change gain only.",
    }
    assert brief[
        "basis"
    ]["reference"]["role"] == "past_winner"
    assert brief[
        "authority"
    ] == {
        "recipe_mutation": "none",
        "candidate_selection": "none",
        "candidate_generation": "none",
    }
    assert validate_variation_brief(
        brief
    )["ok"] is True


def test_brief_can_be_general_without_reference():
    human = _human_input()
    human["reference"] = None

    brief = build_variation_brief(
        _valid_inspector(),
        human,
    )

    assert brief[
        "basis"
    ]["reference"] is None


def test_brief_rejects_reference_not_in_inspector():
    human = _human_input()
    human["reference"] = {
        "entry_id": "decision:missing",
        "role": "past_winner",
    }

    with pytest.raises(
        VariationBriefError,
        match="absent",
    ):
        build_variation_brief(
            _valid_inspector(),
            human,
        )


def test_brief_requires_explicit_hypothesis_and_listening_target():
    human = _human_input()
    human["hypothesis"] = " "

    with pytest.raises(
        VariationBriefError,
        match="hypothesis",
    ):
        build_variation_brief(
            _valid_inspector(),
            human,
        )

    human = _human_input()
    human["listening_for"] = ""

    with pytest.raises(
        VariationBriefError,
        match="listening_for",
    ):
        build_variation_brief(
            _valid_inspector(),
            human,
        )


def test_change_dimension_units_are_validated():
    human = _human_input()
    human["planned_change"] = {
        "dimension": "offset",
        "action": "increase",
        "amount": 15,
        "unit": "ratio",
        "note": None,
    }

    with pytest.raises(
        VariationBriefError,
        match="unit 'ms'",
    ):
        build_variation_brief(
            _valid_inspector(),
            human,
        )


def test_brief_is_content_addressed_and_idempotent(
    tmp_path: Path,
):
    first = create_variation_brief(
        tmp_path,
        _valid_inspector(),
        _human_input(),
    )
    second = create_variation_brief(
        tmp_path,
        _valid_inspector(),
        _human_input(),
    )

    assert first[
        "brief"
    ]["brief_id"] == second[
        "brief"
    ]["brief_id"]
    assert first[
        "saved"
    ]["reused"] is False
    assert second[
        "saved"
    ]["reused"] is True

    listing = list_variation_briefs(
        tmp_path
    )
    assert len(listing) == 1
    assert listing[0]["ok"] is True
    assert listing[0][
        "dimension"
    ] == "gain"


def test_brief_survives_later_current_recipe_changes(
    tmp_path: Path,
):
    result = create_variation_brief(
        tmp_path,
        _valid_inspector(),
        _human_input(),
    )
    brief = result["brief"]

    changed = copy.deepcopy(
        brief
    )
    changed[
        "basis"
    ]["current_recipe"][
        "total_gain"
    ] = 99

    assert validate_variation_brief(
        brief
    )["ok"] is True
    with pytest.raises(
        VariationBriefError,
        match="brief_id",
    ):
        validate_variation_brief(
            changed
        )


def test_brief_rejects_automatic_action_fields():
    brief = build_variation_brief(
        _valid_inspector(),
        _human_input(),
    )
    brief["generated_recipe"] = {
        "id": "auto"
    }

    with pytest.raises(
        VariationBriefError,
        match="automatic-action",
    ):
        validate_variation_brief(
            brief
        )


def test_variation_brief_cli_create_list_validate(
    tmp_path: Path,
    capsys,
):
    inspector_path = tmp_path / "inspector.json"
    inspector_path.write_text(
        json.dumps(
            _valid_inspector()
        ),
        encoding="utf-8",
    )
    input_path = tmp_path / "human-input.json"
    input_path.write_text(
        json.dumps(
            _human_input()
        ),
        encoding="utf-8",
    )
    output = tmp_path / "brief.json"

    assert main(
        [
            "variation-brief-create",
            str(inspector_path),
            str(input_path),
            "--audio-root",
            str(tmp_path),
            "--output",
            str(output),
        ]
    ) == 0
    created = json.loads(
        capsys.readouterr().out
    )
    assert created["brief"][
        "human_input"
    ]["authorship"] == "human_explicit"
    assert output.is_file()

    assert main(
        [
            "variation-brief-list",
            "--audio-root",
            str(tmp_path),
        ]
    ) == 0
    listing = json.loads(
        capsys.readouterr().out
    )
    assert len(listing) == 1
    assert listing[0]["hypothesis"].startswith(
        "Reducing gain"
    )

    assert main(
        [
            "variation-brief-validate",
            str(output),
        ]
    ) == 0
    validated = json.loads(
        capsys.readouterr().out
    )
    assert validated["ok"] is True


def test_variation_brief_contains_no_generated_recipe_or_candidate_action():
    brief = build_variation_brief(
        _valid_inspector(),
        _human_input(),
    )
    raw = json.dumps(brief)

    for token in (
        "generated_recipe",
        "recommended_candidate",
        "auto_select",
        "candidate_ranking",
        "preference_score",
        "similarity_score",
        "apply_winner",
    ):
        assert token not in raw
