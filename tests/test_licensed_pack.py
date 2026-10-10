from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import stat
import wave
import zipfile

import pytest

from mgal.cli import main
from mgal.godot_bridge import stage_godot_adaptive_music
from mgal.licensed_pack import (
    LicensedPackError,
    intake_licensed_zip,
    verify_licensed_pack,
)


def _wav() -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(44100)
        writer.writeframes(b"\x00\x00" * 441)
    return buffer.getvalue()


def _fixture(tmp_path: Path, *, extras: dict[str, bytes] | None = None):
    archive = tmp_path / "music.zip"
    audio = _wav()
    files = {
        "music/forest-low.wav": audio,
        "music/forest-medium.wav": audio,
        "music/forest-high.wav": audio,
        "music/forest-30s.wav": audio,
        "sfx/click.wav": audio,
    }
    files.update(extras or {})
    with zipfile.ZipFile(archive, "w") as zipped:
        for path, payload in files.items():
            zipped.writestr(path, payload)
    evidence = tmp_path / "terms.txt"
    evidence.write_text("Locally reviewed license terms (synthetic fixture).", encoding="utf-8")
    declaration = tmp_path / "declaration.json"
    declaration.write_text(json.dumps({
        "licensed_audio_declaration_version": "0.1",
        "pack_name": "Audio Fixture",
        "publisher": "Fixture creator",
        "source_url": "https://example.org/sample",
        "license_url": "https://example.org/license",
        "reviewed_by": "fixture-human-reviewer",
        "usage_scope": "embedded_game_only",
        "standalone_redistribution": False,
        "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    root = tmp_path / "audio"
    return archive, root, declaration, evidence


def _intake(tmp_path: Path):
    archive, root, declaration, evidence = _fixture(tmp_path)
    result = intake_licensed_zip(archive, root, declaration, evidence, pack_id="fixture")
    return archive, root, declaration, evidence, result


def test_intake_and_reuse_checks_bytes_and_three_tiers(tmp_path: Path):
    archive, root, declaration, evidence, result = _intake(tmp_path)
    assert result["reused"] is False
    assert result["file_count"] == 5
    assert result["music_group_count"] == 1
    manifest = verify_licensed_pack(root, "fixture", evidence)
    assert list(manifest["music_groups"][0]["tiers"]) == ["low", "medium", "high"]
    assert manifest["policy"]["raw_repository_upload"] == "forbidden"
    assert intake_licensed_zip(
        archive, root, declaration, evidence, pack_id="fixture"
    )["reused"] is True


def test_tampering_audio_fails_verify(tmp_path: Path):
    _, root, _, evidence, _ = _intake(tmp_path)
    target = root / ".mgal/private-packs/fixture/audio/music/forest-low.wav"
    target.write_bytes(b"changed")
    with pytest.raises(LicensedPackError, match="drift"):
        verify_licensed_pack(root, "fixture", evidence)


def test_evidence_must_match_exact_reviewed_bytes(tmp_path: Path):
    archive, root, declaration, evidence = _fixture(tmp_path)
    evidence.write_text("different", encoding="utf-8")
    with pytest.raises(LicensedPackError, match="evidence"):
        intake_licensed_zip(archive, root, declaration, evidence)


def test_zip_path_traversal_is_rejected_before_import(tmp_path: Path):
    archive, root, declaration, evidence = _fixture(
        tmp_path, extras={"../escape.wav": _wav()}
    )
    with pytest.raises(LicensedPackError, match="unsafe ZIP"):
        intake_licensed_zip(archive, root, declaration, evidence)
    assert not (tmp_path / "escape.wav").exists()


def test_zip_symlink_is_rejected(tmp_path: Path):
    archive, root, declaration, evidence = _fixture(tmp_path)
    with zipfile.ZipFile(archive, "a") as zipped:
        link = zipfile.ZipInfo("music/link.wav")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        zipped.writestr(link, "../elsewhere")
    with pytest.raises(LicensedPackError, match="links"):
        intake_licensed_zip(archive, root, declaration, evidence)


def test_ambiguous_tier_is_not_guessed(tmp_path: Path):
    archive, root, declaration, evidence = _fixture(
        tmp_path, extras={"music/forest low.ogg": b"OggS" + b"\x00" * 20}
    )
    report = intake_licensed_zip(archive, root, declaration, evidence)
    assert report["music_group_count"] == 0


def test_godot_script_is_metadata_only_until_explicit_copy(tmp_path: Path):
    _, root, _, evidence, _ = _intake(tmp_path)
    project = tmp_path / "game"
    project.mkdir()
    (project / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    dry = stage_godot_adaptive_music(root, "fixture", project, evidence)
    assert dry["ready_for_playback"] is False
    assert dry["track_count"] == 1
    assert Path(dry["bridge_json"]).is_file()
    assert not (project / "assets/mgal_licensed/fixture").exists()

    live = stage_godot_adaptive_music(
        root, "fixture", project, evidence, copy_licensed_audio=True
    )
    assert live["ready_for_playback"] is True
    assert live["copied_file_count"] == 3
    ignored = project / "assets/mgal_licensed/.gitignore"
    assert ignored.read_text(encoding="utf-8") == "*\n!.gitignore\n"
    script = Path(live["gdscript"]).read_text(encoding="utf-8")
    assert "func set_intensity" in script
    assert "res://addons/mgal_adaptive_music/fixture/bridge.json" in script
    index = json.loads(Path(live["bridge_json"]).read_text(encoding="utf-8"))
    assert "res://assets/mgal_licensed/fixture/music/forest-low.wav" in (
        next(iter(index["tracks"].values())).values()
    )
    # Idempotent byte-for-byte staging.
    assert stage_godot_adaptive_music(
        root, "fixture", project, evidence, copy_licensed_audio=True
    )["ok"] is True


def test_godot_stage_rechecks_license_evidence(tmp_path: Path):
    _, root, _, evidence, _ = _intake(tmp_path)
    project = tmp_path / "game"
    project.mkdir()
    (project / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    evidence.unlink()
    with pytest.raises(LicensedPackError, match="evidence"):
        stage_godot_adaptive_music(root, "fixture", project, evidence)


def test_cli_entrypoints(tmp_path: Path, capsys):
    archive, root, declaration, evidence = _fixture(tmp_path)
    assert main([
        "licensed-pack-intake", str(archive), "--audio-root", str(root),
        "--declaration", str(declaration), "--license-evidence", str(evidence),
        "--pack-id", "fixture",
    ]) == 0
    capsys.readouterr()
    assert main([
        "licensed-pack-verify", "--audio-root", str(root),
        "--pack-id", "fixture", "--license-evidence", str(evidence),
    ]) == 0
    assert json.loads(capsys.readouterr().out)["music_group_count"] == 1
