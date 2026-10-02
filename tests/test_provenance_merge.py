from array import array
from pathlib import Path
import wave

import pytest

from mgal.provenance import (
    ProvenanceLedgerError,
    merge_provenance_ledgers,
    update_provenance_entry,
    validate_provenance_ledger,
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


def test_merge_combines_local_and_generated_ledgers(tmp_path: Path):
    local_root = tmp_path / "local"
    generated_root = tmp_path / "generated"
    _write_wav(local_root / "metal.wav", 400)
    _write_wav(generated_root / "impact.wav", 900)

    local = write_provenance_ledger(
        local_root,
        tmp_path / "local.json",
    )
    update_provenance_entry(
        local,
        "metal.wav",
        source_type="free_library",
        license_status="declared",
        license_expression="CC0-1.0",
    )

    generated = write_provenance_ledger(
        generated_root,
        tmp_path / "generated.json",
    )
    update_provenance_entry(
        generated,
        "impact.wav",
        source_type="generated",
        license_status="terms",
        license_expression="provider-terms",
        provider="fixture-provider",
        model="fixture-model",
        prompt="impact",
    )

    merged = merge_provenance_ledgers(
        [local, generated],
        tmp_path / "merged.json",
    )
    report = validate_provenance_ledger(merged)

    assert report["entries"] == 2
    assert report["complete"] is True


def test_merge_prefers_complete_duplicate_over_unknown(tmp_path: Path):
    root = tmp_path / "audio"
    _write_wav(root / "impact.wav", 900)

    unknown = write_provenance_ledger(
        root,
        tmp_path / "unknown.json",
    )
    complete = write_provenance_ledger(
        root,
        tmp_path / "complete.json",
    )
    update_provenance_entry(
        complete,
        "impact.wav",
        source_type="generated",
        license_status="terms",
        license_expression="provider-terms",
        provider="provider",
        model="model",
        prompt="impact",
    )

    merged = merge_provenance_ledgers(
        [unknown, complete],
        tmp_path / "merged.json",
    )
    report = validate_provenance_ledger(merged)

    assert report["entries"] == 1
    assert report["complete"] is True


def test_merge_rejects_conflicting_complete_entries(tmp_path: Path):
    root = tmp_path / "audio"
    _write_wav(root / "impact.wav", 900)

    first = write_provenance_ledger(root, tmp_path / "first.json")
    second = write_provenance_ledger(root, tmp_path / "second.json")

    update_provenance_entry(
        first,
        "impact.wav",
        source_type="generated",
        license_status="terms",
        license_expression="provider-a-terms",
        provider="provider-a",
        model="model",
        prompt="impact",
    )
    update_provenance_entry(
        second,
        "impact.wav",
        source_type="generated",
        license_status="terms",
        license_expression="provider-b-terms",
        provider="provider-b",
        model="model",
        prompt="impact",
    )

    with pytest.raises(ProvenanceLedgerError, match="conflicting"):
        merge_provenance_ledgers(
            [first, second],
            tmp_path / "merged.json",
        )
