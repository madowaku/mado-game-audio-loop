from array import array
import io
import json
from pathlib import Path
import wave

from mgal.evidence import build_evidence_bundle, verify_evidence_bundle
from mgal.normalizer import normalize_provider_result
from mgal.provider import (
    LocalFileProvider,
    SourceRequest,
    write_provider_provenance_ledger,
)
from mgal.provenance import (
    merge_provenance_ledgers,
    update_provenance_entry,
    write_provenance_ledger,
)
from mgal.providers.stability import (
    StabilityAudioProvider,
    StabilityGeneration,
)


def _wav_bytes(
    value: int,
    *,
    sample_rate: int,
    channels: int,
) -> bytes:
    buffer = io.BytesIO()
    samples = array("h")
    for _ in range(160):
        for channel in range(channels):
            samples.append(value + channel * 100)
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(samples.tobytes())
    return buffer.getvalue()


def _write_wav(
    path: Path,
    value: int,
    *,
    sample_rate: int,
    channels: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        _wav_bytes(
            value,
            sample_rate=sample_rate,
            channels=channels,
        )
    )


class FakeTransport:
    def generate(
        self,
        *,
        prompt: str,
        duration_seconds: float,
        seed: int,
        steps: int,
        cfg_scale: float,
    ) -> StabilityGeneration:
        return StabilityGeneration(
            generation_id="b" * 64,
            audio_bytes=_wav_bytes(
                900,
                sample_rate=48_000,
                channels=2,
            ),
            duration_seconds=duration_seconds,
            seed=seed,
            steps=steps,
            cfg_scale=cfg_scale,
        )


def test_stability_candidate_normalizes_into_strict_evidence_bundle(
    tmp_path: Path,
):
    audio_root = tmp_path / "audio"
    local_raw_root = tmp_path / "raw-local"
    _write_wav(
        local_raw_root / "metal.wav",
        400,
        sample_rate=8_000,
        channels=1,
    )

    local_ledger = write_provenance_ledger(
        local_raw_root,
        tmp_path / "local-provenance.json",
    )
    update_provenance_entry(
        local_ledger,
        "metal.wav",
        source_type="free_library",
        license_status="declared",
        license_expression="CC0-1.0",
    )

    local_provider = LocalFileProvider(
        local_raw_root,
        local_ledger,
    )
    local_result = local_provider.provide(
        SourceRequest(
            request_id="metal",
            intent="metal",
            count=1,
        )
    )
    local_normalized = normalize_provider_result(
        local_result,
        audio_root / "canonical" / "local",
    )
    local_normalized_ledger = write_provider_provenance_ledger(
        local_normalized,
        tmp_path / "local-normalized-provenance.json",
    )

    stability_raw_root = tmp_path / "raw-stability"
    provider = StabilityAudioProvider(
        stability_raw_root,
        allow_paid=True,
        transport=FakeTransport(),
    )
    provider_result = provider.provide(
        SourceRequest(
            request_id="impact",
            intent="short metallic impact",
            count=1,
            duration_ms=400,
            seed="42",
        )
    )
    generated_normalized = normalize_provider_result(
        provider_result,
        audio_root / "canonical" / "generated",
    )
    generated_normalized_ledger = write_provider_provenance_ledger(
        generated_normalized,
        tmp_path / "generated-normalized-provenance.json",
    )

    merged_ledger = merge_provenance_ledgers(
        [
            local_normalized_ledger,
            generated_normalized_ledger,
        ],
        tmp_path / "merged-provenance.json",
    )

    local_source = (
        Path("canonical")
        / "local"
        / local_normalized.candidates[0].relative_path
    ).as_posix()
    generated_source = (
        Path("canonical")
        / "generated"
        / generated_normalized.candidates[0].relative_path
    ).as_posix()

    base_id = "slash-base"
    selected_id = "slash-selected"
    board = {
        "candidate_board_version": "0.1",
        "intent": "metallic slash with generated impact",
        "base_recipe": {
            "recipe_version": "0.1",
            "id": base_id,
            "intent": "metallic slash",
            "layers": [
                {
                    "source": local_source,
                    "gain": 0.5,
                    "offset_ms": 0,
                }
            ],
            "processing": {
                "normalize": True,
                "fade_out_ms": 0,
            },
        },
        "active_candidate_id": selected_id,
        "selected_candidate_id": selected_id,
        "candidates": [
            {
                "id": selected_id,
                "label": "A",
                "parent_recipe_id": base_id,
                "revision": 1,
                "lineage": [
                    {
                        "from_recipe_id": base_id,
                        "action": "fork",
                        "revision": 1,
                    }
                ],
                "recipe": {
                    "recipe_version": "0.1",
                    "id": selected_id,
                    "intent": "metallic slash with generated impact",
                    "layers": [
                        {
                            "source": local_source,
                            "gain": 0.5,
                            "offset_ms": 0,
                        },
                        {
                            "source": generated_source,
                            "gain": 0.8,
                            "offset_ms": 0,
                        },
                    ],
                    "processing": {
                        "normalize": True,
                        "fade_out_ms": 0,
                    },
                },
                "decision": {
                    "status": "selected",
                    "reason": "generated impact adds body",
                },
            }
        ],
    }
    board_path = tmp_path / "board.json"
    board_path.write_text(
        json.dumps(board),
        encoding="utf-8",
    )

    bundle = build_evidence_bundle(
        board_path,
        audio_root,
        tmp_path / "evidence",
        provenance_ledger_path=merged_ledger,
        require_provenance=True,
    )

    verification = verify_evidence_bundle(bundle)
    assert verification["ok"] is True
    assert verification["provenance"]["complete"] is True
    assert verification["provenance"]["entries"] == 2

    provenance = json.loads(
        (bundle / "provenance-ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert all(
        entry["normalization"]["profile_id"]
        == "mgal-pcm16-mono-44100-v1"
        for entry in provenance["entries"]
    )

    with wave.open(str(bundle / "output.wav"), "rb") as wav:
        assert wav.getframerate() == 44_100
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
