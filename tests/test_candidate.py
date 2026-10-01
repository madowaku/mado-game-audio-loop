import json
from pathlib import Path

import pytest

from mgal.candidate import CandidateBoardError, load_candidate_board


def _recipe(recipe_id: str) -> dict:
    return {
        "recipe_version": "0.1",
        "id": recipe_id,
        "intent": "heavy sword slash",
        "layers": [
            {"source": "metal.wav", "gain": 0.8, "offset_ms": 20}
        ],
        "processing": {"normalize": True, "fade_out_ms": 0},
    }


def test_candidate_board_loads(tmp_path: Path):
    base_id = "heavy-sword-base"
    a_id = "heavy-sword-base-a"
    b_id = "heavy-sword-base-b"
    board_path = tmp_path / "board.json"
    board_path.write_text(
        json.dumps(
            {
                "candidate_board_version": "0.1",
                "intent": "heavy sword slash",
                "base_recipe": _recipe(base_id),
                "active_candidate_id": a_id,
                "selected_candidate_id": b_id,
                "candidates": [
                    {
                        "id": a_id,
                        "label": "A",
                        "parent_recipe_id": base_id,
                        "revision": 1,
                        "lineage": [
                            {
                                "from_recipe_id": base_id,
                                "action": "fork",
                                "revision": 1,
                            }
                        ],
                        "recipe": _recipe(a_id),
                        "decision": {"status": "favorite", "reason": "good body"},
                    },
                    {
                        "id": b_id,
                        "label": "B",
                        "parent_recipe_id": a_id + "@r1",
                        "revision": 2,
                        "lineage": [
                            {
                                "from_recipe_id": base_id,
                                "action": "fork",
                                "revision": 1,
                            },
                            {
                                "from_recipe_id": a_id + "@r1",
                                "action": "copy",
                                "revision": 2,
                            },
                        ],
                        "recipe": _recipe(b_id),
                        "decision": {"status": "selected", "reason": "clearer hit"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    board = load_candidate_board(board_path)

    assert board.base_recipe.id == base_id
    assert len(board.candidates) == 2
    assert board.selected_candidate_id == b_id
    assert board.candidates[1].parent_recipe_id == a_id + "@r1"


def test_candidate_board_rejects_selected_id_mismatch(tmp_path: Path):
    base_id = "base"
    a_id = "base-a"
    board_path = tmp_path / "bad-board.json"
    board_path.write_text(
        json.dumps(
            {
                "candidate_board_version": "0.1",
                "intent": "test",
                "base_recipe": _recipe(base_id),
                "active_candidate_id": a_id,
                "selected_candidate_id": None,
                "candidates": [
                    {
                        "id": a_id,
                        "label": "A",
                        "parent_recipe_id": base_id,
                        "revision": 1,
                        "lineage": [
                            {
                                "from_recipe_id": base_id,
                                "action": "fork",
                                "revision": 1,
                            }
                        ],
                        "recipe": _recipe(a_id),
                        "decision": {"status": "selected", "reason": "winner"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(CandidateBoardError):
        load_candidate_board(board_path)
