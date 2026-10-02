from array import array
import json
from pathlib import Path
import wave

import pytest

from mgal.context_pack import (
    build_decision_context_pack,
)
from mgal.decision_memory import (
    promote_preference_archive,
)
from mgal.delta_inspector import (
    DeltaInspectorError,
    build_delta_inspector_pack,
    recipe_delta,
    summarize_current_recipe,
    validate_delta_inspector_pack,
)
from mgal.preference import (
    archive_preference_evidence,
    compile_preference_evidence,
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


def _recipe(
    recipe_id: str,
    source: str,
    gain: float,
    offset: int,
) -> dict:
    return {
        "recipe_version": "0.1",
        "id": recipe_id,
        "intent": "metallic slash",
        "layers": [
            {
                "source": source,
                "gain": gain,
                "offset_ms": offset,
            }
        ],
        "processing": {
            "normalize": True,
            "fade_out_ms": 20,
        },
    }


def _board() -> dict:
    rows = [
        (
            "A",
            "a.wav",
            0.5,
            0,
        ),
        (
            "B",
            "b.wav",
            0.8,
            25,
        ),
        (
            "C",
            "c.wav",
            0.65,
            10,
        ),
    ]
    candidates = []
    for (
        label,
        source,
        gain,
        offset,
    ) in rows:
        candidate_id = (
            "metal-" + label.lower()
        )
        candidates.append(
            {
                "id": candidate_id,
                "label": label,
                "parent_recipe_id": "metal-base",
                "revision": 1,
                "lineage": [
                    {
                        "from_recipe_id": "metal-base",
                        "action": "fork",
                        "revision": 1,
                    }
                ],
                "recipe": _recipe(
                    candidate_id,
                    source,
                    gain,
                    offset,
                ),
                "decision": {
                    "status": "undecided",
                    "reason": "",
                },
            }
        )

    return {
        "candidate_board_version": "0.1",
        "intent": "crisp metallic slash",
        "base_recipe": _recipe(
            "metal-base",
            "a.wav",
            0.5,
            0,
        ),
        "active_candidate_id": "metal-a",
        "selected_candidate_id": None,
        "candidates": candidates,
    }


def _payload(
    board: dict,
) -> dict:
    mapping = [
        {
            "alias": "X",
            "candidateId": "metal-b",
        },
        {
            "alias": "Y",
            "candidateId": "metal-a",
        },
        {
            "alias": "Z",
            "candidateId": "metal-c",
        },
    ]
    pairs = [
        [
            mapping[1],
            mapping[0],
        ],
        [
            mapping[2],
            mapping[1],
        ],
        [
            mapping[0],
            mapping[2],
        ],
    ]
    winners = [
        (
            "X",
            "metal-b",
            "metal-a",
        ),
        (
            "Z",
            "metal-c",
            "metal-a",
        ),
        (
            "X",
            "metal-b",
            "metal-c",
        ),
    ]
    votes = []
    for pair, winner in zip(
        pairs,
        winners,
    ):
        votes.append(
            {
                "leftAlias": pair[0][
                    "alias"
                ],
                "rightAlias": pair[1][
                    "alias"
                ],
                "winnerAlias": winner[0],
                "winnerCandidateId": winner[1],
                "loserCandidateId": winner[2],
            }
        )

    return {
        "candidate_board": board,
        "preference": {
            "mapping": mapping,
            "pairs": pairs,
            "votes": votes,
            "revealed": True,
            "appliedCandidateId": None,
        },
    }


def _fixture(
    tmp_path: Path,
) -> tuple[
    Path,
    dict,
]:
    audio_root = tmp_path / "audio"
    for name, value in (
        ("a.wav", 100),
        ("b.wav", 200),
        ("c.wav", 300),
        ("d.wav", 400),
    ):
        _write_wav(
            audio_root / name,
            value,
        )

    evidence = compile_preference_evidence(
        _payload(_board()),
        audio_root,
    )
    archive_preference_evidence(
        evidence,
        audio_root,
        archive_id="metal-archive",
    )
    promote_preference_archive(
        audio_root,
        "metal-archive",
    )
    context = build_decision_context_pack(
        audio_root,
        "metallic slash",
    )
    return (
        audio_root,
        context,
    )


def test_current_recipe_summary_uses_content_source_ids(
    tmp_path: Path,
):
    audio_root, _ = _fixture(
        tmp_path
    )
    current = {
        "recipe_version": "0.1",
        "id": "current",
        "intent": "metallic slash",
        "layers": [
            {
                "source": "b.wav",
                "gain": 0.9,
                "offset_ms": 30,
            },
            {
                "source": "d.wav",
                "gain": 0.4,
                "offset_ms": 5,
            },
        ],
        "processing": {
            "normalize": True,
            "fade_out_ms": 10,
        },
    }

    summary = summarize_current_recipe(
        current,
        audio_root,
    )

    assert summary["layer_count"] == 2
    assert summary["total_gain"] == 1.3
    assert summary[
        "earliest_offset_ms"
    ] == 5
    assert summary[
        "latest_offset_ms"
    ] == 30
    assert len(
        summary["source_ids"]
    ) == 2
    assert all(
        item.startswith("sha256:")
        for item in summary[
            "source_ids"
        ]
    )


def test_recipe_delta_is_current_minus_reference():
    current = {
        "recipe_sha256": "a" * 64,
        "layer_count": 2,
        "total_gain": 1.2,
        "earliest_offset_ms": 10,
        "latest_offset_ms": 30,
        "normalize": True,
        "fade_out_ms": 10,
        "source_ids": [
            "sha256:a",
            "sha256:b",
        ],
    }
    reference = {
        "recipe_sha256": "b" * 64,
        "layer_count": 1,
        "total_gain": 0.8,
        "earliest_offset_ms": 20,
        "latest_offset_ms": 20,
        "normalize": False,
        "fade_out_ms": 30,
        "source_ids": [
            "sha256:b",
            "sha256:c",
        ],
    }

    delta = recipe_delta(
        current,
        reference,
    )

    assert delta == {
        "direction": "current_minus_reference",
        "layer_count_delta": 1,
        "total_gain_delta": 0.4,
        "earliest_offset_ms_delta": -10,
        "latest_offset_ms_delta": 10,
        "fade_out_ms_delta": -20,
        "normalize_changed": True,
        "shared_source_count": 1,
        "current_only_source_count": 1,
        "reference_only_source_count": 1,
    }


def test_inspector_compares_current_to_winner_and_loser(
    tmp_path: Path,
):
    audio_root, context = _fixture(
        tmp_path
    )
    current = _recipe(
        "current",
        "b.wav",
        0.9,
        30,
    )

    inspector = build_delta_inspector_pack(
        audio_root,
        context,
        current,
    )

    assert inspector[
        "inspection_count"
    ] == 3
    first = inspector[
        "inspections"
    ][0]
    assert first[
        "current_vs_winner"
    ]["reference_role"] == "past_winner"
    assert first[
        "current_vs_loser"
    ]["reference_role"] == "past_loser"
    assert (
        first["current_vs_winner"][
            "delta"
        ]["direction"]
        == "current_minus_reference"
    )
    assert validate_delta_inspector_pack(
        inspector
    )["ok"] is True


def test_inspector_preserves_context_order(
    tmp_path: Path,
):
    audio_root, context = _fixture(
        tmp_path
    )
    current = _recipe(
        "current",
        "d.wav",
        0.7,
        15,
    )

    inspector = build_delta_inspector_pack(
        audio_root,
        context,
        current,
    )

    assert [
        item["entry_id"]
        for item in inspector[
            "inspections"
        ]
    ] == [
        item["entry_id"]
        for item in context[
            "observations"
        ]
    ]


def test_inspector_rejects_stale_context(
    tmp_path: Path,
):
    audio_root, context = _fixture(
        tmp_path
    )

    memory_path = (
        audio_root
        / ".mgal"
        / "decision-memory.json"
    )
    memory = json.loads(
        memory_path.read_text(
            encoding="utf-8"
        )
    )
    memory["promotion_count"] = 99
    memory_path.write_text(
        json.dumps(memory),
        encoding="utf-8",
    )

    with pytest.raises(
        DeltaInspectorError,
    ):
        build_delta_inspector_pack(
            audio_root,
            context,
            _recipe(
                "current",
                "d.wav",
                0.7,
                15,
            ),
        )


def test_inspector_rejects_missing_current_source(
    tmp_path: Path,
):
    audio_root, context = _fixture(
        tmp_path
    )

    with pytest.raises(
        DeltaInspectorError,
        match="missing",
    ):
        build_delta_inspector_pack(
            audio_root,
            context,
            _recipe(
                "current",
                "missing.wav",
                0.7,
                15,
            ),
        )


def test_inspector_rejects_evaluation_fields(
    tmp_path: Path,
):
    audio_root, context = _fixture(
        tmp_path
    )
    inspector = build_delta_inspector_pack(
        audio_root,
        context,
        _recipe(
            "current",
            "d.wav",
            0.7,
            15,
        ),
    )
    inspector["similarity_score"] = 0.91

    with pytest.raises(
        DeltaInspectorError,
        match="automatic-evaluation",
    ):
        validate_delta_inspector_pack(
            inspector
        )
