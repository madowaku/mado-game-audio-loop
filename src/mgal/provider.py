from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Protocol
import wave
from array import array

from .audio import read_wav_metadata
from .provenance import (
    load_provenance_ledger,
    source_id_for_hash,
    source_sha256,
)


SOURCE_PROVIDER_CONTRACT_VERSION = "1.0"
PROVIDER_KINDS = {
    "local_file",
    "generated",
    "recorded",
    "recipe",
    "other",
}


class SourceProviderError(ValueError):
    pass


@dataclass(frozen=True)
class SourceRequest:
    request_id: str
    intent: str
    count: int = 4
    hints: tuple[str, ...] = ()
    duration_ms: int | None = None
    seed: str | None = None

    def validate(self) -> None:
        if not self.request_id.strip():
            raise SourceProviderError("request_id must not be empty")
        if not self.intent.strip():
            raise SourceProviderError("intent must not be empty")
        if self.count < 1 or self.count > 32:
            raise SourceProviderError("count must be between 1 and 32")
        if self.duration_ms is not None and self.duration_ms <= 0:
            raise SourceProviderError("duration_ms must be positive")


@dataclass(frozen=True)
class SourceCandidate:
    candidate_id: str
    provider_id: str
    provider_kind: str
    relative_path: str
    source_id: str
    sha256: str
    bytes: int
    duration_ms: int
    sample_rate: int
    channels: int
    sample_width: int
    frames: int
    provenance: dict[str, Any]


@dataclass(frozen=True)
class ProviderResult:
    source_provider_contract_version: str
    provider_id: str
    provider_kind: str
    artifact_root: str
    request: SourceRequest
    candidates: tuple[SourceCandidate, ...]


class SourceProvider(Protocol):
    provider_id: str
    provider_kind: str

    def describe(self) -> dict[str, Any]:
        ...

    def provide(self, request: SourceRequest) -> ProviderResult:
        ...


def _default_provenance(
    path: Path,
    root: Path,
    *,
    source_type: str = "unknown",
) -> dict[str, Any]:
    sha256 = source_sha256(path)
    metadata = read_wav_metadata(path)
    return {
        "source_id": source_id_for_hash(sha256),
        "sha256": sha256,
        "bytes": path.stat().st_size,
        "path_hint": path.relative_to(root).as_posix(),
        "source_type": source_type,
        "origin": {
            "creator": None,
            "title": None,
            "url": None,
        },
        "license": {
            "status": "unknown",
            "expression": None,
            "url": None,
            "attribution": None,
            "notes": None,
        },
        "generation": None,
        "recording": None,
        "notes": None,
        "audio": {
            "duration_ms": metadata.duration_ms,
            "sample_rate": metadata.sample_rate,
            "channels": metadata.channels,
            "sample_width": metadata.sample_width,
            "frames": metadata.frames,
        },
    }


def _candidate_from_path(
    *,
    provider_id: str,
    provider_kind: str,
    root: Path,
    path: Path,
    provenance: dict[str, Any],
    ordinal: int,
) -> SourceCandidate:
    metadata = read_wav_metadata(path)
    sha256 = source_sha256(path)
    source_id = source_id_for_hash(sha256)

    if provenance.get("source_id") != source_id:
        raise SourceProviderError(
            f"provenance source_id does not match candidate bytes: {path}"
        )
    if provenance.get("sha256") != sha256:
        raise SourceProviderError(
            f"provenance sha256 does not match candidate bytes: {path}"
        )

    relative = path.relative_to(root).as_posix()
    return SourceCandidate(
        candidate_id=f"{provider_id}:{ordinal:02d}:{sha256[:12]}",
        provider_id=provider_id,
        provider_kind=provider_kind,
        relative_path=relative,
        source_id=source_id,
        sha256=sha256,
        bytes=path.stat().st_size,
        duration_ms=metadata.duration_ms,
        sample_rate=metadata.sample_rate,
        channels=metadata.channels,
        sample_width=metadata.sample_width,
        frames=metadata.frames,
        provenance=provenance,
    )


def validate_provider_result(result: ProviderResult) -> None:
    if result.source_provider_contract_version != SOURCE_PROVIDER_CONTRACT_VERSION:
        raise SourceProviderError(
            "unsupported source provider contract version: "
            + result.source_provider_contract_version
        )
    if result.provider_kind not in PROVIDER_KINDS:
        raise SourceProviderError(
            f"unsupported provider kind: {result.provider_kind}"
        )
    if not result.provider_id.strip():
        raise SourceProviderError("provider_id must not be empty")

    artifact_root = Path(result.artifact_root)
    if not artifact_root.is_absolute():
        raise SourceProviderError("artifact_root must be an absolute path")
    if not artifact_root.is_dir():
        raise SourceProviderError(
            f"artifact_root does not exist: {artifact_root}"
        )

    result.request.validate()
    if len(result.candidates) > result.request.count:
        raise SourceProviderError("provider returned more candidates than requested")

    candidate_ids: set[str] = set()
    for candidate in result.candidates:
        if candidate.provider_id != result.provider_id:
            raise SourceProviderError("candidate provider_id mismatch")
        if candidate.provider_kind != result.provider_kind:
            raise SourceProviderError("candidate provider_kind mismatch")
        if candidate.candidate_id in candidate_ids:
            raise SourceProviderError(
                f"duplicate provider candidate_id: {candidate.candidate_id}"
            )
        candidate_ids.add(candidate.candidate_id)

        if candidate.source_id != source_id_for_hash(candidate.sha256):
            raise SourceProviderError(
                f"{candidate.candidate_id}: source_id must match sha256"
            )
        if candidate.bytes < 0:
            raise SourceProviderError(
                f"{candidate.candidate_id}: bytes must be non-negative"
            )
        if candidate.duration_ms < 0:
            raise SourceProviderError(
                f"{candidate.candidate_id}: duration_ms must be non-negative"
            )
        if candidate.sample_rate <= 0:
            raise SourceProviderError(
                f"{candidate.candidate_id}: sample_rate must be positive"
            )
        if candidate.channels <= 0:
            raise SourceProviderError(
                f"{candidate.candidate_id}: channels must be positive"
            )

        candidate_path = (artifact_root / candidate.relative_path).resolve()
        try:
            candidate_path.relative_to(artifact_root.resolve())
        except ValueError as exc:
            raise SourceProviderError(
                f"{candidate.candidate_id}: relative_path escapes artifact_root"
            ) from exc
        if not candidate_path.is_file():
            raise SourceProviderError(
                f"{candidate.candidate_id}: candidate artifact is missing"
            )
        if candidate_path.stat().st_size != candidate.bytes:
            raise SourceProviderError(
                f"{candidate.candidate_id}: candidate byte size changed"
            )
        if source_sha256(candidate_path) != candidate.sha256:
            raise SourceProviderError(
                f"{candidate.candidate_id}: candidate hash changed"
            )

        provenance = candidate.provenance
        if not isinstance(provenance, dict):
            raise SourceProviderError(
                f"{candidate.candidate_id}: provenance must be an object"
            )
        if provenance.get("source_id") != candidate.source_id:
            raise SourceProviderError(
                f"{candidate.candidate_id}: provenance source_id mismatch"
            )
        if provenance.get("sha256") != candidate.sha256:
            raise SourceProviderError(
                f"{candidate.candidate_id}: provenance sha256 mismatch"
            )


def provider_result_to_dict(result: ProviderResult) -> dict[str, Any]:
    validate_provider_result(result)
    return {
        "source_provider_contract_version": result.source_provider_contract_version,
        "provider_id": result.provider_id,
        "provider_kind": result.provider_kind,
        "artifact_root": result.artifact_root,
        "request": asdict(result.request),
        "candidate_count": len(result.candidates),
        "candidates": [asdict(candidate) for candidate in result.candidates],
    }


def write_provider_result(result: ProviderResult, output_path: str | Path) -> Path:
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            provider_result_to_dict(result),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def _search_tokens(request: SourceRequest) -> tuple[str, ...]:
    explicit = [hint.strip().lower() for hint in request.hints if hint.strip()]
    if explicit:
        return tuple(explicit)

    return tuple(
        token
        for token in re.findall(r"[a-z0-9_-]+", request.intent.lower())
        if len(token) >= 3
    )


class LocalFileProvider:
    provider_id = "local-files"
    provider_kind = "local_file"

    def __init__(
        self,
        audio_root: str | Path,
        provenance_ledger_path: str | Path | None = None,
    ) -> None:
        self.audio_root = Path(audio_root).resolve()
        if not self.audio_root.is_dir():
            raise SourceProviderError(
                f"audio root does not exist: {self.audio_root}"
            )

        self._provenance_by_id: dict[str, dict[str, Any]] = {}
        if provenance_ledger_path is not None:
            ledger = load_provenance_ledger(provenance_ledger_path)
            self._provenance_by_id = {
                entry["source_id"]: entry
                for entry in ledger["entries"]
            }

    def describe(self) -> dict[str, Any]:
        return {
            "source_provider_contract_version": SOURCE_PROVIDER_CONTRACT_VERSION,
            "provider_id": self.provider_id,
            "provider_kind": self.provider_kind,
            "capabilities": {
                "network": False,
                "generates_audio": False,
                "records_audio": False,
                "deterministic_order": True,
                "provenance_lookup": bool(self._provenance_by_id),
            },
        }

    def provide(self, request: SourceRequest) -> ProviderResult:
        request.validate()
        tokens = _search_tokens(request)

        paths = [
            path
            for path in sorted(self.audio_root.rglob("*.wav"))
            if path.is_file()
        ]

        if tokens:
            matched = [
                path
                for path in paths
                if any(
                    token in path.relative_to(self.audio_root).as_posix().lower()
                    for token in tokens
                )
            ]
            if matched:
                paths = matched

        candidates: list[SourceCandidate] = []
        for path in paths[: request.count]:
            sha256 = source_sha256(path)
            source_id = source_id_for_hash(sha256)
            provenance = self._provenance_by_id.get(source_id)
            if provenance is None:
                provenance = _default_provenance(
                    path,
                    self.audio_root,
                    source_type="unknown",
                )
            candidates.append(
                _candidate_from_path(
                    provider_id=self.provider_id,
                    provider_kind=self.provider_kind,
                    root=self.audio_root,
                    path=path,
                    provenance=provenance,
                    ordinal=len(candidates) + 1,
                )
            )

        result = ProviderResult(
            source_provider_contract_version=SOURCE_PROVIDER_CONTRACT_VERSION,
            provider_id=self.provider_id,
            provider_kind=self.provider_kind,
            artifact_root=str(self.audio_root),
            request=request,
            candidates=tuple(candidates),
        )
        validate_provider_result(result)
        return result


class FixtureGeneratedProvider:
    provider_id = "fixture-generated"
    provider_kind = "generated"

    def __init__(self, output_root: str | Path) -> None:
        self.output_root = Path(output_root).resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)

    def describe(self) -> dict[str, Any]:
        return {
            "source_provider_contract_version": SOURCE_PROVIDER_CONTRACT_VERSION,
            "provider_id": self.provider_id,
            "provider_kind": self.provider_kind,
            "capabilities": {
                "network": False,
                "generates_audio": True,
                "records_audio": False,
                "fixture_only": True,
                "deterministic": True,
            },
        }

    def _write_candidate(
        self,
        request: SourceRequest,
        ordinal: int,
    ) -> Path:
        duration_ms = request.duration_ms or 120
        sample_rate = 8000
        frames = max(1, round(duration_ms / 1000 * sample_rate))

        seed_text = f"{request.seed or '0'}:{request.intent}:{ordinal}"
        seed_digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
        amplitude = 500 + int.from_bytes(seed_digest[:2], "big") % 2500
        cycle = 8 + int.from_bytes(seed_digest[2:4], "big") % 48

        samples = array(
            "h",
            (
                amplitude if (index // cycle) % 2 == 0 else -amplitude
                for index in range(frames)
            ),
        )

        safe_request = re.sub(
            r"[^a-z0-9]+",
            "-",
            request.request_id.lower(),
        ).strip("-") or "request"
        path = self.output_root / f"{safe_request}-{ordinal:02d}.wav"
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(samples.tobytes())
        return path

    def provide(self, request: SourceRequest) -> ProviderResult:
        request.validate()
        candidates: list[SourceCandidate] = []

        for ordinal in range(1, request.count + 1):
            path = self._write_candidate(request, ordinal)
            sha256 = source_sha256(path)
            metadata = read_wav_metadata(path)
            seed = f"{request.seed or '0'}:{ordinal}"
            provenance = {
                "source_id": source_id_for_hash(sha256),
                "sha256": sha256,
                "bytes": path.stat().st_size,
                "path_hint": path.relative_to(self.output_root).as_posix(),
                "source_type": "generated",
                "origin": {
                    "creator": "MGAL fixture provider",
                    "title": None,
                    "url": None,
                },
                "license": {
                    "status": "terms",
                    "expression": "MGAL-fixture-only",
                    "url": None,
                    "attribution": None,
                    "notes": "Synthetic fixture output for contract testing.",
                },
                "generation": {
                    "provider": self.provider_id,
                    "model": "deterministic-square-wave-v1",
                    "prompt": request.intent,
                    "seed": seed,
                    "parameters": {
                        "duration_ms": metadata.duration_ms,
                        "sample_rate": metadata.sample_rate,
                    },
                },
                "recording": None,
                "notes": "Not a production audio generator.",
                "audio": {
                    "duration_ms": metadata.duration_ms,
                    "sample_rate": metadata.sample_rate,
                    "channels": metadata.channels,
                    "sample_width": metadata.sample_width,
                    "frames": metadata.frames,
                },
            }
            candidates.append(
                _candidate_from_path(
                    provider_id=self.provider_id,
                    provider_kind=self.provider_kind,
                    root=self.output_root,
                    path=path,
                    provenance=provenance,
                    ordinal=ordinal,
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
