from array import array
import json
from pathlib import Path
import wave

import pytest

from mgal.evidence import build_evidence_bundle
from mgal.provenance import (
    update_provenance_entry,
    write_provenance_ledger,
)
from mgal.release import (
    ReleasePackError,
    build_release_pack,
    verify_release_pack,
)


def _write_wav(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = array("h", [value] * 80)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(data.tobytes())


def _recipe(recipe_id: str, sources: list[str]) -> dict:
    return {
        "recipe_version": "0.1",
        "id": recipe_id,
        "intent": "release slash",
        "layers": [
            {"source": source, "gain": 1.0, "offset_ms": 0}
            for source in sources
        ],
        "processing": {"normalize": True, "fade_out_ms": 0},
    }


def _bundle(tmp_path: Path, with_provenance: bool = True) -> Path:
    audio = tmp_path / "audio"
    _write_wav(audio / "metal.wav", 400)
    _write_wav(audio / "impact.wav", 900)
    _write_wav(audio / "unused.wav", 1200)

    base_id = "slash-base"
    selected_id = "slash-final"
    board = {
        "candidate_board_version": "0.1",
        "intent": "release slash",
        "base_recipe": _recipe(base_id, ["metal.wav"]),
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
                "recipe": _recipe(selected_id, ["impact.wav"]),
                "decision": {
                    "status": "selected",
                    "reason": "ships cleanly",
                },
            },
        ],
    }
    board_path = tmp_path / "board.json"
    board_path.write_text(json.dumps(board), encoding="utf-8")

    ledger = None
    if with_provenance:
        ledger = write_provenance_ledger(audio, tmp_path / "provenance.json")
        update_provenance_entry(
            ledger,
            "metal.wav",
            source_type="free_library",
            creator="Base Creator",
            title="Unused Base Metal",
            license_status="declared",
            license_expression="CC0-1.0",
        )
        update_provenance_entry(
            ledger,
            "impact.wav",
            source_type="free_library",
            creator="Impact Creator",
            title="Impact Final",
            origin_url="https://example.invalid/impact",
            license_status="declared",
            license_expression="CC-BY-4.0",
            license_url="https://example.invalid/license",
            attribution="Impact Final by Impact Creator",
        )
        update_provenance_entry(
            ledger,
            "unused.wav",
            source_type="recorded",
            license_status="owned",
            recorded_by="fixture",
        )

    return build_evidence_bundle(
        board_path,
        audio,
        tmp_path / "evidence",
        provenance_ledger_path=ledger,
        require_provenance=with_provenance,
    )


def test_release_pack_uses_only_selected_recipe_sources(tmp_path: Path):
    bundle = _bundle(tmp_path)
    pack = build_release_pack(
        bundle,
        tmp_path / "release",
        name="Heavy Slash Final",
    )

    assert (pack / "heavy-slash-final.wav").is_file()
    assert (pack / "ATTRIBUTION.txt").is_file()
    assert (pack / "LICENSE_SUMMARY.json").is_file()
    assert (pack / "PROVENANCE_REPORT.json").is_file()
    assert (pack / "RECIPE.json").is_file()
    assert (pack / "RELEASE_MANIFEST.json").is_file()

    attribution = (pack / "ATTRIBUTION.txt").read_text(encoding="utf-8")
    assert "Impact Final" in attribution
    assert "Impact Final by Impact Creator" in attribution
    assert "Unused Base Metal" not in attribution
    assert "unused.wav" not in attribution

    licenses = json.loads(
        (pack / "LICENSE_SUMMARY.json").read_text(encoding="utf-8")
    )
    assert licenses["source_count"] == 1
    assert licenses["sources"][0]["path_hint"] == "impact.wav"

    result = verify_release_pack(pack)
    assert result["ok"] is True
    assert result["sources"] == 1
    assert result["final_wav"] == "heavy-slash-final.wav"


def test_release_pack_requires_provenance(tmp_path: Path):
    bundle = _bundle(tmp_path, with_provenance=False)

    with pytest.raises(ReleasePackError, match="requires provenance"):
        build_release_pack(bundle, tmp_path / "release")


def test_release_pack_rejects_incomplete_selected_provenance(tmp_path: Path):
    audio = tmp_path / "audio"
    _write_wav(audio / "impact.wav", 900)

    selected_id = "impact-final"
    board = {
        "candidate_board_version": "0.1",
        "intent": "impact",
        "base_recipe": _recipe("base", ["impact.wav"]),
        "active_candidate_id": selected_id,
        "selected_candidate_id": selected_id,
        "candidates": [
            {
                "id": selected_id,
                "label": "A",
                "parent_recipe_id": "base",
                "revision": 1,
                "lineage": [
                    {
                        "from_recipe_id": "base",
                        "action": "fork",
                        "revision": 1,
                    }
                ],
                "recipe": _recipe(selected_id, ["impact.wav"]),
                "decision": {"status": "selected", "reason": "final"},
            }
        ],
    }
    board_path = tmp_path / "board.json"
    board_path.write_text(json.dumps(board), encoding="utf-8")
    ledger = write_provenance_ledger(audio, tmp_path / "provenance.json")
    bundle = build_evidence_bundle(
        board_path,
        audio,
        tmp_path / "evidence",
        provenance_ledger_path=ledger,
        require_provenance=False,
    )

    with pytest.raises(ReleasePackError, match="incomplete"):
        build_release_pack(bundle, tmp_path / "release")


def test_release_verify_detects_tampering(tmp_path: Path):
    bundle = _bundle(tmp_path)
    pack = build_release_pack(bundle, tmp_path / "release")
    (pack / "ATTRIBUTION.txt").write_text("changed\n", encoding="utf-8")

    with pytest.raises(ReleasePackError, match="changed"):
        verify_release_pack(pack)
