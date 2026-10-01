from array import array
import json
from pathlib import Path
import wave

import pytest

from mgal.evidence import (
    EvidenceBundleError,
    build_evidence_bundle,
    verify_evidence_bundle,
)


def _write_wav(path: Path, value: int) -> None:
    data = array("h", [value] * 80)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(data.tobytes())


def _recipe(recipe_id: str, source: str, gain: float) -> dict:
    return {
        "recipe_version": "0.1",
        "id": recipe_id,
        "intent": "heavy slash",
        "layers": [{"source": source, "gain": gain, "offset_ms": 0}],
        "processing": {"normalize": True, "fade_out_ms": 0},
    }


def _board(selected: bool = True) -> dict:
    base_id = "slash-base"
    a_id = "slash-base-a"
    b_id = "slash-base-b"
    return {
        "candidate_board_version": "0.1",
        "intent": "heavy slash",
        "base_recipe": _recipe(base_id, "metal.wav", 0.5),
        "active_candidate_id": b_id,
        "selected_candidate_id": b_id if selected else None,
        "candidates": [
            {
                "id": a_id,
                "label": "A",
                "parent_recipe_id": base_id,
                "revision": 1,
                "lineage": [
                    {
                        "from_recipe_id": base_id,
                        "action": "fork",
                        "revision": 1,
                    }
                ],
                "recipe": _recipe(a_id, "metal.wav", 0.5),
                "decision": {"status": "favorite", "reason": "good body"},
            },
            {
                "id": b_id,
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
                "recipe": _recipe(b_id, "impact.wav", 0.8),
                "decision": {
                    "status": "selected" if selected else "undecided",
                    "reason": "clear hit" if selected else "",
                },
            },
        ],
    }


def test_build_and_verify_evidence_bundle(tmp_path: Path):
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    _write_wav(audio_root / "metal.wav", 400)
    _write_wav(audio_root / "impact.wav", 900)

    board_path = tmp_path / "board.json"
    board_path.write_text(json.dumps(_board()), encoding="utf-8")

    bundle = build_evidence_bundle(
        board_path,
        audio_root,
        tmp_path / "evidence" / "session-001",
    )

    expected = {
        "intent.json",
        "source-index.json",
        "candidate-board.json",
        "selected-recipe.json",
        "decision.json",
        "output.wav",
        "manifest.json",
    }
    assert expected.issubset({path.name for path in bundle.iterdir()})
    assert len(list((bundle / "candidates").glob("*.json"))) == 2

    source_index = json.loads((bundle / "source-index.json").read_text(encoding="utf-8"))
    assert source_index["source_count"] == 2
    assert all(len(item["sha256"]) == 64 for item in source_index["sources"])

    result = verify_evidence_bundle(bundle)
    assert result["ok"] is True
    assert result["files_verified"] >= 8
    assert result["selected_candidate_id"] == "slash-base-b"


def test_verify_detects_tampering(tmp_path: Path):
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    _write_wav(audio_root / "metal.wav", 400)
    _write_wav(audio_root / "impact.wav", 900)
    board_path = tmp_path / "board.json"
    board_path.write_text(json.dumps(_board()), encoding="utf-8")

    bundle = build_evidence_bundle(board_path, audio_root, tmp_path / "bundle")
    (bundle / "decision.json").write_text("changed\n", encoding="utf-8")

    with pytest.raises(EvidenceBundleError):
        verify_evidence_bundle(bundle)


def test_bundle_requires_selected_candidate(tmp_path: Path):
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    _write_wav(audio_root / "metal.wav", 400)
    _write_wav(audio_root / "impact.wav", 900)
    board_path = tmp_path / "board.json"
    board_path.write_text(json.dumps(_board(selected=False)), encoding="utf-8")

    with pytest.raises(EvidenceBundleError):
        build_evidence_bundle(board_path, audio_root, tmp_path / "bundle")
