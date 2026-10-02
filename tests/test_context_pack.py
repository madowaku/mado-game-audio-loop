from array import array
import json
from pathlib import Path
import wave

import pytest

from mgal.cli import main
from mgal.context_pack import (
    DecisionContextError,
    build_decision_context_pack,
    tokenize_intent,
    validate_decision_context_pack,
    verify_decision_context_pack_against_memory,
    write_decision_context_pack,
)
from mgal.decision_memory import (
    promote_preference_archive,
)
from mgal.preference import (
    archive_preference_evidence,
    compile_preference_evidence,
)


def _write_wav(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = array("h", [value] * 80)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(data.tobytes())


def _recipe(
    recipe_id: str,
    source: str,
    gain: float,
) -> dict:
    return {
        "recipe_version": "0.1",
        "id": recipe_id,
        "intent": "fixture",
        "layers": [
            {
                "source": source,
                "gain": gain,
                "offset_ms": 0,
            }
        ],
        "processing": {
            "normalize": True,
            "fade_out_ms": 20,
        },
    }


def _board(intent: str, prefix: str) -> dict:
    candidates = []
    for label, source, gain in (
        ("A", "a.wav", 0.5),
        ("B", "b.wav", 0.8),
        ("C", "c.wav", 0.65),
    ):
        candidate_id = f"{prefix}-{label.lower()}"
        candidates.append(
            {
                "id": candidate_id,
                "label": label,
                "parent_recipe_id": f"{prefix}-base",
                "revision": 1,
                "lineage": [
                    {
                        "from_recipe_id": f"{prefix}-base",
                        "action": "fork",
                        "revision": 1,
                    }
                ],
                "recipe": _recipe(
                    candidate_id,
                    source,
                    gain,
                ),
                "decision": {
                    "status": "undecided",
                    "reason": "",
                },
            }
        )
    return {
        "candidate_board_version": "0.1",
        "intent": intent,
        "base_recipe": _recipe(
            f"{prefix}-base",
            "a.wav",
            0.5,
        ),
        "active_candidate_id": f"{prefix}-a",
        "selected_candidate_id": None,
        "candidates": candidates,
    }


def _payload(board: dict, prefix: str) -> dict:
    mapping = [
        {"alias": "X", "candidateId": f"{prefix}-b"},
        {"alias": "Y", "candidateId": f"{prefix}-a"},
        {"alias": "Z", "candidateId": f"{prefix}-c"},
    ]
    pairs = [
        [mapping[1], mapping[0]],
        [mapping[2], mapping[1]],
        [mapping[0], mapping[2]],
    ]
    winners = [
        ("X", f"{prefix}-b", f"{prefix}-a"),
        ("Z", f"{prefix}-c", f"{prefix}-a"),
        ("X", f"{prefix}-b", f"{prefix}-c"),
    ]
    votes = []
    for pair, winner in zip(pairs, winners):
        votes.append(
            {
                "leftAlias": pair[0]["alias"],
                "rightAlias": pair[1]["alias"],
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


def _promote(
    audio_root: Path,
    *,
    intent: str,
    prefix: str,
) -> None:
    evidence = compile_preference_evidence(
        _payload(
            _board(intent, prefix),
            prefix,
        ),
        audio_root,
    )
    archive_preference_evidence(
        evidence,
        audio_root,
        archive_id=f"{prefix}-archive",
    )
    promote_preference_archive(
        audio_root,
        f"{prefix}-archive",
    )


def _memory_fixture(tmp_path: Path) -> Path:
    audio_root = tmp_path / "audio"
    for name, value in (
        ("a.wav", 100),
        ("b.wav", 200),
        ("c.wav", 300),
    ):
        _write_wav(audio_root / name, value)

    _promote(
        audio_root,
        intent="crisp metallic sword impact",
        prefix="metal",
    )
    _promote(
        audio_root,
        intent="soft wooden UI tap",
        prefix="wood",
    )
    return audio_root


def test_context_retrieval_returns_only_matching_observations(
    tmp_path: Path,
):
    audio_root = _memory_fixture(tmp_path)

    pack = build_decision_context_pack(
        audio_root,
        "metallic sword impact",
        limit=10,
    )

    assert pack["matched_entry_count"] == 3
    assert pack["returned_entry_count"] == 3
    assert pack["truncated"] is False
    assert {
        item["archive_id"]
        for item in pack["observations"]
    } == {"metal-archive"}
    assert all(
        "metallic" in item["match"]["matched_terms"]
        for item in pack["observations"]
    )
    assert pack["usage"] == {
        "role": "reference_only",
        "selection_effect": "none",
    }
    assert validate_decision_context_pack(pack)["ok"] is True


def test_context_retrieval_does_not_backfill_zero_match(
    tmp_path: Path,
):
    audio_root = _memory_fixture(tmp_path)

    pack = build_decision_context_pack(
        audio_root,
        "underwater bubble",
    )

    assert pack["matched_entry_count"] == 0
    assert pack["returned_entry_count"] == 0
    assert pack["observations"] == []


def test_context_retrieval_limit_is_deterministic(
    tmp_path: Path,
):
    audio_root = _memory_fixture(tmp_path)

    first = build_decision_context_pack(
        audio_root,
        "crisp metallic sword impact",
        limit=2,
    )
    second = build_decision_context_pack(
        audio_root,
        "crisp metallic sword impact",
        limit=2,
    )

    assert first == second
    assert first["matched_entry_count"] == 3
    assert first["returned_entry_count"] == 2
    assert first["truncated"] is True


def test_context_tokenizer_has_cjk_overlap():
    broad = set(
        tokenize_intent("重い金属の斬撃")
    )
    narrow = set(
        tokenize_intent("金属の斬撃")
    )

    assert broad & narrow
    assert "斬撃" in broad
    assert "斬撃" in narrow


def test_context_pack_can_be_written_and_verified(
    tmp_path: Path,
):
    audio_root = _memory_fixture(tmp_path)
    path = tmp_path / "context.json"

    write_decision_context_pack(
        audio_root,
        "metallic sword impact",
        path,
        limit=2,
    )
    report = verify_decision_context_pack_against_memory(
        path,
        audio_root,
    )

    assert report["ok"] is True
    assert report["fresh"] is True
    assert report["returned_entries"] == 2


def test_context_pack_becomes_stale_when_memory_changes(
    tmp_path: Path,
):
    audio_root = _memory_fixture(tmp_path)
    path = tmp_path / "context.json"
    write_decision_context_pack(
        audio_root,
        "metallic sword impact",
        path,
    )

    _promote(
        audio_root,
        intent="bright metallic sword impact",
        prefix="bright",
    )

    with pytest.raises(
        DecisionContextError,
        match="stale",
    ):
        verify_decision_context_pack_against_memory(
            path,
            audio_root,
        )


def test_context_pack_rejects_automatic_selection_fields(
    tmp_path: Path,
):
    audio_root = _memory_fixture(tmp_path)
    pack = build_decision_context_pack(
        audio_root,
        "metallic sword impact",
    )
    pack["recommended_candidate"] = "metal-b"

    with pytest.raises(
        DecisionContextError,
        match="automatic-selection",
    ):
        validate_decision_context_pack(pack)


def test_context_cli_builds_and_verifies_pack(
    tmp_path: Path,
    capsys,
):
    audio_root = _memory_fixture(tmp_path)
    output = tmp_path / "context-pack.json"

    assert main(
        [
            "decision-context",
            "metallic sword impact",
            "--audio-root",
            str(audio_root),
            "--limit",
            "2",
            "--output",
            str(output),
        ]
    ) == 0
    built = json.loads(capsys.readouterr().out)
    assert built["returned_entry_count"] == 2
    assert output.is_file()

    assert main(
        [
            "decision-context-verify",
            str(output),
            "--audio-root",
            str(audio_root),
        ]
    ) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["ok"] is True
    assert verified["fresh"] is True


def test_context_pack_contains_no_candidate_action_fields(
    tmp_path: Path,
):
    audio_root = _memory_fixture(tmp_path)
    pack = build_decision_context_pack(
        audio_root,
        "metallic sword impact",
    )
    raw = json.dumps(pack)

    for token in (
        "recommended_candidate",
        "auto_select",
        "preference_score",
        "candidate_ranking",
        "apply_winner",
    ):
        assert token not in raw
