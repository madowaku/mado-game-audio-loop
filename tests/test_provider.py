from array import array
from dataclasses import replace
from pathlib import Path
import wave

import pytest

from mgal.provenance import (
    update_provenance_entry,
    validate_provenance_ledger,
    write_provenance_ledger,
)
from mgal.provider import (
    FixtureGeneratedProvider,
    LocalFileProvider,
    SourceProviderError,
    SourceRequest,
    provider_result_to_dict,
    validate_provider_result,
    write_provider_provenance_ledger,
)


def _write_wav(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = array("h", [value] * 80)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(data.tobytes())


def test_local_provider_returns_stable_contract_and_provenance(tmp_path: Path):
    audio = tmp_path / "audio"
    _write_wav(audio / "metal-hit.wav", 400)
    _write_wav(audio / "whoosh.wav", 900)

    ledger = write_provenance_ledger(audio, tmp_path / "provenance.json")
    update_provenance_entry(
        ledger,
        "metal-hit.wav",
        source_type="free_library",
        creator="Fixture Creator",
        license_status="declared",
        license_expression="CC0-1.0",
    )

    provider = LocalFileProvider(audio, ledger)
    result = provider.provide(
        SourceRequest(
            request_id="slash",
            intent="heavy slash",
            count=1,
            hints=("metal",),
        )
    )

    validate_provider_result(result)
    payload = provider_result_to_dict(result)

    assert payload["source_provider_contract_version"] == "1.0"
    assert payload["provider_kind"] == "local_file"
    assert Path(payload["artifact_root"]).is_absolute()
    assert payload["candidate_count"] == 1
    candidate = payload["candidates"][0]
    assert candidate["relative_path"] == "metal-hit.wav"
    assert candidate["source_id"].startswith("sha256:")
    assert candidate["provenance"]["source_type"] == "free_library"


def test_local_provider_falls_back_to_unknown_provenance(tmp_path: Path):
    audio = tmp_path / "audio"
    _write_wav(audio / "cloth.wav", 300)

    provider = LocalFileProvider(audio)
    result = provider.provide(
        SourceRequest(
            request_id="cloth",
            intent="cloth tear",
            count=1,
        )
    )

    assert result.candidates[0].provenance["source_type"] == "unknown"
    assert result.candidates[0].provenance["license"]["status"] == "unknown"


def test_fixture_generated_provider_is_deterministic(tmp_path: Path):
    request = SourceRequest(
        request_id="impact",
        intent="short metallic impact",
        count=2,
        duration_ms=100,
        seed="42",
    )

    first = FixtureGeneratedProvider(tmp_path / "first").provide(request)
    second = FixtureGeneratedProvider(tmp_path / "second").provide(request)

    assert [item.sha256 for item in first.candidates] == [
        item.sha256 for item in second.candidates
    ]
    assert all(
        item.provenance["source_type"] == "generated"
        for item in first.candidates
    )
    assert all(
        item.provenance["generation"]["prompt"] == request.intent
        for item in first.candidates
    )


def test_provider_contract_rejects_candidate_identity_drift(tmp_path: Path):
    provider = FixtureGeneratedProvider(tmp_path / "generated")
    result = provider.provide(
        SourceRequest(
            request_id="impact",
            intent="impact",
            count=1,
        )
    )
    candidate = result.candidates[0]
    broken = replace(candidate, source_id="sha256:" + "0" * 64)
    broken_result = replace(result, candidates=(broken,))

    with pytest.raises(SourceProviderError, match="source_id"):
        validate_provider_result(broken_result)


def test_request_rejects_unbounded_candidate_count():
    with pytest.raises(SourceProviderError, match="between 1 and 32"):
        SourceRequest(
            request_id="too-many",
            intent="impact",
            count=33,
        ).validate()


def test_explicit_hint_with_no_match_returns_no_candidates(tmp_path: Path):
    audio = tmp_path / "audio"
    _write_wav(audio / "cloth.wav", 300)

    provider = LocalFileProvider(audio)
    result = provider.provide(
        SourceRequest(
            request_id="metal-only",
            intent="heavy hit",
            count=4,
            hints=("metal",),
        )
    )

    assert result.candidates == ()


def test_generated_provider_can_emit_valid_provenance_ledger(tmp_path: Path):
    provider = FixtureGeneratedProvider(tmp_path / "generated")
    result = provider.provide(
        SourceRequest(
            request_id="generated-impact",
            intent="short metallic impact",
            count=2,
            duration_ms=90,
            seed="7",
        )
    )

    ledger_path = write_provider_provenance_ledger(
        result,
        tmp_path / "provider-provenance.json",
    )
    report = validate_provenance_ledger(
        ledger_path,
        audio_root=result.artifact_root,
    )

    assert report["complete"] is True
    assert report["entries"] == 2


def test_provider_validation_detects_artifact_tampering(tmp_path: Path):
    provider = FixtureGeneratedProvider(tmp_path / "generated")
    result = provider.provide(
        SourceRequest(
            request_id="impact",
            intent="impact",
            count=1,
        )
    )

    candidate_path = (
        Path(result.artifact_root) / result.candidates[0].relative_path
    )
    _write_wav(candidate_path, 1234)

    with pytest.raises(SourceProviderError, match="candidate"):
        validate_provider_result(result)
