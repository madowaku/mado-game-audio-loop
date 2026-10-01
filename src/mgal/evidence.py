from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from .audio import read_wav_metadata
from .candidate import CandidateBoard, CandidateSnapshot, load_candidate_board
from .recipe import Recipe
from .render import render_recipe


class EvidenceBundleError(ValueError):
    pass


def _recipe_to_dict(recipe: Recipe) -> dict[str, Any]:
    return {
        "recipe_version": recipe.recipe_version,
        "id": recipe.id,
        "intent": recipe.intent,
        "layers": [
            {
                "source": layer.source,
                "gain": layer.gain,
                "offset_ms": layer.offset_ms,
            }
            for layer in recipe.layers
        ],
        "processing": {
            "normalize": recipe.normalize,
            "fade_out_ms": recipe.fade_out_ms,
        },
    }


def _candidate_to_dict(candidate: CandidateSnapshot) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "label": candidate.label,
        "parent_recipe_id": candidate.parent_recipe_id,
        "revision": candidate.revision,
        "lineage": [asdict(event) for event in candidate.lineage],
        "recipe": _recipe_to_dict(candidate.recipe),
        "decision": asdict(candidate.decision),
    }


def _board_to_dict(board: CandidateBoard) -> dict[str, Any]:
    return {
        "candidate_board_version": board.candidate_board_version,
        "intent": board.intent,
        "base_recipe": _recipe_to_dict(board.base_recipe),
        "active_candidate_id": board.active_candidate_id,
        "selected_candidate_id": board.selected_candidate_id,
        "candidates": [_candidate_to_dict(candidate) for candidate in board.candidates],
    }


def _json_bytes(payload: object) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_json_bytes(payload))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_source(audio_root: Path, source: str) -> Path:
    source_path = Path(source)
    if source_path.is_absolute():
        raise EvidenceBundleError(f"absolute source paths are not portable: {source}")

    root = audio_root.resolve()
    candidate = (root / source_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise EvidenceBundleError(f"source escapes audio root: {source}") from exc

    if not candidate.is_file():
        raise EvidenceBundleError(f"source does not exist: {source}")
    return candidate


def _source_index(board: CandidateBoard, audio_root: Path) -> dict[str, Any]:
    source_names: set[str] = set()
    recipes = [board.base_recipe] + [candidate.recipe for candidate in board.candidates]
    for recipe in recipes:
        for layer in recipe.layers:
            source_names.add(layer.source)

    sources: list[dict[str, Any]] = []
    for source in sorted(source_names):
        path = _resolve_source(audio_root, source)
        metadata = read_wav_metadata(path)
        sources.append(
            {
                "relative_path": source,
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
                "duration_ms": metadata.duration_ms,
                "sample_rate": metadata.sample_rate,
                "channels": metadata.channels,
                "sample_width": metadata.sample_width,
                "frames": metadata.frames,
            }
        )

    return {
        "source_index_version": "0.1",
        "source_count": len(sources),
        "sources": sources,
    }


def _selected_candidate(board: CandidateBoard) -> CandidateSnapshot:
    if board.selected_candidate_id is None:
        raise EvidenceBundleError(
            "Candidate Board must have one selected candidate before bundling"
        )
    for candidate in board.candidates:
        if candidate.id == board.selected_candidate_id:
            return candidate
    raise EvidenceBundleError("selected candidate is missing from board")


def build_evidence_bundle(
    board_path: str | Path,
    audio_root: str | Path,
    output_dir: str | Path,
) -> Path:
    board_path = Path(board_path).resolve()
    audio_root = Path(audio_root).resolve()
    output_dir = Path(output_dir).resolve()

    board = load_candidate_board(board_path)
    selected = _selected_candidate(board)

    if output_dir.exists() and any(output_dir.iterdir()):
        raise EvidenceBundleError(f"output directory is not empty: {output_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    candidates_dir = output_dir / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)

    _write_json(output_dir / "intent.json", {"intent": board.intent})
    _write_json(output_dir / "source-index.json", _source_index(board, audio_root))
    _write_json(output_dir / "candidate-board.json", _board_to_dict(board))

    for candidate in board.candidates:
        filename = f"{candidate.label.lower()}-{candidate.id}.json"
        _write_json(candidates_dir / filename, _recipe_to_dict(candidate.recipe))

    _write_json(output_dir / "selected-recipe.json", _recipe_to_dict(selected.recipe))
    _write_json(
        output_dir / "decision.json",
        {
            "selected_candidate_id": selected.id,
            "label": selected.label,
            "status": selected.decision.status,
            "reason": selected.decision.reason,
            "parent_recipe_id": selected.parent_recipe_id,
            "revision": selected.revision,
            "lineage": [asdict(event) for event in selected.lineage],
        },
    )

    render_recipe(
        selected.recipe,
        board_path,
        output_dir / "output.wav",
        source_root=audio_root,
    )

    payload_paths = sorted(
        path
        for path in output_dir.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    )
    manifest_files = [
        {
            "path": path.relative_to(output_dir).as_posix(),
            "sha256": _sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in payload_paths
    ]

    manifest = {
        "evidence_bundle_version": "0.1",
        "base_recipe_id": board.base_recipe.id,
        "selected_candidate_id": selected.id,
        "file_count": len(manifest_files),
        "files": manifest_files,
    }
    _write_json(output_dir / "manifest.json", manifest)
    return output_dir


def verify_evidence_bundle(bundle_dir: str | Path) -> dict[str, Any]:
    bundle_dir = Path(bundle_dir).resolve()
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.is_file():
        raise EvidenceBundleError("manifest.json is missing")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise EvidenceBundleError("manifest must be an object")
    if manifest.get("evidence_bundle_version") != "0.1":
        raise EvidenceBundleError("unsupported evidence_bundle_version")

    files = manifest.get("files")
    if not isinstance(files, list):
        raise EvidenceBundleError("manifest.files must be a list")

    verified = 0
    for item in files:
        if not isinstance(item, dict):
            raise EvidenceBundleError("manifest file entry must be an object")
        relative = item.get("path")
        expected_hash = item.get("sha256")
        expected_bytes = item.get("bytes")
        if not isinstance(relative, str):
            raise EvidenceBundleError("manifest path must be a string")
        if not isinstance(expected_hash, str):
            raise EvidenceBundleError(f"{relative}: sha256 must be a string")
        if not isinstance(expected_bytes, int):
            raise EvidenceBundleError(f"{relative}: bytes must be an integer")

        candidate = (bundle_dir / relative).resolve()
        try:
            candidate.relative_to(bundle_dir)
        except ValueError as exc:
            raise EvidenceBundleError(f"manifest path escapes bundle: {relative}") from exc

        if not candidate.is_file():
            raise EvidenceBundleError(f"bundle file is missing: {relative}")
        if candidate.stat().st_size != expected_bytes:
            raise EvidenceBundleError(f"bundle file size changed: {relative}")
        if _sha256(candidate) != expected_hash:
            raise EvidenceBundleError(f"bundle file hash changed: {relative}")
        verified += 1

    return {
        "ok": True,
        "files_verified": verified,
        "selected_candidate_id": manifest.get("selected_candidate_id"),
    }
