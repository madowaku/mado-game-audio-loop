"""Generate a minimal Godot 4 adaptive-intensity bridge for reviewed audio.

Generated script/JSON contain references only. Licensed bytes are copied into
an ignored project folder solely after --copy-licensed-audio is requested.
"""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from .licensed_pack import LicensedPackError, _pack_dir, verify_licensed_pack


GDSCRIPT = '''extends Node
## MGAL adaptive-intensity player. Godot 4.x, approximate position-sync.
## Not sample-accurate; inspect loop imports and audition transitions manually.

@export var fade_seconds: float = 0.4

var _tracks: Dictionary = {}
var _current_track: String = ""
var _current_level: String = ""
var _front: AudioStreamPlayer
var _back: AudioStreamPlayer
var _fade: Tween

func _ready() -> void:
    _front = AudioStreamPlayer.new()
    _back = AudioStreamPlayer.new()
    add_child(_front)
    add_child(_back)
    var decoded: Variant = JSON.parse_string(FileAccess.get_file_as_string("INDEX_PATH"))
    if decoded is Dictionary and decoded.has("tracks"):
        _tracks = decoded["tracks"]

func available_tracks() -> Array:
    return _tracks.keys()

func play_track(track_id: String, intensity: String = "low") -> bool:
    if not _tracks.has(track_id):
        push_warning("MGAL unknown track: " + track_id)
        return false
    var tiers: Dictionary = _tracks[track_id]
    if not tiers.has(intensity):
        push_warning("MGAL unknown intensity: " + intensity)
        return false
    if _current_track == track_id and _current_level == intensity and _front.playing:
        return true
    var stream: AudioStream = load(str(tiers[intensity])) as AudioStream
    if stream == null:
        push_warning("MGAL cannot load stream: " + str(tiers[intensity]))
        return false
    if _fade != null and _fade.is_running():
        _fade.kill()
    _back.stop()
    _back.stream = stream
    _back.volume_db = -60.0
    var start_position: float = _front.get_playback_position() if (_front.playing and _current_track == track_id) else 0.0
    _back.play(start_position)
    var previous: AudioStreamPlayer = _front
    _front = _back
    _back = previous
    _fade = create_tween().set_parallel(true)
    _fade.tween_property(_front, "volume_db", 0.0, max(fade_seconds, 0.0))
    if previous.playing:
        _fade.tween_property(previous, "volume_db", -60.0, max(fade_seconds, 0.0))
        _fade.finished.connect(func() -> void: previous.stop())
    _current_track = track_id
    _current_level = intensity
    return true

func set_intensity(intensity: String) -> bool:
    if _current_track.is_empty():
        return false
    return play_track(_current_track, intensity)

func stop_music() -> void:
    if _fade != null and _fade.is_running():
        _fade.kill()
    _front.stop()
    _back.stop()
    _current_track = ""
    _current_level = ""
'''


def _write_if_equal_or_new(path: Path, content: bytes) -> None:
    if path.is_symlink():
        raise LicensedPackError("refusing symlink output: " + str(path))
    if path.exists():
        if not path.is_file() or path.read_bytes() != content:
            raise LicensedPackError("output exists with different contents: " + str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _tracked(project: Path, relative: Path) -> bool:
    proc = subprocess.run(
        ["git", "ls-files", "--", relative.as_posix()],
        cwd=project, capture_output=True, text=True, check=False,
    ) if shutil.which("git") else None
    return bool(proc is not None and proc.returncode == 0 and proc.stdout.strip())


def stage_godot_adaptive_music(audio_root: str | Path, pack_id: str,
                               godot_project: str | Path,
                               license_evidence: str | Path,
                               *, copy_licensed_audio: bool = False) -> dict[str, Any]:
    pack = verify_licensed_pack(audio_root, pack_id, license_evidence)
    project = Path(godot_project).resolve()
    if not (project / "project.godot").is_file():
        raise LicensedPackError("Godot project.godot not found")
    if not pack["music_groups"]:
        raise LicensedPackError("no complete Low/Medium/High track groups found")

    pack_id = pack["pack_id"]
    audio_relative = Path("assets") / "mgal_licensed" / pack_id
    script_relative = Path("addons") / "mgal_adaptive_music" / pack_id
    script_root = project / script_relative
    dest_root = project / audio_relative
    if not script_root.resolve().is_relative_to(project):
        raise LicensedPackError("script output escapes project")
    if not dest_root.resolve().is_relative_to(project):
        raise LicensedPackError("audio output escapes project")

    tracks: dict[str, dict[str, str]] = {}
    copy_plan: list[tuple[Path, Path]] = []
    for group in pack["music_groups"]:
        tier_paths: dict[str, str] = {}
        for level, relative in group["tiers"].items():
            from .licensed_pack import _zip_relative
            safe = _zip_relative(relative)
            source = _pack_dir(audio_root, pack_id) / "audio" / safe.as_posix()
            dest = dest_root / safe.as_posix()
            if not dest.resolve().is_relative_to(dest_root.resolve()):
                raise LicensedPackError("audio output escapes destination")
            tier_paths[level] = "res://" + (audio_relative / safe.as_posix()).as_posix()
            copy_plan.append((source, dest))
        tracks[group["track_id"]] = tier_paths

    index = {
        "adaptive_bridge_version": "0.1",
        "pack_id": pack_id,
        "archive_sha256": pack["archive_sha256"],
        "license_evidence_sha256": pack["license_declaration"]["evidence_sha256"],
        "tracks": tracks,
        "note": "Licensed audio bytes excluded. Copy explicitly; embed in game exports, never ship standalone.",
    }
    index_path = script_root / "bridge.json"
    script_path = script_root / "adaptive_music.gd"
    script = GDSCRIPT.replace(
        "INDEX_PATH", "res://" + (script_relative / "bridge.json").as_posix()
    ).encode("utf-8")
    index_bytes = (json.dumps(index, ensure_ascii=False, indent=2) + "\n").encode("utf-8")

    # Validate all target conflicts before creating any output.
    for path, payload in ((index_path, index_bytes), (script_path, script)):
        if path.is_symlink() or (path.exists() and (not path.is_file() or path.read_bytes() != payload)):
            raise LicensedPackError("bridge output conflicts with existing file: " + str(path))
    if copy_licensed_audio:
        ignore = project / "assets" / "mgal_licensed" / ".gitignore"
        _write_if_equal_or_new(ignore, b"*\n!.gitignore\n")
        for source, dest in copy_plan:
            relative = dest.relative_to(project)
            if _tracked(project, relative):
                raise LicensedPackError("licensed audio already tracked by Git: " + str(relative))
            if dest.is_symlink() or (dest.exists() and (not dest.is_file() or
                source.stat().st_size != dest.stat().st_size or
                source.read_bytes() != dest.read_bytes())):
                raise LicensedPackError("licensed audio output conflict: " + str(relative))
        for source, dest in copy_plan:
            if not dest.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, dest)

    _write_if_equal_or_new(index_path, index_bytes)
    _write_if_equal_or_new(script_path, script)
    return {
        "ok": True, "pack_id": pack_id, "track_count": len(tracks),
        "audio_copied": copy_licensed_audio, "copied_file_count": len(copy_plan) if copy_licensed_audio else 0,
        "bridge_json": str(index_path), "gdscript": str(script_path),
        "ready_for_playback": copy_licensed_audio,
    }
