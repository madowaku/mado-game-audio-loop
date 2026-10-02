from array import array
import json
from pathlib import Path
import wave

import pytest

from mgal.cli import main
from mgal.evidence import build_evidence_bundle, verify_evidence_bundle
from mgal.preference import (
    PreferenceEvidenceError,
    compile_preference_evidence,
    replay_preference_evidence,
    validate_preference_evidence,
)


def _write_wav(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = array("h", [value] * 80)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(44100)
        wav.writeframes(data.tobytes())


def _recipe(recipe_id: str, source: str) -> dict:
    return {
        "recipe_version": "0.1",
        "id": recipe_id,
        "intent": "blind impact preference",
        "layers": [
            {
                "source": source,
                "gain": 1.0,
                "offset_ms": 0,
            }
        ],
        "processing": {
            "normalize": True,
            "fade_out_ms": 0,
        },
    }


def _board(selected: str | None = None) -> dict:
    base_id = "base"
    candidates = []
    for label, source in (
        ("A", "a.wav"),
        ("B", "b.wav"),
        ("C", "c.wav"),
    ):
        candidate_id = "candidate-" + label.lower()
        candidates.append(
            {
                "id": candidate_id,
                "label": label,
                "parent_recipe_id": base_id,
                "revision": 1,
                "lineage": [
                    {
                        "from_recipe_id": base_id,
                        "action": "fork",
                        "revision": 1,
                    }
                ],
                "recipe": _recipe(candidate_id, source),
                "decision": {
                    "status": (
                        "selected"
                        if candidate_id == selected
                        else "undecided"
                    ),
                    "reason": "",
                },
            }
        )
    return {
        "candidate_board_version": "0.1",
        "intent": "blind impact preference",
        "base_recipe": _recipe(base_id, "a.wav"),
        "active_candidate_id": "candidate-a",
        "selected_candidate_id": selected,
        "candidates": candidates,
    }


def _preference_payload(
    board: dict,
    *,
    applied: str | None = None,
    tie: bool = False,
) -> dict:
    mapping = [
        {"alias": "X", "candidateId": "candidate-b"},
        {"alias": "Y", "candidateId": "candidate-a"},
        {"alias": "Z", "candidateId": "candidate-c"},
    ]
    pairs = [
        [mapping[1], mapping[0]],
        [mapping[2], mapping[1]],
        [mapping[0], mapping[2]],
    ]
    if tie:
        winners = [
            ("X", "candidate-b", "candidate-a"),
            ("Y", "candidate-a", "candidate-c"),
            ("Z", "candidate-c", "candidate-b"),
        ]
    else:
        winners = [
            ("X", "candidate-b", "candidate-a"),
            ("Y", "candidate-a", "candidate-c"),
            ("X", "candidate-b", "candidate-c"),
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
            "appliedCandidateId": applied,
        },
    }


def test_compile_and_replay_preference_evidence(tmp_path: Path):
    for name, value in (("a.wav", 100), ("b.wav", 200), ("c.wav", 300)):
        _write_wav(tmp_path / name, value)

    board = _board(selected="candidate-b")
    evidence = compile_preference_evidence(
        _preference_payload(
            board,
            applied="candidate-b",
        ),
        tmp_path,
    )

    report = validate_preference_evidence(evidence)
    assert report["ok"] is True
    assert report["pairs"] == 3
    assert report["winner_candidate_id"] == "candidate-b"
    assert report["applied_candidate_id"] == "candidate-b"
    assert evidence["mapping"][0] == {
        "alias": "X",
        "candidate_id": "candidate-b",
    }
    assert evidence["source_index"]["source_count"] == 3

    path = tmp_path / "preference-evidence.json"
    path.write_text(
        json.dumps(evidence),
        encoding="utf-8",
    )
    replay = replay_preference_evidence(path, tmp_path)

    assert replay["ok"] is True
    assert replay["sources_verified"] == 3
    assert [pair["pair_index"] for pair in replay["replay_pairs"]] == [0, 1, 2]
    assert replay["replay_pairs"][0]["winner_candidate_id"] == "candidate-b"


def test_preference_evidence_supports_tie_without_apply(tmp_path: Path):
    for name, value in (("a.wav", 100), ("b.wav", 200), ("c.wav", 300)):
        _write_wav(tmp_path / name, value)

    evidence = compile_preference_evidence(
        _preference_payload(
            _board(),
            tie=True,
        ),
        tmp_path,
    )

    assert evidence["tie"] is True
    assert evidence["winner_candidate_id"] is None
    assert evidence["applied_candidate_id"] is None


def test_preference_evidence_rejects_apply_that_does_not_match_board(
    tmp_path: Path,
):
    for name, value in (("a.wav", 100), ("b.wav", 200), ("c.wav", 300)):
        _write_wav(tmp_path / name, value)

    with pytest.raises(
        PreferenceEvidenceError,
        match="Board selection",
    ):
        compile_preference_evidence(
            _preference_payload(
                _board(),
                applied="candidate-b",
            ),
            tmp_path,
        )


def test_preference_evidence_rejects_duplicate_pair(tmp_path: Path):
    for name, value in (("a.wav", 100), ("b.wav", 200), ("c.wav", 300)):
        _write_wav(tmp_path / name, value)

    payload = _preference_payload(_board())
    payload["preference"]["pairs"][2] = payload["preference"]["pairs"][0]

    with pytest.raises(
        PreferenceEvidenceError,
        match="duplicate pair",
    ):
        compile_preference_evidence(payload, tmp_path)


def test_preference_replay_detects_changed_audio(tmp_path: Path):
    for name, value in (("a.wav", 100), ("b.wav", 200), ("c.wav", 300)):
        _write_wav(tmp_path / name, value)

    evidence = compile_preference_evidence(
        _preference_payload(_board()),
        tmp_path,
    )
    path = tmp_path / "preference-evidence.json"
    path.write_text(
        json.dumps(evidence),
        encoding="utf-8",
    )

    _write_wav(tmp_path / "b.wav", 999)

    with pytest.raises(
        PreferenceEvidenceError,
        match="hash changed",
    ):
        replay_preference_evidence(path, tmp_path)


def test_preference_cli_validate_and_replay(tmp_path: Path, capsys):
    for name, value in (("a.wav", 100), ("b.wav", 200), ("c.wav", 300)):
        _write_wav(tmp_path / name, value)

    evidence = compile_preference_evidence(
        _preference_payload(_board()),
        tmp_path,
    )
    evidence_path = tmp_path / "preference.json"
    evidence_path.write_text(
        json.dumps(evidence),
        encoding="utf-8",
    )

    assert main(["validate-preference", str(evidence_path)]) == 0
    validated = json.loads(capsys.readouterr().out)
    assert validated["ok"] is True
    assert validated["pairs"] == 3

    replay_path = tmp_path / "replay.json"
    assert main(
        [
            "replay-preference",
            str(evidence_path),
            "--audio-root",
            str(tmp_path),
            "--output",
            str(replay_path),
        ]
    ) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["ok"] is True
    assert replay["sources_verified"] == 3
    assert replay_path.is_file()


def test_preference_evidence_can_attach_to_main_evidence_bundle(
    tmp_path: Path,
):
    for name, value in (("a.wav", 100), ("b.wav", 200), ("c.wav", 300)):
        _write_wav(tmp_path / name, value)

    board = _board(selected="candidate-b")
    board_path = tmp_path / "board.json"
    board_path.write_text(
        json.dumps(board),
        encoding="utf-8",
    )

    preference = compile_preference_evidence(
        _preference_payload(
            board,
            applied="candidate-b",
        ),
        tmp_path,
    )
    preference_path = tmp_path / "preference.json"
    preference_path.write_text(
        json.dumps(preference),
        encoding="utf-8",
    )

    bundle = build_evidence_bundle(
        board_path,
        tmp_path,
        tmp_path / "bundle",
        preference_evidence_path=preference_path,
    )

    assert (bundle / "preference-session.json").is_file()
    verified = verify_evidence_bundle(bundle)
    assert verified["preference"]["pairs"] == 3
    assert (
        verified["preference"]["applied_candidate_id"]
        == "candidate-b"
    )
