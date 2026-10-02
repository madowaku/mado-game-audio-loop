from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from .candidate import CandidateBoardError, parse_candidate_board


PREFERENCE_SESSION_VERSION = "0.1"
_ALLOWED_ALIASES = ("X", "Y", "Z")


class PreferenceEvidenceError(ValueError):
    pass


def _canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_source(audio_root: Path, relative: str) -> Path:
    if Path(relative).is_absolute():
        raise PreferenceEvidenceError(
            f"preference source must be relative: {relative}"
        )
    candidate = (audio_root / relative).resolve()
    try:
        candidate.relative_to(audio_root)
    except ValueError as exc:
        raise PreferenceEvidenceError(
            f"preference source escapes audio root: {relative}"
        ) from exc
    if not candidate.is_file():
        raise PreferenceEvidenceError(
            f"preference source is missing: {relative}"
        )
    return candidate


def _candidate_recipe_sources(
    board_data: dict[str, Any],
    candidate_ids: set[str],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    raw_candidates = board_data.get("candidates", [])
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        candidate_id = item.get("id")
        if candidate_id not in candidate_ids:
            continue
        recipe = item.get("recipe")
        layers = recipe.get("layers") if isinstance(recipe, dict) else None
        if not isinstance(layers, list):
            raise PreferenceEvidenceError(
                f"{candidate_id}: recipe layers are missing"
            )
        sources: list[str] = []
        for layer in layers:
            if not isinstance(layer, dict):
                raise PreferenceEvidenceError(
                    f"{candidate_id}: recipe layer must be an object"
                )
            source = layer.get("source")
            if not isinstance(source, str) or not source:
                raise PreferenceEvidenceError(
                    f"{candidate_id}: recipe layer source must be a string"
                )
            sources.append(source)
        result[candidate_id] = sources
    return result


def _validate_mapping(
    mapping_raw: Any,
    board_ids: set[str],
) -> list[dict[str, str]]:
    if not isinstance(mapping_raw, list):
        raise PreferenceEvidenceError("preference.mapping must be a list")
    if not 2 <= len(mapping_raw) <= 3:
        raise PreferenceEvidenceError(
            "preference mapping must contain two or three candidates"
        )

    aliases: set[str] = set()
    candidate_ids: set[str] = set()
    mapping: list[dict[str, str]] = []

    for index, item in enumerate(mapping_raw):
        if not isinstance(item, dict):
            raise PreferenceEvidenceError(
                f"preference.mapping[{index}] must be an object"
            )
        alias = item.get("alias")
        candidate_id = item.get("candidateId", item.get("candidate_id"))
        if alias not in _ALLOWED_ALIASES:
            raise PreferenceEvidenceError(
                f"unsupported preference alias: {alias}"
            )
        if not isinstance(candidate_id, str) or candidate_id not in board_ids:
            raise PreferenceEvidenceError(
                f"preference mapping references unknown candidate: {candidate_id}"
            )
        if alias in aliases:
            raise PreferenceEvidenceError(
                f"duplicate preference alias: {alias}"
            )
        if candidate_id in candidate_ids:
            raise PreferenceEvidenceError(
                f"duplicate preference candidate: {candidate_id}"
            )
        aliases.add(alias)
        candidate_ids.add(candidate_id)
        mapping.append(
            {
                "alias": alias,
                "candidate_id": candidate_id,
            }
        )

    expected_aliases = set(_ALLOWED_ALIASES[: len(mapping)])
    if aliases != expected_aliases:
        raise PreferenceEvidenceError(
            "preference aliases must be X/Y or X/Y/Z"
        )

    return mapping


def _mapping_lookup(
    mapping: list[dict[str, str]],
) -> tuple[dict[str, str], dict[str, str]]:
    alias_to_candidate = {
        entry["alias"]: entry["candidate_id"]
        for entry in mapping
    }
    candidate_to_alias = {
        entry["candidate_id"]: entry["alias"]
        for entry in mapping
    }
    return alias_to_candidate, candidate_to_alias


def _validate_pairs(
    pairs_raw: Any,
    mapping: list[dict[str, str]],
) -> list[dict[str, str | int]]:
    if not isinstance(pairs_raw, list):
        raise PreferenceEvidenceError("preference.pairs must be a list")

    alias_to_candidate, _ = _mapping_lookup(mapping)
    expected_count = len(mapping) * (len(mapping) - 1) // 2
    if len(pairs_raw) != expected_count:
        raise PreferenceEvidenceError(
            "preference pair count does not cover every unique pair"
        )

    pairs: list[dict[str, str | int]] = []
    seen: set[frozenset[str]] = set()

    for index, raw_pair in enumerate(pairs_raw):
        if not isinstance(raw_pair, list) or len(raw_pair) != 2:
            raise PreferenceEvidenceError(
                f"preference.pairs[{index}] must contain two entries"
            )
        left, right = raw_pair
        if not isinstance(left, dict) or not isinstance(right, dict):
            raise PreferenceEvidenceError(
                f"preference.pairs[{index}] entries must be objects"
            )

        left_alias = left.get("alias")
        right_alias = right.get("alias")
        left_id = left.get("candidateId", left.get("candidate_id"))
        right_id = right.get("candidateId", right.get("candidate_id"))

        if (
            left_alias not in alias_to_candidate
            or right_alias not in alias_to_candidate
            or left_alias == right_alias
        ):
            raise PreferenceEvidenceError(
                f"preference.pairs[{index}] has invalid aliases"
            )
        if (
            alias_to_candidate[left_alias] != left_id
            or alias_to_candidate[right_alias] != right_id
        ):
            raise PreferenceEvidenceError(
                f"preference.pairs[{index}] mapping does not match session mapping"
            )

        unordered = frozenset((str(left_id), str(right_id)))
        if unordered in seen:
            raise PreferenceEvidenceError(
                "preference pair schedule contains a duplicate pair"
            )
        seen.add(unordered)

        pairs.append(
            {
                "index": index,
                "left_alias": str(left_alias),
                "left_candidate_id": str(left_id),
                "right_alias": str(right_alias),
                "right_candidate_id": str(right_id),
            }
        )

    expected_sets: set[frozenset[str]] = set()
    candidate_ids = [entry["candidate_id"] for entry in mapping]
    for left in range(len(candidate_ids)):
        for right in range(left + 1, len(candidate_ids)):
            expected_sets.add(
                frozenset((candidate_ids[left], candidate_ids[right]))
            )
    if seen != expected_sets:
        raise PreferenceEvidenceError(
            "preference pair schedule does not match all candidate combinations"
        )

    return pairs


def _validate_votes(
    votes_raw: Any,
    pairs: list[dict[str, str | int]],
) -> list[dict[str, str | int]]:
    if not isinstance(votes_raw, list):
        raise PreferenceEvidenceError("preference.votes must be a list")
    if len(votes_raw) != len(pairs):
        raise PreferenceEvidenceError(
            "preference evidence requires one vote for every pair"
        )

    votes: list[dict[str, str | int]] = []
    for index, raw_vote in enumerate(votes_raw):
        if not isinstance(raw_vote, dict):
            raise PreferenceEvidenceError(
                f"preference.votes[{index}] must be an object"
            )
        pair = pairs[index]
        winner_alias = raw_vote.get(
            "winnerAlias",
            raw_vote.get("winner_alias"),
        )
        winner_id = raw_vote.get(
            "winnerCandidateId",
            raw_vote.get("winner_candidate_id"),
        )
        loser_id = raw_vote.get(
            "loserCandidateId",
            raw_vote.get("loser_candidate_id"),
        )

        alias_candidate = {
            pair["left_alias"]: pair["left_candidate_id"],
            pair["right_alias"]: pair["right_candidate_id"],
        }
        if winner_alias not in alias_candidate:
            raise PreferenceEvidenceError(
                f"preference.votes[{index}] winner alias is not in pair"
            )
        if alias_candidate[winner_alias] != winner_id:
            raise PreferenceEvidenceError(
                f"preference.votes[{index}] winner identity does not match alias"
            )

        expected_loser = (
            pair["right_candidate_id"]
            if winner_id == pair["left_candidate_id"]
            else pair["left_candidate_id"]
        )
        if loser_id != expected_loser:
            raise PreferenceEvidenceError(
                f"preference.votes[{index}] loser identity does not match pair"
            )

        votes.append(
            {
                "pair_index": index,
                "winner_alias": str(winner_alias),
                "winner_candidate_id": str(winner_id),
                "loser_candidate_id": str(loser_id),
            }
        )

    return votes


def _scores(
    mapping: list[dict[str, str]],
    votes: list[dict[str, str | int]],
) -> dict[str, int]:
    scores = {
        entry["candidate_id"]: 0
        for entry in mapping
    }
    for vote in votes:
        winner_id = str(vote["winner_candidate_id"])
        scores[winner_id] += 1
    return scores


def _winner(scores: dict[str, int]) -> str | None:
    if not scores:
        return None
    best = max(scores.values())
    leaders = [
        candidate_id
        for candidate_id, score in scores.items()
        if score == best
    ]
    return leaders[0] if len(leaders) == 1 else None


def compile_preference_evidence(
    payload: dict[str, Any],
    audio_root: str | Path,
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise PreferenceEvidenceError(
            "preference evidence request must be an object"
        )

    board_data = payload.get("candidate_board")
    preference = payload.get("preference")
    if not isinstance(board_data, dict):
        raise PreferenceEvidenceError(
            "candidate_board must be an object"
        )
    if not isinstance(preference, dict):
        raise PreferenceEvidenceError(
            "preference must be an object"
        )

    try:
        board = parse_candidate_board(board_data)
    except CandidateBoardError as exc:
        raise PreferenceEvidenceError(
            f"candidate board is invalid: {exc}"
        ) from exc

    if preference.get("revealed") is not True:
        raise PreferenceEvidenceError(
            "preference evidence may only be compiled after reveal"
        )

    board_ids = {candidate.id for candidate in board.candidates}
    mapping = _validate_mapping(
        preference.get("mapping"),
        board_ids,
    )
    pairs = _validate_pairs(
        preference.get("pairs"),
        mapping,
    )
    votes = _validate_votes(
        preference.get("votes"),
        pairs,
    )

    scores = _scores(mapping, votes)
    winner_id = _winner(scores)
    applied_id = preference.get(
        "appliedCandidateId",
        preference.get("applied_candidate_id"),
    )
    if applied_id is not None and not isinstance(applied_id, str):
        raise PreferenceEvidenceError(
            "applied candidate id must be string or null"
        )
    if applied_id is not None:
        if winner_id is None or applied_id != winner_id:
            raise PreferenceEvidenceError(
                "applied candidate must match the unique preference winner"
            )
        if board.selected_candidate_id != applied_id:
            raise PreferenceEvidenceError(
                "applied preference winner must match selected Candidate Board decision"
            )

    audio_root_path = Path(audio_root).resolve()
    candidate_ids = {
        entry["candidate_id"]
        for entry in mapping
    }
    sources_by_candidate = _candidate_recipe_sources(
        board_data,
        candidate_ids,
    )

    source_paths = sorted(
        {
            source
            for sources in sources_by_candidate.values()
            for source in sources
        }
    )
    source_index: list[dict[str, Any]] = []
    for relative in source_paths:
        path = _resolve_source(audio_root_path, relative)
        source_index.append(
            {
                "relative_path": relative,
                "sha256": _sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )

    board_sha256 = _sha256_bytes(
        _canonical_json_bytes(board_data)
    )
    score_rows = [
        {
            "candidate_id": entry["candidate_id"],
            "alias": entry["alias"],
            "wins": scores[entry["candidate_id"]],
        }
        for entry in mapping
    ]

    return {
        "preference_session_version": PREFERENCE_SESSION_VERSION,
        "candidate_board_sha256": board_sha256,
        "candidate_board": board_data,
        "mapping": mapping,
        "pairs": pairs,
        "votes": votes,
        "scores": score_rows,
        "winner_candidate_id": winner_id,
        "tie": winner_id is None,
        "applied_candidate_id": applied_id,
        "source_index": {
            "source_count": len(source_index),
            "sources": source_index,
        },
    }


def validate_preference_evidence(
    data: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise PreferenceEvidenceError(
            "preference evidence must be an object"
        )
    if data.get("preference_session_version") != PREFERENCE_SESSION_VERSION:
        raise PreferenceEvidenceError(
            "unsupported preference_session_version"
        )

    board_data = data.get("candidate_board")
    if not isinstance(board_data, dict):
        raise PreferenceEvidenceError(
            "candidate_board must be an object"
        )
    try:
        board = parse_candidate_board(board_data)
    except CandidateBoardError as exc:
        raise PreferenceEvidenceError(
            f"candidate board is invalid: {exc}"
        ) from exc

    expected_board_hash = _sha256_bytes(
        _canonical_json_bytes(board_data)
    )
    if data.get("candidate_board_sha256") != expected_board_hash:
        raise PreferenceEvidenceError(
            "candidate board fingerprint does not match snapshot"
        )

    board_ids = {candidate.id for candidate in board.candidates}
    normalized_mapping = _validate_mapping(
        data.get("mapping"),
        board_ids,
    )

    pairs_raw = data.get("pairs")
    if not isinstance(pairs_raw, list):
        raise PreferenceEvidenceError("pairs must be a list")
    wire_pairs = [
        [
            {
                "alias": item.get("left_alias"),
                "candidate_id": item.get("left_candidate_id"),
            },
            {
                "alias": item.get("right_alias"),
                "candidate_id": item.get("right_candidate_id"),
            },
        ]
        for item in pairs_raw
        if isinstance(item, dict)
    ]
    normalized_pairs = _validate_pairs(
        wire_pairs,
        normalized_mapping,
    )

    votes_raw = data.get("votes")
    if not isinstance(votes_raw, list):
        raise PreferenceEvidenceError("votes must be a list")
    wire_votes = [
        {
            "winner_alias": item.get("winner_alias"),
            "winner_candidate_id": item.get("winner_candidate_id"),
            "loser_candidate_id": item.get("loser_candidate_id"),
        }
        for item in votes_raw
        if isinstance(item, dict)
    ]
    normalized_votes = _validate_votes(
        wire_votes,
        normalized_pairs,
    )

    scores = _scores(
        normalized_mapping,
        normalized_votes,
    )
    winner_id = _winner(scores)
    if data.get("winner_candidate_id") != winner_id:
        raise PreferenceEvidenceError(
            "winner_candidate_id does not match votes"
        )
    if data.get("tie") is not (winner_id is None):
        raise PreferenceEvidenceError(
            "tie flag does not match vote result"
        )

    declared_scores = data.get("scores")
    if not isinstance(declared_scores, list):
        raise PreferenceEvidenceError("scores must be a list")
    score_map: dict[str, int] = {}
    for item in declared_scores:
        if not isinstance(item, dict):
            raise PreferenceEvidenceError(
                "score entry must be an object"
            )
        candidate_id = item.get("candidate_id")
        wins = item.get("wins")
        if not isinstance(candidate_id, str) or not isinstance(wins, int):
            raise PreferenceEvidenceError(
                "score entry has invalid fields"
            )
        score_map[candidate_id] = wins
    if score_map != scores:
        raise PreferenceEvidenceError(
            "scores do not match preference votes"
        )

    applied_id = data.get("applied_candidate_id")
    if applied_id is not None:
        if applied_id != winner_id:
            raise PreferenceEvidenceError(
                "applied candidate does not match preference winner"
            )
        if board.selected_candidate_id != applied_id:
            raise PreferenceEvidenceError(
                "applied candidate does not match Board selection"
            )

    source_index = data.get("source_index")
    if not isinstance(source_index, dict):
        raise PreferenceEvidenceError(
            "source_index must be an object"
        )
    sources = source_index.get("sources")
    count = source_index.get("source_count")
    if not isinstance(sources, list):
        raise PreferenceEvidenceError(
            "source_index.sources must be a list"
        )
    if not isinstance(count, int) or count != len(sources):
        raise PreferenceEvidenceError(
            "source_index.source_count does not match sources"
        )

    seen_sources: set[str] = set()
    for item in sources:
        if not isinstance(item, dict):
            raise PreferenceEvidenceError(
                "source index entry must be an object"
            )
        relative = item.get("relative_path")
        sha256 = item.get("sha256")
        byte_count = item.get("bytes")
        if not isinstance(relative, str) or not relative:
            raise PreferenceEvidenceError(
                "source relative_path must be a string"
            )
        if relative in seen_sources:
            raise PreferenceEvidenceError(
                f"duplicate preference source: {relative}"
            )
        seen_sources.add(relative)
        if not isinstance(sha256, str) or len(sha256) != 64:
            raise PreferenceEvidenceError(
                f"{relative}: sha256 must be 64 characters"
            )
        if not isinstance(byte_count, int) or byte_count < 0:
            raise PreferenceEvidenceError(
                f"{relative}: bytes must be non-negative integer"
            )

    return {
        "ok": True,
        "candidates": len(normalized_mapping),
        "pairs": len(normalized_pairs),
        "winner_candidate_id": winner_id,
        "tie": winner_id is None,
        "applied_candidate_id": applied_id,
        "sources": len(sources),
    }


def load_preference_evidence(
    path: str | Path,
) -> dict[str, Any]:
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PreferenceEvidenceError(
            f"preference evidence contains invalid JSON: {path}"
        ) from exc
    if not isinstance(data, dict):
        raise PreferenceEvidenceError(
            "preference evidence must contain an object"
        )
    validate_preference_evidence(data)
    return data


def replay_preference_evidence(
    evidence_path: str | Path,
    audio_root: str | Path,
) -> dict[str, Any]:
    data = load_preference_evidence(evidence_path)
    return _replay_preference_data(
        data,
        audio_root,
    )


PREFERENCE_ARCHIVE_VERSION = "0.1"


def _archive_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "preference"


def _preference_evidence_hash(data: dict[str, Any]) -> str:
    return _sha256_bytes(_canonical_json_bytes(data))


def _candidate_recipe_payloads(
    board_data: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    raw_candidates = board_data.get("candidates")
    if not isinstance(raw_candidates, list):
        raise PreferenceEvidenceError(
            "candidate board candidates must be a list"
        )
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        candidate_id = item.get("id")
        recipe = item.get("recipe")
        if isinstance(candidate_id, str) and isinstance(recipe, dict):
            result[candidate_id] = recipe
    return result


def _replay_preference_data(
    data: dict[str, Any],
    audio_root: str | Path,
    *,
    source_overrides: dict[str, Path] | None = None,
) -> dict[str, Any]:
    validate_preference_evidence(data)
    audio_root_path = Path(audio_root).resolve()

    source_index = data["source_index"]
    source_lookup: dict[str, dict[str, Any]] = {}
    resolved_sources: dict[str, str] = {}
    for item in source_index["sources"]:
        relative = item["relative_path"]
        if source_overrides is not None and relative in source_overrides:
            path = source_overrides[relative].resolve()
            try:
                target_relative = path.relative_to(
                    audio_root_path
                ).as_posix()
            except ValueError as exc:
                raise PreferenceEvidenceError(
                    f"preference replay override escapes source root: {relative}"
                ) from exc
        else:
            path = _resolve_source(audio_root_path, relative)
            target_relative = relative

        if not path.is_file():
            raise PreferenceEvidenceError(
                f"preference replay source is missing: {relative}"
            )
        if path.stat().st_size != item["bytes"]:
            raise PreferenceEvidenceError(
                f"preference replay source byte size changed: {relative}"
            )
        if _sha256_file(path) != item["sha256"]:
            raise PreferenceEvidenceError(
                f"preference replay source hash changed: {relative}"
            )
        source_lookup[relative] = item
        resolved_sources[relative] = target_relative

    board_data = data["candidate_board"]
    candidate_ids = {
        entry["candidate_id"]
        for entry in data["mapping"]
    }
    sources_by_candidate = _candidate_recipe_sources(
        board_data,
        candidate_ids,
    )
    recipes_by_candidate = _candidate_recipe_payloads(board_data)

    def resolved_recipe(candidate_id: str) -> dict[str, Any]:
        recipe = json.loads(
            json.dumps(
                recipes_by_candidate[candidate_id],
                ensure_ascii=False,
            )
        )
        for layer in recipe.get("layers", []):
            if not isinstance(layer, dict):
                continue
            source = layer.get("source")
            if isinstance(source, str) and source in resolved_sources:
                layer["source"] = resolved_sources[source]
        return recipe

    replay_pairs: list[dict[str, Any]] = []
    for pair in data["pairs"]:
        vote = data["votes"][pair["index"]]
        left_id = pair["left_candidate_id"]
        right_id = pair["right_candidate_id"]
        replay_pairs.append(
            {
                "pair_index": pair["index"],
                "left_alias": pair["left_alias"],
                "left_candidate_id": left_id,
                "left_sources": sources_by_candidate[left_id],
                "left_recipe": resolved_recipe(left_id),
                "right_alias": pair["right_alias"],
                "right_candidate_id": right_id,
                "right_sources": sources_by_candidate[right_id],
                "right_recipe": resolved_recipe(right_id),
                "winner_alias": vote["winner_alias"],
                "winner_candidate_id": vote["winner_candidate_id"],
            }
        )

    return {
        "ok": True,
        "preference_session_version": data[
            "preference_session_version"
        ],
        "candidate_board_sha256": data[
            "candidate_board_sha256"
        ],
        "sources_verified": len(source_lookup),
        "source_resolution": [
            {
                "source": source,
                "target": resolved_sources[source],
                "relinked": resolved_sources[source] != source,
            }
            for source in sorted(resolved_sources)
        ],
        "mapping": data["mapping"],
        "replay_pairs": replay_pairs,
        "winner_candidate_id": data["winner_candidate_id"],
        "tie": data["tie"],
        "applied_candidate_id": data["applied_candidate_id"],
    }


def preference_archive_root(
    audio_root: str | Path,
) -> Path:
    return Path(audio_root).resolve() / ".mgal" / "preferences"


def archive_preference_evidence(
    evidence: dict[str, Any],
    audio_root: str | Path,
    *,
    archive_id: str | None = None,
) -> dict[str, Any]:
    validate_preference_evidence(evidence)
    replay = _replay_preference_data(
        evidence,
        audio_root,
    )

    board = evidence["candidate_board"]
    base_recipe = board.get("base_recipe")
    base_id = (
        base_recipe.get("id")
        if isinstance(base_recipe, dict)
        else "preference"
    )
    if not isinstance(base_id, str):
        base_id = "preference"

    evidence_hash = _preference_evidence_hash(evidence)
    resolved_id = _archive_slug(
        archive_id
        or f"{base_id}-{evidence_hash[:12]}"
    )
    root = preference_archive_root(audio_root)
    session_dir = (root / resolved_id).resolve()
    try:
        session_dir.relative_to(root.resolve())
    except ValueError as exc:
        raise PreferenceEvidenceError(
            "preference archive id escapes archive root"
        ) from exc

    evidence_path = session_dir / "evidence.json"
    manifest_path = session_dir / "manifest.json"

    if manifest_path.is_file() or evidence_path.is_file():
        if not (manifest_path.is_file() and evidence_path.is_file()):
            raise PreferenceEvidenceError(
                f"preference archive is incomplete: {resolved_id}"
            )
        existing_manifest = json.loads(
            manifest_path.read_text(encoding="utf-8")
        )
        if (
            not isinstance(existing_manifest, dict)
            or existing_manifest.get("evidence_sha256")
            != evidence_hash
        ):
            raise PreferenceEvidenceError(
                f"preference archive id already exists for different evidence: {resolved_id}"
            )
        verify_preference_archive(
            audio_root,
            resolved_id,
        )
        return {
            "ok": True,
            "archive_id": resolved_id,
            "archive_dir": str(session_dir),
            "evidence_path": str(evidence_path),
            "reused": True,
        }

    session_dir.mkdir(parents=True, exist_ok=False)
    evidence_path.write_text(
        json.dumps(
            evidence,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    manifest = {
        "preference_archive_version": PREFERENCE_ARCHIVE_VERSION,
        "archive_id": resolved_id,
        "evidence_sha256": evidence_hash,
        "candidate_board_sha256": evidence[
            "candidate_board_sha256"
        ],
        "candidate_count": len(evidence["mapping"]),
        "pair_count": len(evidence["pairs"]),
        "source_count": evidence["source_index"][
            "source_count"
        ],
        "winner_candidate_id": evidence[
            "winner_candidate_id"
        ],
        "tie": evidence["tie"],
        "applied_candidate_id": evidence[
            "applied_candidate_id"
        ],
    }
    manifest_path.write_text(
        json.dumps(
            manifest,
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    verify_preference_archive(
        audio_root,
        resolved_id,
    )

    return {
        "ok": True,
        "archive_id": resolved_id,
        "archive_dir": str(session_dir),
        "evidence_path": str(evidence_path),
        "reused": False,
        "sources_verified": replay["sources_verified"],
    }


def _resolve_archive_session(
    audio_root: str | Path,
    archive_id: str,
) -> Path:
    root = preference_archive_root(audio_root).resolve()
    session_dir = (root / archive_id).resolve()
    try:
        session_dir.relative_to(root)
    except ValueError as exc:
        raise PreferenceEvidenceError(
            "preference archive id escapes archive root"
        ) from exc
    if not session_dir.is_dir():
        raise PreferenceEvidenceError(
            f"preference archive does not exist: {archive_id}"
        )
    return session_dir


def load_preference_archive_metadata(
    audio_root: str | Path,
    archive_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    session_dir = _resolve_archive_session(
        audio_root,
        archive_id,
    )
    manifest_path = session_dir / "manifest.json"
    evidence_path = session_dir / "evidence.json"
    if not manifest_path.is_file() or not evidence_path.is_file():
        raise PreferenceEvidenceError(
            f"preference archive is incomplete: {archive_id}"
        )

    manifest = json.loads(
        manifest_path.read_text(encoding="utf-8")
    )
    if not isinstance(manifest, dict):
        raise PreferenceEvidenceError(
            "preference archive manifest must be an object"
        )
    if (
        manifest.get("preference_archive_version")
        != PREFERENCE_ARCHIVE_VERSION
    ):
        raise PreferenceEvidenceError(
            "unsupported preference_archive_version"
        )
    if manifest.get("archive_id") != archive_id:
        raise PreferenceEvidenceError(
            "preference archive manifest id mismatch"
        )

    evidence = load_preference_evidence(evidence_path)
    evidence_hash = _preference_evidence_hash(evidence)
    if manifest.get("evidence_sha256") != evidence_hash:
        raise PreferenceEvidenceError(
            "preference archive evidence hash mismatch"
        )
    if (
        manifest.get("candidate_board_sha256")
        != evidence["candidate_board_sha256"]
    ):
        raise PreferenceEvidenceError(
            "preference archive board hash mismatch"
        )
    return manifest, evidence


def verify_preference_archive(
    audio_root: str | Path,
    archive_id: str,
) -> dict[str, Any]:
    manifest, evidence = load_preference_archive_metadata(
        audio_root,
        archive_id,
    )

    replay = _replay_preference_data(
        evidence,
        audio_root,
    )
    return {
        "ok": True,
        "archive_id": archive_id,
        "candidate_count": len(evidence["mapping"]),
        "pair_count": len(evidence["pairs"]),
        "source_count": evidence["source_index"][
            "source_count"
        ],
        "sources_verified": replay["sources_verified"],
        "winner_candidate_id": evidence[
            "winner_candidate_id"
        ],
        "tie": evidence["tie"],
        "applied_candidate_id": evidence[
            "applied_candidate_id"
        ],
    }


def list_preference_archives(
    audio_root: str | Path,
) -> list[dict[str, Any]]:
    root = preference_archive_root(audio_root)
    if not root.is_dir():
        return []

    result: list[dict[str, Any]] = []
    for manifest_path in sorted(root.glob("*/manifest.json")):
        archive_id = manifest_path.parent.name
        try:
            report = verify_preference_archive(
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
                    "error": str(exc),
                }
            )
            continue

        result.append(report)
    return result


def load_preference_archive(
    audio_root: str | Path,
    archive_id: str,
) -> dict[str, Any]:
    _, evidence = load_preference_archive_metadata(
        audio_root,
        archive_id,
    )
    _replay_preference_data(
        evidence,
        audio_root,
    )
    return evidence


def replay_preference_archive(
    audio_root: str | Path,
    archive_id: str,
) -> dict[str, Any]:
    evidence = load_preference_archive(
        audio_root,
        archive_id,
    )
    replay = _replay_preference_data(
        evidence,
        audio_root,
    )
    replay["archive_id"] = archive_id
    return replay
