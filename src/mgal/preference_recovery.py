from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .preference import (
    PreferenceEvidenceError,
    _replay_preference_data,
    load_preference_archive_metadata,
    preference_archive_root,
)


PREFERENCE_RELINK_VERSION = "0.1"


class PreferenceRecoveryError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_relative(root: Path, path: Path) -> str:
    root = root.resolve()
    path = path.resolve()
    try:
        return path.relative_to(root).as_posix()
    except ValueError as exc:
        raise PreferenceRecoveryError(
            f"path escapes preference search root: {path}"
        ) from exc


def _scan_by_size(search_root: Path) -> dict[int, list[Path]]:
    index: dict[int, list[Path]] = {}
    for path in sorted(search_root.rglob("*.wav")):
        if not path.is_file():
            continue
        index.setdefault(path.stat().st_size, []).append(path)
    return index


def preference_relink_root(
    audio_root: str | Path,
) -> Path:
    return (
        Path(audio_root).resolve()
        / ".mgal"
        / "preference-relinks"
    )


def default_preference_relink_path(
    audio_root: str | Path,
    archive_id: str,
) -> Path:
    return (
        preference_relink_root(audio_root)
        / f"{archive_id}.json"
    )


def recover_preference_sources(
    audio_root: str | Path,
    archive_id: str,
    search_root: str | Path,
) -> dict[str, Any]:
    audio_root = Path(audio_root).resolve()
    search_root = Path(search_root).resolve()
    if not search_root.is_dir():
        raise PreferenceRecoveryError(
            f"preference search root does not exist: {search_root}"
        )

    try:
        manifest, evidence = load_preference_archive_metadata(
            audio_root,
            archive_id,
        )
    except PreferenceEvidenceError as exc:
        raise PreferenceRecoveryError(
            f"preference archive metadata verification failed: {exc}"
        ) from exc

    source_index = evidence.get("source_index")
    if not isinstance(source_index, dict):
        raise PreferenceRecoveryError(
            "preference source_index must be an object"
        )
    sources = source_index.get("sources")
    count = source_index.get("source_count")
    if not isinstance(sources, list):
        raise PreferenceRecoveryError(
            "preference source_index.sources must be a list"
        )
    if not isinstance(count, int) or count != len(sources):
        raise PreferenceRecoveryError(
            "preference source_index.source_count does not match sources"
        )

    candidates_by_size = _scan_by_size(search_root)
    hash_cache: dict[Path, str] = {}

    def file_hash(path: Path) -> str:
        if path not in hash_cache:
            hash_cache[path] = _sha256(path)
        return hash_cache[path]

    mappings: list[dict[str, Any]] = []
    for item in sources:
        if not isinstance(item, dict):
            raise PreferenceRecoveryError(
                "preference source index entry must be an object"
            )
        logical = item.get("relative_path")
        expected_hash = item.get("sha256")
        expected_bytes = item.get("bytes")
        if not isinstance(logical, str) or not logical:
            raise PreferenceRecoveryError(
                "preference source relative_path must be a string"
            )
        if not isinstance(expected_hash, str):
            raise PreferenceRecoveryError(
                f"{logical}: preference source sha256 must be a string"
            )
        if not isinstance(expected_bytes, int):
            raise PreferenceRecoveryError(
                f"{logical}: preference source bytes must be an integer"
            )

        logical_path = Path(logical)
        if logical_path.is_absolute():
            raise PreferenceRecoveryError(
                f"preference source path must be relative: {logical}"
            )

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
            target = _safe_relative(search_root, direct)
            mappings.append(
                {
                    "source": logical,
                    "status": "direct",
                    "target": target,
                    "sha256": expected_hash,
                    "bytes": expected_bytes,
                    "matches": [target],
                }
            )
            continue

        matches: list[Path] = []
        for candidate in candidates_by_size.get(
            expected_bytes,
            [],
        ):
            if file_hash(candidate) == expected_hash:
                matches.append(candidate)

        relative_matches = [
            _safe_relative(search_root, path)
            for path in matches
        ]
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
        1
        for item in mappings
        if item["status"] in {"direct", "relinked"}
    )
    ambiguous = sum(
        1
        for item in mappings
        if item["status"] == "ambiguous"
    )
    missing = sum(
        1
        for item in mappings
        if item["status"] == "missing"
    )

    return {
        "preference_relink_version": PREFERENCE_RELINK_VERSION,
        "archive_id": archive_id,
        "archive_evidence_sha256": manifest[
            "evidence_sha256"
        ],
        "candidate_board_sha256": manifest[
            "candidate_board_sha256"
        ],
        "search_root": ".",
        "source_count": len(mappings),
        "resolved_count": resolved,
        "ambiguous_count": ambiguous,
        "missing_count": missing,
        "complete": ambiguous == 0 and missing == 0,
        "mappings": mappings,
    }


def write_preference_relink_map(
    audio_root: str | Path,
    archive_id: str,
    search_root: str | Path,
    output_path: str | Path | None = None,
) -> Path:
    audio_root = Path(audio_root).resolve()
    output = (
        Path(output_path).resolve()
        if output_path is not None
        else default_preference_relink_path(
            audio_root,
            archive_id,
        ).resolve()
    )

    archive_root = preference_archive_root(
        audio_root
    ).resolve()
    try:
        output.relative_to(archive_root)
    except ValueError:
        pass
    else:
        raise PreferenceRecoveryError(
            "preference relink map must be outside Preference Archive evidence directories"
        )

    payload = recover_preference_sources(
        audio_root,
        archive_id,
        search_root,
    )
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def load_preference_relink_map(
    path: str | Path,
    search_root: str | Path,
    audio_root: str | Path,
    archive_id: str,
) -> dict[str, Path]:
    path = Path(path).resolve()
    search_root = Path(search_root).resolve()
    audio_root = Path(audio_root).resolve()

    try:
        manifest, evidence = load_preference_archive_metadata(
            audio_root,
            archive_id,
        )
    except PreferenceEvidenceError as exc:
        raise PreferenceRecoveryError(
            f"preference archive metadata verification failed: {exc}"
        ) from exc

    data = json.loads(
        path.read_text(encoding="utf-8")
    )
    if not isinstance(data, dict):
        raise PreferenceRecoveryError(
            "preference relink map must contain an object"
        )
    if (
        data.get("preference_relink_version")
        != PREFERENCE_RELINK_VERSION
    ):
        raise PreferenceRecoveryError(
            "unsupported preference_relink_version"
        )
    if data.get("archive_id") != archive_id:
        raise PreferenceRecoveryError(
            "preference relink map belongs to a different archive"
        )
    if (
        data.get("archive_evidence_sha256")
        != manifest.get("evidence_sha256")
    ):
        raise PreferenceRecoveryError(
            "preference relink map evidence fingerprint mismatch"
        )
    if (
        data.get("candidate_board_sha256")
        != evidence.get("candidate_board_sha256")
    ):
        raise PreferenceRecoveryError(
            "preference relink map Candidate Board fingerprint mismatch"
        )
    if data.get("complete") is not True:
        raise PreferenceRecoveryError(
            "preference relink map is incomplete"
        )

    mappings = data.get("mappings")
    count = data.get("source_count")
    if not isinstance(mappings, list):
        raise PreferenceRecoveryError(
            "preference relink mappings must be a list"
        )
    if not isinstance(count, int) or count != len(mappings):
        raise PreferenceRecoveryError(
            "preference relink source_count does not match mappings"
        )

    expected_sources = {
        item["relative_path"]
        for item in evidence["source_index"]["sources"]
    }
    seen_sources: set[str] = set()
    resolved: dict[str, Path] = {}

    for item in mappings:
        if not isinstance(item, dict):
            raise PreferenceRecoveryError(
                "preference relink mapping must be an object"
            )
        source = item.get("source")
        status = item.get("status")
        target = item.get("target")
        expected_hash = item.get("sha256")
        expected_bytes = item.get("bytes")

        if not isinstance(source, str):
            raise PreferenceRecoveryError(
                "preference relink source must be a string"
            )
        if source in seen_sources:
            raise PreferenceRecoveryError(
                f"duplicate preference relink source: {source}"
            )
        seen_sources.add(source)

        if status not in {"direct", "relinked"}:
            raise PreferenceRecoveryError(
                f"{source}: unresolved preference relink status: {status}"
            )
        if not isinstance(target, str):
            raise PreferenceRecoveryError(
                f"{source}: preference relink target must be a string"
            )
        if not isinstance(expected_hash, str):
            raise PreferenceRecoveryError(
                f"{source}: preference relink sha256 must be a string"
            )
        if not isinstance(expected_bytes, int):
            raise PreferenceRecoveryError(
                f"{source}: preference relink bytes must be an integer"
            )

        target_path = Path(target)
        if target_path.is_absolute():
            raise PreferenceRecoveryError(
                f"{source}: preference relink target must be relative"
            )

        candidate = (
            search_root / target_path
        ).resolve()
        try:
            candidate.relative_to(search_root)
        except ValueError as exc:
            raise PreferenceRecoveryError(
                f"{source}: preference relink target escapes search root"
            ) from exc

        if not candidate.is_file():
            raise PreferenceRecoveryError(
                f"{source}: preference relink target is missing"
            )
        if candidate.stat().st_size != expected_bytes:
            raise PreferenceRecoveryError(
                f"{source}: preference relink target byte size changed"
            )
        if _sha256(candidate) != expected_hash:
            raise PreferenceRecoveryError(
                f"{source}: preference relink target hash changed"
            )

        resolved[source] = candidate

    if seen_sources != expected_sources:
        raise PreferenceRecoveryError(
            "preference relink source set does not match archive source index"
        )

    return resolved


def replay_preference_archive_portable(
    audio_root: str | Path,
    archive_id: str,
    *,
    search_root: str | Path | None = None,
    relink_map_path: str | Path | None = None,
) -> dict[str, Any]:
    audio_root = Path(audio_root).resolve()
    source_root = (
        Path(search_root).resolve()
        if search_root is not None
        else audio_root
    )

    try:
        _, evidence = load_preference_archive_metadata(
            audio_root,
            archive_id,
        )
    except PreferenceEvidenceError as exc:
        raise PreferenceRecoveryError(
            f"preference archive metadata verification failed: {exc}"
        ) from exc

    if relink_map_path is not None:
        overrides = load_preference_relink_map(
            relink_map_path,
            source_root,
            audio_root,
            archive_id,
        )
        try:
            replay = _replay_preference_data(
                evidence,
                source_root,
                source_overrides=overrides,
            )
        except PreferenceEvidenceError as exc:
            raise PreferenceRecoveryError(
                f"preference replay failed: {exc}"
            ) from exc
        replay["archive_id"] = archive_id
        replay["source_status"] = "relinked"
        replay["relink_map"] = str(
            Path(relink_map_path).resolve()
        )
        return replay

    try:
        replay = _replay_preference_data(
            evidence,
            source_root,
        )
    except PreferenceEvidenceError as direct_error:
        default_map = default_preference_relink_path(
            audio_root,
            archive_id,
        )
        if not default_map.is_file():
            raise PreferenceRecoveryError(
                f"preference replay sources unresolved: {direct_error}"
            ) from direct_error

        overrides = load_preference_relink_map(
            default_map,
            source_root,
            audio_root,
            archive_id,
        )
        try:
            replay = _replay_preference_data(
                evidence,
                source_root,
                source_overrides=overrides,
            )
        except PreferenceEvidenceError as exc:
            raise PreferenceRecoveryError(
                f"preference replay failed after relink: {exc}"
            ) from exc
        replay["source_status"] = "relinked"
        replay["relink_map"] = str(default_map)
    else:
        replay["source_status"] = "direct"
        replay["relink_map"] = None

    replay["archive_id"] = archive_id
    return replay


def list_portable_preference_archives(
    audio_root: str | Path,
) -> list[dict[str, Any]]:
    audio_root = Path(audio_root).resolve()
    root = preference_archive_root(audio_root)
    if not root.is_dir():
        return []

    result: list[dict[str, Any]] = []
    for manifest_path in sorted(
        root.glob("*/manifest.json")
    ):
        archive_id = manifest_path.parent.name
        try:
            manifest, _ = load_preference_archive_metadata(
                audio_root,
                archive_id,
            )
        except (
            OSError,
            json.JSONDecodeError,
            PreferenceEvidenceError,
        ) as exc:
            result.append(
                {
                    "archive_id": archive_id,
                    "ok": False,
                    "recoverable": False,
                    "error": str(exc),
                }
            )
            continue

        try:
            replay = replay_preference_archive_portable(
                audio_root,
                archive_id,
            )
        except (
            OSError,
            json.JSONDecodeError,
            PreferenceEvidenceError,
            PreferenceRecoveryError,
        ) as exc:
            result.append(
                {
                    "archive_id": archive_id,
                    "archive_evidence_sha256": manifest[
                        "evidence_sha256"
                    ],
                    "ok": False,
                    "recoverable": True,
                    "source_status": "unresolved",
                    "error": str(exc),
                    "candidate_count": manifest[
                        "candidate_count"
                    ],
                    "pair_count": manifest[
                        "pair_count"
                    ],
                    "source_count": manifest[
                        "source_count"
                    ],
                    "winner_candidate_id": manifest[
                        "winner_candidate_id"
                    ],
                    "tie": manifest["tie"],
                    "applied_candidate_id": manifest[
                        "applied_candidate_id"
                    ],
                }
            )
            continue

        result.append(
            {
                "archive_id": archive_id,
                "archive_evidence_sha256": manifest[
                    "evidence_sha256"
                ],
                "ok": True,
                "recoverable": False,
                "source_status": replay[
                    "source_status"
                ],
                "candidate_count": manifest[
                    "candidate_count"
                ],
                "pair_count": manifest[
                    "pair_count"
                ],
                "source_count": manifest[
                    "source_count"
                ],
                "winner_candidate_id": manifest[
                    "winner_candidate_id"
                ],
                "tie": manifest["tie"],
                "applied_candidate_id": manifest[
                    "applied_candidate_id"
                ],
            }
        )

    return result
