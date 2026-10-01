from array import array
import json
from pathlib import Path
import wave

import pytest

from mgal.evidence import build_evidence_bundle
from mgal.recovery import (
    SourceRecoveryError,
    load_relink_map,
    recover_sources,
    write_relink_map,
)


def _write_wav(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = array("h", [value] * 80)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(data.tobytes())


def _recipe(recipe_id: str, source: str) -> dict:
    return {
        "recipe_version": "0.1",
        "id": recipe_id,
        "intent": "slash",
        "layers": [{"source": source, "gain": 1.0, "offset_ms": 0}],
        "processing": {"normalize": True, "fade_out_ms": 0},
    }


def _bundle(tmp_path: Path) -> tuple[Path, Path]:
    original = tmp_path / "original"
    _write_wav(original / "metal.wav", 400)
    _write_wav(original / "impact.wav", 900)

    base_id = "slash-base"
    selected_id = "slash-base-b"
    board = {
        "candidate_board_version": "0.1",
        "intent": "slash",
        "base_recipe": _recipe(base_id, "metal.wav"),
        "active_candidate_id": selected_id,
        "selected_candidate_id": selected_id,
        "candidates": [
            {
                "id": selected_id,
                "label": "B",
                "parent_recipe_id": base_id,
                "revision": 1,
                "lineage": [
                    {
                        "from_recipe_id": base_id,
                        "action": "fork",
                        "revision": 1,
                    }
                ],
                "recipe": _recipe(selected_id, "impact.wav"),
                "decision": {"status": "selected", "reason": "clear"},
            }
        ],
    }
    board_path = tmp_path / "board.json"
    board_path.write_text(json.dumps(board), encoding="utf-8")
    bundle = build_evidence_bundle(board_path, original, tmp_path / "bundle")
    return bundle, original


def test_recover_sources_after_move(tmp_path: Path):
    bundle, original = _bundle(tmp_path)
    reorganized = tmp_path / "reorganized"
    _write_wav(reorganized / "archive" / "metal_03.wav", 400)
    _write_wav(reorganized / "combat" / "impact_final.wav", 900)

    result = recover_sources(bundle, reorganized)

    assert result["complete"] is True
    assert result["resolved_count"] == 2
    assert result["missing_count"] == 0
    assert {item["status"] for item in result["mappings"]} == {"relinked"}
    assert {
        item["target"] for item in result["mappings"]
    } == {"archive/metal_03.wav", "combat/impact_final.wav"}


def test_recovery_marks_duplicate_hash_as_ambiguous(tmp_path: Path):
    bundle, original = _bundle(tmp_path)
    search = tmp_path / "search"
    _write_wav(search / "one" / "metal.wav", 400)
    _write_wav(search / "two" / "metal-copy.wav", 400)
    _write_wav(search / "impact.wav", 900)

    result = recover_sources(bundle, search)
    metal = next(item for item in result["mappings"] if item["source"] == "metal.wav")

    assert metal["status"] == "ambiguous"
    assert metal["target"] is None
    assert len(metal["matches"]) == 2
    assert result["complete"] is False


def test_load_relink_map_revalidates_target_hash(tmp_path: Path):
    bundle, original = _bundle(tmp_path)
    search = tmp_path / "search"
    _write_wav(search / "moved" / "metal.wav", 400)
    _write_wav(search / "moved" / "impact.wav", 900)

    map_path = write_relink_map(bundle, search, tmp_path / "relink-map.json")
    _write_wav(search / "moved" / "impact.wav", 901)

    with pytest.raises(SourceRecoveryError, match="hash changed"):
        load_relink_map(map_path, search)


def test_relink_map_is_bound_to_bundle_manifest(tmp_path: Path):
    bundle, original = _bundle(tmp_path)
    search = tmp_path / "search"
    _write_wav(search / "moved" / "metal.wav", 400)
    _write_wav(search / "moved" / "impact.wav", 900)

    map_path = write_relink_map(bundle, search, tmp_path / "relink-map.json")

    other_root = tmp_path / "other-original"
    _write_wav(other_root / "metal.wav", 400)
    _write_wav(other_root / "impact.wav", 901)

    base_id = "other-base"
    selected_id = "other-b"
    board = {
        "candidate_board_version": "0.1",
        "intent": "other",
        "base_recipe": _recipe(base_id, "metal.wav"),
        "active_candidate_id": selected_id,
        "selected_candidate_id": selected_id,
        "candidates": [
            {
                "id": selected_id,
                "label": "B",
                "parent_recipe_id": base_id,
                "revision": 1,
                "lineage": [
                    {
                        "from_recipe_id": base_id,
                        "action": "fork",
                        "revision": 1,
                    }
                ],
                "recipe": _recipe(selected_id, "impact.wav"),
                "decision": {"status": "selected", "reason": "other"},
            }
        ],
    }
    board_path = tmp_path / "other-board.json"
    board_path.write_text(json.dumps(board), encoding="utf-8")
    other_bundle = build_evidence_bundle(
        board_path,
        other_root,
        tmp_path / "other-bundle",
    )

    with pytest.raises(SourceRecoveryError, match="different Evidence Bundle"):
        load_relink_map(map_path, search, bundle_dir=other_bundle)
