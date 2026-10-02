from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import time
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

from ..audio import read_wav_metadata
from ..provider import (
    SOURCE_PROVIDER_CONTRACT_VERSION,
    ProviderResult,
    SourceCandidate,
    SourceProviderError,
    SourceRequest,
    validate_provider_result,
)
from ..provenance import source_id_for_hash, source_sha256


STABILITY_API_BASE = "https://api.stability.ai/v2beta/audio"
STABILITY_TEXT_TO_AUDIO_URL = (
    STABILITY_API_BASE + "/stable-audio/text-to-audio"
)
STABILITY_RESULT_URL = STABILITY_API_BASE + "/results/{generation_id}"
STABILITY_MODEL = "stable-audio-3"
STABILITY_TERMS_URL = "https://platform.stability.ai/legal/terms-of-service"
STABILITY_DOCS_URL = "https://platform.stability.ai/docs/api-reference"

MIN_DURATION_SECONDS = 1.0
MAX_DURATION_SECONDS = 380.0
MIN_STEPS = 4
MAX_STEPS = 8
MIN_CFG_SCALE = 1.0
MAX_CFG_SCALE = 25.0
MAX_SEED = 4_294_967_294


class StabilityAudioError(SourceProviderError):
    pass


@dataclass(frozen=True)
class StabilityGeneration:
    generation_id: str
    audio_bytes: bytes
    duration_seconds: float
    seed: int
    steps: int
    cfg_scale: float
    model: str = STABILITY_MODEL


class StabilityTransport(Protocol):
    def generate(
        self,
        *,
        prompt: str,
        duration_seconds: float,
        seed: int,
        steps: int,
        cfg_scale: float,
    ) -> StabilityGeneration:
        ...


class _HTTPResponse(Protocol):
    status: int

    def read(self) -> bytes:
        ...

    def __enter__(self) -> "_HTTPResponse":
        ...

    def __exit__(self, exc_type, exc, tb) -> None:
        ...


def _multipart_body(fields: dict[str, str]) -> tuple[bytes, str]:
    boundary = "----mgal-" + uuid.uuid4().hex
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                ).encode("utf-8"),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )

    chunks.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(chunks), boundary


def _response_error(prefix: str, status: int, body: bytes) -> StabilityAudioError:
    text = body.decode("utf-8", errors="replace").strip()
    if len(text) > 500:
        text = text[:500] + "..."
    return StabilityAudioError(
        f"{prefix} failed with HTTP {status}: {text or '<empty response>'}"
    )


class StabilityHTTPTransport:
    def __init__(
        self,
        *,
        api_key: str,
        poll_interval_seconds: float = 10.0,
        max_wait_seconds: float = 300.0,
        request_timeout_seconds: float = 60.0,
        opener: Callable[..., _HTTPResponse] = urlopen,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key.strip():
            raise StabilityAudioError("Stability API key is empty")
        if poll_interval_seconds <= 0:
            raise StabilityAudioError("poll_interval_seconds must be positive")
        if max_wait_seconds <= 0:
            raise StabilityAudioError("max_wait_seconds must be positive")
        if request_timeout_seconds <= 0:
            raise StabilityAudioError("request_timeout_seconds must be positive")

        self.api_key = api_key
        self.poll_interval_seconds = poll_interval_seconds
        self.max_wait_seconds = max_wait_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.opener = opener
        self.sleeper = sleeper

    def _open(self, request: Request) -> _HTTPResponse:
        try:
            return self.opener(
                request,
                timeout=self.request_timeout_seconds,
            )
        except HTTPError as exc:
            body = exc.read()
            raise _response_error("Stability API request", exc.code, body) from exc
        except URLError as exc:
            raise StabilityAudioError(
                f"Stability API network error: {exc.reason}"
            ) from exc

    def generate(
        self,
        *,
        prompt: str,
        duration_seconds: float,
        seed: int,
        steps: int,
        cfg_scale: float,
    ) -> StabilityGeneration:
        body, boundary = _multipart_body(
            {
                "prompt": prompt,
                "model": STABILITY_MODEL,
                "duration": str(duration_seconds),
                "seed": str(seed),
                "steps": str(steps),
                "cfg_scale": str(cfg_scale),
                "output_format": "wav",
            }
        )

        start_request = Request(
            STABILITY_TEXT_TO_AUDIO_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Stability-Client-ID": "mado-game-audio-loop",
            },
        )

        with self._open(start_request) as response:
            start_body = response.read()
            if response.status != 202:
                raise _response_error(
                    "Stable Audio generation start",
                    response.status,
                    start_body,
                )

        try:
            payload = json.loads(start_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StabilityAudioError(
                "Stable Audio generation start returned invalid JSON"
            ) from exc

        generation_id = payload.get("id") if isinstance(payload, dict) else None
        if not isinstance(generation_id, str) or not generation_id:
            raise StabilityAudioError(
                "Stable Audio generation start response is missing id"
            )

        deadline = time.monotonic() + self.max_wait_seconds
        result_url = STABILITY_RESULT_URL.format(
            generation_id=generation_id
        )

        while True:
            result_request = Request(
                result_url,
                method="GET",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "audio/*",
                    "Stability-Client-ID": "mado-game-audio-loop",
                },
            )
            with self._open(result_request) as response:
                result_body = response.read()
                status = response.status

            if status == 200:
                if not result_body:
                    raise StabilityAudioError(
                        "Stable Audio result returned empty audio"
                    )
                return StabilityGeneration(
                    generation_id=generation_id,
                    audio_bytes=result_body,
                    duration_seconds=duration_seconds,
                    seed=seed,
                    steps=steps,
                    cfg_scale=cfg_scale,
                )

            if status != 202:
                raise _response_error(
                    "Stable Audio result fetch",
                    status,
                    result_body,
                )

            if time.monotonic() >= deadline:
                raise StabilityAudioError(
                    "Stable Audio generation exceeded max wait time"
                )
            self.sleeper(self.poll_interval_seconds)


def _safe_slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned or "generation"


def _seed_for_candidate(seed: str | None, ordinal: int) -> int:
    if seed is None or not seed.strip():
        return 0

    raw = seed.strip()
    try:
        base = int(raw, 10)
    except ValueError:
        import hashlib

        digest = hashlib.sha256(raw.encode("utf-8")).digest()
        base = int.from_bytes(digest[:4], "big")

    if base < 0:
        base = abs(base)
    if base == 0:
        base = 1

    value = ((base - 1 + ordinal - 1) % MAX_SEED) + 1
    return value


def _effective_duration_seconds(duration_ms: int | None) -> float:
    if duration_ms is None:
        return MIN_DURATION_SECONDS

    requested = duration_ms / 1000
    if requested > MAX_DURATION_SECONDS:
        raise StabilityAudioError(
            f"Stable Audio duration exceeds {MAX_DURATION_SECONDS:g} seconds"
        )
    return max(MIN_DURATION_SECONDS, math.ceil(requested * 1000) / 1000)


class StabilityAudioProvider:
    provider_id = "stability-audio"
    provider_kind = "generated"

    def __init__(
        self,
        output_root: str | Path,
        *,
        allow_paid: bool = False,
        api_key_env: str = "STABILITY_API_KEY",
        steps: int = 8,
        cfg_scale: float = 1.0,
        transport: StabilityTransport | None = None,
        poll_interval_seconds: float = 10.0,
        max_wait_seconds: float = 300.0,
    ) -> None:
        self.output_root = Path(output_root).resolve()
        self.allow_paid = allow_paid
        self.api_key_env = api_key_env
        self.steps = steps
        self.cfg_scale = cfg_scale
        self._transport = transport
        self.poll_interval_seconds = poll_interval_seconds
        self.max_wait_seconds = max_wait_seconds

        if not (MIN_STEPS <= steps <= MAX_STEPS):
            raise StabilityAudioError(
                f"steps must be between {MIN_STEPS} and {MAX_STEPS}"
            )
        if not (MIN_CFG_SCALE <= cfg_scale <= MAX_CFG_SCALE):
            raise StabilityAudioError(
                f"cfg_scale must be between {MIN_CFG_SCALE:g} "
                f"and {MAX_CFG_SCALE:g}"
            )

    def describe(self) -> dict[str, object]:
        return {
            "source_provider_contract_version": SOURCE_PROVIDER_CONTRACT_VERSION,
            "provider_id": self.provider_id,
            "provider_kind": self.provider_kind,
            "capabilities": {
                "network": True,
                "generates_audio": True,
                "records_audio": False,
                "paid_generation": True,
                "async_api": True,
                "output_format": "wav",
                "model": STABILITY_MODEL,
                "duration_seconds": {
                    "min": MIN_DURATION_SECONDS,
                    "max": MAX_DURATION_SECONDS,
                },
                "steps": {
                    "min": MIN_STEPS,
                    "max": MAX_STEPS,
                },
                "cfg_scale": {
                    "min": MIN_CFG_SCALE,
                    "max": MAX_CFG_SCALE,
                },
                "requires_explicit_paid_opt_in": True,
                "api_key_env": self.api_key_env,
            },
        }

    def _transport_or_live(self) -> StabilityTransport:
        if self._transport is not None:
            return self._transport

        api_key = os.environ.get(self.api_key_env, "")
        if not api_key:
            raise StabilityAudioError(
                f"missing Stability API key in environment variable "
                f"{self.api_key_env}"
            )
        return StabilityHTTPTransport(
            api_key=api_key,
            poll_interval_seconds=self.poll_interval_seconds,
            max_wait_seconds=self.max_wait_seconds,
        )

    def provide(self, request: SourceRequest) -> ProviderResult:
        request.validate()
        if not self.allow_paid:
            raise StabilityAudioError(
                "paid Stable Audio generation is disabled; "
                "explicitly enable allow_paid / --allow-paid"
            )

        duration_seconds = _effective_duration_seconds(request.duration_ms)
        self.output_root.mkdir(parents=True, exist_ok=True)
        transport = self._transport_or_live()

        candidates: list[SourceCandidate] = []
        request_slug = _safe_slug(request.request_id)

        for ordinal in range(1, request.count + 1):
            seed = _seed_for_candidate(request.seed, ordinal)
            generation = transport.generate(
                prompt=request.intent,
                duration_seconds=duration_seconds,
                seed=seed,
                steps=self.steps,
                cfg_scale=self.cfg_scale,
            )

            output_path = (
                self.output_root
                / f"{request_slug}-{ordinal:02d}-{generation.generation_id[:12]}.wav"
            )
            output_path.write_bytes(generation.audio_bytes)

            try:
                metadata = read_wav_metadata(output_path)
            except Exception as exc:
                output_path.unlink(missing_ok=True)
                raise StabilityAudioError(
                    "Stable Audio API did not return a readable WAV artifact"
                ) from exc

            sha256 = source_sha256(output_path)
            source_id = source_id_for_hash(sha256)

            provenance = {
                "source_id": source_id,
                "sha256": sha256,
                "bytes": output_path.stat().st_size,
                "path_hint": output_path.relative_to(
                    self.output_root
                ).as_posix(),
                "source_type": "generated",
                "origin": {
                    "creator": "Stability AI",
                    "title": None,
                    "url": STABILITY_DOCS_URL,
                },
                "license": {
                    "status": "terms",
                    "expression": "Stability AI Terms of Service",
                    "url": STABILITY_TERMS_URL,
                    "attribution": None,
                    "notes": (
                        "Review current Stability AI terms, acceptable-use "
                        "policy, and applicable plan/API requirements before release."
                    ),
                },
                "generation": {
                    "provider": self.provider_id,
                    "model": generation.model,
                    "prompt": request.intent,
                    "seed": str(generation.seed),
                    "parameters": {
                        "generation_id": generation.generation_id,
                        "requested_duration_ms": request.duration_ms,
                        "api_duration_seconds": generation.duration_seconds,
                        "steps": generation.steps,
                        "cfg_scale": generation.cfg_scale,
                        "output_format": "wav",
                        "endpoint": STABILITY_TEXT_TO_AUDIO_URL,
                    },
                },
                "recording": None,
                "notes": (
                    "Generated through the Stability AI hosted API. "
                    "API credentials are never stored in MGAL provenance."
                ),
                "audio": {
                    "duration_ms": metadata.duration_ms,
                    "sample_rate": metadata.sample_rate,
                    "channels": metadata.channels,
                    "sample_width": metadata.sample_width,
                    "frames": metadata.frames,
                },
            }

            candidates.append(
                SourceCandidate(
                    candidate_id=(
                        f"{self.provider_id}:{ordinal:02d}:{sha256[:12]}"
                    ),
                    provider_id=self.provider_id,
                    provider_kind=self.provider_kind,
                    relative_path=output_path.relative_to(
                        self.output_root
                    ).as_posix(),
                    source_id=source_id,
                    sha256=sha256,
                    bytes=output_path.stat().st_size,
                    duration_ms=metadata.duration_ms,
                    sample_rate=metadata.sample_rate,
                    channels=metadata.channels,
                    sample_width=metadata.sample_width,
                    frames=metadata.frames,
                    provenance=provenance,
                )
            )

        result = ProviderResult(
            source_provider_contract_version=SOURCE_PROVIDER_CONTRACT_VERSION,
            provider_id=self.provider_id,
            provider_kind=self.provider_kind,
            artifact_root=str(self.output_root),
            request=request,
            candidates=tuple(candidates),
        )
        validate_provider_result(result)
        return result
