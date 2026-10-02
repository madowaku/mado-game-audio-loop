from array import array
import json
from pathlib import Path
import wave

import pytest

from mgal.cli import main
from mgal.decision_memory import (
    DecisionMemoryError,
    decision_memory_path,
    decision_memory_view,
    promote_preference_archive,
    verify_decision_memory_against_archives,
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
    *,
    gain: float,
    offset_ms: int,
) -> dict:
    return {
        "recipe_version": "0.1",
        "id": recipe_id,
        "intent": "crisp sword impact",
        "layers": [
            {
                "source": source,
                "gain": gain,
                "offset_ms": offset_ms,
            }
        ],
        "processing": {
            "normalize": True,
            "fade_out_ms": 40,
        },
    }


def _board() -> dict:
    base_id = "memory-base"
    rows = [
        ("A", "a.wav", 0.6, 0),
        ("B", "b.wav", 0.9, 25),
        ("C", "c.wav", 0.7, 10),
    ]
    candidates = []
    for label, source, gain, offset in rows:
        candidate_id = "memory-" + label.lower()
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
                "recipe": _recipe(
                    candidate_id,
                    source,
                    gain=gain,
                    offset_ms=offset,
                ),
                "decision": {
                    "status": "undecided",
                    "reason": "",
                },
            }
        )
    return {
        "candidate_board_version": "0.1",
        "intent": "crisp sword impact",
        "base_recipe": _recipe(
            base_id,
            "a.wav",
            gain=0.6,
            offset_ms=0,
        ),
        "active_candidate_id": "memory-a",
        "selected_candidate_id": None,
        "candidates": candidates,
    }


def _preference(board: dict) -> dict:
    mapping = [
        {"alias": "X", "candidateId": "memory-b"},
        {"alias": "Y", "candidateId": "memory-a"},
        {"alias": "Z", "candidateId": "memory-c"},
    ]
    pairs = [
        [mapping[1], mapping[0]],
        [mapping[2], mapping[1]],
        [mapping[0], mapping[2]],
    ]
    winners = [
        ("X", "memory-b", "memory-a"),
        ("Z", "memory-c", "memory-a"),
        ("X", "memory-b", "memory-c"),
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


def _archive(tmp_path: Path, archive_id: str = "memory-session") -> Path:
    audio_root = tmp_path / "audio"
    for name, value in (("a.wav", 100), ("b.wav", 200), ("c.wav", 300)):
        _write_wav(audio_root / name, value)

    evidence = compile_preference_evidence(
        _preference(_board()),
        audio_root,
    )
    archive_preference_evidence(
        evidence,
        audio_root,
        archive_id=archive_id,
    )
    return audio_root


def test_promote_archive_builds_pairwise_decision_memory(tmp_path: Path):
    audio_root = _archive(tmp_path)

    result = promote_preference_archive(
        audio_root,
        "memory-session",
    )

    assert result["ok"] is True
    assert result["reused"] is False
    assert decision_memory_path(audio_root).is_file()

    view = decision_memory_view(audio_root)
    assert view["summary"]["promotion_count"] == 1
    assert view["summary"]["entry_count"] == 3
    assert len(view["entries"]) == 3

    first = view["entries"][0]
    assert first["winner_candidate_id"] == "memory-b"
    assert first["loser_candidate_id"] == "memory-a"
    assert first["winner_recipe"]["total_gain"] == 0.9
    assert first["loser_recipe"]["total_gain"] == 0.6
    assert first["observed_differences"]["total_gain_delta"] == 0.3
    assert first["winner_recipe"]["source_ids"][0].startswith("sha256:")


def test_promotion_is_idempotent_by_evidence_hash(tmp_path: Path):
    audio_root = _archive(tmp_path)

    first = promote_preference_archive(
        audio_root,
        "memory-session",
    )
    second = promote_preference_archive(
        audio_root,
        "memory-session",
    )

    assert first["reused"] is False
    assert second["reused"] is True
    view = decision_memory_view(audio_root)
    assert view["summary"]["promotion_count"] == 1
    assert view["summary"]["entry_count"] == 3


def test_memory_promotion_does_not_require_current_source_paths(tmp_path: Path):
    audio_root = _archive(tmp_path)
    for name in ("a.wav", "b.wav", "c.wav"):
        (audio_root / name).unlink()

    result = promote_preference_archive(
        audio_root,
        "memory-session",
    )

    assert result["ok"] is True
    assert result["memory"]["entry_count"] == 3


def test_decision_memory_verifies_against_archives(tmp_path: Path):
    audio_root = _archive(tmp_path)
    promote_preference_archive(
        audio_root,
        "memory-session",
    )

    report = verify_decision_memory_against_archives(
        audio_root
    )

    assert report == {
        "ok": True,
        "promotions_verified": 1,
        "entries_verified": 3,
    }


def test_decision_memory_detects_derived_difference_tamper(tmp_path: Path):
    audio_root = _archive(tmp_path)
    promote_preference_archive(
        audio_root,
        "memory-session",
    )

    path = decision_memory_path(audio_root)
    data = json.loads(
        path.read_text(encoding="utf-8")
    )
    data["entries"][0][
        "observed_differences"
    ]["total_gain_delta"] = 99
    path.write_text(
        json.dumps(data),
        encoding="utf-8",
    )

    with pytest.raises(
        DecisionMemoryError,
        match="observed differences",
    ):
        decision_memory_view(audio_root)


def test_decision_memory_cli_promote_view_and_verify(
    tmp_path: Path,
    capsys,
):
    audio_root = _archive(tmp_path)

    assert main(
        [
            "decision-promote",
            "memory-session",
            "--audio-root",
            str(audio_root),
        ]
    ) == 0
    promoted = json.loads(capsys.readouterr().out)
    assert promoted["ok"] is True
    assert promoted["memory"]["entry_count"] == 3

    assert main(
        [
            "decision-memory",
            "--audio-root",
            str(audio_root),
        ]
    ) == 0
    view = json.loads(capsys.readouterr().out)
    assert view["summary"]["promotion_count"] == 1
    assert view["summary"]["entry_count"] == 3

    assert main(
        [
            "decision-memory-verify",
            "--audio-root",
            str(audio_root),
        ]
    ) == 0
    verified = json.loads(capsys.readouterr().out)
    assert verified["promotions_verified"] == 1
    assert verified["entries_verified"] == 3


def test_decision_memory_records_observations_not_automatic_rules(
    tmp_path: Path,
):
    audio_root = _archive(tmp_path)
    promote_preference_archive(
        audio_root,
        "memory-session",
    )

    view = decision_memory_view(audio_root)
    raw = json.dumps(view)

    assert "recommended_candidate" not in raw
    assert "auto_select" not in raw
    assert "preference_score" not in raw
    assert "winner_candidate_id" in raw
    assert "loser_candidate_id" in raw
    assert "observed_differences" in raw
