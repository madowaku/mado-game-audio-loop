from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audio import scan_audio
from .recipe import load_recipe
from .render import render_recipe


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mgal", description="MADO Game Audio Loop")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate a recipe JSON file")
    validate.add_argument("recipe")

    scan = sub.add_parser("scan", help="Scan a folder for supported audio files")
    scan.add_argument("folder")

    render = sub.add_parser("render", help="Render a recipe to a WAV file")
    render.add_argument("recipe")
    render.add_argument("--output", "-o", required=True)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "validate":
        recipe = load_recipe(args.recipe)
        print(json.dumps({"ok": True, "id": recipe.id, "layers": len(recipe.layers)}))
        return 0

    if args.command == "scan":
        print(json.dumps(scan_audio(args.folder), ensure_ascii=False, indent=2))
        return 0

    if args.command == "render":
        recipe_path = Path(args.recipe).resolve()
        recipe = load_recipe(recipe_path)
        output = render_recipe(recipe, recipe_path, Path(args.output).resolve())
        print(output)
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
