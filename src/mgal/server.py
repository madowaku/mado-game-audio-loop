from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse
import webbrowser

from .audio import read_wav_metadata
from .context_pack import (
    DecisionContextError,
    build_decision_context_pack,
)
from .delta_inspector import (
    DeltaInspectorError,
    build_delta_inspector_pack,
)
from .variation_brief import (
    VariationBriefError,
    create_variation_brief,
    list_variation_briefs,
)
from .decision_memory import (
    DecisionMemoryError,
    decision_memory_view,
    load_decision_memory,
    promote_preference_archive,
)
from .preference import (
    PreferenceEvidenceError,
    archive_preference_evidence,
    compile_preference_evidence,
)
from .preference_recovery import (
    PreferenceRecoveryError,
    list_portable_preference_archives,
    recover_preference_sources,
    replay_preference_archive_portable,
    write_preference_relink_map,
)
from .intake import (
    ProviderIntakeError,
    build_intake_candidate_seed,
    load_intake_catalog,
)


WEB_ROOT = Path(__file__).with_name("web")


def build_catalog(audio_root: str | Path) -> list[dict[str, object]]:
    root = Path(audio_root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)

    intake_catalog = load_intake_catalog(root)

    catalog: list[dict[str, object]] = []
    for path in sorted(root.rglob("*.wav")):
        if not path.is_file():
            continue
        metadata = read_wav_metadata(path)
        relative = path.relative_to(root).as_posix()
        row: dict[str, object] = {
            "name": path.name,
            "relative_path": relative,
            "duration_ms": metadata.duration_ms,
            "sample_rate": metadata.sample_rate,
            "channels": metadata.channels,
            "sample_width": metadata.sample_width,
            "frames": metadata.frames,
            "bytes": path.stat().st_size,
            "url": "/audio/" + quote(relative, safe="/"),
        }
        intake = intake_catalog.get(relative)
        if intake is not None:
            row["intake"] = intake
        catalog.append(row)
    return catalog


def resolve_audio_path(audio_root: Path, relative_path: str) -> Path:
    root = audio_root.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PermissionError("audio path escapes configured root") from exc
    if not candidate.is_file():
        raise FileNotFoundError(candidate)
    return candidate


def _content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def make_handler(audio_root: str | Path) -> type[BaseHTTPRequestHandler]:
    root = Path(audio_root).resolve()

    class MGALHandler(BaseHTTPRequestHandler):
        server_version = "MGAL/2.5"

        def log_message(self, format: str, *args: object) -> None:
            print(f"[mgal] {self.address_string()} - {format % args}")

        def do_GET(self) -> None:
            parsed = urlparse(self.path)

            if parsed.path == "/api/audio":
                self._send_json(build_catalog(root))
                return

            if parsed.path == "/api/preferences":
                archives = list_portable_preference_archives(root)
                try:
                    memory = load_decision_memory(root)
                    promoted_hashes = {
                        item["archive_evidence_sha256"]
                        for item in memory["promotions"]
                    }
                except DecisionMemoryError:
                    promoted_hashes = set()

                for entry in archives:
                    evidence_hash = entry.get(
                        "archive_evidence_sha256"
                    )
                    entry["promotable"] = (
                        evidence_hash is not None
                    )
                    entry["promoted"] = (
                        evidence_hash in promoted_hashes
                    )
                self._send_json(archives)
                return

            if parsed.path == "/api/materialized-recipe-sets":
                self._send_json(
                    list_materialized_recipe_sets(root)
                )
                return

            if parsed.path == "/api/materialized-recipe-sets":
                raw_length = self.headers.get("Content-Length")
                try:
                    content_length = int(raw_length or "0")
                except ValueError:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "invalid Content-Length",
                    )
                    return
                if content_length <= 0 or content_length > 2_000_000:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "materialization payload size is invalid",
                    )
                    return
                try:
                    request_data = json.loads(
                        self.rfile.read(content_length).decode("utf-8")
                    )
                except (
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                ):
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "request body must be valid JSON",
                    )
                    return
                if not isinstance(request_data, dict):
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "request body must contain an object",
                    )
                    return
                try:
                    payload = materialize_saved_candidate_plan(
                        root,
                        request_data.get("plan_id"),
                        request_data.get("current_recipe"),
                    )
                except RecipeMaterializerError as exc:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        str(exc),
                    )
                    return
                self._send_json(payload)
                return

            if parsed.path == "/api/candidate-plans":
                self._send_json(
                    list_candidate_plans(root)
                )
                return

            if parsed.path == "/api/variation-briefs":
                self._send_json(
                    list_variation_briefs(root)
                )
                return

            if parsed.path == "/api/decision-memory":
                try:
                    payload = decision_memory_view(root)
                except DecisionMemoryError as exc:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        str(exc),
                    )
                    return
                self._send_json(payload)
                return

            if parsed.path == "/api/decision-context":
                params = parse_qs(parsed.query)
                intent_values = params.get("intent", [])
                limit_values = params.get("limit", ["6"])
                intent_value = (
                    intent_values[0]
                    if intent_values
                    else ""
                )
                try:
                    limit_value = int(limit_values[0])
                except (TypeError, ValueError):
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "decision context limit must be an integer",
                    )
                    return
                try:
                    payload = build_decision_context_pack(
                        root,
                        intent_value,
                        limit=limit_value,
                    )
                except DecisionContextError as exc:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        str(exc),
                    )
                    return
                self._send_json(payload)
                return

            if (
                parsed.path.startswith("/api/preferences/")
                and parsed.path.endswith("/replay")
            ):
                encoded_id = parsed.path[
                    len("/api/preferences/") : -len("/replay")
                ].strip("/")
                archive_id = unquote(encoded_id)
                try:
                    payload = replay_preference_archive_portable(
                        root,
                        archive_id,
                    )
                except (
                    PreferenceEvidenceError,
                    PreferenceRecoveryError,
                ) as exc:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        str(exc),
                    )
                    return
                self._send_json(payload)
                return

            if (
                parsed.path.startswith("/api/intakes/")
                and parsed.path.endswith("/seed-board")
            ):
                encoded_id = parsed.path[
                    len("/api/intakes/") : -len("/seed-board")
                ].strip("/")
                intake_id = unquote(encoded_id)
                try:
                    payload = build_intake_candidate_seed(
                        root,
                        intake_id,
                    )
                except ProviderIntakeError as exc:
                    self._send_json_error(
                        HTTPStatus.NOT_FOUND,
                        str(exc),
                    )
                    return
                self._send_json(payload)
                return

            if parsed.path.startswith("/audio/"):
                relative = unquote(parsed.path.removeprefix("/audio/"))
                try:
                    path = resolve_audio_path(root, relative)
                except PermissionError:
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return
                except FileNotFoundError:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                self._send_file(path)
                return

            if parsed.path in {"/", "/index.html"}:
                self._send_file(WEB_ROOT / "index.html")
                return

            if parsed.path in {"/app.js", "/style.css"}:
                self._send_file(WEB_ROOT / parsed.path.lstrip("/"))
                return

            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)

            if parsed.path == "/api/candidate-plans":
                raw_length = self.headers.get("Content-Length")
                try:
                    content_length = int(raw_length or "0")
                except ValueError:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "invalid Content-Length",
                    )
                    return
                if content_length <= 0 or content_length > 200_000:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "candidate plan payload size is invalid",
                    )
                    return
                try:
                    request_data = json.loads(
                        self.rfile.read(content_length).decode("utf-8")
                    )
                except (
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                ):
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "request body must be valid JSON",
                    )
                    return
                if not isinstance(request_data, dict):
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "request body must contain an object",
                    )
                    return
                try:
                    payload = create_candidate_plan_from_brief_id(
                        root,
                        request_data.get("brief_id"),
                    )
                except CandidatePlanError as exc:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        str(exc),
                    )
                    return
                self._send_json(payload)
                return

            if parsed.path == "/api/variation-briefs":
                raw_length = self.headers.get("Content-Length")
                try:
                    content_length = int(raw_length or "0")
                except ValueError:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "invalid Content-Length",
                    )
                    return
                if content_length <= 0 or content_length > 2_000_000:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "variation brief payload size is invalid",
                    )
                    return
                try:
                    request_data = json.loads(
                        self.rfile.read(content_length).decode("utf-8")
                    )
                except (
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                ):
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "request body must be valid JSON",
                    )
                    return
                if not isinstance(request_data, dict):
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "request body must contain an object",
                    )
                    return
                try:
                    payload = create_variation_brief(
                        root,
                        request_data.get("inspector"),
                        request_data.get("human_input"),
                    )
                except VariationBriefError as exc:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        str(exc),
                    )
                    return
                self._send_json(payload)
                return

            if parsed.path == "/api/decision-context-inspect":
                raw_length = self.headers.get("Content-Length")
                try:
                    content_length = int(raw_length or "0")
                except ValueError:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "invalid Content-Length",
                    )
                    return

                if content_length <= 0 or content_length > 2_000_000:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "delta inspector payload size is invalid",
                    )
                    return

                try:
                    body = self.rfile.read(content_length)
                    request_data = json.loads(
                        body.decode("utf-8")
                    )
                except (
                    UnicodeDecodeError,
                    json.JSONDecodeError,
                ):
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "request body must be valid JSON",
                    )
                    return

                if not isinstance(request_data, dict):
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        "request body must contain an object",
                    )
                    return

                context_pack = request_data.get(
                    "context_pack"
                )
                current_recipe = request_data.get(
                    "current_recipe"
                )
                try:
                    payload = build_delta_inspector_pack(
                        root,
                        context_pack,
                        current_recipe,
                    )
                except DeltaInspectorError as exc:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        str(exc),
                    )
                    return

                self._send_json(payload)
                return

            if (
                parsed.path.startswith("/api/preferences/")
                and parsed.path.endswith("/promote")
            ):
                encoded_id = parsed.path[
                    len("/api/preferences/") : -len("/promote")
                ].strip("/")
                archive_id = unquote(encoded_id)
                try:
                    payload = promote_preference_archive(
                        root,
                        archive_id,
                    )
                except DecisionMemoryError as exc:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        str(exc),
                    )
                    return
                self._send_json(payload)
                return

            if (
                parsed.path.startswith("/api/preferences/")
                and parsed.path.endswith("/recover")
            ):
                encoded_id = parsed.path[
                    len("/api/preferences/") : -len("/recover")
                ].strip("/")
                archive_id = unquote(encoded_id)
                try:
                    recovery = recover_preference_sources(
                        root,
                        archive_id,
                        root,
                    )
                    output = write_preference_relink_map(
                        root,
                        archive_id,
                        root,
                    )
                    replay = (
                        replay_preference_archive_portable(
                            root,
                            archive_id,
                        )
                        if recovery["complete"]
                        else None
                    )
                except (
                    PreferenceEvidenceError,
                    PreferenceRecoveryError,
                    OSError,
                    json.JSONDecodeError,
                ) as exc:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        str(exc),
                    )
                    return
                self._send_json(
                    {
                        "ok": recovery["complete"],
                        "archive_id": archive_id,
                        "relink_map": str(output),
                        "recovery": recovery,
                        "source_status": (
                            replay["source_status"]
                            if replay is not None
                            else "unresolved"
                        ),
                        "source_resolution": (
                            replay["source_resolution"]
                            if replay is not None
                            else []
                        ),
                    }
                )
                return

            if parsed.path not in {
                "/api/preference-evidence",
                "/api/preference-archive",
            }:
                self.send_error(HTTPStatus.NOT_FOUND)
                return

            raw_length = self.headers.get("Content-Length")
            try:
                content_length = int(raw_length or "0")
            except ValueError:
                self._send_json_error(
                    HTTPStatus.BAD_REQUEST,
                    "invalid Content-Length",
                )
                return

            if content_length <= 0 or content_length > 2_000_000:
                self._send_json_error(
                    HTTPStatus.BAD_REQUEST,
                    "preference evidence payload size is invalid",
                )
                return

            try:
                body = self.rfile.read(content_length)
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._send_json_error(
                    HTTPStatus.BAD_REQUEST,
                    "request body must be valid JSON",
                )
                return

            if not isinstance(payload, dict):
                self._send_json_error(
                    HTTPStatus.BAD_REQUEST,
                    "request body must contain an object",
                )
                return

            try:
                evidence = compile_preference_evidence(
                    payload,
                    root,
                )
            except PreferenceEvidenceError as exc:
                self._send_json_error(
                    HTTPStatus.BAD_REQUEST,
                    str(exc),
                )
                return

            if parsed.path == "/api/preference-archive":
                try:
                    archive = archive_preference_evidence(
                        evidence,
                        root,
                    )
                except PreferenceEvidenceError as exc:
                    self._send_json_error(
                        HTTPStatus.BAD_REQUEST,
                        str(exc),
                    )
                    return
                self._send_json(
                    {
                        "evidence": evidence,
                        "archive": archive,
                    }
                )
                return

            self._send_json(evidence)

        def _send_json_error(
            self,
            status: HTTPStatus,
            message: str,
        ) -> None:
            body = json.dumps(
                {"error": message},
                ensure_ascii=False,
            ).encode("utf-8")
            self.send_response(status)
            self.send_header(
                "Content-Type",
                "application/json; charset=utf-8",
            )
            self.send_header(
                "Content-Length",
                str(len(body)),
            )
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, path: Path) -> None:
            if not path.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", _content_type(path))
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return MGALHandler


def serve(
    audio_root: str | Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    root = Path(audio_root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)

    server = ThreadingHTTPServer((host, port), make_handler(root))
    url = f"http://{host}:{port}"
    print(f"MGAL Candidate Board: {url}")
    print(f"Audio root: {root}")
    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping MGAL server.")
    finally:
        server.server_close()
