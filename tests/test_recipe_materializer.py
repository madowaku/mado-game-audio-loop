from array import array
import json
from pathlib import Path
import wave

import pytest

from mgal.cli import main
from mgal.candidate_plan import (
    compile_candidate_plan,
)
from mgal.recipe_materializer import (
    RecipeMaterializerError,
    build_materialized_recipe_set,
    list_materialized_recipe_sets,
    materialize_candidate_plan,
    validate_materialized_recipe_set,
    verify_materialized_recipe_set,
)
from mgal.variation_brief import (
    _sha256_json,
)


def _write_wav(
    path: Path,
    value: int,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    data = array(
        "h",
        [value] * 80,
    )
    with wave.open(
        str(path),
        "wb",
    ) as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(
            data.tobytes()
        )


def _recipe() -> dict:
    return {
        "recipe_version": "0.1",
        "id": "current",
        "intent": "metallic slash",
        "layers": [
            {
                "source": "a.wav",
                "gain": 0.8,
                "offset_ms": 20,
            },
            {
                "source": "b.wav",
                "gain": 0.4,
                "offset_ms": 40,
            },
        ],
        "processing": {
            "normalize": True,
            "fade_out_ms": 50,
        },
    }


def _summary(
    audio_root: Path,
    recipe: dict,
) -> dict:
    from mgal.delta_inspector import (
        summarize_current_recipe,
    )

    return summarize_current_recipe(
        recipe,
        audio_root,
    )


def _brief(
    audio_root: Path,
    *,
    dimension: str = "gain",
    action: str = "decrease",
    amount: float | int | None = 0.1,
    unit: str | None = "ratio",
) -> dict:
    recipe = _recipe()
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
            "current_recipe": _summary(
                audio_root,
                recipe,
            ),
            "reference": None,
        },
        "human_input": {
            "authorship": "human_explicit",
            "hypothesis": "Change one scalar and listen.",
            "listening_for": "A cleaner transient.",
            "planned_change": {
                "dimension": dimension,
                "action": action,
                "amount": amount,
                "unit": unit,
                "note": "Scalar test.",
            },
            "preserve": [
                "source set",
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
        + _sha256_json(payload)[:20]
    )
    return payload


def _workspace(
    tmp_path: Path,
) -> Path:
    audio_root = tmp_path / "audio"
    _write_wav(
        audio_root / "a.wav",
        100,
    )
    _write_wav(
        audio_root / "b.wav",
        200,
    )
    return audio_root


def _plan(
    audio_root: Path,
    **kwargs,
) -> dict:
    return compile_candidate_plan(
        _brief(
            audio_root,
            **kwargs,
        )
    )


def test_gain_materialization_produces_control_hypothesis_contrast(
    tmp_path: Path,
):
    audio_root = _workspace(
        tmp_path
    )
    recipe_set = build_materialized_recipe_set(
        audio_root,
        _plan(audio_root),
        _recipe(),
    )

    a, b, c = recipe_set[
        "variants"
    ]
    assert [
        item["role"]
        for item in recipe_set[
            "variants"
        ]
    ] == [
        "control",
        "hypothesis",
        "contrast",
    ]
    assert [
        layer["gain"]
        for layer in a[
            "recipe"
        ]["layers"]
    ] == [
        0.8,
        0.4,
    ]
    assert [
        layer["gain"]
        for layer in b[
            "recipe"
        ]["layers"]
    ] == [
        0.7,
        0.3,
    ]
    assert [
        layer["gain"]
        for layer in c[
            "recipe"
        ]["layers"]
    ] == [
        0.9,
        0.5,
    ]
    assert a[
        "application"
    ] is None
    assert b[
        "application"
    ]["scope"] == "all_layers"
    assert validate_materialized_recipe_set(
        recipe_set
    )["ok"] is True


def test_offset_materialization_is_whole_recipe_and_exact(
    tmp_path: Path,
):
    audio_root = _workspace(
        tmp_path
    )
    recipe_set = build_materialized_recipe_set(
        audio_root,
        _plan(
            audio_root,
            dimension="offset",
            action="increase",
            amount=15,
            unit="ms",
        ),
        _recipe(),
    )

    b = recipe_set[
        "variants"
    ][1]["recipe"]
    c = recipe_set[
        "variants"
    ][2]["recipe"]
    assert [
        layer["offset_ms"]
        for layer in b["layers"]
    ] == [
        35,
        55,
    ]
    assert [
        layer["offset_ms"]
        for layer in c["layers"]
    ] == [
        5,
        25,
    ]


def test_fade_materialization_changes_processing_only(
    tmp_path: Path,
):
    audio_root = _workspace(
        tmp_path
    )
    recipe_set = build_materialized_recipe_set(
        audio_root,
        _plan(
            audio_root,
            dimension="fade",
            action="decrease",
            amount=10,
            unit="ms",
        ),
        _recipe(),
    )
    a, b, c = [
        item["recipe"]
        for item in recipe_set[
            "variants"
        ]
    ]

    assert a[
        "processing"
    ]["fade_out_ms"] == 50
    assert b[
        "processing"
    ]["fade_out_ms"] == 40
    assert c[
        "processing"
    ]["fade_out_ms"] == 60
    assert b["layers"] == a["layers"]
    assert c["layers"] == a["layers"]


def test_materializer_rejects_recipe_not_matching_plan_snapshot(
    tmp_path: Path,
):
    audio_root = _workspace(
        tmp_path
    )
    changed = _recipe()
    changed["layers"][0][
        "gain"
    ] = 0.9

    with pytest.raises(
        RecipeMaterializerError,
        match="does not match",
    ):
        build_materialized_recipe_set(
            audio_root,
            _plan(audio_root),
            changed,
        )


def test_materializer_rejects_unresolved_plan(
    tmp_path: Path,
):
    audio_root = _workspace(
        tmp_path
    )
    plan = _plan(
        audio_root,
        dimension="other",
        action="custom",
        amount=None,
        unit=None,
    )
    with pytest.raises(
        RecipeMaterializerError,
        match="not ready",
    ):
        build_materialized_recipe_set(
            audio_root,
            plan,
            _recipe(),
        )


def test_materializer_rejects_ready_but_unsupported_dimension(
    tmp_path: Path,
):
    audio_root = _workspace(
        tmp_path
    )
    plan = _plan(
        audio_root,
        dimension="layers",
        action="add",
        amount=1,
        unit="count",
    )

    with pytest.raises(
        RecipeMaterializerError,
        match="does not support dimension",
    ):
        build_materialized_recipe_set(
            audio_root,
            plan,
            _recipe(),
        )


def test_offset_decrease_rejects_negative_result(
    tmp_path: Path,
):
    audio_root = _workspace(
        tmp_path
    )
    plan = _plan(
        audio_root,
        dimension="offset",
        action="decrease",
        amount=30,
        unit="ms",
    )

    with pytest.raises(
        RecipeMaterializerError,
        match="negative offset",
    ):
        build_materialized_recipe_set(
            audio_root,
            plan,
            _recipe(),
        )


def test_materialized_set_is_content_addressed_and_idempotent(
    tmp_path: Path,
):
    audio_root = _workspace(
        tmp_path
    )
    plan = _plan(
        audio_root
    )
    first = materialize_candidate_plan(
        audio_root,
        plan,
        _recipe(),
    )
    second = materialize_candidate_plan(
        audio_root,
        plan,
        _recipe(),
    )

    assert first[
        "recipe_set"
    ][
        "materialization_id"
    ] == second[
        "recipe_set"
    ][
        "materialization_id"
    ]
    assert first[
        "saved"
    ]["reused"] is False
    assert second[
        "saved"
    ]["reused"] is True

    directory = Path(
        first["saved"]["path"]
    )
    assert (
        directory
        / "set.json"
    ).is_file()
    assert (
        directory
        / "A-control.json"
    ).is_file()
    assert (
        directory
        / "B-hypothesis.json"
    ).is_file()
    assert (
        directory
        / "C-contrast.json"
    ).is_file()


def test_materialized_set_detects_recipe_tamper_even_with_new_id(
    tmp_path: Path,
):
    audio_root = _workspace(
        tmp_path
    )
    recipe_set = build_materialized_recipe_set(
        audio_root,
        _plan(audio_root),
        _recipe(),
    )
    recipe_set[
        "variants"
    ][1]["recipe"][
        "layers"
    ][0]["gain"] = 9

    payload = dict(
        recipe_set
    )
    payload.pop(
        "materialization_id",
        None,
    )
    recipe_set[
        "materialization_id"
    ] = (
        "materialized:"
        + _sha256_json(
            payload
        )[:20]
    )

    with pytest.raises(
        RecipeMaterializerError,
        match="do not recompute",
    ):
        validate_materialized_recipe_set(
            recipe_set
        )


def test_materialized_set_verification_detects_source_drift(
    tmp_path: Path,
):
    audio_root = _workspace(
        tmp_path
    )
    recipe_set = build_materialized_recipe_set(
        audio_root,
        _plan(audio_root),
        _recipe(),
    )

    assert verify_materialized_recipe_set(
        recipe_set,
        audio_root,
    )["fresh"] is True

    _write_wav(
        audio_root / "a.wav",
        999,
    )

    with pytest.raises(
        RecipeMaterializerError,
        match="no longer match",
    ):
        verify_materialized_recipe_set(
            recipe_set,
            audio_root,
        )


def test_materializer_cli_build_list_verify(
    tmp_path: Path,
    capsys,
):
    audio_root = _workspace(
        tmp_path
    )
    plan = _plan(
        audio_root
    )
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(
        json.dumps(_recipe()),
        encoding="utf-8",
    )
    output = tmp_path / "set-copy.json"

    assert main(
        [
            "candidate-plan-materialize",
            str(plan_path),
            str(recipe_path),
            "--audio-root",
            str(audio_root),
            "--output",
            str(output),
        ]
    ) == 0
    built = json.loads(
        capsys.readouterr().out
    )
    assert built[
        "recipe_set"
    ]["materialized_recipe_set_version"] == "0.1"
    assert output.is_file()

    assert main(
        [
            "materialized-recipe-list",
            "--audio-root",
            str(audio_root),
        ]
    ) == 0
    listing = json.loads(
        capsys.readouterr().out
    )
    assert len(listing) == 1
    assert [
        item["role"]
        for item in listing[0][
            "variants"
        ]
    ] == [
        "control",
        "hypothesis",
        "contrast",
    ]

    assert main(
        [
            "materialized-recipe-verify",
            str(output),
            "--audio-root",
            str(audio_root),
        ]
    ) == 0
    verified = json.loads(
        capsys.readouterr().out
    )
    assert verified["fresh"] is True


def test_materialized_list_contains_no_candidate_selection(
    tmp_path: Path,
):
    audio_root = _workspace(
        tmp_path
    )
    materialize_candidate_plan(
        audio_root,
        _plan(audio_root),
        _recipe(),
    )
    listing = list_materialized_recipe_sets(
        audio_root
    )
    raw = json.dumps(listing)

    for token in (
        "selected_candidate_id",
        "candidate_decision",
        "recommended_candidate",
        "auto_select",
        "apply_winner",
    ):
        assert token not in raw
