from array import array
import hashlib
import json
from pathlib import Path
import wave

import pytest

from mgal.evidence import build_evidence_bundle
from mgal.replay import EvidenceReplayError, replay_evidence_bundle


def _write_wav(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def _board() -> dict:
    base_id = "slash-base"
    selected_id = "slash-base-b"
    return {
        "candidate_board_version": "0.1",
        "intent": "heavy slash",
        "base_recipe": _recipe(base_id, "metal.wav", 0.5),
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
                "recipe": _recipe(selected_id, "impact.wav", 0.8),
                "decision": {"status": "selected", "reason": "clear hit"},
            }
        ],
    }


def _bundle(tmp_path: Path) -> tuple[Path, Path]:
    audio_root = tmp_path / "audio"
    _write_wav(audio_root / "metal.wav", 400)
    _write_wav(audio_root / "impact.wav", 900)

    board_path = tmp_path / "board.json"
    board_path.write_text(json.dumps(_board()), encoding="utf-8")
    bundle = build_evidence_bundle(board_path, audio_root, tmp_path / "bundle")
    return bundle, audio_root


def test_replay_is_byte_identical(tmp_path: Path):
    bundle, audio_root = _bundle(tmp_path)
    replay_copy = tmp_path / "replay.wav"

    result = replay_evidence_bundle(
        bundle,
        audio_root,
        output_path=replay_copy,
    )

    assert result["ok"] is True
    assert result["byte_identical"] is True
    assert result["sources_verified"] == 2
    assert result["stored_output_sha256"] == result["replayed_output_sha256"]
    assert replay_copy.read_bytes() == (bundle / "output.wav").read_bytes()


def test_replay_rejects_changed_source(tmp_path: Path):
    bundle, audio_root = _bundle(tmp_path)
    _write_wav(audio_root / "impact.wav", 901)

    with pytest.raises(EvidenceReplayError, match="source hash changed"):
        replay_evidence_bundle(bundle, audio_root)


def test_replay_rejects_missing_source(tmp_path: Path):
    bundle, audio_root = _bundle(tmp_path)
    (audio_root / "impact.wav").unlink()

    with pytest.raises(EvidenceReplayError, match="source is missing"):
        replay_evidence_bundle(bundle, audio_root)


def test_replay_output_must_stay_outside_bundle(tmp_path: Path):
    bundle, audio_root = _bundle(tmp_path)

    with pytest.raises(EvidenceReplayError, match="outside"):
        replay_evidence_bundle(
            bundle,
            audio_root,
            output_path=bundle / "replayed.wav",
        )


def _rehash_manifest_entry(bundle: Path, relative_path: str) -> None:
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    target = bundle / relative_path
    digest = hashlib.sha256(target.read_bytes()).hexdigest()

    for item in manifest["files"]:
        if item["path"] == relative_path:
            item["sha256"] = digest
            item["bytes"] = target.stat().st_size
            break
    else:
        raise AssertionError(f"missing manifest entry: {relative_path}")

    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def test_replay_detects_semantic_decision_drift_after_rehash(tmp_path: Path):
    bundle, audio_root = _bundle(tmp_path)

    decision_path = bundle / "decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["reason"] = "rewritten reason"
    decision_path.write_text(
        json.dumps(decision, indent=2) + "\n",
        encoding="utf-8",
    )
    _rehash_manifest_entry(bundle, "decision.json")

    with pytest.raises(EvidenceReplayError, match="reason does not match"):
        replay_evidence_bundle(bundle, audio_root)
