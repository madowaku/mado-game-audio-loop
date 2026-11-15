"""Offline-first BGM intake, loop candidates and Godot preview for MGSF M0.2.

Never calls the music provider. A real human must review music and its rights.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


SCHEMA = "mgsf-scene-music/0.2"
SCENE_ID = re.compile(r"^[a-z][a-z0-9_-]{1,47}$")
SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a", ".aac"}


class SceneMusicError(ValueError):
    """Invalid or unsafe pipeline input."""


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _within(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise SceneMusicError("Path must be relative to the scene workspace")
    if any(part in {"..", "."} for part in Path(relative).parts):
        raise SceneMusicError("Traversal is forbidden in workspace paths")
    base = root.resolve()
    result = (base / relative).resolve()
    if not result.is_relative_to(base):
        raise SceneMusicError("Path escapes the scene workspace")
    return result


def _write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as out:
        tmp = Path(out.name)
        try:
            json.dump(value, out, indent=2, ensure_ascii=False, sort_keys=True)
            out.write("\n")
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
    os.replace(tmp, path)


def _run(command: list[str]) -> str:
    try:
        result = subprocess.run(command, text=True, capture_output=True, check=False)
    except FileNotFoundError as exc:
        raise SceneMusicError(f"Required executable missing: {command[0]}") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[-900:]
        raise SceneMusicError(f"{command[0]} failed: {detail}")
    return result.stdout


def _probe(path: Path, ffprobe: str = "ffprobe") -> dict:
    output = _run([ffprobe, "-v", "error", "-select_streams", "a:0",
                   "-show_entries", "stream=codec_name,sample_rate,channels:format=duration",
                   "-of", "json", str(path)])
    try:
        data = json.loads(output)
        stream = data["streams"][0]
        duration = float(data["format"]["duration"])
        if duration <= 0 or not stream.get("codec_name"):
            raise ValueError("empty stream")
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SceneMusicError(f"Not a readable audio file: {path}") from exc
    return {"duration_s": round(duration, 3), "codec": stream["codec_name"],
            "sample_rate": int(stream["sample_rate"]), "channels": int(stream["channels"])}


def _load(manifest_path: str | Path) -> tuple[Path, dict]:
    path = Path(manifest_path).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SceneMusicError("Cannot read scene music manifest") from exc
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA:
        raise SceneMusicError("Unsupported manifest schema")
    if not SCENE_ID.fullmatch(str(data.get("scene_id", ""))):
        raise SceneMusicError("Invalid scene ID")
    if not isinstance(data.get("candidates"), dict):
        raise SceneMusicError("Invalid candidate map")
    return path, data


def _checked(root: Path, entry: dict) -> Path:
    path = _within(root, entry["path"])
    if not path.is_file() or _hash(path) != entry["sha256"]:
        raise SceneMusicError(f"Missing or modified media: {entry['path']}")
    if path.stat().st_size != entry["bytes"]:
        raise SceneMusicError(f"Media size mismatch: {entry['path']}")
    return path


def ingest(source: str | Path, workspace: str | Path, scene_id: str,
           *, provider: str = "bgmcreator", origin_url: str | None = None,
           ffprobe: str = "ffprobe") -> Path:
    if not SCENE_ID.fullmatch(scene_id):
        raise SceneMusicError("scene_id must be 2–48 lowercase URL-safe characters")
    incoming = Path(source).resolve(strict=True)
    if not incoming.is_file() or incoming.suffix.lower() not in SUFFIXES:
        raise SceneMusicError("Unsupported source format (WAV/MP3/FLAC/OGG/M4A/AAC)")
    info = _probe(incoming, ffprobe)
    root = Path(workspace).resolve() / "scene-music" / scene_id
    manifest_path = root / "manifest.json"
    relative = f"original/source{incoming.suffix.lower()}"
    stored = _within(root, relative)
    incoming_hash = _hash(incoming)
    if manifest_path.exists():
        _, existing = _load(manifest_path)
        if existing["source"]["sha256"] != incoming_hash:
            raise SceneMusicError("Scene already has a different immutable original")
        _checked(root, existing["source"])
        return manifest_path
    if stored.exists() and _hash(stored) != incoming_hash:
        raise SceneMusicError("Existing original differs; refusing overwrite")
    stored.parent.mkdir(parents=True, exist_ok=True)
    if not stored.exists():
        with tempfile.NamedTemporaryFile(dir=stored.parent, delete=False) as out:
            tmp = Path(out.name)
        try:
            shutil.copyfile(incoming, tmp)
            if _hash(tmp) != incoming_hash:
                raise SceneMusicError("Original changed during copying")
            os.replace(tmp, stored)
        finally:
            tmp.unlink(missing_ok=True)
    manifest = {
        "schema_version": SCHEMA, "scene_id": scene_id,
        "provider": {"name": provider, "origin_url": origin_url,
                     "method": "human_download_and_local_ingest"},
        "source": {"path": relative, "sha256": incoming_hash,
                   "bytes": stored.stat().st_size, **info},
        "rights": {"reviewed": False, "commercial_use_allowed": None,
                   "terms_url": None, "reviewed_at": None, "evidence": None},
        "candidates": {}, "selected_candidate": None,
        "godot_playtest_verified": False,
    }
    _write_json(manifest_path, manifest)
    return manifest_path


def prepare(manifest_path: str | Path, candidate: str, start_s: float, end_s: float,
            crossfade_s: float = 0.35, *, ffmpeg: str = "ffmpeg",
            ffprobe: str = "ffprobe") -> dict:
    path, data = _load(manifest_path)
    root = path.parent
    source = _checked(root, data["source"])
    if candidate not in {"A", "B", "C"}:
        raise SceneMusicError("Candidate must be A, B or C")
    values = (start_s, end_s, crossfade_s)
    if not all(isinstance(v, (int, float)) and float("-inf") < v < float("inf") for v in values):
        raise SceneMusicError("Times must be finite numbers")
    if start_s < 0 or end_s <= start_s or crossfade_s < 0:
        raise SceneMusicError("Invalid trim or crossfade times")
    length = end_s - start_s
    if length < 4 or crossfade_s * 2 >= length:
        raise SceneMusicError("Clip must be >= 4 s and > 2x crossfade")
    if end_s > data["source"]["duration_s"] + 0.001:
        raise SceneMusicError("Clip end exceeds source duration")
    params = {"start_s": start_s, "end_s": end_s, "crossfade_s": crossfade_s}
    prior = data["candidates"].get(candidate)
    if prior:
        if prior.get("parameters") != params:
            raise SceneMusicError("Candidate is immutable; use a different A/B/C slot")
        _checked(root, prior["loop"])
        _checked(root, prior["boundary_preview"])
        return prior
    with tempfile.TemporaryDirectory(dir=root) as temp_dir:
        ogg_tmp = Path(temp_dir) / "loop.ogg"
        wav_tmp = Path(temp_dir) / "boundary-preview.wav"
        duration = round(length, 6)
        fade = round(crossfade_s, 6)
        if fade:
            # Center of a 2*fade tail/head overlap gives the circular seam.
            # Independent inputs avoid split-filter scheduling deadlocks.
            flt = (f"[0:a]atrim=start={start_s+fade}:end={end_s-fade},"
                   "asetpts=PTS-STARTPTS,aresample=48000,"
                   "aformat=channel_layouts=stereo[mid];"
                   f"[1:a]atrim=start={end_s-2*fade}:end={end_s},"
                   "asetpts=PTS-STARTPTS,aresample=48000,"
                   "aformat=channel_layouts=stereo[tail];"
                   f"[2:a]atrim=start={start_s}:end={start_s+2*fade},"
                   "asetpts=PTS-STARTPTS,aresample=48000,"
                   "aformat=channel_layouts=stereo[head];"
                   f"[tail][head]acrossfade=d={fade}:c1=tri:c2=tri[raw];"
                   f"[raw]atrim=start={fade}:end={2*fade},asetpts=PTS-STARTPTS[seam];"
                   "[mid][seam]concat=n=2:v=0:a=1[loop]")
        else:
            flt = (f"[0:a]atrim=start={start_s}:end={end_s},asetpts=PTS-STARTPTS,"
                   "aresample=48000,aformat=channel_layouts=stereo[loop]")
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                   "-i", str(source)]
        if fade:
            command.extend(["-i", str(source), "-i", str(source)])
        _run(command + ["-filter_complex", flt, "-map", "[loop]",
                        "-c:a", "libvorbis", "-q:a", "5", str(ogg_tmp)])
        loop_info = _probe(ogg_tmp, ffprobe)
        expected = duration - fade
        if abs(loop_info["duration_s"] - expected) > 0.2:
            raise SceneMusicError("Unexpected rendered loop duration")
        preview_half = min(2.0, loop_info["duration_s"] / 2)
        cut = round(loop_info["duration_s"] - preview_half, 3)
        flt_preview = (f"[0:a]atrim=start={cut},asetpts=PTS-STARTPTS[tail];"
                       f"[1:a]atrim=end={preview_half},asetpts=PTS-STARTPTS[head];"
                       "[tail][head]concat=n=2:v=0:a=1[preview]")
        _run([ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
              "-i", str(ogg_tmp), "-i", str(ogg_tmp),
              "-filter_complex", flt_preview,
              "-map", "[preview]", "-c:a", "pcm_s16le", str(wav_tmp)])
        _probe(wav_tmp, ffprobe)
        final_dir = _within(root, f"processed/{candidate}")
        final_dir.mkdir(parents=True, exist_ok=True)
        ogg = final_dir / "loop.ogg"
        wav = final_dir / "boundary-preview.wav"
        if ogg.exists() or wav.exists():
            raise SceneMusicError("Output exists without manifest receipt; refusing overwrite")
        os.replace(ogg_tmp, ogg)
        os.replace(wav_tmp, wav)
    entry = {"parameters": params, "loop": {"path": str(ogg.relative_to(root)),
             "sha256": _hash(ogg), "bytes": ogg.stat().st_size, **loop_info},
             "boundary_preview": {"path": str(wav.relative_to(root)),
             "sha256": _hash(wav), "bytes": wav.stat().st_size},
             "audition": {"human_reviewed": False, "seam_acceptable": None},
             "godot_preview": None}
    data["candidates"][candidate] = entry
    _write_json(path, data)
    return entry


def _immutable_text(path: Path, text: str) -> None:
    if path.exists():
        if not path.is_file() or path.read_text(encoding="utf-8") != text:
            raise SceneMusicError(f"Godot scaffold modified; refusing overwrite: {path.name}")
    else:
        path.write_text(text, encoding="utf-8")


def godot_preview(manifest_path: str | Path, candidate: str) -> Path:
    path, data = _load(manifest_path)
    root = path.parent
    entry = data["candidates"].get(candidate)
    if not entry:
        raise SceneMusicError("Prepare candidate before creating Godot preview")
    audio = _checked(root, entry["loop"])
    project = _within(root, f"godot-preview/{candidate}")
    project.mkdir(parents=True, exist_ok=True)
    music = project / "music.ogg"
    if music.exists() and _hash(music) != entry["loop"]["sha256"]:
        raise SceneMusicError("Godot preview music differs; refusing overwrite")
    if not music.exists():
        shutil.copyfile(audio, music)
    _immutable_text(project / "project.godot", 
        'config_version=5\n\n[application]\nconfig/name="MGSF Music Preview"\n'
        'run/main_scene="res://main.tscn"\n\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',
)
    _immutable_text(project / "main.tscn", 
        '[gd_scene load_steps=2 format=3]\n'
        '[ext_resource type="Script" path="res://main.gd" id="1"]\n'
        '[node name="MusicPreview" type="Node2D"]\nscript = ExtResource("1")\n'
        '[node name="Music" type="AudioStreamPlayer" parent="."]\n'
        '[node name="Instructions" type="Label" parent="."]\n'
        'offset_left = 24.0\noffset_top = 24.0\n'
        'text = "MGSF Music Preview: listen through the loop boundary"\n',
)
    _immutable_text(project / "main.gd", 
        'extends Node2D\n\n@onready var music: AudioStreamPlayer = $Music\n\n'
        'func _ready() -> void:\n'
        '\tvar track := AudioStreamOggVorbis.load_from_file("res://music.ogg")\n'
        '\tif track == null:\n'
        '\t\tpush_error("Cannot load music.ogg")\n\t\treturn\n'
        '\ttrack.loop = true\n\tmusic.stream = track\n\tmusic.play()\n',
    )
    entry["godot_preview"] = {"path": str(project.relative_to(root)),
                              "audio_sha256": _hash(music),
                              "scaffold_sha256": {name: _hash(project / name) for name in
                                                  ("project.godot", "main.tscn", "main.gd")},
                              "engine_tested": False}
    _write_json(path, data)
    return project


def verify(manifest_path: str | Path) -> dict:
    path, data = _load(manifest_path)
    root = path.parent
    _checked(root, data["source"])
    for name, entry in data["candidates"].items():
        if name not in {"A", "B", "C"}:
            raise SceneMusicError("Unexpected candidate ID")
        _checked(root, entry["loop"])
        _checked(root, entry["boundary_preview"])
        if entry.get("godot_preview"):
            preview = entry["godot_preview"]
            audio = _within(root, preview["path"] + "/music.ogg")
            if not audio.is_file() or _hash(audio) != preview["audio_sha256"]:
                raise SceneMusicError("Godot preview media changed")
            for filename, digest in preview.get("scaffold_sha256", {}).items():
                if filename not in {"project.godot", "main.tscn", "main.gd"}:
                    raise SceneMusicError("Unknown Godot preview file")
                scaffold = _within(root, preview["path"] + "/" + filename)
                if not scaffold.is_file() or _hash(scaffold) != digest:
                    raise SceneMusicError("Godot scaffold changed")
    return {"integrity": "PASS", "scene_id": data["scene_id"],
            "candidate_count": len(data["candidates"]),
            "commercial_release_ready": False,
            "notes": "Hash integrity only. Human musical, rights and engine review remain required."}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mgal-music", description="MGSF Living Music Pipeline M0.2")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("ingest", help="Copy and fingerprint a human-downloaded BGM")
    p.add_argument("source")
    p.add_argument("--workspace", required=True)
    p.add_argument("--scene-id", required=True)
    p.add_argument("--provider", default="bgmcreator")
    p.add_argument("--origin-url", default="https://bgmcreator.cotorano.com/ja")
    p = sub.add_parser("prepare", help="Render immutable A/B/C loop and boundary preview")
    p.add_argument("manifest")
    p.add_argument("--candidate", choices=["A", "B", "C"], required=True)
    p.add_argument("--start", type=float, required=True)
    p.add_argument("--end", type=float, required=True)
    p.add_argument("--crossfade", type=float, default=0.35)
    p = sub.add_parser("godot-preview", help="Export a Godot 4 audition project (not a playtest)")
    p.add_argument("manifest")
    p.add_argument("--candidate", choices=["A", "B", "C"], required=True)
    p = sub.add_parser("verify", help="Verify source and candidate hashes")
    p.add_argument("manifest")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "ingest":
            result = {"manifest": str(ingest(args.source, args.workspace, args.scene_id,
                                              provider=args.provider, origin_url=args.origin_url))}
        elif args.command == "prepare":
            result = prepare(args.manifest, args.candidate, args.start, args.end, args.crossfade)
        elif args.command == "godot-preview":
            result = {"project": str(godot_preview(args.manifest, args.candidate)),
                      "engine_tested": False}
        else:
            result = verify(args.manifest)
    except (SceneMusicError, OSError) as exc:
        build_parser().exit(2, f"mgal-music: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
