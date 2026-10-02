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
from mgal.provenance import (
    update_provenance_entry,
    write_provenance_ledger,
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


def test_verify_rejects_untracked_bundle_payload(tmp_path: Path):
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    _write_wav(audio_root / "metal.wav", 400)
    _write_wav(audio_root / "impact.wav", 900)
    board_path = tmp_path / "board.json"
    board_path.write_text(json.dumps(_board()), encoding="utf-8")

    bundle = build_evidence_bundle(board_path, audio_root, tmp_path / "bundle")
    (bundle / "extra.txt").write_text("not in manifest\n", encoding="utf-8")

    with pytest.raises(EvidenceBundleError, match="payload set"):
        verify_evidence_bundle(bundle)


def _complete_provenance(audio_root: Path, output: Path) -> Path:
    ledger = write_provenance_ledger(audio_root, output)
    update_provenance_entry(
        ledger,
        "metal.wav",
        source_type="free_library",
        creator="Fixture Author",
        title="Metal Fixture",
        origin_url="https://example.invalid/metal",
        license_status="declared",
        license_expression="CC0-1.0",
        license_url="https://example.invalid/license",
        attribution="Fixture Author",
    )
    update_provenance_entry(
        ledger,
        "impact.wav",
        source_type="recorded",
        license_status="owned",
        recorded_by="MGAL fixture",
        recorded_at="2026-10-02",
        device="procedural test writer",
    )
    return ledger


def test_bundle_can_embed_complete_provenance_ledger(tmp_path: Path):
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    _write_wav(audio_root / "metal.wav", 400)
    _write_wav(audio_root / "impact.wav", 900)
    board_path = tmp_path / "board.json"
    board_path.write_text(json.dumps(_board()), encoding="utf-8")
    ledger = _complete_provenance(audio_root, tmp_path / "provenance.json")

    bundle = build_evidence_bundle(
        board_path,
        audio_root,
        tmp_path / "bundle",
        provenance_ledger_path=ledger,
        require_provenance=True,
    )

    provenance = json.loads(
        (bundle / "provenance-ledger.json").read_text(encoding="utf-8")
    )
    source_index = json.loads(
        (bundle / "source-index.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (bundle / "manifest.json").read_text(encoding="utf-8")
    )

    assert provenance["complete"] is True
    assert provenance["entry_count"] == 2
    assert all("source_id" in source for source in source_index["sources"])
    assert manifest["provenance_required"] is True

    result = verify_evidence_bundle(bundle)
    assert result["provenance"]["complete"] is True
    assert result["provenance"]["entries"] == 2


def test_strict_bundle_rejects_unknown_provenance(tmp_path: Path):
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    _write_wav(audio_root / "metal.wav", 400)
    _write_wav(audio_root / "impact.wav", 900)
    board_path = tmp_path / "board.json"
    board_path.write_text(json.dumps(_board()), encoding="utf-8")
    ledger = write_provenance_ledger(audio_root, tmp_path / "provenance.json")

    with pytest.raises(EvidenceBundleError, match="complete provenance"):
        build_evidence_bundle(
            board_path,
            audio_root,
            tmp_path / "bundle",
            provenance_ledger_path=ledger,
            require_provenance=True,
        )


def test_strict_provenance_preflight_leaves_no_partial_bundle(tmp_path: Path):
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    _write_wav(audio_root / "metal.wav", 400)
    _write_wav(audio_root / "impact.wav", 900)
    board_path = tmp_path / "board.json"
    board_path.write_text(json.dumps(_board()), encoding="utf-8")
    ledger = write_provenance_ledger(audio_root, tmp_path / "provenance.json")
    output = tmp_path / "bundle"

    with pytest.raises(EvidenceBundleError, match="complete provenance"):
        build_evidence_bundle(
            board_path,
            audio_root,
            output,
            provenance_ledger_path=ledger,
            require_provenance=True,
        )

    assert not output.exists()


def test_bundle_rejects_ledger_missing_referenced_fingerprint(tmp_path: Path):
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    _write_wav(audio_root / "metal.wav", 400)
    _write_wav(audio_root / "impact.wav", 900)
    board_path = tmp_path / "board.json"
    board_path.write_text(json.dumps(_board()), encoding="utf-8")
    ledger = write_provenance_ledger(audio_root, tmp_path / "provenance.json")

    payload = json.loads(ledger.read_text(encoding="utf-8"))
    payload["entries"] = [
        entry for entry in payload["entries"]
        if entry["path_hint"] != "impact.wav"
    ]
    payload["entry_count"] = len(payload["entries"])
    ledger.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(EvidenceBundleError, match="does not cover"):
        build_evidence_bundle(
            board_path,
            audio_root,
            tmp_path / "bundle",
            provenance_ledger_path=ledger,
        )
