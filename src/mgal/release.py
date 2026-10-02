from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

from .evidence import EvidenceBundleError, verify_evidence_bundle
from .provenance import (
    entry_is_complete,
    source_id_for_hash,
)
from .recipe import load_recipe


class ReleasePackError(ValueError):
    pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _safe_slug(value: str) -> str:
    cleaned = "".join(
        character.lower() if character.isalnum() else "-"
        for character in value
    )
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned or "game-audio"


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ReleasePackError(f"{label} must contain an object")
    return data


def _selected_source_ids(
    bundle_dir: Path,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    recipe = load_recipe(bundle_dir / "selected-recipe.json")
    source_index = _load_json_object(
        bundle_dir / "source-index.json",
        "source-index.json",
    )
    sources = source_index.get("sources")
    if not isinstance(sources, list):
        raise ReleasePackError("source-index.sources must be a list")

    by_path: dict[str, dict[str, Any]] = {}
    for item in sources:
        if not isinstance(item, dict):
            raise ReleasePackError("source-index entry must be an object")
        relative = item.get("relative_path")
        sha256 = item.get("sha256")
        if not isinstance(relative, str):
            raise ReleasePackError("source-index relative_path must be a string")
        if not isinstance(sha256, str):
            raise ReleasePackError(f"{relative}: sha256 must be a string")

        expected_id = source_id_for_hash(sha256)
        source_id = item.get("source_id")
        if source_id is not None and source_id != expected_id:
            raise ReleasePackError(
                f"{relative}: source_id does not match sha256"
            )
        copied = dict(item)
        copied["source_id"] = expected_id
        by_path[relative] = copied

    ordered_ids: list[str] = []
    selected_sources: dict[str, dict[str, Any]] = {}
    for layer in recipe.layers:
        item = by_path.get(layer.source)
        if item is None:
            raise ReleasePackError(
                f"selected Recipe source missing from source-index: {layer.source}"
            )
        source_id = item["source_id"]
        if source_id not in selected_sources:
            ordered_ids.append(source_id)
            selected_sources[source_id] = {
                **item,
                "selected_recipe_paths": [],
            }
        paths = selected_sources[source_id]["selected_recipe_paths"]
        if layer.source not in paths:
            paths.append(layer.source)

    return ordered_ids, selected_sources


def _load_release_provenance(
    bundle_dir: Path,
    ordered_ids: list[str],
) -> list[dict[str, Any]]:
    provenance_path = bundle_dir / "provenance-ledger.json"
    if not provenance_path.is_file():
        raise ReleasePackError(
            "release pack requires provenance-ledger.json in the Evidence Bundle"
        )

    provenance = _load_json_object(
        provenance_path,
        "provenance-ledger.json",
    )
    entries = provenance.get("entries")
    if not isinstance(entries, list):
        raise ReleasePackError("provenance entries must be a list")

    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ReleasePackError("provenance entry must be an object")
        source_id = entry.get("source_id")
        if not isinstance(source_id, str):
            raise ReleasePackError("provenance source_id must be a string")
        if source_id in by_id:
            raise ReleasePackError(f"duplicate provenance source_id: {source_id}")
        by_id[source_id] = entry

    selected: list[dict[str, Any]] = []
    for source_id in ordered_ids:
        entry = by_id.get(source_id)
        if entry is None:
            raise ReleasePackError(
                f"selected source has no provenance entry: {source_id}"
            )
        if not entry_is_complete(entry):
            raise ReleasePackError(
                f"selected source provenance is incomplete: {source_id}"
            )
        selected.append(entry)

    return selected


def _license_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for entry in entries:
        origin = entry.get("origin", {})
        license_info = entry.get("license", {})
        generation = entry.get("generation")
        recording = entry.get("recording")
        rows.append(
            {
                "source_id": entry["source_id"],
                "path_hint": entry["path_hint"],
                "source_type": entry["source_type"],
                "origin": {
                    "creator": origin.get("creator"),
                    "title": origin.get("title"),
                    "url": origin.get("url"),
                },
                "license": {
                    "status": license_info.get("status"),
                    "expression": license_info.get("expression"),
                    "url": license_info.get("url"),
                    "attribution": license_info.get("attribution"),
                    "notes": license_info.get("notes"),
                },
                "generation": generation,
                "recording": recording,
            }
        )

    return {
        "license_summary_version": "0.1",
        "disclaimer": (
            "This file summarizes provenance/license declarations recorded in MGAL. "
            "It is not a legal determination of usage rights."
        ),
        "source_count": len(rows),
        "sources": rows,
    }


def _attribution_text(entries: list[dict[str, Any]]) -> str:
    lines = [
        "MGAL ATTRIBUTION",
        "================",
        "",
        "This file lists attribution/provenance declarations for sources used",
        "by the final selected audio recipe.",
        "",
    ]

    for index, entry in enumerate(entries, start=1):
        origin = entry.get("origin", {})
        license_info = entry.get("license", {})
        generation = entry.get("generation")
        recording = entry.get("recording")

        title = origin.get("title") or entry.get("path_hint") or entry["source_id"]
        lines.append(f"{index}. {title}")
        lines.append(f"   Source ID: {entry['source_id']}")
        lines.append(f"   Type: {entry['source_type']}")

        creator = origin.get("creator")
        if creator:
            lines.append(f"   Creator: {creator}")

        attribution = license_info.get("attribution")
        if attribution:
            lines.append(f"   Attribution: {attribution}")

        expression = license_info.get("expression")
        status = license_info.get("status")
        lines.append(
            f"   License: {expression or status or 'unknown'}"
        )

        origin_url = origin.get("url")
        if origin_url:
            lines.append(f"   Source URL: {origin_url}")

        license_url = license_info.get("url")
        if license_url:
            lines.append(f"   License URL: {license_url}")

        if isinstance(generation, dict):
            provider = generation.get("provider")
            model = generation.get("model")
            prompt = generation.get("prompt")
            seed = generation.get("seed")
            if provider:
                lines.append(f"   Generator provider: {provider}")
            if model:
                lines.append(f"   Generator model: {model}")
            if prompt:
                lines.append(f"   Generator prompt: {prompt}")
            if seed:
                lines.append(f"   Generator seed: {seed}")

        if isinstance(recording, dict):
            recorded_by = recording.get("recorded_by")
            recorded_at = recording.get("recorded_at")
            device = recording.get("device")
            if recorded_by:
                lines.append(f"   Recorded by: {recorded_by}")
            if recorded_at:
                lines.append(f"   Recorded at: {recorded_at}")
            if device:
                lines.append(f"   Device: {device}")

        notes = license_info.get("notes")
        if notes:
            lines.append(f"   License notes: {notes}")

        lines.append("")

    lines.extend(
        [
            "Note: MGAL records declared provenance and license metadata.",
            "This attribution file is not legal advice and does not independently",
            "verify that the recorded terms are sufficient for a specific release.",
            "",
        ]
    )
    return "\n".join(lines)


def _provenance_report(
    bundle_dir: Path,
    entries: list[dict[str, Any]],
    selected_sources: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    decision = _load_json_object(bundle_dir / "decision.json", "decision.json")
    recipe = _load_json_object(
        bundle_dir / "selected-recipe.json",
        "selected-recipe.json",
    )

    sources = []
    for entry in entries:
        source_id = entry["source_id"]
        source = selected_sources[source_id]
        sources.append(
            {
                "source_id": source_id,
                "selected_recipe_paths": source["selected_recipe_paths"],
                "sha256": source["sha256"],
                "bytes": source["bytes"],
                "source_type": entry["source_type"],
                "path_hint": entry["path_hint"],
                "origin": entry.get("origin"),
                "license": entry.get("license"),
                "generation": entry.get("generation"),
                "recording": entry.get("recording"),
                "normalization": entry.get("normalization"),
                "notes": entry.get("notes"),
            }
        )

    return {
        "provenance_report_version": "0.1",
        "selected_candidate_id": decision.get("selected_candidate_id"),
        "selected_recipe_id": recipe.get("id"),
        "intent": recipe.get("intent"),
        "source_count": len(sources),
        "sources": sources,
    }


def build_release_pack(
    bundle_dir: str | Path,
    output_dir: str | Path,
    name: str | None = None,
) -> Path:
    bundle_dir = Path(bundle_dir).resolve()
    output_dir = Path(output_dir).resolve()

    try:
        verification = verify_evidence_bundle(bundle_dir)
    except EvidenceBundleError as exc:
        raise ReleasePackError(f"Evidence Bundle verification failed: {exc}") from exc

    try:
        output_dir.relative_to(bundle_dir)
    except ValueError:
        pass
    else:
        raise ReleasePackError(
            "release output must be outside the Evidence Bundle"
        )

    if output_dir.exists() and not output_dir.is_dir():
        raise ReleasePackError(f"output path is not a directory: {output_dir}")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ReleasePackError(f"output directory is not empty: {output_dir}")

    recipe = load_recipe(bundle_dir / "selected-recipe.json")
    ordered_ids, selected_sources = _selected_source_ids(bundle_dir)
    entries = _load_release_provenance(bundle_dir, ordered_ids)

    output_name = _safe_slug(name or recipe.id)
    output_dir.mkdir(parents=True, exist_ok=True)

    final_wav = output_dir / f"{output_name}.wav"
    shutil.copyfile(bundle_dir / "output.wav", final_wav)

    recipe_path = output_dir / "RECIPE.json"
    shutil.copyfile(bundle_dir / "selected-recipe.json", recipe_path)

    attribution_path = output_dir / "ATTRIBUTION.txt"
    attribution_path.write_text(
        _attribution_text(entries),
        encoding="utf-8",
    )

    license_path = output_dir / "LICENSE_SUMMARY.json"
    _write_json(license_path, _license_summary(entries))

    provenance_path = output_dir / "PROVENANCE_REPORT.json"
    _write_json(
        provenance_path,
        _provenance_report(
            bundle_dir,
            entries,
            selected_sources,
        ),
    )

    evidence_ref = {
        "evidence_ref_version": "0.1",
        "evidence_manifest_sha256": _sha256(bundle_dir / "manifest.json"),
        "selected_candidate_id": verification.get("selected_candidate_id"),
        "selected_recipe_id": recipe.id,
        "evidence_output_sha256": _sha256(bundle_dir / "output.wav"),
    }
    _write_json(output_dir / "EVIDENCE_REF.json", evidence_ref)

    payloads = sorted(
        path
        for path in output_dir.iterdir()
        if path.is_file() and path.name != "RELEASE_MANIFEST.json"
    )
    manifest = {
        "release_pack_version": "0.1",
        "release_name": output_name,
        "selected_recipe_id": recipe.id,
        "selected_candidate_id": verification.get("selected_candidate_id"),
        "evidence_manifest_sha256": evidence_ref["evidence_manifest_sha256"],
        "source_count": len(entries),
        "file_count": len(payloads),
        "files": [
            {
                "path": path.name,
                "sha256": _sha256(path),
                "bytes": path.stat().st_size,
            }
            for path in payloads
        ],
    }
    _write_json(output_dir / "RELEASE_MANIFEST.json", manifest)
    return output_dir


def verify_release_pack(pack_dir: str | Path) -> dict[str, Any]:
    pack_dir = Path(pack_dir).resolve()
    manifest_path = pack_dir / "RELEASE_MANIFEST.json"
    if not manifest_path.is_file():
        raise ReleasePackError("RELEASE_MANIFEST.json is missing")

    manifest = _load_json_object(
        manifest_path,
        "RELEASE_MANIFEST.json",
    )
    if manifest.get("release_pack_version") != "0.1":
        raise ReleasePackError("unsupported release_pack_version")

    files = manifest.get("files")
    file_count = manifest.get("file_count")
    if not isinstance(files, list):
        raise ReleasePackError("release manifest files must be a list")
    if not isinstance(file_count, int) or file_count != len(files):
        raise ReleasePackError("release manifest file_count does not match files")

    seen: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise ReleasePackError("release manifest file entry must be an object")

        relative = item.get("path")
        expected_hash = item.get("sha256")
        expected_bytes = item.get("bytes")
        if not isinstance(relative, str):
            raise ReleasePackError("release manifest path must be a string")
        if Path(relative).is_absolute() or "/" in relative or "\\" in relative:
            raise ReleasePackError(f"release manifest path must be top-level: {relative}")
        if relative in seen:
            raise ReleasePackError(f"duplicate release manifest path: {relative}")
        seen.add(relative)

        path = (pack_dir / relative).resolve()
        try:
            path.relative_to(pack_dir)
        except ValueError as exc:
            raise ReleasePackError(
                f"release manifest path escapes pack: {relative}"
            ) from exc
        if not path.is_file():
            raise ReleasePackError(f"release file is missing: {relative}")
        if not isinstance(expected_bytes, int) or path.stat().st_size != expected_bytes:
            raise ReleasePackError(f"release file byte size changed: {relative}")
        if not isinstance(expected_hash, str) or _sha256(path) != expected_hash:
            raise ReleasePackError(f"release file hash changed: {relative}")

    actual = {
        path.name
        for path in pack_dir.iterdir()
        if path.is_file() and path.name != "RELEASE_MANIFEST.json"
    }
    if actual != seen:
        raise ReleasePackError("release payload set does not match manifest")

    required = {
        "ATTRIBUTION.txt",
        "LICENSE_SUMMARY.json",
        "PROVENANCE_REPORT.json",
        "RECIPE.json",
        "EVIDENCE_REF.json",
    }
    if not required.issubset(seen):
        raise ReleasePackError("release pack is missing required metadata files")

    wavs = [path for path in seen if path.lower().endswith(".wav")]
    if len(wavs) != 1:
        raise ReleasePackError("release pack must contain exactly one final WAV")

    recipe = _load_json_object(pack_dir / "RECIPE.json", "RECIPE.json")
    selected_recipe_id = manifest.get("selected_recipe_id")
    if recipe.get("id") != selected_recipe_id:
        raise ReleasePackError(
            "RECIPE.json id does not match release manifest"
        )

    license_summary = _load_json_object(
        pack_dir / "LICENSE_SUMMARY.json",
        "LICENSE_SUMMARY.json",
    )
    if license_summary.get("license_summary_version") != "0.1":
        raise ReleasePackError("unsupported license_summary_version")

    provenance_report = _load_json_object(
        pack_dir / "PROVENANCE_REPORT.json",
        "PROVENANCE_REPORT.json",
    )
    if provenance_report.get("provenance_report_version") != "0.1":
        raise ReleasePackError("unsupported provenance_report_version")

    source_count = manifest.get("source_count")
    if not isinstance(source_count, int):
        raise ReleasePackError("release manifest source_count must be an integer")
    if license_summary.get("source_count") != source_count:
        raise ReleasePackError(
            "LICENSE_SUMMARY source_count does not match release manifest"
        )
    if provenance_report.get("source_count") != source_count:
        raise ReleasePackError(
            "PROVENANCE_REPORT source_count does not match release manifest"
        )

    license_sources = license_summary.get("sources")
    provenance_sources = provenance_report.get("sources")
    if not isinstance(license_sources, list) or not isinstance(provenance_sources, list):
        raise ReleasePackError("release source summaries must be lists")

    license_ids = {
        item.get("source_id")
        for item in license_sources
        if isinstance(item, dict)
    }
    provenance_ids = {
        item.get("source_id")
        for item in provenance_sources
        if isinstance(item, dict)
    }
    if len(license_ids) != source_count or license_ids != provenance_ids:
        raise ReleasePackError(
            "release provenance/license source sets do not match"
        )

    selected_candidate_id = manifest.get("selected_candidate_id")
    if provenance_report.get("selected_candidate_id") != selected_candidate_id:
        raise ReleasePackError(
            "PROVENANCE_REPORT candidate does not match release manifest"
        )
    if provenance_report.get("selected_recipe_id") != selected_recipe_id:
        raise ReleasePackError(
            "PROVENANCE_REPORT recipe does not match release manifest"
        )

    evidence_ref = _load_json_object(
        pack_dir / "EVIDENCE_REF.json",
        "EVIDENCE_REF.json",
    )
    if evidence_ref.get("evidence_ref_version") != "0.1":
        raise ReleasePackError("unsupported evidence_ref_version")
    if evidence_ref.get("selected_candidate_id") != selected_candidate_id:
        raise ReleasePackError(
            "EVIDENCE_REF candidate does not match release manifest"
        )
    if evidence_ref.get("selected_recipe_id") != selected_recipe_id:
        raise ReleasePackError(
            "EVIDENCE_REF recipe does not match release manifest"
        )
    if (
        evidence_ref.get("evidence_manifest_sha256")
        != manifest.get("evidence_manifest_sha256")
    ):
        raise ReleasePackError(
            "EVIDENCE_REF manifest hash does not match release manifest"
        )

    final_wav = wavs[0]
    if evidence_ref.get("evidence_output_sha256") != _sha256(pack_dir / final_wav):
        raise ReleasePackError(
            "final WAV does not match Evidence output hash"
        )

    return {
        "ok": True,
        "release_name": manifest.get("release_name"),
        "selected_recipe_id": selected_recipe_id,
        "selected_candidate_id": selected_candidate_id,
        "sources": source_count,
        "files_verified": len(seen),
        "final_wav": final_wav,
        "evidence_manifest_sha256": manifest.get("evidence_manifest_sha256"),
    }
