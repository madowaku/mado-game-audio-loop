from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .audio import read_wav_metadata


SOURCE_TYPES = {
    "unknown",
    "free_library",
    "recorded",
    "generated",
    "procedural",
    "purchased",
    "commissioned",
    "other",
}
LICENSE_STATUSES = {"unknown", "declared", "owned", "terms"}


class ProvenanceLedgerError(ValueError):
    pass


def source_sha256(path: str | Path) -> str:
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_id_for_hash(sha256: str) -> str:
    return f"sha256:{sha256}"


def _unknown_entry(path: Path, root: Path) -> dict[str, Any]:
    sha256 = source_sha256(path)
    metadata = read_wav_metadata(path)
    return {
        "source_id": source_id_for_hash(sha256),
        "sha256": sha256,
        "bytes": path.stat().st_size,
        "path_hint": path.relative_to(root).as_posix(),
        "source_type": "unknown",
        "origin": {
            "creator": None,
            "title": None,
            "url": None,
        },
        "license": {
            "status": "unknown",
            "expression": None,
            "url": None,
            "attribution": None,
            "notes": None,
        },
        "generation": None,
        "recording": None,
        "notes": None,
        "audio": {
            "duration_ms": metadata.duration_ms,
            "sample_rate": metadata.sample_rate,
            "channels": metadata.channels,
            "sample_width": metadata.sample_width,
            "frames": metadata.frames,
        },
    }


def create_provenance_ledger(audio_root: str | Path) -> dict[str, Any]:
    root = Path(audio_root).resolve()
    if not root.is_dir():
        raise ProvenanceLedgerError(f"audio root does not exist: {root}")

    entries = [
        _unknown_entry(path, root)
        for path in sorted(root.rglob("*.wav"))
        if path.is_file()
    ]
    return {
        "provenance_ledger_version": "0.1",
        "entry_count": len(entries),
        "entries": entries,
    }


def write_provenance_ledger(
    audio_root: str | Path,
    output_path: str | Path,
) -> Path:
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = create_provenance_ledger(audio_root)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def _require_string_or_none(value: Any, field: str) -> None:
    if value is not None and not isinstance(value, str):
        raise ProvenanceLedgerError(f"{field} must be string or null")


def _validate_entry_shape(entry: dict[str, Any], index: int) -> None:
    prefix = f"entries[{index}]"
    source_id = entry.get("source_id")
    sha256 = entry.get("sha256")
    byte_count = entry.get("bytes")
    path_hint = entry.get("path_hint")
    source_type = entry.get("source_type")

    if not isinstance(source_id, str):
        raise ProvenanceLedgerError(f"{prefix}.source_id must be a string")
    if not isinstance(sha256, str) or len(sha256) != 64:
        raise ProvenanceLedgerError(f"{prefix}.sha256 must be a 64-character string")
    if source_id != source_id_for_hash(sha256):
        raise ProvenanceLedgerError(f"{prefix}.source_id must match sha256")
    if not isinstance(byte_count, int) or byte_count < 0:
        raise ProvenanceLedgerError(f"{prefix}.bytes must be a non-negative integer")
    if not isinstance(path_hint, str) or not path_hint:
        raise ProvenanceLedgerError(f"{prefix}.path_hint must be a non-empty string")
    if Path(path_hint).is_absolute():
        raise ProvenanceLedgerError(f"{prefix}.path_hint must be relative")
    if source_type not in SOURCE_TYPES:
        raise ProvenanceLedgerError(f"{prefix}.source_type is unsupported: {source_type}")

    origin = entry.get("origin")
    if not isinstance(origin, dict):
        raise ProvenanceLedgerError(f"{prefix}.origin must be an object")
    for key in ("creator", "title", "url"):
        _require_string_or_none(origin.get(key), f"{prefix}.origin.{key}")

    license_info = entry.get("license")
    if not isinstance(license_info, dict):
        raise ProvenanceLedgerError(f"{prefix}.license must be an object")
    status = license_info.get("status")
    if status not in LICENSE_STATUSES:
        raise ProvenanceLedgerError(f"{prefix}.license.status is unsupported: {status}")
    for key in ("expression", "url", "attribution", "notes"):
        _require_string_or_none(license_info.get(key), f"{prefix}.license.{key}")

    generation = entry.get("generation")
    if generation is not None:
        if not isinstance(generation, dict):
            raise ProvenanceLedgerError(f"{prefix}.generation must be object or null")
        for key in ("provider", "model", "prompt", "seed"):
            _require_string_or_none(generation.get(key), f"{prefix}.generation.{key}")
        parameters = generation.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ProvenanceLedgerError(f"{prefix}.generation.parameters must be an object")

    recording = entry.get("recording")
    if recording is not None:
        if not isinstance(recording, dict):
            raise ProvenanceLedgerError(f"{prefix}.recording must be object or null")
        for key in ("recorded_by", "recorded_at", "device"):
            _require_string_or_none(recording.get(key), f"{prefix}.recording.{key}")

    _require_string_or_none(entry.get("notes"), f"{prefix}.notes")


def load_provenance_ledger(path: str | Path) -> dict[str, Any]:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ProvenanceLedgerError("provenance ledger must contain an object")
    if data.get("provenance_ledger_version") != "0.1":
        raise ProvenanceLedgerError("unsupported provenance_ledger_version")

    entries = data.get("entries")
    count = data.get("entry_count")
    if not isinstance(entries, list):
        raise ProvenanceLedgerError("entries must be a list")
    if not isinstance(count, int) or count != len(entries):
        raise ProvenanceLedgerError("entry_count does not match entries")

    source_ids: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ProvenanceLedgerError(f"entries[{index}] must be an object")
        _validate_entry_shape(entry, index)
        source_id = entry["source_id"]
        if source_id in source_ids:
            raise ProvenanceLedgerError(f"duplicate source_id: {source_id}")
        source_ids.add(source_id)

    return data


def entry_is_complete(entry: dict[str, Any]) -> bool:
    if entry.get("source_type") == "unknown":
        return False

    license_info = entry.get("license", {})
    if license_info.get("status") == "unknown":
        return False
    if license_info.get("status") in {"declared", "terms"}:
        expression = license_info.get("expression")
        if not isinstance(expression, str) or not expression.strip():
            return False

    if entry.get("source_type") == "generated":
        generation = entry.get("generation")
        if not isinstance(generation, dict):
            return False
        for key in ("provider", "model", "prompt"):
            value = generation.get(key)
            if not isinstance(value, str) or not value.strip():
                return False

    if entry.get("source_type") == "recorded":
        recording = entry.get("recording")
        if not isinstance(recording, dict):
            return False
        recorded_by = recording.get("recorded_by")
        if not isinstance(recorded_by, str) or not recorded_by.strip():
            return False

    return True


def validate_provenance_ledger(
    ledger_path: str | Path,
    audio_root: str | Path | None = None,
) -> dict[str, Any]:
    data = load_provenance_ledger(ledger_path)
    entries = data["entries"]

    if audio_root is not None:
        root = Path(audio_root).resolve()
        if not root.is_dir():
            raise ProvenanceLedgerError(f"audio root does not exist: {root}")

        for entry in entries:
            path_hint = entry["path_hint"]
            candidate = (root / path_hint).resolve()
            try:
                candidate.relative_to(root)
            except ValueError as exc:
                raise ProvenanceLedgerError(
                    f"path_hint escapes audio root: {path_hint}"
                ) from exc
            if not candidate.is_file():
                raise ProvenanceLedgerError(f"ledger source is missing: {path_hint}")
            if candidate.stat().st_size != entry["bytes"]:
                raise ProvenanceLedgerError(f"ledger byte size changed: {path_hint}")
            if source_sha256(candidate) != entry["sha256"]:
                raise ProvenanceLedgerError(f"ledger source hash changed: {path_hint}")

    complete = sum(1 for entry in entries if entry_is_complete(entry))
    return {
        "ok": True,
        "entries": len(entries),
        "complete_entries": complete,
        "incomplete_entries": len(entries) - complete,
        "complete": complete == len(entries),
    }


def update_provenance_entry(
    ledger_path: str | Path,
    source_ref: str,
    *,
    source_type: str | None = None,
    creator: str | None = None,
    title: str | None = None,
    origin_url: str | None = None,
    license_status: str | None = None,
    license_expression: str | None = None,
    license_url: str | None = None,
    attribution: str | None = None,
    license_notes: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    seed: str | None = None,
    recorded_by: str | None = None,
    recorded_at: str | None = None,
    device: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    path = Path(ledger_path).resolve()
    data = load_provenance_ledger(path)

    matches = [
        entry
        for entry in data["entries"]
        if entry["source_id"] == source_ref or entry["path_hint"] == source_ref
    ]
    if len(matches) != 1:
        raise ProvenanceLedgerError(
            f"source reference must match exactly one ledger entry: {source_ref}"
        )

    entry = matches[0]
    if source_type is not None:
        if source_type not in SOURCE_TYPES:
            raise ProvenanceLedgerError(f"unsupported source_type: {source_type}")
        entry["source_type"] = source_type

    if any(value is not None for value in (creator, title, origin_url)):
        entry["origin"].update(
            {
                key: value
                for key, value in {
                    "creator": creator,
                    "title": title,
                    "url": origin_url,
                }.items()
                if value is not None
            }
        )

    if any(
        value is not None
        for value in (
            license_status,
            license_expression,
            license_url,
            attribution,
            license_notes,
        )
    ):
        if license_status is not None and license_status not in LICENSE_STATUSES:
            raise ProvenanceLedgerError(
                f"unsupported license status: {license_status}"
            )
        entry["license"].update(
            {
                key: value
                for key, value in {
                    "status": license_status,
                    "expression": license_expression,
                    "url": license_url,
                    "attribution": attribution,
                    "notes": license_notes,
                }.items()
                if value is not None
            }
        )

    if any(value is not None for value in (provider, model, prompt, seed)):
        generation = entry.get("generation") or {
            "provider": None,
            "model": None,
            "prompt": None,
            "seed": None,
            "parameters": {},
        }
        generation.update(
            {
                key: value
                for key, value in {
                    "provider": provider,
                    "model": model,
                    "prompt": prompt,
                    "seed": seed,
                }.items()
                if value is not None
            }
        )
        entry["generation"] = generation

    if any(value is not None for value in (recorded_by, recorded_at, device)):
        recording = entry.get("recording") or {
            "recorded_by": None,
            "recorded_at": None,
            "device": None,
        }
        recording.update(
            {
                key: value
                for key, value in {
                    "recorded_by": recorded_by,
                    "recorded_at": recorded_at,
                    "device": device,
                }.items()
                if value is not None
            }
        )
        entry["recording"] = recording

    if notes is not None:
        entry["notes"] = notes

    _validate_entry_shape(entry, data["entries"].index(entry))
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return entry


def subset_ledger_for_source_index(
    ledger_path: str | Path,
    source_index: dict[str, Any],
) -> dict[str, Any]:
    ledger = load_provenance_ledger(ledger_path)
    by_id = {entry["source_id"]: entry for entry in ledger["entries"]}

    selected: list[dict[str, Any]] = []
    missing_ids: list[str] = []
    for source in source_index["sources"]:
        source_id = source_id_for_hash(source["sha256"])
        entry = by_id.get(source_id)
        if entry is None:
            missing_ids.append(source_id)
            continue
        selected.append(entry)

    if missing_ids:
        raise ProvenanceLedgerError(
            "ledger does not cover referenced source fingerprints: "
            + ",".join(missing_ids)
        )

    complete_entries = sum(1 for entry in selected if entry_is_complete(entry))
    return {
        "provenance_ledger_version": "0.1",
        "scope": "evidence_sources",
        "entry_count": len(selected),
        "expected_source_count": len(source_index["sources"]),
        "missing_source_ids": [],
        "complete_entries": complete_entries,
        "incomplete_entries": len(selected) - complete_entries,
        "complete": (
            len(selected) == len(source_index["sources"])
            and complete_entries == len(selected)
        ),
        "entries": selected,
    }


def verify_provenance_subset(
    provenance_data: dict[str, Any],
    source_index: dict[str, Any],
) -> dict[str, Any]:
    if provenance_data.get("provenance_ledger_version") != "0.1":
        raise ProvenanceLedgerError("unsupported provenance_ledger_version")

    entries = provenance_data.get("entries")
    if not isinstance(entries, list):
        raise ProvenanceLedgerError("provenance entries must be a list")

    indexed_ids = {
        source_id_for_hash(item["sha256"])
        for item in source_index.get("sources", [])
        if isinstance(item, dict) and isinstance(item.get("sha256"), str)
    }
    ledger_ids = {
        entry.get("source_id")
        for entry in entries
        if isinstance(entry, dict)
    }

    if ledger_ids != indexed_ids:
        raise ProvenanceLedgerError(
            "provenance source IDs do not match source-index fingerprints"
        )

    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ProvenanceLedgerError(f"entries[{index}] must be an object")
        _validate_entry_shape(entry, index)

    complete = sum(1 for entry in entries if entry_is_complete(entry))
    return {
        "ok": True,
        "entries": len(entries),
        "complete_entries": complete,
        "incomplete_entries": len(entries) - complete,
        "complete": complete == len(entries),
    }
