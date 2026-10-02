from array import array
import io
import json
from pathlib import Path
import wave

from mgal.evidence import build_evidence_bundle, verify_evidence_bundle
from mgal.provider import (
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


def _wav_bytes(value: int) -> bytes:
    buffer = io.BytesIO()
    data = array("h", [value] * 80)
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(data.tobytes())
    return buffer.getvalue()


def _write_wav(path: Path, value: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_wav_bytes(value))


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
            audio_bytes=_wav_bytes(900),
            duration_seconds=duration_seconds,
            seed=seed,
            steps=steps,
            cfg_scale=cfg_scale,
        )


def test_stability_candidate_reaches_strict_evidence_bundle(tmp_path: Path):
    audio_root = tmp_path / "audio"
    _write_wav(audio_root / "metal.wav", 400)

    local_ledger = write_provenance_ledger(
        audio_root,
        tmp_path / "local-provenance.json",
    )
    update_provenance_entry(
        local_ledger,
        "metal.wav",
        source_type="free_library",
        license_status="declared",
        license_expression="CC0-1.0",
    )

    generated_root = audio_root / "generated"
    provider = StabilityAudioProvider(
        generated_root,
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
    generated = provider_result.candidates[0]

    provider_ledger = write_provider_provenance_ledger(
        provider_result,
        tmp_path / "generated-provenance.json",
    )
    merged_ledger = merge_provenance_ledgers(
        [local_ledger, provider_ledger],
        tmp_path / "merged-provenance.json",
    )

    generated_source = (
        Path("generated") / generated.relative_path
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
                    "source": "metal.wav",
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
                            "source": "metal.wav",
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
