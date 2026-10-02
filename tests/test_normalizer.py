from array import array
import json
from pathlib import Path
import wave

import pytest

from mgal.normalizer import (
    AudioNormalizationError,
    CANONICAL_PROFILE_ID,
    CANONICAL_SAMPLE_RATE,
    normalize_provider_result,
)
from mgal.provider import (
    LocalFileProvider,
    SourceRequest,
    validate_provider_result,
    write_provider_provenance_ledger,
    write_provider_result,
    load_provider_result,
)
from mgal.recipe import load_recipe
from mgal.render import render_recipe
from mgal.provenance import validate_provenance_ledger, source_sha256


def _write_pcm_wav(
    path: Path,
    *,
    sample_rate: int,
    channels: int,
    sample_width: int,
    frames: list[tuple[int, ...]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = bytearray()

    for frame in frames:
        assert len(frame) == channels
        for sample in frame:
            if sample_width == 1:
                payload.append(max(0, min(255, (sample >> 8) + 128)))
            elif sample_width == 2:
                payload.extend(
                    int(sample).to_bytes(2, "little", signed=True)
                )
            elif sample_width == 3:
                value = int(sample) << 8
                if value < 0:
                    value += 1 << 24
                payload.extend(value.to_bytes(3, "little", signed=False))
            elif sample_width == 4:
                value = int(sample) << 16
                payload.extend(value.to_bytes(4, "little", signed=True))
            else:
                raise AssertionError("unsupported fixture sample width")

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(payload))


def test_normalizer_converts_stereo_48k_to_canonical_mono_44100(tmp_path: Path):
    source_root = tmp_path / "source"
    source = source_root / "stereo.wav"
    frames = [
        (1000, -1000),
        (3000, 1000),
        (-2000, 2000),
        (4000, 2000),
    ] * 100
    _write_pcm_wav(
        source,
        sample_rate=48_000,
        channels=2,
        sample_width=2,
        frames=frames,
    )

    original_hash = source_sha256(source)
    provider = LocalFileProvider(source_root)
    result = provider.provide(
        SourceRequest(
            request_id="stereo",
            intent="stereo",
            count=1,
        )
    )

    normalized = normalize_provider_result(
        result,
        tmp_path / "canonical",
    )
    validate_provider_result(normalized)
    candidate = normalized.candidates[0]

    assert candidate.sample_rate == 44_100
    assert candidate.channels == 1
    assert candidate.sample_width == 2
    assert source_sha256(source) == original_hash
    assert candidate.provenance["normalization"]["profile_id"] == CANONICAL_PROFILE_ID
    assert candidate.provenance["normalization"]["passthrough"] is False
    assert (
        candidate.provenance["normalization"]["original"]["source_id"]
        == result.candidates[0].source_id
    )
    assert (
        candidate.provenance["normalization"]["normalized"]["source_id"]
        == candidate.source_id
    )


def test_normalizer_resamples_mono_8k_deterministically(tmp_path: Path):
    source_root = tmp_path / "source"
    source = source_root / "mono.wav"
    _write_pcm_wav(
        source,
        sample_rate=8_000,
        channels=1,
        sample_width=2,
        frames=[(1000,), (-1000,)] * 80,
    )

    provider = LocalFileProvider(source_root)
    result = provider.provide(
        SourceRequest(
            request_id="mono",
            intent="mono",
            count=1,
        )
    )

    first = normalize_provider_result(
        result,
        tmp_path / "first",
    )
    second = normalize_provider_result(
        result,
        tmp_path / "second",
    )

    assert first.candidates[0].sha256 == second.candidates[0].sha256
    assert first.candidates[0].frames == second.candidates[0].frames
    assert first.candidates[0].sample_rate == CANONICAL_SAMPLE_RATE


def test_canonical_input_uses_byte_preserving_passthrough(tmp_path: Path):
    source_root = tmp_path / "source"
    source = source_root / "canonical.wav"
    _write_pcm_wav(
        source,
        sample_rate=44_100,
        channels=1,
        sample_width=2,
        frames=[(700,), (-700,)] * 100,
    )

    provider = LocalFileProvider(source_root)
    result = provider.provide(
        SourceRequest(
            request_id="canonical",
            intent="canonical",
            count=1,
        )
    )
    normalized = normalize_provider_result(
        result,
        tmp_path / "canonical-output",
    )

    candidate = normalized.candidates[0]
    assert candidate.sha256 == result.candidates[0].sha256
    assert candidate.provenance["normalization"]["passthrough"] is True


def test_normalized_provenance_is_valid_standard_ledger(tmp_path: Path):
    source_root = tmp_path / "source"
    source = source_root / "stereo.wav"
    _write_pcm_wav(
        source,
        sample_rate=48_000,
        channels=2,
        sample_width=3,
        frames=[(1000, 3000), (-1000, 1000)] * 100,
    )

    provider = LocalFileProvider(source_root)
    result = provider.provide(
        SourceRequest(
            request_id="audio",
            intent="audio",
            count=1,
        )
    )
    normalized = normalize_provider_result(
        result,
        tmp_path / "canonical",
    )
    ledger = write_provider_provenance_ledger(
        normalized,
        tmp_path / "normalized-provenance.json",
    )

    report = validate_provenance_ledger(
        ledger,
        audio_root=normalized.artifact_root,
    )
    assert report["entries"] == 1


def test_normalizer_rejects_same_input_and_output_root(tmp_path: Path):
    source_root = tmp_path / "source"
    source = source_root / "mono.wav"
    _write_pcm_wav(
        source,
        sample_rate=44_100,
        channels=1,
        sample_width=2,
        frames=[(1,)] * 10,
    )

    provider = LocalFileProvider(source_root)
    result = provider.provide(
        SourceRequest(
            request_id="audio",
            intent="audio",
            count=1,
        )
    )

    with pytest.raises(AudioNormalizationError, match="must differ"):
        normalize_provider_result(result, source_root)


def test_saved_provider_result_can_be_loaded_and_normalized(tmp_path: Path):
    source_root = tmp_path / "source"
    source = source_root / "stereo.wav"
    _write_pcm_wav(
        source,
        sample_rate=48_000,
        channels=2,
        sample_width=2,
        frames=[(1000, 3000), (-1000, 1000)] * 100,
    )

    provider = LocalFileProvider(source_root)
    result = provider.provide(
        SourceRequest(
            request_id="saved",
            intent="saved",
            count=1,
        )
    )
    result_path = write_provider_result(
        result,
        tmp_path / "provider-result.json",
    )

    loaded = load_provider_result(result_path)
    normalized = normalize_provider_result(
        loaded,
        tmp_path / "canonical",
    )

    assert normalized.candidates[0].sample_rate == CANONICAL_SAMPLE_RATE
    assert normalized.candidates[0].channels == 1


def test_normalized_mixed_formats_render_in_one_recipe(tmp_path: Path):
    source_root = tmp_path / "source"
    _write_pcm_wav(
        source_root / "stereo-48k.wav",
        sample_rate=48_000,
        channels=2,
        sample_width=2,
        frames=[(1200, -400), (600, 200)] * 240,
    )
    _write_pcm_wav(
        source_root / "mono-8k.wav",
        sample_rate=8_000,
        channels=1,
        sample_width=2,
        frames=[(900,), (-900,)] * 80,
    )

    provider = LocalFileProvider(source_root)
    result = provider.provide(
        SourceRequest(
            request_id="mixed",
            intent="mixed",
            count=2,
        )
    )
    normalized = normalize_provider_result(
        result,
        tmp_path / "canonical",
    )

    recipe_payload = {
        "recipe_version": "0.1",
        "id": "normalized-mix",
        "intent": "mixed normalized provider audio",
        "layers": [
            {
                "source": candidate.relative_path,
                "gain": 0.5,
                "offset_ms": index * 10,
            }
            for index, candidate in enumerate(normalized.candidates)
        ],
        "processing": {
            "normalize": True,
            "fade_out_ms": 0,
        },
    }
    recipe_path = tmp_path / "recipe.json"
    recipe_path.write_text(
        json.dumps(recipe_payload),
        encoding="utf-8",
    )

    recipe = load_recipe(recipe_path)
    output = render_recipe(
        recipe,
        recipe_path,
        tmp_path / "output.wav",
        source_root=Path(normalized.artifact_root),
    )

    with wave.open(str(output), "rb") as wav:
        assert wav.getframerate() == CANONICAL_SAMPLE_RATE
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2


def test_normalization_lineage_validation_rejects_wrong_normalized_hash(
    tmp_path: Path,
):
    source_root = tmp_path / "source"
    source = source_root / "mono.wav"
    _write_pcm_wav(
        source,
        sample_rate=8_000,
        channels=1,
        sample_width=2,
        frames=[(100,), (-100,)] * 20,
    )

    provider = LocalFileProvider(source_root)
    result = provider.provide(
        SourceRequest(
            request_id="lineage",
            intent="lineage",
            count=1,
        )
    )
    normalized = normalize_provider_result(
        result,
        tmp_path / "canonical",
    )

    broken = json.loads(
        json.dumps(normalized.candidates[0].provenance)
    )
    broken["normalization"]["normalized"]["sha256"] = "0" * 64

    ledger = {
        "provenance_ledger_version": "0.1",
        "entry_count": 1,
        "entries": [broken],
    }
    ledger_path = tmp_path / "broken-ledger.json"
    ledger_path.write_text(
        json.dumps(ledger),
        encoding="utf-8",
    )

    with pytest.raises(Exception, match="normalization.normalized"):
        validate_provenance_ledger(ledger_path)
