from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unicodedata
from typing import Any

from .decision_memory import (
    DecisionMemoryError,
    load_decision_memory,
    validate_decision_memory,
)


DECISION_CONTEXT_PACK_VERSION = "0.1"
RETRIEVAL_STRATEGY = "intent-token-overlap-v1"
_STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "in",
    "of",
    "on",
    "the",
    "to",
    "with",
}


class DecisionContextError(ValueError):
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


def _is_cjk(character: str) -> bool:
    code = ord(character)
    return (
        0x3040 <= code <= 0x30FF
        or 0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xF900 <= code <= 0xFAFF
        or 0xAC00 <= code <= 0xD7AF
    )


def normalize_intent(value: str) -> str:
    return " ".join(
        unicodedata.normalize("NFKC", value)
        .casefold()
        .split()
    )


def tokenize_intent(value: str) -> list[str]:
    normalized = normalize_intent(value)
    tokens: set[str] = set()

    for token in re.findall(
        r"[^\W_]+",
        normalized,
        flags=re.UNICODE,
    ):
        if len(token) >= 2 and token not in _STOPWORDS:
            tokens.add(token)

    cjk_run: list[str] = []

    def flush_cjk() -> None:
        if not cjk_run:
            return
        run = "".join(cjk_run)
        if len(run) >= 2:
            tokens.add(run)
            for index in range(len(run) - 1):
                tokens.add(run[index : index + 2])
        cjk_run.clear()

    for character in normalized:
        if _is_cjk(character):
            cjk_run.append(character)
        else:
            flush_cjk()
    flush_cjk()

    return sorted(tokens)


def _match_entry(
    query_intent: str,
    query_tokens: set[str],
    entry: dict[str, Any],
) -> dict[str, Any] | None:
    source_intent = entry.get("intent")
    if not isinstance(source_intent, str):
        source_intent = ""

    source_tokens = set(
        tokenize_intent(source_intent)
    )
    matched = sorted(
        query_tokens & source_tokens
    )
    exact = (
        normalize_intent(query_intent)
        == normalize_intent(source_intent)
        and bool(normalize_intent(query_intent))
    )
    if not matched and not exact:
        return None

    return {
        "entry": entry,
        "source_intent": source_intent,
        "exact_intent": exact,
        "matched_terms": matched,
        "match_count": len(matched),
        "query_term_count": len(query_tokens),
        "source_term_count": len(source_tokens),
    }


def _observation_from_match(
    match: dict[str, Any],
) -> dict[str, Any]:
    entry = match["entry"]
    return {
        "entry_id": entry["entry_id"],
        "archive_id": entry["archive_id"],
        "archive_evidence_sha256": entry[
            "archive_evidence_sha256"
        ],
        "source_intent": match["source_intent"],
        "match": {
            "exact_intent": match["exact_intent"],
            "matched_terms": match["matched_terms"],
            "match_count": match["match_count"],
            "query_term_count": match[
                "query_term_count"
            ],
            "source_term_count": match[
                "source_term_count"
            ],
        },
        "pair_index": entry["pair_index"],
        "winner_candidate_id": entry[
            "winner_candidate_id"
        ],
        "loser_candidate_id": entry[
            "loser_candidate_id"
        ],
        "winner_recipe": entry["winner_recipe"],
        "loser_recipe": entry["loser_recipe"],
        "observed_differences": entry[
            "observed_differences"
        ],
    }


def build_decision_context_pack(
    audio_root: str | Path,
    intent: str,
    *,
    limit: int = 6,
) -> dict[str, Any]:
    if not isinstance(intent, str) or not intent.strip():
        raise DecisionContextError(
            "decision context intent must be a non-empty string"
        )
    if not isinstance(limit, int) or not 1 <= limit <= 50:
        raise DecisionContextError(
            "decision context limit must be between 1 and 50"
        )

    try:
        memory = load_decision_memory(audio_root)
    except DecisionMemoryError as exc:
        raise DecisionContextError(
            f"Decision Memory is invalid: {exc}"
        ) from exc

    query_tokens = set(
        tokenize_intent(intent)
    )
    matches: list[dict[str, Any]] = []
    for entry in memory["entries"]:
        match = _match_entry(
            intent,
            query_tokens,
            entry,
        )
        if match is not None:
            matches.append(match)

    matches.sort(
        key=lambda item: (
            -int(item["exact_intent"]),
            -item["match_count"],
            item["source_intent"],
            item["entry"]["archive_id"],
            item["entry"]["pair_index"],
            item["entry"]["entry_id"],
        )
    )

    observations = [
        _observation_from_match(item)
        for item in matches[:limit]
    ]
    memory_hash = _sha256_json(memory)

    payload: dict[str, Any] = {
        "decision_context_pack_version": DECISION_CONTEXT_PACK_VERSION,
        "retrieval_strategy": RETRIEVAL_STRATEGY,
        "decision_memory_sha256": memory_hash,
        "query": {
            "intent": intent,
            "normalized_intent": normalize_intent(intent),
            "terms": sorted(query_tokens),
            "limit": limit,
        },
        "memory_snapshot": {
            "promotion_count": memory[
                "promotion_count"
            ],
            "entry_count": memory["entry_count"],
        },
        "matched_entry_count": len(matches),
        "returned_entry_count": len(observations),
        "truncated": len(matches) > len(observations),
        "observations": observations,
        "usage": {
            "role": "reference_only",
            "selection_effect": "none",
        },
    }
    payload["context_pack_id"] = (
        "context:" + _sha256_json(payload)[:20]
    )
    return payload


def validate_decision_context_pack(
    data: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise DecisionContextError(
            "Decision Context Pack must be an object"
        )
    if (
        data.get("decision_context_pack_version")
        != DECISION_CONTEXT_PACK_VERSION
    ):
        raise DecisionContextError(
            "unsupported decision_context_pack_version"
        )
    if data.get("retrieval_strategy") != RETRIEVAL_STRATEGY:
        raise DecisionContextError(
            "unsupported Decision Context retrieval strategy"
        )

    memory_hash = data.get(
        "decision_memory_sha256"
    )
    if not isinstance(memory_hash, str) or len(memory_hash) != 64:
        raise DecisionContextError(
            "decision_memory_sha256 must be a 64-character hash"
        )

    query = data.get("query")
    if not isinstance(query, dict):
        raise DecisionContextError(
            "Decision Context query must be an object"
        )
    intent = query.get("intent")
    normalized = query.get("normalized_intent")
    terms = query.get("terms")
    limit = query.get("limit")
    if not isinstance(intent, str) or not intent.strip():
        raise DecisionContextError(
            "Decision Context query intent must be non-empty"
        )
    if normalized != normalize_intent(intent):
        raise DecisionContextError(
            "Decision Context normalized intent does not match intent"
        )
    if terms != tokenize_intent(intent):
        raise DecisionContextError(
            "Decision Context query terms do not match tokenizer"
        )
    if not isinstance(limit, int) or not 1 <= limit <= 50:
        raise DecisionContextError(
            "Decision Context query limit is invalid"
        )

    snapshot = data.get("memory_snapshot")
    if not isinstance(snapshot, dict):
        raise DecisionContextError(
            "Decision Context memory_snapshot must be an object"
        )
    for field in ("promotion_count", "entry_count"):
        if (
            not isinstance(snapshot.get(field), int)
            or snapshot[field] < 0
        ):
            raise DecisionContextError(
                f"Decision Context memory_snapshot {field} is invalid"
            )

    observations = data.get("observations")
    if not isinstance(observations, list):
        raise DecisionContextError(
            "Decision Context observations must be a list"
        )

    matched_count = data.get(
        "matched_entry_count"
    )
    returned_count = data.get(
        "returned_entry_count"
    )
    if (
        not isinstance(matched_count, int)
        or matched_count < 0
    ):
        raise DecisionContextError(
            "matched_entry_count must be non-negative"
        )
    if (
        not isinstance(returned_count, int)
        or returned_count != len(observations)
    ):
        raise DecisionContextError(
            "returned_entry_count does not match observations"
        )
    if returned_count > matched_count:
        raise DecisionContextError(
            "returned_entry_count exceeds matched_entry_count"
        )
    if returned_count > limit:
        raise DecisionContextError(
            "Decision Context observations exceed query limit"
        )
    if data.get("truncated") is not (
        matched_count > returned_count
    ):
        raise DecisionContextError(
            "Decision Context truncated flag is inconsistent"
        )

    seen: set[str] = set()
    query_terms = set(terms)
    for item in observations:
        if not isinstance(item, dict):
            raise DecisionContextError(
                "Decision Context observation must be an object"
            )
        entry_id = item.get("entry_id")
        if not isinstance(entry_id, str) or not entry_id:
            raise DecisionContextError(
                "Decision Context observation entry_id must be a string"
            )
        if entry_id in seen:
            raise DecisionContextError(
                f"duplicate Decision Context entry: {entry_id}"
            )
        seen.add(entry_id)

        source_intent = item.get(
            "source_intent"
        )
        match = item.get("match")
        if (
            not isinstance(source_intent, str)
            or not isinstance(match, dict)
        ):
            raise DecisionContextError(
                f"{entry_id}: source intent/match metadata is invalid"
            )

        source_terms = set(
            tokenize_intent(source_intent)
        )
        matched_terms = sorted(
            query_terms & source_terms
        )
        exact = (
            normalize_intent(intent)
            == normalize_intent(source_intent)
            and bool(normalize_intent(intent))
        )
        if (
            match.get("exact_intent") is not exact
            or match.get("matched_terms") != matched_terms
            or match.get("match_count") != len(matched_terms)
            or match.get("query_term_count") != len(query_terms)
            or match.get("source_term_count") != len(source_terms)
        ):
            raise DecisionContextError(
                f"{entry_id}: match metadata does not recompute"
            )
        if not matched_terms and not exact:
            raise DecisionContextError(
                f"{entry_id}: observation does not match query"
            )

        for field in (
            "winner_recipe",
            "loser_recipe",
            "observed_differences",
        ):
            if not isinstance(item.get(field), dict):
                raise DecisionContextError(
                    f"{entry_id}: {field} must be an object"
                )

    usage = data.get("usage")
    if usage != {
        "role": "reference_only",
        "selection_effect": "none",
    }:
        raise DecisionContextError(
            "Decision Context usage boundary is invalid"
        )

    forbidden = {
        "recommended_candidate",
        "auto_select",
        "preference_score",
        "candidate_ranking",
    }
    serialized_keys: set[str] = set()

    def collect_keys(value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                serialized_keys.add(str(key))
                collect_keys(child)
        elif isinstance(value, list):
            for child in value:
                collect_keys(child)

    collect_keys(data)
    if forbidden & serialized_keys:
        raise DecisionContextError(
            "Decision Context contains an automatic-selection field"
        )

    context_pack_id = data.get(
        "context_pack_id"
    )
    if not isinstance(context_pack_id, str):
        raise DecisionContextError(
            "Decision Context context_pack_id must be a string"
        )
    payload = dict(data)
    payload.pop("context_pack_id", None)
    expected_id = (
        "context:" + _sha256_json(payload)[:20]
    )
    if context_pack_id != expected_id:
        raise DecisionContextError(
            "Decision Context context_pack_id does not match payload"
        )

    return {
        "ok": True,
        "context_pack_id": context_pack_id,
        "matched_entries": matched_count,
        "returned_entries": returned_count,
        "truncated": data["truncated"],
    }


def write_decision_context_pack(
    audio_root: str | Path,
    intent: str,
    output_path: str | Path,
    *,
    limit: int = 6,
) -> Path:
    pack = build_decision_context_pack(
        audio_root,
        intent,
        limit=limit,
    )
    validate_decision_context_pack(pack)
    output = Path(output_path).resolve()
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    output.write_text(
        json.dumps(
            pack,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def load_decision_context_pack(
    path: str | Path,
) -> dict[str, Any]:
    path = Path(path)
    try:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )
    except json.JSONDecodeError as exc:
        raise DecisionContextError(
            "Decision Context Pack contains invalid JSON"
        ) from exc
    if not isinstance(data, dict):
        raise DecisionContextError(
            "Decision Context Pack must contain an object"
        )
    validate_decision_context_pack(data)
    return data


def verify_decision_context_pack_against_memory(
    pack_path: str | Path,
    audio_root: str | Path,
) -> dict[str, Any]:
    pack = load_decision_context_pack(pack_path)
    try:
        memory = load_decision_memory(audio_root)
        validate_decision_memory(memory)
    except DecisionMemoryError as exc:
        raise DecisionContextError(
            f"Decision Memory is invalid: {exc}"
        ) from exc

    current_hash = _sha256_json(memory)
    if pack["decision_memory_sha256"] != current_hash:
        raise DecisionContextError(
            "Decision Context Pack is stale: Decision Memory fingerprint changed"
        )

    rebuilt = build_decision_context_pack(
        audio_root,
        pack["query"]["intent"],
        limit=pack["query"]["limit"],
    )
    if rebuilt != pack:
        raise DecisionContextError(
            "Decision Context Pack does not match deterministic retrieval"
        )

    return {
        "ok": True,
        "context_pack_id": pack[
            "context_pack_id"
        ],
        "fresh": True,
        "returned_entries": pack[
            "returned_entry_count"
        ],
    }
