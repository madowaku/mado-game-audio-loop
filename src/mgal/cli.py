from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audio import scan_audio
from .candidate import load_candidate_board
from .context_pack import (
    build_decision_context_pack,
    verify_decision_context_pack_against_memory,
)
from .decision_memory import (
    decision_memory_view,
    promote_preference_archive,
    verify_decision_memory_against_archives,
)
from .delta_inspector import (
    build_delta_inspector_pack,
    load_delta_inspector_pack,
    verify_delta_inspector_pack_against_current,
)
from .evidence import build_evidence_bundle, verify_evidence_bundle
from .intake import (
    build_provider_intake,
    write_intake_candidate_seed,
)
from .normalizer import normalize_provider_result_file
from .preference import (
    archive_preference_evidence,
    load_preference_evidence,
    replay_preference_evidence,
    validate_preference_evidence,
)
from .preference_recovery import (
    list_portable_preference_archives,
    replay_preference_archive_portable,
    write_preference_relink_map,
)
from .provenance import (
    merge_provenance_ledgers,
    update_provenance_entry,
    validate_provenance_ledger,
    write_provenance_ledger,
)
from .provider import (
    FixtureGeneratedProvider,
    LocalFileProvider,
    SourceRequest,
    provider_result_to_dict,
    write_provider_provenance_ledger,
    write_provider_result,
)
from .providers.stability import StabilityAudioProvider
from .recipe import load_recipe
from .recovery import recover_sources, write_relink_map
from .release import build_release_pack, verify_release_pack
from .render import render_recipe
from .replay import replay_evidence_bundle
from .server import serve
from .variation_brief import (
    create_variation_brief,
    list_variation_briefs,
    load_variation_brief,
    validate_variation_brief,
)


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
    bundle.add_argument(
        "--provenance-ledger",
        help="Optional provenance/license ledger JSON",
    )
    bundle.add_argument(
        "--require-provenance",
        action="store_true",
        help="Reject bundling unless every referenced source has complete provenance",
    )
    bundle.add_argument(
        "--preference-evidence",
        help="Optional Preference Session Evidence JSON to include in the bundle",
    )

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
    replay_bundle.add_argument(
        "--relink-map",
        help="Optional relink-map JSON for moved or renamed source WAV files",
    )

    validate_preference = sub.add_parser(
        "validate-preference",
        help="Validate a Preference Session Evidence JSON file",
    )
    validate_preference.add_argument("evidence")

    replay_preference = sub.add_parser(
        "replay-preference",
        help="Verify Preference Evidence sources and reconstruct pair order",
    )
    replay_preference.add_argument("evidence")
    replay_preference.add_argument(
        "--audio-root",
        required=True,
        help="Folder containing the Candidate source WAV files",
    )
    replay_preference.add_argument(
        "--output",
        "-o",
        help="Optional JSON file for the reconstructed replay plan",
    )

    preference_archive = sub.add_parser(
        "preference-archive",
        help="Archive Preference Evidence inside an MGAL audio workspace",
    )
    preference_archive.add_argument("evidence")
    preference_archive.add_argument(
        "--audio-root",
        required=True,
    )
    preference_archive.add_argument(
        "--archive-id",
        help="Optional stable archive ID",
    )

    preference_list = sub.add_parser(
        "preference-list",
        help="List archived Preference Sessions in an audio workspace",
    )
    preference_list.add_argument(
        "--audio-root",
        required=True,
    )

    preference_recover = sub.add_parser(
        "preference-recover",
        help="Recover moved Preference Archive WAV sources by fingerprint",
    )
    preference_recover.add_argument("archive_id")
    preference_recover.add_argument(
        "--audio-root",
        required=True,
        help="Workspace containing .mgal/preferences",
    )
    preference_recover.add_argument(
        "--search-root",
        required=True,
        help="Folder to scan recursively for matching WAV files",
    )
    preference_recover.add_argument(
        "--output",
        "-o",
        help="Optional relink-map path; defaults to .mgal/preference-relinks/<archive>.json",
    )

    preference_replay_archive = sub.add_parser(
        "preference-replay-archive",
        help="Verify and replay one archived Preference Session",
    )
    preference_replay_archive.add_argument("archive_id")
    preference_replay_archive.add_argument(
        "--audio-root",
        required=True,
        help="Workspace containing .mgal/preferences",
    )
    preference_replay_archive.add_argument(
        "--search-root",
        help="Optional current source library root; defaults to --audio-root",
    )
    preference_replay_archive.add_argument(
        "--relink-map",
        help="Optional Preference relink map for moved or renamed WAV files",
    )
    preference_replay_archive.add_argument(
        "--output",
        "-o",
    )

    decision_promote = sub.add_parser(
        "decision-promote",
        help="Explicitly promote one Preference Archive into Decision Memory",
    )
    decision_promote.add_argument("archive_id")
    decision_promote.add_argument(
        "--audio-root",
        required=True,
    )

    decision_memory = sub.add_parser(
        "decision-memory",
        help="Show the current explicit Decision Memory",
    )
    decision_memory.add_argument(
        "--audio-root",
        required=True,
    )

    decision_memory_verify = sub.add_parser(
        "decision-memory-verify",
        help="Verify Decision Memory against promoted Preference Archives",
    )
    decision_memory_verify.add_argument(
        "--audio-root",
        required=True,
    )

    decision_context = sub.add_parser(
        "decision-context",
        help="Retrieve reference-only Decision Memory context for an intent",
    )
    decision_context.add_argument("intent")
    decision_context.add_argument(
        "--audio-root",
        required=True,
    )
    decision_context.add_argument(
        "--limit",
        type=int,
        default=6,
    )
    decision_context.add_argument(
        "--output",
        "-o",
        help="Optional Context Pack JSON output path",
    )

    decision_context_verify = sub.add_parser(
        "decision-context-verify",
        help="Verify a Decision Context Pack against current Decision Memory",
    )
    decision_context_verify.add_argument("context_pack")
    decision_context_verify.add_argument(
        "--audio-root",
        required=True,
    )

    delta_inspect = sub.add_parser(
        "decision-context-inspect",
        help="Compare the current Recipe with winner/loser Recipes in a Decision Context Pack",
    )
    delta_inspect.add_argument("context_pack")
    delta_inspect.add_argument("recipe")
    delta_inspect.add_argument(
        "--audio-root",
        required=True,
    )
    delta_inspect.add_argument(
        "--output",
        "-o",
        help="Optional Delta Inspector Pack JSON output path",
    )

    delta_verify = sub.add_parser(
        "decision-context-inspect-verify",
        help="Verify a Delta Inspector Pack against current Decision Memory, Context retrieval, Recipe, and sources",
    )
    delta_verify.add_argument("inspector_pack")
    delta_verify.add_argument(
        "--audio-root",
        required=True,
    )

    variation_create = sub.add_parser(
        "variation-brief-create",
        help="Create a human-authored Variation Brief from a Delta Inspector Pack and input JSON",
    )
    variation_create.add_argument("inspector_pack")
    variation_create.add_argument("input_json")
    variation_create.add_argument(
        "--audio-root",
        required=True,
    )
    variation_create.add_argument(
        "--output",
        "-o",
        help="Optional copy of the created Variation Brief",
    )

    variation_list = sub.add_parser(
        "variation-brief-list",
        help="List saved Variation Briefs in an MGAL workspace",
    )
    variation_list.add_argument(
        "--audio-root",
        required=True,
    )

    variation_validate = sub.add_parser(
        "variation-brief-validate",
        help="Validate one saved Variation Brief",
    )
    variation_validate.add_argument("brief")

    provenance_scan = sub.add_parser(
        "provenance-scan",
        help="Create a content-addressed provenance ledger from a WAV library",
    )
    provenance_scan.add_argument("audio_root")
    provenance_scan.add_argument("--output", "-o", required=True)

    provenance_set = sub.add_parser(
        "provenance-set",
        help="Update provenance/license metadata for one ledger source",
    )
    provenance_set.add_argument("ledger")
    provenance_set.add_argument("source")
    provenance_set.add_argument("--source-type")
    provenance_set.add_argument("--creator")
    provenance_set.add_argument("--title")
    provenance_set.add_argument("--origin-url")
    provenance_set.add_argument("--license-status")
    provenance_set.add_argument("--license-expression")
    provenance_set.add_argument("--license-url")
    provenance_set.add_argument("--attribution")
    provenance_set.add_argument("--license-notes")
    provenance_set.add_argument("--provider")
    provenance_set.add_argument("--model")
    provenance_set.add_argument("--prompt")
    provenance_set.add_argument("--seed")
    provenance_set.add_argument("--recorded-by")
    provenance_set.add_argument("--recorded-at")
    provenance_set.add_argument("--device")
    provenance_set.add_argument("--notes")

    validate_ledger = sub.add_parser(
        "validate-ledger",
        help="Validate provenance ledger structure and optional source fingerprints",
    )
    validate_ledger.add_argument("ledger")
    validate_ledger.add_argument("--audio-root")

    provenance_merge = sub.add_parser(
        "provenance-merge",
        help="Merge provenance ledgers by content source_id",
    )
    provenance_merge.add_argument("ledgers", nargs="+")
    provenance_merge.add_argument("--output", "-o", required=True)

    release_pack = sub.add_parser(
        "release-pack",
        help="Build a release-ready WAV + attribution/provenance pack",
    )
    release_pack.add_argument("bundle_dir")
    release_pack.add_argument("--output", "-o", required=True)
    release_pack.add_argument(
        "--name",
        help="Optional release name used for the final WAV filename",
    )

    verify_release = sub.add_parser(
        "verify-release",
        help="Verify a Release / Attribution Pack",
    )
    verify_release.add_argument("pack_dir")

    source_provide = sub.add_parser(
        "source-provide",
        help="Run a Source Provider through the MGAL v1.0 contract",
    )
    source_provide.add_argument(
        "--provider",
        choices=("local", "fixture-generated", "stability"),
        required=True,
    )
    source_provide.add_argument("--request-id", required=True)
    source_provide.add_argument("--intent", required=True)
    source_provide.add_argument("--count", type=int)
    source_provide.add_argument("--hint", action="append", default=[])
    source_provide.add_argument("--duration-ms", type=int)
    source_provide.add_argument("--seed")
    source_provide.add_argument("--audio-root")
    source_provide.add_argument("--provenance-ledger")
    source_provide.add_argument("--artifact-root")
    source_provide.add_argument(
        "--allow-paid",
        action="store_true",
        help="Explicitly allow a paid provider request",
    )
    source_provide.add_argument(
        "--api-key-env",
        default="STABILITY_API_KEY",
        help="Environment variable containing provider API key",
    )
    source_provide.add_argument("--steps", type=int, default=8)
    source_provide.add_argument("--cfg-scale", type=float, default=1.0)
    source_provide.add_argument(
        "--poll-interval",
        type=float,
        default=10.0,
    )
    source_provide.add_argument(
        "--max-wait",
        type=float,
        default=300.0,
    )
    source_provide.add_argument("--output", "-o")
    source_provide.add_argument("--provenance-output")

    intake_seed_board = sub.add_parser(
        "intake-seed-board",
        help="Compile one intake session into an A/B/C Candidate Board",
    )
    intake_seed_board.add_argument(
        "--audio-root",
        required=True,
    )
    intake_seed_board.add_argument(
        "--intake-id",
        required=True,
    )
    intake_seed_board.add_argument(
        "--output",
        "-o",
        required=True,
    )

    provider_intake = sub.add_parser(
        "provider-intake",
        help="Normalize and register Provider candidates in an MGAL audio workspace",
    )
    provider_intake.add_argument("result")
    provider_intake.add_argument(
        "--audio-root",
        required=True,
        help="MGAL audio workspace served by the Audition Board",
    )
    provider_intake.add_argument(
        "--intake-id",
        help="Optional stable intake session ID",
    )

    provider_normalize = sub.add_parser(
        "provider-normalize",
        help="Normalize a saved Provider Result to MGAL canonical WAV",
    )
    provider_normalize.add_argument("result")
    provider_normalize.add_argument(
        "--output-root",
        required=True,
        help="Directory for normalized canonical WAV artifacts",
    )
    provider_normalize.add_argument(
        "--output",
        "-o",
        required=True,
        help="Normalized Provider Result JSON",
    )
    provider_normalize.add_argument(
        "--provenance-output",
        help="Optional normalized Provenance Ledger JSON",
    )

    provider_describe = sub.add_parser(
        "provider-describe",
        help="Describe one Source Provider and its capabilities",
    )
    provider_describe.add_argument(
        "--provider",
        choices=("local", "fixture-generated", "stability"),
        required=True,
    )
    provider_describe.add_argument("--audio-root")
    provider_describe.add_argument("--provenance-ledger")
    provider_describe.add_argument("--artifact-root")
    provider_describe.add_argument(
        "--api-key-env",
        default="STABILITY_API_KEY",
    )

    recover = sub.add_parser(
        "recover-sources",
        help="Find moved or renamed source WAV files by SHA-256",
    )
    recover.add_argument("bundle_dir")
    recover.add_argument(
        "--search-root",
        required=True,
        help="Folder to scan recursively for WAV source matches",
    )
    recover.add_argument(
        "--output",
        "-o",
        help="Write relink-map JSON to this path",
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
            provenance_ledger_path=args.provenance_ledger,
            require_provenance=args.require_provenance,
            preference_evidence_path=args.preference_evidence,
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
                    relink_map_path=args.relink_map,
                ),
                indent=2,
            )
        )
        return 0

    if args.command == "validate-preference":
        evidence = load_preference_evidence(args.evidence)
        print(
            json.dumps(
                validate_preference_evidence(evidence),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "replay-preference":
        result = replay_preference_evidence(
            args.evidence,
            args.audio_root,
        )
        if args.output:
            output = Path(args.output).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "preference-archive":
        evidence = load_preference_evidence(
            args.evidence
        )
        print(
            json.dumps(
                archive_preference_evidence(
                    evidence,
                    args.audio_root,
                    archive_id=args.archive_id,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "preference-list":
        print(
            json.dumps(
                list_portable_preference_archives(
                    args.audio_root,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "preference-recover":
        output = write_preference_relink_map(
            args.audio_root,
            args.archive_id,
            args.search_root,
            args.output,
        )
        print(output)
        return 0

    if args.command == "preference-replay-archive":
        result = replay_preference_archive_portable(
            args.audio_root,
            args.archive_id,
            search_root=args.search_root,
            relink_map_path=args.relink_map,
        )
        if args.output:
            output = Path(args.output).resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "decision-promote":
        print(
            json.dumps(
                promote_preference_archive(
                    args.audio_root,
                    args.archive_id,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "decision-memory":
        print(
            json.dumps(
                decision_memory_view(
                    args.audio_root,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "decision-memory-verify":
        print(
            json.dumps(
                verify_decision_memory_against_archives(
                    args.audio_root,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "decision-context":
        pack = build_decision_context_pack(
            args.audio_root,
            args.intent,
            limit=args.limit,
        )
        if args.output:
            output = Path(args.output).resolve()
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
        print(
            json.dumps(
                pack,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "decision-context-verify":
        print(
            json.dumps(
                verify_decision_context_pack_against_memory(
                    args.context_pack,
                    args.audio_root,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "decision-context-inspect":
        context_pack = json.loads(
            Path(args.context_pack).read_text(
                encoding="utf-8"
            )
        )
        recipe_data = json.loads(
            Path(args.recipe).read_text(
                encoding="utf-8"
            )
        )
        result = build_delta_inspector_pack(
            args.audio_root,
            context_pack,
            recipe_data,
        )
        if args.output:
            output = Path(args.output).resolve()
            output.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            output.write_text(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "decision-context-inspect-verify":
        print(
            json.dumps(
                verify_delta_inspector_pack_against_current(
                    args.inspector_pack,
                    args.audio_root,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "variation-brief-create":
        inspector = load_delta_inspector_pack(
            args.inspector_pack
        )
        human_input = json.loads(
            Path(args.input_json).read_text(
                encoding="utf-8"
            )
        )
        result = create_variation_brief(
            args.audio_root,
            inspector,
            human_input,
        )
        if args.output:
            output = Path(args.output).resolve()
            output.parent.mkdir(
                parents=True,
                exist_ok=True,
            )
            output.write_text(
                json.dumps(
                    result["brief"],
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        print(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "variation-brief-list":
        print(
            json.dumps(
                list_variation_briefs(
                    args.audio_root,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "variation-brief-validate":
        print(
            json.dumps(
                validate_variation_brief(
                    load_variation_brief(
                        args.brief
                    )
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "provenance-scan":
        output = write_provenance_ledger(args.audio_root, args.output)
        print(output)
        return 0

    if args.command == "provenance-set":
        entry = update_provenance_entry(
            args.ledger,
            args.source,
            source_type=args.source_type,
            creator=args.creator,
            title=args.title,
            origin_url=args.origin_url,
            license_status=args.license_status,
            license_expression=args.license_expression,
            license_url=args.license_url,
            attribution=args.attribution,
            license_notes=args.license_notes,
            provider=args.provider,
            model=args.model,
            prompt=args.prompt,
            seed=args.seed,
            recorded_by=args.recorded_by,
            recorded_at=args.recorded_at,
            device=args.device,
            notes=args.notes,
        )
        print(json.dumps(entry, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-ledger":
        print(
            json.dumps(
                validate_provenance_ledger(
                    args.ledger,
                    audio_root=args.audio_root,
                ),
                indent=2,
            )
        )
        return 0

    if args.command == "provenance-merge":
        output = merge_provenance_ledgers(
            args.ledgers,
            args.output,
        )
        print(output)
        return 0

    if args.command == "release-pack":
        output = build_release_pack(
            args.bundle_dir,
            args.output,
            name=args.name,
        )
        print(output)
        return 0

    if args.command == "verify-release":
        print(
            json.dumps(
                verify_release_pack(args.pack_dir),
                indent=2,
            )
        )
        return 0

    if args.command == "intake-seed-board":
        output = write_intake_candidate_seed(
            args.audio_root,
            args.intake_id,
            args.output,
        )
        print(output)
        return 0

    if args.command == "provider-intake":
        print(
            json.dumps(
                build_provider_intake(
                    args.result,
                    args.audio_root,
                    intake_id=args.intake_id,
                ),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "provider-normalize":
        normalized = normalize_provider_result_file(
            args.result,
            args.output_root,
        )
        write_provider_result(normalized, args.output)
        if args.provenance_output:
            write_provider_provenance_ledger(
                normalized,
                args.provenance_output,
            )
        print(
            json.dumps(
                provider_result_to_dict(normalized),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command in {"source-provide", "provider-describe"}:
        if args.provider == "local":
            if not args.audio_root:
                parser = build_parser()
                parser.error("--audio-root is required for provider=local")
            provider = LocalFileProvider(
                args.audio_root,
                getattr(args, "provenance_ledger", None),
            )
        elif args.provider == "fixture-generated":
            artifact_root = getattr(args, "artifact_root", None)
            if not artifact_root:
                parser = build_parser()
                parser.error(
                    "--artifact-root is required for provider=fixture-generated"
                )
            provider = FixtureGeneratedProvider(artifact_root)
        else:
            artifact_root = getattr(args, "artifact_root", None)
            if args.command == "source-provide" and not artifact_root:
                parser = build_parser()
                parser.error(
                    "--artifact-root is required for provider=stability"
                )
            provider = StabilityAudioProvider(
                artifact_root or ".",
                allow_paid=getattr(args, "allow_paid", False),
                api_key_env=getattr(
                    args,
                    "api_key_env",
                    "STABILITY_API_KEY",
                ),
                steps=getattr(args, "steps", 8),
                cfg_scale=getattr(args, "cfg_scale", 1.0),
                poll_interval_seconds=getattr(
                    args,
                    "poll_interval",
                    10.0,
                ),
                max_wait_seconds=getattr(
                    args,
                    "max_wait",
                    300.0,
                ),
            )

        if args.command == "provider-describe":
            print(
                json.dumps(
                    provider.describe(),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        count = args.count
        if count is None:
            count = 1 if args.provider == "stability" else 4

        request = SourceRequest(
            request_id=args.request_id,
            intent=args.intent,
            count=count,
            hints=tuple(args.hint),
            duration_ms=args.duration_ms,
            seed=args.seed,
        )
        result = provider.provide(request)

        if args.output:
            write_provider_result(result, args.output)
        if args.provenance_output:
            write_provider_provenance_ledger(
                result,
                args.provenance_output,
            )

        print(
            json.dumps(
                provider_result_to_dict(result),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "recover-sources":
        if args.output:
            output = write_relink_map(
                args.bundle_dir,
                args.search_root,
                args.output,
            )
            payload = json.loads(Path(output).read_text(encoding="utf-8"))
            payload["relink_map_path"] = str(Path(output).resolve())
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(
                json.dumps(
                    recover_sources(args.bundle_dir, args.search_root),
                    ensure_ascii=False,
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
