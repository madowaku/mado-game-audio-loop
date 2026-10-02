from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Any

from .normalizer import (
    CANONICAL_PROFILE_ID,
    normalize_provider_result_file,
)
from .provider import (
    ProviderResult,
    provider_result_to_dict,
    write_provider_result,
)
from .provenance import (
    ProvenanceLedgerError,
    merge_provenance_ledgers,
    source_sha256,
    validate_provenance_entry,
)


INTAKE_VERSION = "0.1"


class ProviderIntakeError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "intake"


def _default_intake_id(
    result_path: Path,
    result: ProviderResult,
) -> str:
    result_hash = _sha256(result_path)
    return "-".join(
        [
            _slug(result.request.request_id),
            _slug(result.provider_id),
            result_hash[:8],
        ]
    )


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _workspace_entry(
    candidate: Any,
    *,
    artifact_root: Path,
    audio_root: Path,
) -> dict[str, Any]:
    physical = (artifact_root / candidate.relative_path).resolve()
    try:
        relative = physical.relative_to(audio_root).as_posix()
    except ValueError as exc:
        raise ProviderIntakeError(
            "normalized candidate is outside the audio workspace"
        ) from exc

    entry = json.loads(
        json.dumps(candidate.provenance, ensure_ascii=False)
    )
    entry["path_hint"] = relative
    try:
        validate_provenance_entry(entry)
    except ProvenanceLedgerError as exc:
        raise ProviderIntakeError(
            f"normalized candidate provenance is invalid: {exc}"
        ) from exc
    return entry


def _workspace_ledger(
    result: ProviderResult,
    audio_root: Path,
) -> dict[str, Any]:
    artifact_root = Path(result.artifact_root).resolve()
    entries = [
        _workspace_entry(
            candidate,
            artifact_root=artifact_root,
            audio_root=audio_root,
        )
        for candidate in result.candidates
    ]
    return {
        "provenance_ledger_version": "0.1",
        "entry_count": len(entries),
        "entries": entries,
    }


def _manifest_candidate(
    candidate: Any,
    *,
    artifact_root: Path,
    audio_root: Path,
) -> dict[str, Any]:
    physical = (artifact_root / candidate.relative_path).resolve()
    relative = physical.relative_to(audio_root).as_posix()
    provenance = candidate.provenance
    generation = provenance.get("generation")
    normalization = provenance.get("normalization")

    return {
        "candidate_id": candidate.candidate_id,
        "relative_path": relative,
        "source_id": candidate.source_id,
        "sha256": candidate.sha256,
        "bytes": candidate.bytes,
        "source_type": provenance.get("source_type"),
        "generation": generation,
        "normalization": normalization,
    }


def verify_intake_manifest(
    audio_root: str | Path,
    manifest_path: str | Path,
) -> dict[str, Any]:
    audio_root = Path(audio_root).resolve()
    manifest_path = Path(manifest_path).resolve()

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ProviderIntakeError("intake manifest must contain an object")
    if data.get("intake_version") != INTAKE_VERSION:
        raise ProviderIntakeError("unsupported intake_version")

    candidates = data.get("candidates")
    count = data.get("candidate_count")
    if not isinstance(candidates, list):
        raise ProviderIntakeError("intake candidates must be a list")
    if not isinstance(count, int) or count != len(candidates):
        raise ProviderIntakeError(
            "intake candidate_count does not match candidates"
        )

    seen: set[str] = set()
    for item in candidates:
        if not isinstance(item, dict):
            raise ProviderIntakeError("intake candidate must be an object")
        relative = item.get("relative_path")
        expected_hash = item.get("sha256")
        expected_bytes = item.get("bytes")
        if not isinstance(relative, str) or not relative:
            raise ProviderIntakeError(
                "intake candidate relative_path must be a string"
            )
        if relative in seen:
            raise ProviderIntakeError(
                f"duplicate intake relative_path: {relative}"
            )
        seen.add(relative)

        path = (audio_root / relative).resolve()
        try:
            path.relative_to(audio_root)
        except ValueError as exc:
            raise ProviderIntakeError(
                f"intake path escapes audio root: {relative}"
            ) from exc
        if not path.is_file():
            raise ProviderIntakeError(
                f"intake candidate is missing: {relative}"
            )
        if not isinstance(expected_bytes, int) or path.stat().st_size != expected_bytes:
            raise ProviderIntakeError(
                f"intake candidate byte size changed: {relative}"
            )
        if not isinstance(expected_hash, str) or source_sha256(path) != expected_hash:
            raise ProviderIntakeError(
                f"intake candidate hash changed: {relative}"
            )

    return {
        "ok": True,
        "intake_id": data.get("intake_id"),
        "provider_id": data.get("provider_id"),
        "candidate_count": len(candidates),
    }


def build_provider_intake(
    result_path: str | Path,
    audio_root: str | Path,
    *,
    intake_id: str | None = None,
) -> dict[str, Any]:
    result_path = Path(result_path).resolve()
    audio_root = Path(audio_root).resolve()
    if not result_path.is_file():
        raise ProviderIntakeError(
            f"Provider Result does not exist: {result_path}"
        )

    audio_root.mkdir(parents=True, exist_ok=True)

    from .provider import load_provider_result

    raw_result = load_provider_result(result_path)
    resolved_id = _slug(
        intake_id or _default_intake_id(result_path, raw_result)
    )

    metadata_root = audio_root / ".mgal"
    session_root = metadata_root / "intakes" / resolved_id
    manifest_path = session_root / "manifest.json"
    result_hash = _sha256(result_path)

    if manifest_path.is_file():
        existing = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
        if (
            isinstance(existing, dict)
            and existing.get("provider_result_sha256") == result_hash
        ):
            verified = verify_intake_manifest(
                audio_root,
                manifest_path,
            )
            return {
                **verified,
                "manifest_path": str(manifest_path),
                "workspace_ledger": str(
                    metadata_root / "provenance-ledger.json"
                ),
                "reused": True,
            }
        raise ProviderIntakeError(
            f"intake id already exists for different input: {resolved_id}"
        )

    canonical_root = audio_root / "incoming" / resolved_id
    if canonical_root.exists() and any(canonical_root.iterdir()):
        raise ProviderIntakeError(
            f"intake canonical directory is not empty: {canonical_root}"
        )

    created_session = False
    created_canonical = False

    try:
        normalized = normalize_provider_result_file(
            result_path,
            canonical_root,
        )
        created_canonical = True

        session_root.mkdir(parents=True, exist_ok=False)
        created_session = True

        normalized_result_path = session_root / "provider-result.json"
        write_provider_result(
            normalized,
            normalized_result_path,
        )

        intake_ledger_path = session_root / "provenance-ledger.json"
        intake_ledger = _workspace_ledger(
            normalized,
            audio_root,
        )
        _write_json(intake_ledger_path, intake_ledger)

        workspace_ledger_path = metadata_root / "provenance-ledger.json"

        artifact_root = Path(normalized.artifact_root).resolve()
        candidates = [
            _manifest_candidate(
                candidate,
                artifact_root=artifact_root,
                audio_root=audio_root,
            )
            for candidate in normalized.candidates
        ]

        manifest = {
            "intake_version": INTAKE_VERSION,
            "intake_id": resolved_id,
            "provider_result_sha256": result_hash,
            "provider_id": raw_result.provider_id,
            "provider_kind": raw_result.provider_kind,
            "request": {
                "request_id": raw_result.request.request_id,
                "intent": raw_result.request.intent,
                "count": raw_result.request.count,
                "hints": list(raw_result.request.hints),
                "duration_ms": raw_result.request.duration_ms,
                "seed": raw_result.request.seed,
            },
            "normalization_profile_id": CANONICAL_PROFILE_ID,
            "normalized_provider_result_sha256": _sha256(
                normalized_result_path
            ),
            "candidate_count": len(candidates),
            "candidates": candidates,
        }
        _write_json(manifest_path, manifest)
        verify_intake_manifest(audio_root, manifest_path)

        if workspace_ledger_path.is_file():
            merge_provenance_ledgers(
                [workspace_ledger_path, intake_ledger_path],
                workspace_ledger_path,
            )
        else:
            workspace_ledger_path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            shutil.copyfile(
                intake_ledger_path,
                workspace_ledger_path,
            )

        return {
            "ok": True,
            "intake_id": resolved_id,
            "provider_id": raw_result.provider_id,
            "candidate_count": len(candidates),
            "manifest_path": str(manifest_path),
            "workspace_ledger": str(workspace_ledger_path),
            "reused": False,
        }
    except Exception:
        if created_session and session_root.exists():
            shutil.rmtree(session_root)
        if created_canonical and canonical_root.exists():
            shutil.rmtree(canonical_root)
        raise


def load_intake_catalog(
    audio_root: str | Path,
) -> dict[str, dict[str, Any]]:
    audio_root = Path(audio_root).resolve()
    intake_root = audio_root / ".mgal" / "intakes"
    if not intake_root.is_dir():
        return {}

    catalog: dict[str, dict[str, Any]] = {}
    for manifest_path in sorted(intake_root.glob("*/manifest.json")):
        try:
            data = json.loads(
                manifest_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get("intake_version") != INTAKE_VERSION:
            continue

        request = data.get("request")
        if not isinstance(request, dict):
            request = {}

        for item in data.get("candidates", []):
            if not isinstance(item, dict):
                continue
            relative = item.get("relative_path")
            if not isinstance(relative, str):
                continue
            generation = item.get("generation")
            if not isinstance(generation, dict):
                generation = {}
            normalization = item.get("normalization")
            if not isinstance(normalization, dict):
                normalization = {}

            catalog[relative] = {
                "intake_id": data.get("intake_id"),
                "provider_id": data.get("provider_id"),
                "provider_kind": data.get("provider_kind"),
                "request_id": request.get("request_id"),
                "intent": request.get("intent"),
                "source_type": item.get("source_type"),
                "source_id": item.get("source_id"),
                "generation_provider": generation.get("provider"),
                "generation_model": generation.get("model"),
                "prompt": generation.get("prompt"),
                "normalization_profile_id": data.get(
                    "normalization_profile_id"
                ),
                "original_source_id": (
                    normalization.get("original", {}).get("source_id")
                    if isinstance(normalization.get("original"), dict)
                    else None
                ),
            }

    return catalog
