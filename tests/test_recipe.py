from pathlib import Path

from mgal.recipe import load_recipe


def test_fixture_recipe_loads():
    recipe = load_recipe(Path("fixtures/recipes/sword_slash_heavy.json"))
    assert recipe.id == "sword-slash-heavy-001"
    assert len(recipe.layers) == 2
    assert recipe.normalize is True
