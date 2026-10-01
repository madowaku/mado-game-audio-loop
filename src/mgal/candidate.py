from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .recipe import Recipe, RecipeError, parse_recipe


ALLOWED_DECISIONS = {"undecided", "favorite", "reject", "selected"}
ALLOWED_LINEAGE_ACTIONS = {"fork", "copy"}


class CandidateBoardError(ValueError):
    pass


@dataclass(frozen=True)
class CandidateDecision:
    status: str
    reason: str


@dataclass(frozen=True)
class LineageEvent:
    from_recipe_id: str
    action: str
    revision: int


@dataclass(frozen=True)
class CandidateSnapshot:
    id: str
    label: str
    parent_recipe_id: str
    revision: int
    lineage: tuple[LineageEvent, ...]
    recipe: Recipe
    decision: CandidateDecision


@dataclass(frozen=True)
class CandidateBoard:
    candidate_board_version: str
    intent: str
    base_recipe: Recipe
    active_candidate_id: str | None
    selected_candidate_id: str | None
    candidates: tuple[CandidateSnapshot, ...]


def _require(data: dict[str, Any], key: str, expected_type: type) -> Any:
    if key not in data:
        raise CandidateBoardError(f"missing required field: {key}")
    value = data[key]
    if not isinstance(value, expected_type):
        raise CandidateBoardError(f"{key} must be {expected_type.__name__}")
    return value


def _parse_lineage(
    candidate_id: str,
    parent_recipe_id: str,
    revision: int,
    raw_lineage: list[Any],
) -> tuple[LineageEvent, ...]:
    if not raw_lineage:
        raise CandidateBoardError(f"{candidate_id}: lineage must not be empty")

    events: list[LineageEvent] = []
    previous_revision = 0

    for index, raw_event in enumerate(raw_lineage):
        if not isinstance(raw_event, dict):
            raise CandidateBoardError(
                f"{candidate_id}: lineage[{index}] must be an object"
            )
        from_recipe_id = _require(raw_event, "from_recipe_id", str)
        action = _require(raw_event, "action", str)
        event_revision = _require(raw_event, "revision", int)

        if action not in ALLOWED_LINEAGE_ACTIONS:
            raise CandidateBoardError(
                f"{candidate_id}: unsupported lineage action: {action}"
            )
        if event_revision <= previous_revision:
            raise CandidateBoardError(
                f"{candidate_id}: lineage revisions must increase"
            )

        events.append(
            LineageEvent(
                from_recipe_id=from_recipe_id,
                action=action,
                revision=event_revision,
            )
        )
        previous_revision = event_revision

    if events[-1].revision != revision:
        raise CandidateBoardError(
            f"{candidate_id}: last lineage revision must match candidate revision"
        )
    if events[-1].from_recipe_id != parent_recipe_id:
        raise CandidateBoardError(
            f"{candidate_id}: parent_recipe_id must match latest lineage source"
        )

    return tuple(events)


def parse_candidate_board(data: dict[str, Any]) -> CandidateBoard:
    version = _require(data, "candidate_board_version", str)
    intent = _require(data, "intent", str)
    raw_base = _require(data, "base_recipe", dict)
    raw_candidates = _require(data, "candidates", list)

    if version != "0.1":
        raise CandidateBoardError(f"unsupported candidate_board_version: {version}")
    if not raw_candidates:
        raise CandidateBoardError("candidates must not be empty")

    try:
        base_recipe = parse_recipe(raw_base)
    except RecipeError as exc:
        raise CandidateBoardError(f"invalid base_recipe: {exc}") from exc

    candidates: list[CandidateSnapshot] = []
    ids: set[str] = set()
    selected_ids: list[str] = []

    for index, item in enumerate(raw_candidates):
        if not isinstance(item, dict):
            raise CandidateBoardError(f"candidates[{index}] must be an object")

        candidate_id = _require(item, "id", str)
        label = _require(item, "label", str)
        parent_recipe_id = _require(item, "parent_recipe_id", str)
        revision = _require(item, "revision", int)
        raw_lineage = _require(item, "lineage", list)
        raw_recipe = _require(item, "recipe", dict)
        raw_decision = _require(item, "decision", dict)

        if candidate_id in ids:
            raise CandidateBoardError(f"duplicate candidate id: {candidate_id}")
        if revision < 1:
            raise CandidateBoardError(f"{candidate_id}: revision must be >= 1")

        lineage = _parse_lineage(
            candidate_id,
            parent_recipe_id,
            revision,
            raw_lineage,
        )

        try:
            recipe = parse_recipe(raw_recipe)
        except RecipeError as exc:
            raise CandidateBoardError(f"{candidate_id}: invalid recipe: {exc}") from exc
        if recipe.id != candidate_id:
            raise CandidateBoardError(
                f"{candidate_id}: embedded recipe id must match candidate id"
            )

        status = _require(raw_decision, "status", str)
        reason = _require(raw_decision, "reason", str)
        if status not in ALLOWED_DECISIONS:
            raise CandidateBoardError(
                f"{candidate_id}: unsupported decision status: {status}"
            )
        if status == "selected":
            selected_ids.append(candidate_id)

        ids.add(candidate_id)
        candidates.append(
            CandidateSnapshot(
                id=candidate_id,
                label=label,
                parent_recipe_id=parent_recipe_id,
                revision=revision,
                lineage=lineage,
                recipe=recipe,
                decision=CandidateDecision(status=status, reason=reason),
            )
        )

    if len(selected_ids) > 1:
        raise CandidateBoardError("at most one candidate may be selected")

    active_candidate_id = data.get("active_candidate_id")
    if active_candidate_id is not None and not isinstance(active_candidate_id, str):
        raise CandidateBoardError("active_candidate_id must be string or null")
    if active_candidate_id is not None and active_candidate_id not in ids:
        raise CandidateBoardError("active_candidate_id must reference a candidate")

    selected_candidate_id = data.get("selected_candidate_id")
    if selected_candidate_id is not None and not isinstance(selected_candidate_id, str):
        raise CandidateBoardError("selected_candidate_id must be string or null")
    if selected_candidate_id is not None and selected_candidate_id not in ids:
        raise CandidateBoardError("selected_candidate_id must reference a candidate")

    actual_selected = selected_ids[0] if selected_ids else None
    if selected_candidate_id != actual_selected:
        raise CandidateBoardError(
            "selected_candidate_id must match the candidate with decision.status=selected"
        )

    return CandidateBoard(
        candidate_board_version=version,
        intent=intent,
        base_recipe=base_recipe,
        active_candidate_id=active_candidate_id,
        selected_candidate_id=selected_candidate_id,
        candidates=tuple(candidates),
    )


def load_candidate_board(path: str | Path) -> CandidateBoard:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CandidateBoardError("candidate board document must be an object")
    return parse_candidate_board(data)
