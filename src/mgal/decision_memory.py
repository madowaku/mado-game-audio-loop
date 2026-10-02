from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .preference import (
    PreferenceEvidenceError,
    load_preference_archive_metadata,
)


DECISION_MEMORY_VERSION = "0.1"


class DecisionMemoryError(ValueError):
    pass


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_json(value: object) -> str:
    return hashlib.sha256(
        _canonical_json_bytes(value)
    ).hexdigest()


def decision_memory_path(
    audio_root: str | Path,
) -> Path:
    return (
        Path(audio_root).resolve()
        / ".mgal"
        / "decision-memory.json"
    )


def _empty_memory() -> dict[str, Any]:
    return {
        "decision_memory_version": DECISION_MEMORY_VERSION,
        "promotion_count": 0,
        "entry_count": 0,
        "promotions": [],
        "entries": [],
    }


def _source_hash_lookup(
    evidence: dict[str, Any],
) -> dict[str, str]:
    source_index = evidence.get("source_index")
    if not isinstance(source_index, dict):
        raise DecisionMemoryError(
            "preference evidence source_index must be an object"
        )
    sources = source_index.get("sources")
    if not isinstance(sources, list):
        raise DecisionMemoryError(
            "preference evidence source_index.sources must be a list"
        )

    lookup: dict[str, str] = {}
    for item in sources:
        if not isinstance(item, dict):
            raise DecisionMemoryError(
                "preference source index entry must be an object"
            )
        relative = item.get("relative_path")
        sha256 = item.get("sha256")
        if (
            not isinstance(relative, str)
            or not isinstance(sha256, str)
        ):
            raise DecisionMemoryError(
                "preference source index entry is incomplete"
            )
        lookup[relative] = sha256
    return lookup


def _candidate_recipe_lookup(
    evidence: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    board = evidence.get("candidate_board")
    if not isinstance(board, dict):
        raise DecisionMemoryError(
            "preference evidence candidate_board must be an object"
        )
    candidates = board.get("candidates")
    if not isinstance(candidates, list):
        raise DecisionMemoryError(
            "candidate_board.candidates must be a list"
        )

    result: dict[str, dict[str, Any]] = {}
    for item in candidates:
        if not isinstance(item, dict):
            continue
        candidate_id = item.get("id")
        recipe = item.get("recipe")
        if isinstance(candidate_id, str) and isinstance(recipe, dict):
            result[candidate_id] = recipe
    return result


def _recipe_summary(
    recipe: dict[str, Any],
    source_hashes: dict[str, str],
) -> dict[str, Any]:
    layers = recipe.get("layers")
    if not isinstance(layers, list):
        raise DecisionMemoryError(
            "recipe layers must be a list"
        )

    gains: list[float] = []
    offsets: list[int] = []
    source_ids: list[str] = []

    for layer in layers:
        if not isinstance(layer, dict):
            raise DecisionMemoryError(
                "recipe layer must be an object"
            )
        source = layer.get("source")
        gain = layer.get("gain")
        offset = layer.get("offset_ms")
        if not isinstance(source, str):
            raise DecisionMemoryError(
                "recipe layer source must be a string"
            )
        if source not in source_hashes:
            raise DecisionMemoryError(
                f"recipe source is absent from Preference Evidence source index: {source}"
            )
        if not isinstance(gain, (int, float)):
            raise DecisionMemoryError(
                "recipe layer gain must be numeric"
            )
        if not isinstance(offset, int):
            raise DecisionMemoryError(
                "recipe layer offset_ms must be an integer"
            )

        gains.append(float(gain))
        offsets.append(offset)
        source_ids.append(
            "sha256:" + source_hashes[source]
        )

    processing = recipe.get("processing")
    if not isinstance(processing, dict):
        processing = {}

    normalize = processing.get("normalize")
    fade_out_ms = processing.get("fade_out_ms")
    if not isinstance(normalize, bool):
        normalize = False
    if not isinstance(fade_out_ms, int):
        fade_out_ms = 0

    return {
        "recipe_id": recipe.get("id"),
        "recipe_sha256": _sha256_json(recipe),
        "layer_count": len(layers),
        "total_gain": round(sum(gains), 6),
        "earliest_offset_ms": min(offsets) if offsets else 0,
        "latest_offset_ms": max(offsets) if offsets else 0,
        "normalize": normalize,
        "fade_out_ms": fade_out_ms,
        "source_ids": sorted(source_ids),
    }


def _observed_differences(
    winner: dict[str, Any],
    loser: dict[str, Any],
) -> dict[str, Any]:
    winner_sources = set(winner["source_ids"])
    loser_sources = set(loser["source_ids"])

    return {
        "layer_count_delta": (
            winner["layer_count"]
            - loser["layer_count"]
        ),
        "total_gain_delta": round(
            winner["total_gain"]
            - loser["total_gain"],
            6,
        ),
        "earliest_offset_ms_delta": (
            winner["earliest_offset_ms"]
            - loser["earliest_offset_ms"]
        ),
        "latest_offset_ms_delta": (
            winner["latest_offset_ms"]
            - loser["latest_offset_ms"]
        ),
        "fade_out_ms_delta": (
            winner["fade_out_ms"]
            - loser["fade_out_ms"]
        ),
        "normalize_changed": (
            winner["normalize"]
            != loser["normalize"]
        ),
        "shared_source_count": len(
            winner_sources & loser_sources
        ),
        "winner_only_source_count": len(
            winner_sources - loser_sources
        ),
        "loser_only_source_count": len(
            loser_sources - winner_sources
        ),
    }


def compile_archive_memory_entries(
    audio_root: str | Path,
    archive_id: str,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    try:
        manifest, evidence = load_preference_archive_metadata(
            audio_root,
            archive_id,
        )
    except PreferenceEvidenceError as exc:
        raise DecisionMemoryError(
            f"preference archive cannot be promoted: {exc}"
        ) from exc

    board = evidence["candidate_board"]
    intent = board.get("intent")
    if not isinstance(intent, str):
        intent = ""

    source_hashes = _source_hash_lookup(evidence)
    recipes = _candidate_recipe_lookup(evidence)

    votes = evidence.get("votes")
    pairs = evidence.get("pairs")
    if not isinstance(votes, list) or not isinstance(pairs, list):
        raise DecisionMemoryError(
            "preference evidence pairs/votes must be lists"
        )
    if len(votes) != len(pairs):
        raise DecisionMemoryError(
            "preference evidence pair/vote count mismatch"
        )

    evidence_sha256 = manifest.get("evidence_sha256")
    board_sha256 = manifest.get("candidate_board_sha256")
    if not isinstance(evidence_sha256, str):
        raise DecisionMemoryError(
            "archive evidence fingerprint is missing"
        )
    if not isinstance(board_sha256, str):
        raise DecisionMemoryError(
            "archive Board fingerprint is missing"
        )

    entries: list[dict[str, Any]] = []
    for index, (pair, vote) in enumerate(
        zip(pairs, votes)
    ):
        if not isinstance(pair, dict) or not isinstance(vote, dict):
            raise DecisionMemoryError(
                "preference pair/vote entry must be an object"
            )

        winner_id = vote.get("winner_candidate_id")
        loser_id = vote.get("loser_candidate_id")
        winner_alias = vote.get("winner_alias")
        if (
            not isinstance(winner_id, str)
            or not isinstance(loser_id, str)
            or winner_id not in recipes
            or loser_id not in recipes
        ):
            raise DecisionMemoryError(
                "preference vote references an unknown Candidate"
            )

        winner_summary = _recipe_summary(
            recipes[winner_id],
            source_hashes,
        )
        loser_summary = _recipe_summary(
            recipes[loser_id],
            source_hashes,
        )

        entry_seed = {
            "archive_evidence_sha256": evidence_sha256,
            "pair_index": index,
            "winner_candidate_id": winner_id,
            "loser_candidate_id": loser_id,
        }
        entry_id = "decision:" + _sha256_json(
            entry_seed
        )[:20]

        entries.append(
            {
                "entry_id": entry_id,
                "archive_id": archive_id,
                "archive_evidence_sha256": evidence_sha256,
                "candidate_board_sha256": board_sha256,
                "intent": intent,
                "pair_index": index,
                "winner_alias": winner_alias,
                "winner_candidate_id": winner_id,
                "loser_candidate_id": loser_id,
                "winner_recipe": winner_summary,
                "loser_recipe": loser_summary,
                "observed_differences": _observed_differences(
                    winner_summary,
                    loser_summary,
                ),
            }
        )

    promotion = {
        "archive_id": archive_id,
        "archive_evidence_sha256": evidence_sha256,
        "candidate_board_sha256": board_sha256,
        "intent": intent,
        "pair_count": len(entries),
        "winner_candidate_id": evidence.get(
            "winner_candidate_id"
        ),
        "tie": evidence.get("tie"),
        "applied_candidate_id": evidence.get(
            "applied_candidate_id"
        ),
        "entry_ids": [
            entry["entry_id"]
            for entry in entries
        ],
    }
    return promotion, entries


def validate_decision_memory(
    data: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise DecisionMemoryError(
            "Decision Memory must be an object"
        )
    if (
        data.get("decision_memory_version")
        != DECISION_MEMORY_VERSION
    ):
        raise DecisionMemoryError(
            "unsupported decision_memory_version"
        )

    promotions = data.get("promotions")
    entries = data.get("entries")
    if not isinstance(promotions, list):
        raise DecisionMemoryError(
            "Decision Memory promotions must be a list"
        )
    if not isinstance(entries, list):
        raise DecisionMemoryError(
            "Decision Memory entries must be a list"
        )
    if data.get("promotion_count") != len(promotions):
        raise DecisionMemoryError(
            "Decision Memory promotion_count does not match promotions"
        )
    if data.get("entry_count") != len(entries):
        raise DecisionMemoryError(
            "Decision Memory entry_count does not match entries"
        )

    entry_by_id: dict[str, dict[str, Any]] = {}
    for item in entries:
        if not isinstance(item, dict):
            raise DecisionMemoryError(
                "Decision Memory entry must be an object"
            )
        entry_id = item.get("entry_id")
        if not isinstance(entry_id, str) or not entry_id:
            raise DecisionMemoryError(
                "Decision Memory entry_id must be a string"
            )
        if entry_id in entry_by_id:
            raise DecisionMemoryError(
                f"duplicate Decision Memory entry: {entry_id}"
            )
        winner = item.get("winner_recipe")
        loser = item.get("loser_recipe")
        observed = item.get("observed_differences")
        if (
            not isinstance(winner, dict)
            or not isinstance(loser, dict)
            or not isinstance(observed, dict)
        ):
            raise DecisionMemoryError(
                f"{entry_id}: recipe summaries/differences are missing"
            )
        if observed != _observed_differences(
            winner,
            loser,
        ):
            raise DecisionMemoryError(
                f"{entry_id}: observed differences do not match recipe summaries"
            )
        entry_by_id[entry_id] = item

    evidence_hashes: set[str] = set()
    referenced_entries: set[str] = set()
    for promotion in promotions:
        if not isinstance(promotion, dict):
            raise DecisionMemoryError(
                "Decision Memory promotion must be an object"
            )
        evidence_hash = promotion.get(
            "archive_evidence_sha256"
        )
        if not isinstance(evidence_hash, str):
            raise DecisionMemoryError(
                "Decision Memory promotion evidence hash must be a string"
            )
        if evidence_hash in evidence_hashes:
            raise DecisionMemoryError(
                "Decision Memory contains duplicate promoted Evidence"
            )
        evidence_hashes.add(evidence_hash)

        entry_ids = promotion.get("entry_ids")
        pair_count = promotion.get("pair_count")
        if not isinstance(entry_ids, list):
            raise DecisionMemoryError(
                "Decision Memory promotion entry_ids must be a list"
            )
        if pair_count != len(entry_ids):
            raise DecisionMemoryError(
                "Decision Memory promotion pair_count does not match entry_ids"
            )
        for entry_id in entry_ids:
            if (
                not isinstance(entry_id, str)
                or entry_id not in entry_by_id
            ):
                raise DecisionMemoryError(
                    "Decision Memory promotion references unknown entry"
                )
            entry = entry_by_id[entry_id]
            if (
                entry.get("archive_evidence_sha256")
                != evidence_hash
            ):
                raise DecisionMemoryError(
                    "Decision Memory entry belongs to a different promotion"
                )
            if entry_id in referenced_entries:
                raise DecisionMemoryError(
                    "Decision Memory entry is referenced by multiple promotions"
                )
            referenced_entries.add(entry_id)

    if referenced_entries != set(entry_by_id):
        raise DecisionMemoryError(
            "Decision Memory contains unreferenced entries"
        )

    return {
        "ok": True,
        "promotions": len(promotions),
        "entries": len(entries),
    }


def load_decision_memory(
    audio_root: str | Path,
) -> dict[str, Any]:
    path = decision_memory_path(audio_root)
    if not path.is_file():
        return _empty_memory()
    try:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise DecisionMemoryError(
            "Decision Memory contains invalid JSON"
        ) from exc
    if not isinstance(data, dict):
        raise DecisionMemoryError(
            "Decision Memory must contain an object"
        )
    validate_decision_memory(data)
    return data


def write_decision_memory(
    audio_root: str | Path,
    data: dict[str, Any],
) -> Path:
    validate_decision_memory(data)
    path = decision_memory_path(audio_root)
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def promote_preference_archive(
    audio_root: str | Path,
    archive_id: str,
) -> dict[str, Any]:
    promotion, entries = compile_archive_memory_entries(
        audio_root,
        archive_id,
    )
    memory = load_decision_memory(audio_root)

    evidence_hash = promotion[
        "archive_evidence_sha256"
    ]
    existing = next(
        (
            item
            for item in memory["promotions"]
            if item.get("archive_evidence_sha256")
            == evidence_hash
        ),
        None,
    )
    if existing is not None:
        return {
            "ok": True,
            "reused": True,
            "archive_id": existing["archive_id"],
            "promotion": existing,
            "memory": decision_memory_summary(memory),
        }

    memory["promotions"].append(promotion)
    memory["entries"].extend(entries)
    memory["promotion_count"] = len(
        memory["promotions"]
    )
    memory["entry_count"] = len(
        memory["entries"]
    )
    write_decision_memory(
        audio_root,
        memory,
    )

    return {
        "ok": True,
        "reused": False,
        "archive_id": archive_id,
        "promotion": promotion,
        "memory": decision_memory_summary(memory),
    }


def decision_memory_summary(
    memory: dict[str, Any],
) -> dict[str, Any]:
    validate_decision_memory(memory)
    intents: dict[str, int] = {}
    for promotion in memory["promotions"]:
        intent = promotion.get("intent")
        if not isinstance(intent, str):
            intent = ""
        intents[intent] = intents.get(intent, 0) + 1

    return {
        "decision_memory_version": DECISION_MEMORY_VERSION,
        "promotion_count": memory["promotion_count"],
        "entry_count": memory["entry_count"],
        "intent_counts": [
            {
                "intent": intent,
                "promotions": count,
            }
            for intent, count in sorted(
                intents.items(),
                key=lambda item: (-item[1], item[0]),
            )
        ],
    }


def decision_memory_view(
    audio_root: str | Path,
) -> dict[str, Any]:
    memory = load_decision_memory(audio_root)
    return {
        "summary": decision_memory_summary(memory),
        "promotions": memory["promotions"],
        "entries": memory["entries"],
    }


def promoted_archive_ids(
    audio_root: str | Path,
) -> set[str]:
    memory = load_decision_memory(audio_root)
    return {
        item["archive_id"]
        for item in memory["promotions"]
        if isinstance(item.get("archive_id"), str)
    }


def verify_decision_memory_against_archives(
    audio_root: str | Path,
) -> dict[str, Any]:
    memory = load_decision_memory(audio_root)
    by_evidence = {
        item["archive_evidence_sha256"]: item
        for item in memory["promotions"]
    }

    verified = 0
    for evidence_hash, promotion in by_evidence.items():
        archive_id = promotion["archive_id"]
        compiled_promotion, compiled_entries = (
            compile_archive_memory_entries(
                audio_root,
                archive_id,
            )
        )
        if (
            compiled_promotion[
                "archive_evidence_sha256"
            ]
            != evidence_hash
        ):
            raise DecisionMemoryError(
                f"{archive_id}: promoted Evidence fingerprint changed"
            )

        expected_entry_ids = set(
            compiled_promotion["entry_ids"]
        )
        stored_entry_ids = set(
            promotion["entry_ids"]
        )
        if expected_entry_ids != stored_entry_ids:
            raise DecisionMemoryError(
                f"{archive_id}: promoted entry set does not match archive"
            )

        stored_entries = {
            item["entry_id"]: item
            for item in memory["entries"]
            if item["entry_id"] in stored_entry_ids
        }
        compiled_by_id = {
            item["entry_id"]: item
            for item in compiled_entries
        }
        if stored_entries != compiled_by_id:
            raise DecisionMemoryError(
                f"{archive_id}: Decision Memory entries do not match archive"
            )
        verified += 1

    return {
        "ok": True,
        "promotions_verified": verified,
        "entries_verified": memory["entry_count"],
    }
