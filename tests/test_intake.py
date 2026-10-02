from array import array
import json
from pathlib import Path
import wave

from mgal.candidate import parse_candidate_board
from mgal.intake import (
    build_intake_candidate_seed,
    build_provider_intake,
    load_intake_catalog,
    verify_intake_manifest,
)
from mgal.provider import (
    FixtureGeneratedProvider,
    SourceRequest,
    write_provider_result,
)
from mgal.provenance import validate_provenance_ledger


def test_provider_intake_normalizes_and_registers_workspace(tmp_path: Path):
    raw_root = tmp_path / "raw"
    provider = FixtureGeneratedProvider(raw_root)
    result = provider.provide(
        SourceRequest(
            request_id="impact",
            intent="short impact",
            count=2,
            seed="42",
        )
    )
    result_path = write_provider_result(
        result,
        tmp_path / "provider-result.json",
    )

    audio_root = tmp_path / "audio"
    intake = build_provider_intake(
        result_path,
        audio_root,
        intake_id="impact-run",
    )

    assert intake["ok"] is True
    assert intake["intake_id"] == "impact-run"
    assert intake["candidate_count"] == 2
    assert intake["reused"] is False

    manifest_path = Path(intake["manifest_path"])
    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )
    assert manifest["normalization_profile_id"] == "mgal-pcm16-mono-44100-v1"
    assert all(
        item["relative_path"].startswith("incoming/impact-run/")
        for item in manifest["candidates"]
    )
    assert all(
        (audio_root / item["relative_path"]).is_file()
        for item in manifest["candidates"]
    )

    verification = verify_intake_manifest(
        audio_root,
        manifest_path,
    )
    assert verification["candidate_count"] == 2

    ledger_path = Path(intake["workspace_ledger"])
    report = validate_provenance_ledger(
        ledger_path,
        audio_root=audio_root,
    )
    assert report["entries"] == 2
    assert report["complete"] is True

    catalog = load_intake_catalog(audio_root)
    assert len(catalog) == 2
    assert all(
        metadata["intake_id"] == "impact-run"
        for metadata in catalog.values()
    )
    assert all(
        metadata["provider_id"] == "fixture-generated"
        for metadata in catalog.values()
    )


def test_provider_intake_is_idempotent_for_same_result(tmp_path: Path):
    provider = FixtureGeneratedProvider(tmp_path / "raw")
    result = provider.provide(
        SourceRequest(
            request_id="impact",
            intent="impact",
            count=1,
        )
    )
    result_path = write_provider_result(
        result,
        tmp_path / "provider-result.json",
    )
    audio_root = tmp_path / "audio"

    first = build_provider_intake(
        result_path,
        audio_root,
        intake_id="same",
    )
    second = build_provider_intake(
        result_path,
        audio_root,
        intake_id="same",
    )

    assert first["reused"] is False
    assert second["reused"] is True


def test_workspace_ledger_uses_audio_root_relative_paths(tmp_path: Path):
    provider = FixtureGeneratedProvider(tmp_path / "raw")
    result = provider.provide(
        SourceRequest(
            request_id="impact",
            intent="impact",
            count=1,
        )
    )
    result_path = write_provider_result(
        result,
        tmp_path / "provider-result.json",
    )
    audio_root = tmp_path / "audio"

    intake = build_provider_intake(
        result_path,
        audio_root,
        intake_id="relative",
    )

    ledger = json.loads(
        Path(intake["workspace_ledger"]).read_text(
            encoding="utf-8"
        )
    )
    path_hint = ledger["entries"][0]["path_hint"]
    assert path_hint.startswith("incoming/relative/")
    assert (audio_root / path_hint).is_file()


def _intake_with_count(
    tmp_path: Path,
    *,
    count: int,
    intake_id: str,
):
    provider = FixtureGeneratedProvider(tmp_path / ("raw-" + intake_id))
    result = provider.provide(
        SourceRequest(
            request_id=intake_id,
            intent="compare generated impact",
            count=count,
            seed="42",
        )
    )
    result_path = write_provider_result(
        result,
        tmp_path / (intake_id + "-provider-result.json"),
    )
    audio_root = tmp_path / ("audio-" + intake_id)
    build_provider_intake(
        result_path,
        audio_root,
        intake_id=intake_id,
    )
    return audio_root


def test_intake_candidate_seed_compiles_first_three_to_valid_board(
    tmp_path: Path,
):
    audio_root = _intake_with_count(
        tmp_path,
        count=4,
        intake_id="four",
    )

    board = build_intake_candidate_seed(
        audio_root,
        "four",
    )
    parsed = parse_candidate_board(board)

    assert [candidate.label for candidate in parsed.candidates] == [
        "A",
        "B",
        "C",
    ]
    assert len(parsed.candidates) == 3
    assert parsed.intent == "compare generated impact"
    assert len(parsed.base_recipe.layers) == 1
    assert (
        parsed.base_recipe.layers[0].source
        == parsed.candidates[0].recipe.layers[0].source
    )
    assert len(
        {
            candidate.recipe.layers[0].source
            for candidate in parsed.candidates
        }
    ) == 3


def test_intake_candidate_seed_supports_single_candidate(tmp_path: Path):
    audio_root = _intake_with_count(
        tmp_path,
        count=1,
        intake_id="single",
    )

    board = build_intake_candidate_seed(
        audio_root,
        "single",
    )
    parsed = parse_candidate_board(board)

    assert len(parsed.candidates) == 1
    assert parsed.candidates[0].label == "A"
    assert parsed.active_candidate_id == parsed.candidates[0].id
    assert parsed.selected_candidate_id is None
