from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .evidence import EvidenceBundleError, verify_evidence_bundle


class SourceRecoveryError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_source_index(bundle_dir: Path) -> dict[str, Any]:
    path = bundle_dir / "source-index.json"
    if not path.is_file():
        raise SourceRecoveryError("source-index.json is missing")

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SourceRecoveryError("source-index.json must contain an object")
    if data.get("source_index_version") != "0.1":
        raise SourceRecoveryError("unsupported source_index_version")

    sources = data.get("sources")
    count = data.get("source_count")
    if not isinstance(sources, list):
        raise SourceRecoveryError("source-index.sources must be a list")
    if not isinstance(count, int) or count != len(sources):
        raise SourceRecoveryError("source-index.source_count does not match sources")
    return data


def _safe_relative(root: Path, path: Path) -> str:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        return resolved_path.relative_to(resolved_root).as_posix()
    except ValueError as exc:
        raise SourceRecoveryError(f"path escapes search root: {path}") from exc


def _scan_by_size(search_root: Path) -> dict[int, list[Path]]:
    index: dict[int, list[Path]] = {}
    for path in sorted(search_root.rglob("*.wav")):
        if not path.is_file():
            continue
        index.setdefault(path.stat().st_size, []).append(path)
    return index


def recover_sources(
    bundle_dir: str | Path,
    search_root: str | Path,
) -> dict[str, Any]:
    bundle_dir = Path(bundle_dir).resolve()
    search_root = Path(search_root).resolve()

    if not bundle_dir.is_dir():
        raise SourceRecoveryError(f"bundle directory does not exist: {bundle_dir}")
    if not search_root.is_dir():
        raise SourceRecoveryError(f"search root does not exist: {search_root}")

    try:
        verify_evidence_bundle(bundle_dir)
    except EvidenceBundleError as exc:
        raise SourceRecoveryError(f"bundle verification failed: {exc}") from exc

    source_index = _load_source_index(bundle_dir)
    manifest_hash = _sha256(bundle_dir / "manifest.json")
    candidates_by_size = _scan_by_size(search_root)
    hash_cache: dict[Path, str] = {}
    mappings: list[dict[str, Any]] = []

    def file_hash(path: Path) -> str:
        if path not in hash_cache:
            hash_cache[path] = _sha256(path)
        return hash_cache[path]

    for item in source_index["sources"]:
        if not isinstance(item, dict):
            raise SourceRecoveryError("source-index entry must be an object")

        logical = item.get("relative_path")
        expected_hash = item.get("sha256")
        expected_bytes = item.get("bytes")
        if not isinstance(logical, str):
            raise SourceRecoveryError("source relative_path must be a string")
        if not isinstance(expected_hash, str):
            raise SourceRecoveryError(f"{logical}: sha256 must be a string")
        if not isinstance(expected_bytes, int):
            raise SourceRecoveryError(f"{logical}: bytes must be an integer")

        logical_path = Path(logical)
        if logical_path.is_absolute():
            raise SourceRecoveryError(f"logical source path must be relative: {logical}")

        direct = (search_root / logical_path).resolve()
        direct_valid = False
        try:
            direct.relative_to(search_root)
        except ValueError:
            direct_valid = False
        else:
            if (
                direct.is_file()
                and direct.stat().st_size == expected_bytes
                and file_hash(direct) == expected_hash
            ):
                direct_valid = True

        if direct_valid:
            mappings.append(
                {
                    "source": logical,
                    "status": "direct",
                    "target": _safe_relative(search_root, direct),
                    "sha256": expected_hash,
                    "bytes": expected_bytes,
                    "matches": [_safe_relative(search_root, direct)],
                }
            )
            continue

        matches: list[Path] = []
        for candidate in candidates_by_size.get(expected_bytes, []):
            if file_hash(candidate) == expected_hash:
                matches.append(candidate)

        relative_matches = [_safe_relative(search_root, path) for path in matches]

        if len(matches) == 1:
            mappings.append(
                {
                    "source": logical,
                    "status": "relinked",
                    "target": relative_matches[0],
                    "sha256": expected_hash,
                    "bytes": expected_bytes,
                    "matches": relative_matches,
                }
            )
        elif len(matches) > 1:
            mappings.append(
                {
                    "source": logical,
                    "status": "ambiguous",
                    "target": None,
                    "sha256": expected_hash,
                    "bytes": expected_bytes,
                    "matches": relative_matches,
                }
            )
        else:
            mappings.append(
                {
                    "source": logical,
                    "status": "missing",
                    "target": None,
                    "sha256": expected_hash,
                    "bytes": expected_bytes,
                    "matches": [],
                }
            )

    resolved = sum(
        1 for item in mappings if item["status"] in {"direct", "relinked"}
    )
    ambiguous = sum(1 for item in mappings if item["status"] == "ambiguous")
    missing = sum(1 for item in mappings if item["status"] == "missing")

    return {
        "relink_map_version": "0.1",
        "bundle_manifest_sha256": manifest_hash,
        "search_root": ".",
        "source_count": len(mappings),
        "resolved_count": resolved,
        "ambiguous_count": ambiguous,
        "missing_count": missing,
        "complete": ambiguous == 0 and missing == 0,
        "mappings": mappings,
    }


def write_relink_map(
    bundle_dir: str | Path,
    search_root: str | Path,
    output_path: str | Path,
) -> Path:
    bundle_dir = Path(bundle_dir).resolve()
    output_path = Path(output_path).resolve()
    try:
        output_path.relative_to(bundle_dir)
    except ValueError:
        pass
    else:
        raise SourceRecoveryError(
            "relink map output must be outside the Evidence Bundle"
        )

    payload = recover_sources(bundle_dir, search_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path


def load_relink_map(
    path: str | Path,
    search_root: str | Path,
    bundle_dir: str | Path | None = None,
) -> dict[str, Path]:
    path = Path(path).resolve()
    search_root = Path(search_root).resolve()

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SourceRecoveryError("relink map must contain an object")
    if data.get("relink_map_version") != "0.1":
        raise SourceRecoveryError("unsupported relink_map_version")

    manifest_hash = data.get("bundle_manifest_sha256")
    if not isinstance(manifest_hash, str):
        raise SourceRecoveryError("bundle_manifest_sha256 must be a string")
    if bundle_dir is not None:
        bundle_path = Path(bundle_dir).resolve()
        current_manifest = bundle_path / "manifest.json"
        if not current_manifest.is_file():
            raise SourceRecoveryError("bundle manifest.json is missing")
        if _sha256(current_manifest) != manifest_hash:
            raise SourceRecoveryError("relink map belongs to a different Evidence Bundle")

    if data.get("complete") is not True:
        raise SourceRecoveryError("relink map is incomplete")

    mappings = data.get("mappings")
    count = data.get("source_count")
    if not isinstance(mappings, list):
        raise SourceRecoveryError("relink map mappings must be a list")
    if not isinstance(count, int) or count != len(mappings):
        raise SourceRecoveryError("relink map source_count does not match mappings")

    resolved: dict[str, Path] = {}
    for item in mappings:
        if not isinstance(item, dict):
            raise SourceRecoveryError("relink mapping must be an object")

        source = item.get("source")
        target = item.get("target")
        status = item.get("status")
        expected_hash = item.get("sha256")
        expected_bytes = item.get("bytes")

        if not isinstance(source, str):
            raise SourceRecoveryError("relink source must be a string")
        if source in resolved:
            raise SourceRecoveryError(f"duplicate relink source: {source}")
        if status not in {"direct", "relinked"}:
            raise SourceRecoveryError(f"{source}: unresolved relink status: {status}")
        if not isinstance(target, str):
            raise SourceRecoveryError(f"{source}: relink target must be a string")
        if not isinstance(expected_hash, str):
            raise SourceRecoveryError(f"{source}: relink sha256 must be a string")
        if not isinstance(expected_bytes, int):
            raise SourceRecoveryError(f"{source}: relink bytes must be an integer")

        target_path = Path(target)
        if target_path.is_absolute():
            raise SourceRecoveryError(f"{source}: relink target must be relative")

        candidate = (search_root / target_path).resolve()
        try:
            candidate.relative_to(search_root)
        except ValueError as exc:
            raise SourceRecoveryError(
                f"{source}: relink target escapes search root"
            ) from exc

        if not candidate.is_file():
            raise SourceRecoveryError(f"{source}: relink target is missing")
        if candidate.stat().st_size != expected_bytes:
            raise SourceRecoveryError(f"{source}: relink target byte size changed")
        if _sha256(candidate) != expected_hash:
            raise SourceRecoveryError(f"{source}: relink target hash changed")

        resolved[source] = candidate

    return resolved
