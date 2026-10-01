from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

from .candidate import CandidateSnapshot, load_candidate_board
from .evidence import EvidenceBundleError, verify_evidence_bundle
from .recipe import load_recipe
from .recovery import SourceRecoveryError, load_relink_map
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


def _expected_sources_from_board(
    bundle_dir: Path,
) -> tuple[set[str], CandidateSnapshot]:
    board = load_candidate_board(bundle_dir / "candidate-board.json")
    if board.selected_candidate_id is None:
        raise EvidenceReplayError("bundle Candidate Board has no selected candidate")

    selected_candidate = next(
        (
            candidate
            for candidate in board.candidates
            if candidate.id == board.selected_candidate_id
        ),
        None,
    )
    if selected_candidate is None:
        raise EvidenceReplayError("selected candidate is missing from Candidate Board")

    expected: set[str] = set()
    recipes = [board.base_recipe] + [candidate.recipe for candidate in board.candidates]
    for recipe in recipes:
        for layer in recipe.layers:
            expected.add(layer.source)

    return expected, selected_candidate


def _verify_sources(
    source_index: dict[str, Any],
    audio_root: Path,
    expected_sources: set[str],
    source_overrides: dict[str, Path] | None = None,
) -> list[dict[str, Any]]:
    verified: list[dict[str, Any]] = []
    seen: set[str] = set()

    indexed_paths: set[str] = set()

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
        indexed_paths.add(relative)
        if not isinstance(expected_hash, str):
            raise EvidenceReplayError(f"{relative}: sha256 must be a string")
        if not isinstance(expected_bytes, int):
            raise EvidenceReplayError(f"{relative}: bytes must be an integer")

        if source_overrides is not None and relative in source_overrides:
            source = source_overrides[relative].resolve()
        else:
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

    if indexed_paths != expected_sources:
        missing = sorted(expected_sources - indexed_paths)
        unexpected = sorted(indexed_paths - expected_sources)
        details: list[str] = []
        if missing:
            details.append("missing=" + ",".join(missing))
        if unexpected:
            details.append("unexpected=" + ",".join(unexpected))
        raise EvidenceReplayError(
            "source-index paths do not match Candidate Board: " + "; ".join(details)
        )

    return verified


def replay_evidence_bundle(
    bundle_dir: str | Path,
    audio_root: str | Path,
    output_path: str | Path | None = None,
    relink_map_path: str | Path | None = None,
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

    expected_sources, selected_candidate = _expected_sources_from_board(bundle_dir)
    board_selected_id = selected_candidate.id

    manifest_selected_id = bundle_result.get("selected_candidate_id")
    if manifest_selected_id != board_selected_id:
        raise EvidenceReplayError(
            "manifest selected candidate does not match Candidate Board"
        )

    source_overrides: dict[str, Path] | None = None
    if relink_map_path is not None:
        try:
            source_overrides = load_relink_map(relink_map_path, audio_root)
        except SourceRecoveryError as exc:
            raise EvidenceReplayError(f"relink map validation failed: {exc}") from exc
        if set(source_overrides) != expected_sources:
            missing = sorted(expected_sources - set(source_overrides))
            unexpected = sorted(set(source_overrides) - expected_sources)
            details: list[str] = []
            if missing:
                details.append("missing=" + ",".join(missing))
            if unexpected:
                details.append("unexpected=" + ",".join(unexpected))
            raise EvidenceReplayError(
                "relink map source set does not match Candidate Board: "
                + "; ".join(details)
            )

    source_index = _load_source_index(bundle_dir)
    verified_sources = _verify_sources(
        source_index,
        audio_root,
        expected_sources,
        source_overrides=source_overrides,
    )

    selected_recipe_path = bundle_dir / "selected-recipe.json"
    stored_output = bundle_dir / "output.wav"
    if not selected_recipe_path.is_file():
        raise EvidenceReplayError("selected-recipe.json is missing")
    if not stored_output.is_file():
        raise EvidenceReplayError("output.wav is missing")

    recipe = load_recipe(selected_recipe_path)
    if recipe.id != board_selected_id:
        raise EvidenceReplayError(
            "selected-recipe.json does not match selected Candidate Board ID"
        )
    if recipe != selected_candidate.recipe:
        raise EvidenceReplayError(
            "selected-recipe.json does not match selected Candidate Board recipe"
        )

    decision_path = bundle_dir / "decision.json"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    if not isinstance(decision, dict):
        raise EvidenceReplayError("decision.json must contain an object")
    if decision.get("selected_candidate_id") != board_selected_id:
        raise EvidenceReplayError(
            "decision.json does not match selected Candidate Board ID"
        )
    if decision.get("status") != "selected":
        raise EvidenceReplayError("decision.json status must be selected")
    if decision.get("reason") != selected_candidate.decision.reason:
        raise EvidenceReplayError(
            "decision.json reason does not match selected Candidate Board decision"
        )
    if decision.get("parent_recipe_id") != selected_candidate.parent_recipe_id:
        raise EvidenceReplayError(
            "decision.json parent does not match selected Candidate Board"
        )
    if decision.get("revision") != selected_candidate.revision:
        raise EvidenceReplayError(
            "decision.json revision does not match selected Candidate Board"
        )

    expected_lineage = [
        {
            "from_recipe_id": event.from_recipe_id,
            "action": event.action,
            "revision": event.revision,
        }
        for event in selected_candidate.lineage
    ]
    if decision.get("lineage") != expected_lineage:
        raise EvidenceReplayError(
            "decision.json lineage does not match selected Candidate Board"
        )

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
            source_overrides=source_overrides,
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
        "relink_map_used": str(Path(relink_map_path).resolve()) if relink_map_path is not None else None,
    }
