from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from .evidence import EvidenceBundleError, verify_evidence_bundle
from .recipe import load_recipe
from .render import render_recipe


class EvidenceReplayError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_source(audio_root: Path, relative: str) -> Path:
    source = Path(relative)
    if source.is_absolute():
        raise EvidenceReplayError(f"source path must be relative: {relative}")

    root = audio_root.resolve()
    candidate = (root / source).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise EvidenceReplayError(f"source escapes audio root: {relative}") from exc

    if not candidate.is_file():
        raise EvidenceReplayError(f"source is missing: {relative}")
    return candidate


def _load_source_index(bundle_dir: Path) -> dict[str, Any]:
    path = bundle_dir / "source-index.json"
    if not path.is_file():
        raise EvidenceReplayError("source-index.json is missing")

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise EvidenceReplayError("source-index.json must contain an object")
    if data.get("source_index_version") != "0.1":
        raise EvidenceReplayError("unsupported source_index_version")

    sources = data.get("sources")
    count = data.get("source_count")
    if not isinstance(sources, list):
        raise EvidenceReplayError("source-index.sources must be a list")
    if not isinstance(count, int) or count != len(sources):
        raise EvidenceReplayError("source-index.source_count does not match sources")

    return data


def _verify_sources(
    source_index: dict[str, Any],
    audio_root: Path,
) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in source_index["sources"]:
        if not isinstance(item, dict):
            raise EvidenceReplayError("source-index entry must be an object")

        relative = item.get("relative_path")
        expected_hash = item.get("sha256")
        expected_bytes = item.get("bytes")
        if not isinstance(relative, str):
            raise EvidenceReplayError("source relative_path must be a string")
        if relative in seen:
            raise EvidenceReplayError(f"duplicate source path: {relative}")
        seen.add(relative)
        if not isinstance(expected_hash, str):
            raise EvidenceReplayError(f"{relative}: sha256 must be a string")
        if not isinstance(expected_bytes, int):
            raise EvidenceReplayError(f"{relative}: bytes must be an integer")

        source = _resolve_source(audio_root, relative)
        actual_bytes = source.stat().st_size
        if actual_bytes != expected_bytes:
            raise EvidenceReplayError(
                f"source byte size changed: {relative} "
                f"(expected {expected_bytes}, got {actual_bytes})"
            )

        actual_hash = _sha256(source)
        if actual_hash != expected_hash:
            raise EvidenceReplayError(f"source hash changed: {relative}")

        verified.append(
            {
                "relative_path": relative,
                "sha256": actual_hash,
                "bytes": actual_bytes,
            }
        )

    return verified


def replay_evidence_bundle(
    bundle_dir: str | Path,
    audio_root: str | Path,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    bundle_dir = Path(bundle_dir).resolve()
    audio_root = Path(audio_root).resolve()

    if not bundle_dir.is_dir():
        raise EvidenceReplayError(f"bundle directory does not exist: {bundle_dir}")
    if not audio_root.is_dir():
        raise EvidenceReplayError(f"audio root does not exist: {audio_root}")

    try:
        bundle_result = verify_evidence_bundle(bundle_dir)
    except EvidenceBundleError as exc:
        raise EvidenceReplayError(f"bundle verification failed: {exc}") from exc

    source_index = _load_source_index(bundle_dir)
    verified_sources = _verify_sources(source_index, audio_root)

    selected_recipe_path = bundle_dir / "selected-recipe.json"
    stored_output = bundle_dir / "output.wav"
    if not selected_recipe_path.is_file():
        raise EvidenceReplayError("selected-recipe.json is missing")
    if not stored_output.is_file():
        raise EvidenceReplayError("output.wav is missing")

    recipe = load_recipe(selected_recipe_path)

    requested_output: Path | None = None
    if output_path is not None:
        requested_output = Path(output_path).resolve()
        try:
            requested_output.relative_to(bundle_dir)
        except ValueError:
            pass
        else:
            raise EvidenceReplayError(
                "replay output must be outside the Evidence Bundle"
            )

    with tempfile.TemporaryDirectory(prefix="mgal-replay-") as temp_dir:
        replayed_output = Path(temp_dir) / "replayed-output.wav"
        render_recipe(
            recipe,
            selected_recipe_path,
            replayed_output,
            source_root=audio_root,
        )

        stored_hash = _sha256(stored_output)
        replayed_hash = _sha256(replayed_output)
        stored_bytes = stored_output.stat().st_size
        replayed_bytes = replayed_output.stat().st_size

        if stored_bytes != replayed_bytes:
            raise EvidenceReplayError(
                "replayed output byte size does not match stored output.wav"
            )
        if stored_hash != replayed_hash:
            raise EvidenceReplayError(
                "replayed output hash does not match stored output.wav"
            )

        if requested_output is not None:
            requested_output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(replayed_output, requested_output)

    return {
        "ok": True,
        "bundle_verified": bool(bundle_result.get("ok")),
        "files_verified": bundle_result.get("files_verified"),
        "sources_verified": len(verified_sources),
        "selected_candidate_id": bundle_result.get("selected_candidate_id"),
        "selected_recipe_id": recipe.id,
        "stored_output_sha256": stored_hash,
        "replayed_output_sha256": replayed_hash,
        "output_bytes": stored_bytes,
        "byte_identical": True,
        "replay_output": str(requested_output) if requested_output is not None else None,
    }
