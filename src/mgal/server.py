from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
from urllib.parse import quote, unquote, urlparse
import webbrowser

from .audio import read_wav_metadata


WEB_ROOT = Path(__file__).with_name("web")


def build_catalog(audio_root: str | Path) -> list[dict[str, object]]:
    root = Path(audio_root).resolve()
    if not root.is_dir():
        raise NotADirectoryError(root)

    catalog: list[dict[str, object]] = []
    for path in sorted(root.rglob("*.wav")):
        if not path.is_file():
            continue
        metadata = read_wav_metadata(path)
        relative = path.relative_to(root).as_posix()
        catalog.append(
            {
                "name": path.name,
                "relative_path": relative,
                "duration_ms": metadata.duration_ms,
                "sample_rate": metadata.sample_rate,
                "channels": metadata.channels,
                "sample_width": metadata.sample_width,
                "frames": metadata.frames,
                "url": "/audio/" + quote(relative, safe="/"),
            }
        )
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
        server_version = "MGAL/0.4"

        def log_message(self, format: str, *args: object) -> None:
            print(f"[mgal] {self.address_string()} - {format % args}")

        def do_GET(self) -> None:
            parsed = urlparse(self.path)

            if parsed.path == "/api/audio":
                self._send_json(build_catalog(root))
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
