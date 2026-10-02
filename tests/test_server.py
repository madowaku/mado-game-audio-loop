from array import array
from pathlib import Path
import wave

import pytest

from mgal.intake import build_provider_intake
from mgal.provider import (
    FixtureGeneratedProvider,
    SourceRequest,
    write_provider_result,
)
from mgal.server import build_catalog, resolve_audio_path


def _write_wav(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = array("h", [0] * 800)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(samples.tobytes())


def test_build_catalog_uses_relative_paths(tmp_path: Path):
    audio = tmp_path / "audio"
    _write_wav(audio / "swords" / "slash.wav")

    catalog = build_catalog(audio)

    assert len(catalog) == 1
    assert catalog[0]["relative_path"] == "swords/slash.wav"
    assert catalog[0]["duration_ms"] == 100
    assert catalog[0]["url"] == "/audio/swords/slash.wav"


def test_resolve_audio_path_rejects_escape(tmp_path: Path):
    audio = tmp_path / "audio"
    audio.mkdir()
    outside = tmp_path / "outside.wav"
    _write_wav(outside)

    with pytest.raises(PermissionError):
        resolve_audio_path(audio, "../outside.wav")


def test_build_catalog_enriches_provider_intake_metadata(tmp_path: Path):
    provider = FixtureGeneratedProvider(tmp_path / "raw")
    result = provider.provide(
        SourceRequest(
            request_id="impact",
            intent="short metallic impact",
            count=1,
            seed="42",
        )
    )
    result_path = write_provider_result(
        result,
        tmp_path / "provider-result.json",
    )
    audio_root = tmp_path / "audio"
    build_provider_intake(
        result_path,
        audio_root,
        intake_id="impact-run",
    )

    catalog = build_catalog(audio_root)

    assert len(catalog) == 1
    row = catalog[0]
    assert row["relative_path"].startswith("incoming/impact-run/")
    assert row["bytes"] > 0
    assert row["intake"]["intake_id"] == "impact-run"
    assert row["intake"]["provider_id"] == "fixture-generated"
    assert row["intake"]["source_type"] == "generated"
    assert row["intake"]["prompt"] == "short metallic impact"
    assert row["intake"]["normalization_profile_id"] == "mgal-pcm16-mono-44100-v1"


def test_server_exposes_preference_evidence_post_contract():
    from mgal import server

    source = Path(server.__file__).read_text(encoding="utf-8")
    assert 'def do_POST(self)' in source
    assert '"/api/preference-evidence"' in source
    assert "compile_preference_evidence" in source
    assert "2_000_000" in source


def test_server_exposes_preference_archive_replay_contract():
    from mgal import server as server_module

    source = Path(server_module.__file__).read_text(encoding="utf-8")
    assert '"/api/preference-archive"' in source
    assert 'parsed.path == "/api/preferences"' in source
    assert 'parsed.path.startswith("/api/preferences/")' in source
    assert 'parsed.path.endswith("/replay")' in source
    assert "archive_preference_evidence" in source
    assert "list_portable_preference_archives" in source
    assert "replay_preference_archive_portable" in source
    assert "write_preference_relink_map" in source
    assert 'parsed.path.endswith("/recover")' in source


def test_server_exposes_explicit_decision_memory_contract():
    from mgal import server as server_module

    source = Path(server_module.__file__).read_text(encoding="utf-8")
    assert 'parsed.path == "/api/decision-memory"' in source
    assert 'parsed.path.endswith("/promote")' in source
    assert "promote_preference_archive" in source
    assert "decision_memory_view" in source
    assert "promoted_hashes" in source
    assert 'entry["promotable"]' in source
    assert 'entry["promoted"]' in source
