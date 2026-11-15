import json
from math import pi, sin
from pathlib import Path
import shutil
import struct
import wave

import pytest

from mgal.scene_music import (
    SceneMusicError,
    _within,
    godot_preview,
    ingest,
    prepare,
    verify,
)


@pytest.fixture
def tone(tmp_path: Path) -> Path:
    source = tmp_path / "tone.wav"
    with wave.open(str(source), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(b"".join(struct.pack("<h", int(9000 * sin(2 * pi * 220 * t / 8000)))
                                 for t in range(8000 * 8)))
    return source


@pytest.mark.skipif(not shutil.which("ffprobe"), reason="ffprobe not installed")
def test_ingest_is_idempotent_and_source_immutable(tone, tmp_path):
    path = ingest(tone, tmp_path / "audio", "cozy_village")
    data = json.loads(path.read_text())
    assert data["rights"]["reviewed"] is False
    assert data["source"]["duration_s"] == 8
    assert ingest(tone, tmp_path / "audio", "cozy_village") == path
    assert verify(path)["integrity"] == "PASS"
    changed = tmp_path / "changed.wav"
    changed.write_bytes(tone.read_bytes() + b"X")
    with pytest.raises(SceneMusicError, match="different immutable original"):
        ingest(changed, tmp_path / "audio", "cozy_village")
    (path.parent / data["source"]["path"]).write_bytes(b"tampered")
    with pytest.raises(SceneMusicError, match="modified media"):
        verify(path)


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                    reason="ffmpeg/ffprobe not installed")
def test_prepare_real_ffmpeg_and_godot_scaffold(tone, tmp_path):
    path = ingest(tone, tmp_path / "audio", "mystery_forest")
    candidate = prepare(path, "A", 1, 6, 0.3)
    assert candidate["loop"]["duration_s"] == pytest.approx(4.7, abs=0.15)
    assert verify(path)["candidate_count"] == 1
    assert candidate == prepare(path, "A", 1, 6, 0.3)
    with pytest.raises(SceneMusicError, match="immutable"):
        prepare(path, "A", 2, 6, 0.3)
    project = godot_preview(path, "A")
    assert (project / "music.ogg").is_file()
    assert "track.loop = true" in (project / "main.gd").read_text()
    assert "run/main_scene" in (project / "project.godot").read_text()
    assert verify(path)["commercial_release_ready"] is False
    (project / "music.ogg").write_bytes(b"broken")
    with pytest.raises(SceneMusicError, match="preview media changed"):
        verify(path)


@pytest.mark.skipif(not shutil.which("ffprobe"), reason="ffprobe not installed")
def test_rejects_traversal_and_bad_time_ranges(tone, tmp_path):
    with pytest.raises(SceneMusicError, match="Traversal"):
        _within(tmp_path, "../escape")
    with pytest.raises(SceneMusicError):
        ingest(tone, tmp_path, "../../bad")
    path = ingest(tone, tmp_path, "safe_scene")
    with pytest.raises(SceneMusicError, match="source duration"):
        prepare(path, "A", 0, 9, 0.2)
    with pytest.raises(SceneMusicError, match="Clip must"):
        prepare(path, "A", 0, 4, 2)
    data = json.loads(path.read_text())
    data["source"]["path"] = "../../unsafe.wav"
    path.write_text(json.dumps(data))
    with pytest.raises(SceneMusicError, match="Traversal"):
        verify(path)


@pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                    reason="ffmpeg/ffprobe not installed")
def test_second_candidate_without_crossfade_and_scaffold_immutable(tone, tmp_path):
    path = ingest(tone, tmp_path / "audio", "quiet_rest_stop")
    first = prepare(path, "A", 0, 4, 0)
    assert first["loop"]["duration_s"] == pytest.approx(4.0, abs=0.15)
    second = prepare(path, "B", 2, 7, 0.5)
    assert second["loop"]["duration_s"] == pytest.approx(4.5, abs=0.15)
    project = godot_preview(path, "B")
    assert godot_preview(path, "B") == project
    (project / "main.gd").write_text("# changed")
    with pytest.raises(SceneMusicError, match="refusing overwrite"):
        godot_preview(path, "B")
    with pytest.raises(SceneMusicError, match="scaffold changed"):
        verify(path)


@pytest.mark.skipif(not shutil.which("ffprobe"), reason="ffprobe not installed")
def test_cli_ingest_smoke(tone, tmp_path, capsys):
    from mgal.scene_music import main
    assert main(["ingest", str(tone), "--workspace", str(tmp_path / "audio"),
                 "--scene-id", "cozy_village"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert Path(payload["manifest"]).is_file()
    assert main(["verify", payload["manifest"]]) == 0
    assert json.loads(capsys.readouterr().out)["commercial_release_ready"] is False
