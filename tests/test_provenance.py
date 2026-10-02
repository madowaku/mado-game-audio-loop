from array import array
import json
from pathlib import Path
import wave

import pytest

from mgal.provenance import (
    ProvenanceLedgerError,
    create_provenance_ledger,
    source_id_for_hash,
    subset_ledger_for_source_index,
    update_provenance_entry,
    validate_provenance_ledger,
    verify_provenance_subset,
    write_provenance_ledger,
)


def _write_wav(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = array("h", [value] * 80)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(data.tobytes())


def test_scan_creates_content_addressed_unknown_entries(tmp_path: Path):
    audio = tmp_path / "audio"
    _write_wav(audio / "metal.wav", 400)

    ledger = create_provenance_ledger(audio)

    assert ledger["entry_count"] == 1
    entry = ledger["entries"][0]
    assert entry["source_id"] == source_id_for_hash(entry["sha256"])
    assert entry["path_hint"] == "metal.wav"
    assert entry["source_type"] == "unknown"
    assert entry["license"]["status"] == "unknown"


def test_update_generated_entry_can_become_complete(tmp_path: Path):
    audio = tmp_path / "audio"
    _write_wav(audio / "generated.wav", 700)
    ledger_path = write_provenance_ledger(audio, tmp_path / "provenance.json")

    update_provenance_entry(
        ledger_path,
        "generated.wav",
        source_type="generated",
        license_status="terms",
        license_expression="provider-terms",
        license_url="https://example.invalid/terms",
        provider="ExampleProvider",
        model="ExampleModel",
        prompt="short metallic impact",
        seed="42",
    )

    report = validate_provenance_ledger(ledger_path, audio)
    assert report["complete"] is True
    assert report["complete_entries"] == 1


def test_validate_detects_source_hash_drift(tmp_path: Path):
    audio = tmp_path / "audio"
    _write_wav(audio / "metal.wav", 400)
    ledger_path = write_provenance_ledger(audio, tmp_path / "provenance.json")

    _write_wav(audio / "metal.wav", 401)

    with pytest.raises(ProvenanceLedgerError, match="hash changed"):
        validate_provenance_ledger(ledger_path, audio)


def test_subset_matches_sources_by_hash_not_path(tmp_path: Path):
    audio = tmp_path / "audio"
    _write_wav(audio / "metal.wav", 400)
    ledger_path = write_provenance_ledger(audio, tmp_path / "provenance.json")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    entry = ledger["entries"][0]

    source_index = {
        "source_index_version": "0.1",
        "source_count": 1,
        "sources": [
            {
                "relative_path": "renamed/metal_v2.wav",
                "sha256": entry["sha256"],
                "bytes": entry["bytes"],
            }
        ],
    }

    subset = subset_ledger_for_source_index(ledger_path, source_index)
    assert subset["entry_count"] == 1
    assert subset["entries"][0]["path_hint"] == "metal.wav"


def test_provenance_subset_requires_exact_fingerprint_set(tmp_path: Path):
    audio = tmp_path / "audio"
    _write_wav(audio / "metal.wav", 400)
    ledger_path = write_provenance_ledger(audio, tmp_path / "provenance.json")
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    entry = ledger["entries"][0]

    source_index = {
        "source_index_version": "0.1",
        "source_count": 1,
        "sources": [
            {
                "relative_path": "metal.wav",
                "sha256": entry["sha256"],
                "bytes": entry["bytes"],
            }
        ],
    }
    subset = subset_ledger_for_source_index(ledger_path, source_index)
    subset["entries"] = []

    with pytest.raises(ProvenanceLedgerError, match="do not match"):
        verify_provenance_subset(subset, source_index)
