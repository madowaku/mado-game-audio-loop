"""Licensed audio archives: private, hash-addressed intake with fail-closed license evidence.

No network, no audio transcoding, no standalone redistribution, and no automatic
permission inference. Only human-reviewed declarations are accepted.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import wave
import zipfile
from typing import Any


PACK_VERSION = "0.1"
AUDIO_SUFFIXES = {".wav", ".ogg", ".mp3"}
MAX_MEMBERS = 4000
MAX_UNCOMPRESSED_BYTES = 3 * 1024**3
MAX_FILE_BYTES = 512 * 1024**2
_TIER = re.compile(r"(?<![a-z0-9])(low|medium|high)(?![a-z0-9])", re.I)
_SHORT_CUT = re.compile(r"(?<![a-z0-9])(?:30|60)[ _-]?(?:s|sec|seconds)(?![a-z0-9])", re.I)
_SLUG = re.compile(r"[^a-z0-9]+")


class LicensedPackError(ValueError):
    """A pack is unsafe, unlicensed, ambiguous, or has changed."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _slug(value: str) -> str:
    value = _SLUG.sub("-", value.lower()).strip("-")
    if not value or len(value) > 75:
        raise LicensedPackError("pack_id must be 1-75 slug characters")
    return value


def _declaration(path: str | Path, evidence: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("licensed_audio_declaration_version") != PACK_VERSION:
        raise LicensedPackError("unsupported license declaration version")
    for key in ("pack_name", "publisher", "source_url", "license_url", "reviewed_by", "evidence_sha256"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise LicensedPackError("license declaration requires " + key)
    if data.get("usage_scope") != "embedded_game_only":
        raise LicensedPackError("usage_scope must be embedded_game_only")
    if data.get("standalone_redistribution") is not False:
        raise LicensedPackError("standalone_redistribution must explicitly be false")
    if not re.fullmatch(r"[a-f0-9]{64}", data["evidence_sha256"]):
        raise LicensedPackError("invalid evidence_sha256")
    if not Path(evidence).is_file() or sha256_file(evidence) != data["evidence_sha256"]:
        raise LicensedPackError("license evidence missing or SHA-256 mismatch")
    return data


def _zip_relative(name: str) -> PurePosixPath:
    if "\\" in name or name.startswith("/") or name.startswith("//") or re.match(r"^[a-zA-Z]:", name):
        raise LicensedPackError("unsafe ZIP member path")
    path = PurePosixPath(name)
    if any(part in ("", ".", "..") for part in name.rstrip("/").split("/")):
        raise LicensedPackError("unsafe ZIP member path")
    if not path.parts:
        raise LicensedPackError("empty ZIP member path")
    return path


def _validate_magic(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        head = fh.read(12)
    suffix = path.suffix.lower()
    meta: dict[str, Any] = {}
    if suffix == ".wav":
        if head[:4] != b"RIFF" or head[8:12] != b"WAVE":
            raise LicensedPackError("WAV signature mismatch")
        try:
            with wave.open(str(path), "rb") as wf:
                rate = wf.getframerate()
                if rate <= 0 or wf.getnchannels() <= 0:
                    raise LicensedPackError("invalid WAV metadata")
                meta = {"duration_ms": round(wf.getnframes() / rate * 1000),
                        "sample_rate": rate, "channels": wf.getnchannels()}
        except (wave.Error, EOFError) as exc:
            raise LicensedPackError("unsupported or corrupt WAV") from exc
    elif suffix == ".ogg" and head[:4] != b"OggS":
        raise LicensedPackError("OGG signature mismatch")
    elif suffix == ".mp3" and not (head.startswith(b"ID3") or
                                    (len(head) > 1 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)):
        raise LicensedPackError("MP3 signature mismatch")
    return meta


def _music_groups(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, str]] = {}
    for item in files:
        raw = PurePosixPath(item["relative_path"])
        if _SHORT_CUT.search(raw.stem):
            continue
        found = list(_TIER.finditer(raw.stem))
        if len(found) != 1:
            continue
        tier = found[0].group(1).lower()
        stem = _TIER.sub("", raw.stem)
        stem = _SLUG.sub("-", stem.lower()).strip("-")
        parent = _SLUG.sub("-", str(raw.parent).lower()).strip("-")
        key = parent + "/" + stem
        variants = groups.setdefault(key, {})
        if tier in variants:
            # A duplicated intensity is ambiguous: never guess which to play.
            variants[tier] = ""
        else:
            variants[tier] = item["relative_path"]
    result: list[dict[str, Any]] = []
    for key, tiers in sorted(groups.items()):
        if set(tiers) == {"low", "medium", "high"} and all(tiers.values()):
            track_id = "track-" + hashlib.sha256(key.encode()).hexdigest()[:12]
            result.append({"track_id": track_id, "key": key,
                           "tiers": {tier: tiers[tier] for tier in ("low", "medium", "high")}})
    return result


def _pack_dir(audio_root: str | Path, pack_id: str) -> Path:
    return Path(audio_root).resolve() / ".mgal" / "private-packs" / _slug(pack_id)


def verify_licensed_pack(audio_root: str | Path, pack_id: str,
                         license_evidence: str | Path) -> dict[str, Any]:
    folder = _pack_dir(audio_root, pack_id)
    data = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    if data.get("licensed_pack_version") != PACK_VERSION or data.get("pack_id") != _slug(pack_id):
        raise LicensedPackError("pack manifest version/id mismatch")
    declaration = data.get("license_declaration")
    if not isinstance(declaration, dict):
        raise LicensedPackError("missing license declaration")
    # Re-hash evidence without trusting a cached approval status.
    if not Path(license_evidence).is_file() or sha256_file(license_evidence) != declaration["evidence_sha256"]:
        raise LicensedPackError("license evidence missing or modified")
    if declaration.get("usage_scope") != "embedded_game_only" or declaration.get("standalone_redistribution") is not False:
        raise LicensedPackError("license scope disallows bridge")
    if not isinstance(data.get("files"), list) or not data["files"]:
        raise LicensedPackError("empty pack")
    seen: set[str] = set()
    for item in data["files"]:
        relative = item.get("relative_path")
        if not isinstance(relative, str):
            raise LicensedPackError("invalid file path")
        safe = _zip_relative(relative)
        if relative != safe.as_posix() or relative.casefold() in seen:
            raise LicensedPackError("duplicate/unsafe manifest path")
        seen.add(relative.casefold())
        path = (folder / "audio" / relative).resolve()
        if not path.is_relative_to((folder / "audio").resolve()) or not path.is_file() or path.is_symlink():
            raise LicensedPackError("audio missing or escaped private pack")
        if path.stat().st_size != item.get("bytes") or sha256_file(path) != item.get("sha256"):
            raise LicensedPackError("audio SHA-256/size drift: " + relative)
    if data.get("music_groups") != _music_groups(data["files"]):
        raise LicensedPackError("music group manifest changed")
    return data


def intake_licensed_zip(archive: str | Path, audio_root: str | Path,
                        declaration_path: str | Path, license_evidence: str | Path,
                        *, pack_id: str | None = None) -> dict[str, Any]:
    archive = Path(archive).resolve()
    declaration = _declaration(declaration_path, license_evidence)
    selected_id = _slug(pack_id or declaration["pack_name"])
    target = _pack_dir(audio_root, selected_id)
    zip_hash = sha256_file(archive)
    declaration_hash = hashlib.sha256(_json_bytes(declaration)).hexdigest()
    if target.exists():
        manifest = verify_licensed_pack(audio_root, selected_id, license_evidence)
        if manifest["archive_sha256"] != zip_hash or manifest["declaration_sha256"] != declaration_hash:
            raise LicensedPackError("pack_id already exists with different archive/declaration")
        return {"ok": True, "reused": True, "pack_id": selected_id,
                "manifest_path": str(target / "manifest.json"),
                "file_count": len(manifest["files"]), "music_group_count": len(manifest["music_groups"])}
    parent = target.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".mgal-pack-stage-", dir=parent))
    try:
        records: list[dict[str, Any]] = []
        seen: set[str] = set()
        with zipfile.ZipFile(archive) as zipped:
            infos = zipped.infolist()
            if len(infos) > MAX_MEMBERS or sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
                raise LicensedPackError("ZIP exceeds safety limits")
            for info in infos:
                rel = _zip_relative(info.filename)
                if stat.S_ISLNK(info.external_attr >> 16) or info.flag_bits & 1:
                    raise LicensedPackError("ZIP links/encrypted members are forbidden")
                if info.is_dir():
                    continue
                if rel.as_posix().casefold() in seen:
                    raise LicensedPackError("duplicate ZIP member")
                seen.add(rel.as_posix().casefold())
                if info.file_size > MAX_FILE_BYTES:
                    raise LicensedPackError("ZIP member too large")
                if rel.suffix.lower() not in AUDIO_SUFFIXES:
                    continue
                dst = staging / "audio" / rel.as_posix()
                dst.parent.mkdir(parents=True, exist_ok=True)
                digest = hashlib.sha256()
                size = 0
                with zipped.open(info) as source, dst.open("xb") as output:
                    while chunk := source.read(1024 * 1024):
                        size += len(chunk)
                        if size > MAX_FILE_BYTES or size > info.file_size:
                            raise LicensedPackError("ZIP member exceeds declared size")
                        digest.update(chunk)
                        output.write(chunk)
                if size != info.file_size:
                    raise LicensedPackError("ZIP member truncated")
                meta = _validate_magic(dst)
                records.append({"relative_path": rel.as_posix(), "sha256": digest.hexdigest(),
                                "bytes": size, "format": rel.suffix.lower().lstrip("."), **meta})
        if not records:
            raise LicensedPackError("ZIP has no supported audio files")
        records.sort(key=lambda row: row["relative_path"])
        groups = _music_groups(records)
        manifest = {"licensed_pack_version": PACK_VERSION, "pack_id": selected_id,
                    "archive_sha256": zip_hash, "declaration_sha256": declaration_hash,
                    "license_declaration": declaration,
                    "policy": {"raw_repository_upload": "forbidden",
                               "godot_copy": "explicit_opt_in",
                               "license_claim": "human_reviewed_not_independently_verified"},
                    "files": records, "music_groups": groups}
        _write_json(staging / "manifest.json", manifest)
        try:
            staging.rename(target)
        except FileExistsError as exc:
            raise LicensedPackError("pack destination appeared during intake") from exc
        verify_licensed_pack(audio_root, selected_id, license_evidence)
        return {"ok": True, "reused": False, "pack_id": selected_id,
                "manifest_path": str(target / "manifest.json"),
                "file_count": len(records), "music_group_count": len(groups)}
    finally:
        if staging.exists():
            shutil.rmtree(staging)
