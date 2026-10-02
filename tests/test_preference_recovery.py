from array import array
import json
from pathlib import Path
import shutil
import wave

import pytest

from mgal.cli import main
from mgal.preference import (
    archive_preference_evidence,
    compile_preference_evidence,
    load_preference_archive_metadata,
)
from mgal.preference_recovery import (
    PreferenceRecoveryError,
    list_portable_preference_archives,
    load_preference_relink_map,
    recover_preference_sources,
    replay_preference_archive_portable,
    write_preference_relink_map,
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
        "intent": "portable blind comparison",
        "layers": [
            {
                "source": source,
                "gain": 0.75,
                "offset_ms": 35,
            }
        ],
        "processing": {
            "normalize": True,
            "fade_out_ms": 0,
        },
    }


def _board(*, selected: str | None = None) -> dict:
    base_id = "portable-base"
    candidates = []
    for label, source in (
        ("A", "original/a.wav"),
        ("B", "original/b.wav"),
        ("C", "original/c.wav"),
    ):
        candidate_id = "portable-" + label.lower()
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
        "intent": "portable blind comparison",
        "base_recipe": _recipe(
            base_id,
            "original/a.wav",
        ),
        "active_candidate_id": "portable-a",
        "selected_candidate_id": selected,
        "candidates": candidates,
    }


def _payload(board: dict, *, tie: bool = False) -> dict:
    mapping = [
        {"alias": "X", "candidateId": "portable-b"},
        {"alias": "Y", "candidateId": "portable-a"},
        {"alias": "Z", "candidateId": "portable-c"},
    ]
    pairs = [
        [mapping[1], mapping[0]],
        [mapping[2], mapping[1]],
        [mapping[0], mapping[2]],
    ]
    winners = (
        [
            ("X", "portable-b", "portable-a"),
            ("Y", "portable-a", "portable-c"),
            ("Z", "portable-c", "portable-b"),
        ]
        if tie
        else [
            ("X", "portable-b", "portable-a"),
            ("Y", "portable-a", "portable-c"),
            ("X", "portable-b", "portable-c"),
        ]
    )
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


def _archive_fixture(
    tmp_path: Path,
    *,
    archive_id: str = "portable-session",
    tie: bool = False,
) -> tuple[Path, dict]:
    audio_root = tmp_path / "audio"
    for name, value in (
        ("a.wav", 100),
        ("b.wav", 200),
        ("c.wav", 300),
    ):
        _write_wav(
            audio_root / "original" / name,
            value,
        )

    evidence = compile_preference_evidence(
        _payload(_board(), tie=tie),
        audio_root,
    )
    archive_preference_evidence(
        evidence,
        audio_root,
        archive_id=archive_id,
    )
    return audio_root, evidence


def _move_sources(audio_root: Path) -> None:
    moved = audio_root / "reorganized"
    moved.mkdir(parents=True, exist_ok=True)
    for old, new in (
        ("a.wav", "alpha.wav"),
        ("b.wav", "beta.wav"),
        ("c.wav", "gamma.wav"),
    ):
        shutil.move(
            str(audio_root / "original" / old),
            str(moved / new),
        )


def test_preference_recovery_relinks_moved_sources_and_rewrites_replay_recipe(
    tmp_path: Path,
):
    audio_root, _ = _archive_fixture(tmp_path)
    _move_sources(audio_root)

    report = recover_preference_sources(
        audio_root,
        "portable-session",
        audio_root,
    )

    assert report["complete"] is True
    assert report["resolved_count"] == 3
    assert report["ambiguous_count"] == 0
    assert report["missing_count"] == 0
    assert all(
        item["status"] == "relinked"
        for item in report["mappings"]
    )

    map_path = write_preference_relink_map(
        audio_root,
        "portable-session",
        audio_root,
    )
    replay = replay_preference_archive_portable(
        audio_root,
        "portable-session",
    )

    assert map_path.is_file()
    assert replay["source_status"] == "relinked"
    assert all(
        item["relinked"]
        for item in replay["source_resolution"]
    )
    pair = replay["replay_pairs"][0]
    sources = {
        layer["source"]
        for layer in pair["left_recipe"]["layers"]
        + pair["right_recipe"]["layers"]
    }
    assert all(
        source.startswith("reorganized/")
        for source in sources
    )
    assert pair["left_recipe"]["layers"][0]["gain"] == 0.75
    assert pair["left_recipe"]["layers"][0]["offset_ms"] == 35


def test_preference_recovery_refuses_ambiguous_fingerprint_matches(
    tmp_path: Path,
):
    audio_root, _ = _archive_fixture(tmp_path)
    source = audio_root / "original" / "b.wav"
    payload = source.read_bytes()
    source.unlink()

    (audio_root / "duplicates").mkdir()
    (audio_root / "duplicates" / "b-one.wav").write_bytes(
        payload
    )
    (audio_root / "duplicates" / "b-two.wav").write_bytes(
        payload
    )

    report = recover_preference_sources(
        audio_root,
        "portable-session",
        audio_root,
    )

    mapping = next(
        item
        for item in report["mappings"]
        if item["source"] == "original/b.wav"
    )
    assert mapping["status"] == "ambiguous"
    assert len(mapping["matches"]) == 2
    assert report["complete"] is False
    assert report["ambiguous_count"] == 1


def test_preference_recovery_reports_missing_source(tmp_path: Path):
    audio_root, _ = _archive_fixture(tmp_path)
    (audio_root / "original" / "c.wav").unlink()

    report = recover_preference_sources(
        audio_root,
        "portable-session",
        audio_root,
    )

    mapping = next(
        item
        for item in report["mappings"]
        if item["source"] == "original/c.wav"
    )
    assert mapping["status"] == "missing"
    assert report["missing_count"] == 1
    assert report["complete"] is False


def test_preference_relink_map_is_bound_to_archive_identity(
    tmp_path: Path,
):
    audio_root, _ = _archive_fixture(
        tmp_path,
        archive_id="first",
    )
    evidence_two = compile_preference_evidence(
        _payload(_board(), tie=True),
        audio_root,
    )
    archive_preference_evidence(
        evidence_two,
        audio_root,
        archive_id="second",
    )

    _move_sources(audio_root)
    map_path = write_preference_relink_map(
        audio_root,
        "first",
        audio_root,
    )

    with pytest.raises(
        PreferenceRecoveryError,
        match="different archive",
    ):
        load_preference_relink_map(
            map_path,
            audio_root,
            audio_root,
            "second",
        )


def test_preference_relink_target_drift_is_rejected(tmp_path: Path):
    audio_root, _ = _archive_fixture(tmp_path)
    _move_sources(audio_root)
    map_path = write_preference_relink_map(
        audio_root,
        "portable-session",
        audio_root,
    )

    _write_wav(
        audio_root / "reorganized" / "beta.wav",
        999,
    )

    with pytest.raises(
        PreferenceRecoveryError,
        match="hash changed",
    ):
        load_preference_relink_map(
            map_path,
            audio_root,
            audio_root,
            "portable-session",
        )


def test_preference_archive_metadata_survives_missing_source_files(
    tmp_path: Path,
):
    audio_root, _ = _archive_fixture(tmp_path)
    _move_sources(audio_root)

    manifest, evidence = load_preference_archive_metadata(
        audio_root,
        "portable-session",
    )

    assert manifest["archive_id"] == "portable-session"
    assert evidence["preference_session_version"] == "0.1"


def test_preference_portable_replay_can_use_external_search_root(
    tmp_path: Path,
):
    audio_root, _ = _archive_fixture(tmp_path)
    external = tmp_path / "portable-library"
    external.mkdir()

    for old, new in (
        ("a.wav", "one.wav"),
        ("b.wav", "two.wav"),
        ("c.wav", "three.wav"),
    ):
        shutil.move(
            str(audio_root / "original" / old),
            str(external / new),
        )

    map_path = tmp_path / "portable-relink.json"
    write_preference_relink_map(
        audio_root,
        "portable-session",
        external,
        map_path,
    )
    replay = replay_preference_archive_portable(
        audio_root,
        "portable-session",
        search_root=external,
        relink_map_path=map_path,
    )

    assert replay["source_status"] == "relinked"
    resolved_targets = {
        item["target"]
        for item in replay["source_resolution"]
    }
    assert resolved_targets == {
        "one.wav",
        "two.wav",
        "three.wav",
    }


def test_portable_archive_list_moves_from_recoverable_to_relinked(
    tmp_path: Path,
):
    audio_root, _ = _archive_fixture(tmp_path)
    _move_sources(audio_root)

    before = list_portable_preference_archives(
        audio_root
    )
    assert before[0]["ok"] is False
    assert before[0]["recoverable"] is True
    assert before[0]["source_status"] == "unresolved"

    write_preference_relink_map(
        audio_root,
        "portable-session",
        audio_root,
    )

    after = list_portable_preference_archives(
        audio_root
    )
    assert after[0]["ok"] is True
    assert after[0]["source_status"] == "relinked"


def test_preference_recovery_cli_round_trip(tmp_path: Path, capsys):
    audio_root, _ = _archive_fixture(tmp_path)
    _move_sources(audio_root)

    assert main(
        [
            "preference-recover",
            "portable-session",
            "--audio-root",
            str(audio_root),
            "--search-root",
            str(audio_root),
        ]
    ) == 0
    relink_path = Path(
        capsys.readouterr().out.strip()
    )
    assert relink_path.is_file()

    assert main(
        [
            "preference-list",
            "--audio-root",
            str(audio_root),
        ]
    ) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing[0]["source_status"] == "relinked"

    output = tmp_path / "portable-replay.json"
    assert main(
        [
            "preference-replay-archive",
            "portable-session",
            "--audio-root",
            str(audio_root),
            "--output",
            str(output),
        ]
    ) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["source_status"] == "relinked"
    assert output.is_file()
