from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audio import scan_audio
from .candidate import load_candidate_board
from .evidence import build_evidence_bundle, verify_evidence_bundle
from .recipe import load_recipe
from .render import render_recipe
from .replay import replay_evidence_bundle
from .server import serve


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mgal", description="MADO Game Audio Loop")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate a recipe JSON file")
    validate.add_argument("recipe")

    validate_board = sub.add_parser(
        "validate-board",
        help="Validate a Candidate Board JSON file",
    )
    validate_board.add_argument("board")

    bundle = sub.add_parser(
        "bundle",
        help="Build an Evidence Bundle from a selected Candidate Board",
    )
    bundle.add_argument("board", help="Candidate Board JSON file")
    bundle.add_argument("--audio-root", required=True, help="Folder containing source WAV files")
    bundle.add_argument("--output", "-o", required=True, help="Evidence Bundle output directory")

    verify_bundle = sub.add_parser(
        "verify-bundle",
        help="Verify Evidence Bundle hashes and file sizes",
    )
    verify_bundle.add_argument("bundle_dir")

    replay_bundle = sub.add_parser(
        "replay-bundle",
        help="Replay an Evidence Bundle against the current source library",
    )
    replay_bundle.add_argument("bundle_dir")
    replay_bundle.add_argument(
        "--audio-root",
        required=True,
        help="Folder containing source WAV files",
    )
    replay_bundle.add_argument(
        "--output",
        help="Optional replayed WAV path outside the Evidence Bundle",
    )

    scan = sub.add_parser("scan", help="Scan a folder for supported audio files")
    scan.add_argument("folder")

    render = sub.add_parser("render", help="Render a recipe to a WAV file")
    render.add_argument("recipe")
    render.add_argument("--output", "-o", required=True)
    render.add_argument("--audio-root", help="Resolve relative recipe sources from this folder")

    browser = sub.add_parser("serve", help="Launch the MGAL local audio workbench")
    browser.add_argument("audio_root", help="Folder containing WAV files")
    browser.add_argument("--host", default="127.0.0.1")
    browser.add_argument("--port", type=int, default=8765)
    browser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the browser automatically",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "validate":
        recipe = load_recipe(args.recipe)
        print(json.dumps({"ok": True, "id": recipe.id, "layers": len(recipe.layers)}))
        return 0

    if args.command == "validate-board":
        board = load_candidate_board(args.board)
        print(
            json.dumps(
                {
                    "ok": True,
                    "base_id": board.base_recipe.id,
                    "candidates": len(board.candidates),
                    "selected_candidate_id": board.selected_candidate_id,
                }
            )
        )
        return 0

    if args.command == "bundle":
        output = build_evidence_bundle(
            args.board,
            args.audio_root,
            args.output,
        )
        print(output)
        return 0

    if args.command == "verify-bundle":
        print(json.dumps(verify_evidence_bundle(args.bundle_dir), indent=2))
        return 0

    if args.command == "replay-bundle":
        print(
            json.dumps(
                replay_evidence_bundle(
                    args.bundle_dir,
                    args.audio_root,
                    output_path=args.output,
                ),
                indent=2,
            )
        )
        return 0

    if args.command == "scan":
        print(json.dumps(scan_audio(args.folder), ensure_ascii=False, indent=2))
        return 0

    if args.command == "render":
        recipe_path = Path(args.recipe).resolve()
        recipe = load_recipe(recipe_path)
        output = render_recipe(
            recipe,
            recipe_path,
            Path(args.output).resolve(),
            source_root=Path(args.audio_root).resolve() if args.audio_root else None,
        )
        print(output)
        return 0

    if args.command == "serve":
        serve(
            audio_root=args.audio_root,
            host=args.host,
            port=args.port,
            open_browser=not args.no_browser,
        )
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
