from __future__ import annotations

from array import array
from dataclasses import replace
import json
import math
from pathlib import Path
import shutil
import wave
from typing import Any

from .audio import read_wav_metadata
from .provider import (
    ProviderResult,
    SourceCandidate,
    SourceProviderError,
    load_provider_result,
    validate_provider_result,
)
from .provenance import source_id_for_hash, source_sha256


CANONICAL_PROFILE_ID = "mgal-pcm16-mono-44100-v1"
CANONICAL_SAMPLE_RATE = 44_100
CANONICAL_CHANNELS = 1
CANONICAL_SAMPLE_WIDTH = 2


class AudioNormalizationError(ValueError):
    pass


def _decode_sample(raw: bytes, sample_width: int) -> int:
    if sample_width == 1:
        return (raw[0] - 128) << 8
    if sample_width == 2:
        return int.from_bytes(raw, "little", signed=True)
    if sample_width == 3:
        value = int.from_bytes(raw, "little", signed=False)
        if value & 0x800000:
            value -= 1 << 24
        return value >> 8
    if sample_width == 4:
        value = int.from_bytes(raw, "little", signed=True)
        return value >> 16
    raise AudioNormalizationError(
        f"unsupported PCM sample width: {sample_width} bytes"
    )


def _read_pcm_as_mono16(path: Path) -> tuple[int, array]:
    try:
        with wave.open(str(path), "rb") as wav:
            if wav.getcomptype() != "NONE":
                raise AudioNormalizationError(
                    f"{path}: compressed WAV is not supported"
                )
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            sample_rate = wav.getframerate()
            frame_count = wav.getnframes()
            if channels <= 0:
                raise AudioNormalizationError(f"{path}: invalid channel count")
            if sample_rate <= 0:
                raise AudioNormalizationError(f"{path}: invalid sample rate")
            raw = wav.readframes(frame_count)
    except wave.Error as exc:
        raise AudioNormalizationError(
            f"{path}: unreadable PCM WAV: {exc}"
        ) from exc

    frame_size = channels * sample_width
    expected = frame_count * frame_size
    if len(raw) < expected:
        raise AudioNormalizationError(
            f"{path}: truncated PCM WAV payload"
        )

    mono = array("h")
    cursor = 0
    for _frame in range(frame_count):
        total = 0
        for _channel in range(channels):
            sample_raw = raw[cursor : cursor + sample_width]
            cursor += sample_width
            total += _decode_sample(sample_raw, sample_width)
        averaged = round(total / channels)
        mono.append(max(-32768, min(32767, averaged)))

    return sample_rate, mono


def _resample_linear(
    samples: array,
    source_rate: int,
    target_rate: int,
) -> array:
    if source_rate == target_rate:
        return array("h", samples)
    if not samples:
        return array("h")

    target_frames = max(
        1,
        round(len(samples) * target_rate / source_rate),
    )
    if len(samples) == 1:
        return array("h", [samples[0]] * target_frames)

    output = array("h")
    ratio = source_rate / target_rate

    for target_index in range(target_frames):
        source_position = target_index * ratio
        left = min(int(math.floor(source_position)), len(samples) - 1)
        right = min(left + 1, len(samples) - 1)
        fraction = source_position - left
        value = round(
            samples[left] * (1.0 - fraction)
            + samples[right] * fraction
        )
        output.append(max(-32768, min(32767, value)))

    return output


def _write_pcm16_mono(
    path: Path,
    samples: array,
    sample_rate: int = CANONICAL_SAMPLE_RATE,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(CANONICAL_CHANNELS)
        wav.setsampwidth(CANONICAL_SAMPLE_WIDTH)
        wav.setframerate(sample_rate)
        wav.writeframes(samples.tobytes())


def _is_canonical(path: Path) -> bool:
    metadata = read_wav_metadata(path)
    return (
        metadata.sample_rate == CANONICAL_SAMPLE_RATE
        and metadata.channels == CANONICAL_CHANNELS
        and metadata.sample_width == CANONICAL_SAMPLE_WIDTH
    )


def _safe_name(candidate: SourceCandidate, ordinal: int) -> str:
    stem = Path(candidate.relative_path).stem
    safe = "".join(
        char.lower() if char.isalnum() else "-"
        for char in stem
    )
    safe = "-".join(part for part in safe.split("-") if part) or "audio"
    return f"{ordinal:02d}-{safe}-{candidate.sha256[:12]}.wav"


def _normalization_provenance(
    candidate: SourceCandidate,
    *,
    output_path: Path,
    output_root: Path,
    passthrough: bool,
) -> dict[str, Any]:
    provenance = json.loads(
        json.dumps(candidate.provenance, ensure_ascii=False)
    )
    normalized_sha = source_sha256(output_path)
    normalized_id = source_id_for_hash(normalized_sha)
    metadata = read_wav_metadata(output_path)

    provenance["source_id"] = normalized_id
    provenance["sha256"] = normalized_sha
    provenance["bytes"] = output_path.stat().st_size
    provenance["path_hint"] = output_path.relative_to(output_root).as_posix()
    provenance["audio"] = {
        "duration_ms": metadata.duration_ms,
        "sample_rate": metadata.sample_rate,
        "channels": metadata.channels,
        "sample_width": metadata.sample_width,
        "frames": metadata.frames,
    }
    provenance["normalization"] = {
        "profile_id": CANONICAL_PROFILE_ID,
        "passthrough": passthrough,
        "original": {
            "candidate_id": candidate.candidate_id,
            "source_id": candidate.source_id,
            "sha256": candidate.sha256,
            "bytes": candidate.bytes,
            "relative_path": candidate.relative_path,
            "sample_rate": candidate.sample_rate,
            "channels": candidate.channels,
            "sample_width": candidate.sample_width,
            "frames": candidate.frames,
        },
        "normalized": {
            "source_id": normalized_id,
            "sha256": normalized_sha,
            "bytes": output_path.stat().st_size,
            "sample_rate": metadata.sample_rate,
            "channels": metadata.channels,
            "sample_width": metadata.sample_width,
            "frames": metadata.frames,
        },
        "algorithm": (
            "byte-preserving-copy"
            if passthrough
            else "channel-average+linear-resample+pcm16"
        ),
    }
    return provenance


def normalize_provider_result(
    result: ProviderResult,
    output_root: str | Path,
) -> ProviderResult:
    validate_provider_result(result)

    source_root = Path(result.artifact_root).resolve()
    output_root = Path(output_root).resolve()
    if output_root == source_root:
        raise AudioNormalizationError(
            "normalization output root must differ from provider artifact root"
        )

    output_root.mkdir(parents=True, exist_ok=True)
    normalized: list[SourceCandidate] = []

    for ordinal, candidate in enumerate(result.candidates, start=1):
        source_path = (source_root / candidate.relative_path).resolve()
        try:
            source_path.relative_to(source_root)
        except ValueError as exc:
            raise AudioNormalizationError(
                f"candidate escapes provider artifact root: {candidate.relative_path}"
            ) from exc

        output_path = output_root / _safe_name(candidate, ordinal)
        passthrough = _is_canonical(source_path)

        if passthrough:
            shutil.copyfile(source_path, output_path)
        else:
            source_rate, mono = _read_pcm_as_mono16(source_path)
            resampled = _resample_linear(
                mono,
                source_rate,
                CANONICAL_SAMPLE_RATE,
            )
            _write_pcm16_mono(output_path, resampled)

        metadata = read_wav_metadata(output_path)
        if (
            metadata.sample_rate != CANONICAL_SAMPLE_RATE
            or metadata.channels != CANONICAL_CHANNELS
            or metadata.sample_width != CANONICAL_SAMPLE_WIDTH
        ):
            raise AudioNormalizationError(
                f"failed to produce canonical WAV: {output_path}"
            )

        sha256 = source_sha256(output_path)
        source_id = source_id_for_hash(sha256)
        provenance = _normalization_provenance(
            candidate,
            output_path=output_path,
            output_root=output_root,
            passthrough=passthrough,
        )

        normalized.append(
            SourceCandidate(
                candidate_id=(
                    f"mgal-normalized:{ordinal:02d}:{sha256[:12]}"
                ),
                provider_id=f"mgal-normalizer/{result.provider_id}",
                provider_kind=result.provider_kind,
                relative_path=output_path.relative_to(
                    output_root
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

    normalized_result = ProviderResult(
        source_provider_contract_version=result.source_provider_contract_version,
        provider_id=f"mgal-normalizer/{result.provider_id}",
        provider_kind=result.provider_kind,
        artifact_root=str(output_root),
        request=result.request,
        candidates=tuple(normalized),
    )
    validate_provider_result(normalized_result)
    return normalized_result


def normalize_provider_result_file(
    result_path: str | Path,
    output_root: str | Path,
) -> ProviderResult:
    return normalize_provider_result(
        load_provider_result(result_path),
        output_root,
    )
