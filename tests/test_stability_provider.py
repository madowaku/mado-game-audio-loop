from array import array
import io
import json
from pathlib import Path
import wave

import pytest

from mgal.provider import SourceRequest, validate_provider_result
from mgal.provenance import (
    entry_is_complete,
    validate_provenance_ledger,
)
from mgal.providers.stability import (
    StabilityAudioError,
    StabilityAudioProvider,
    StabilityGeneration,
    StabilityHTTPTransport,
    _effective_duration_seconds,
)
from mgal.provider import write_provider_provenance_ledger


def _wav_bytes(value: int, frames: int = 80) -> bytes:
    buffer = io.BytesIO()
    data = array("h", [value] * frames)
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(data.tobytes())
    return buffer.getvalue()


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def generate(
        self,
        *,
        prompt: str,
        duration_seconds: float,
        seed: int,
        steps: int,
        cfg_scale: float,
    ) -> StabilityGeneration:
        ordinal = len(self.calls) + 1
        self.calls.append(
            {
                "prompt": prompt,
                "duration_seconds": duration_seconds,
                "seed": seed,
                "steps": steps,
                "cfg_scale": cfg_scale,
            }
        )
        return StabilityGeneration(
            generation_id=f"{ordinal:064d}",
            audio_bytes=_wav_bytes(500 + ordinal),
            duration_seconds=duration_seconds,
            seed=seed,
            steps=steps,
            cfg_scale=cfg_scale,
        )


def test_stability_provider_normalizes_to_source_contract(tmp_path: Path):
    transport = FakeTransport()
    provider = StabilityAudioProvider(
        tmp_path / "generated",
        allow_paid=True,
        transport=transport,
        steps=6,
        cfg_scale=2.0,
    )
    request = SourceRequest(
        request_id="heavy-slash",
        intent="short stylized metallic sword slash",
        count=2,
        duration_ms=400,
        seed="42",
    )

    result = provider.provide(request)
    validate_provider_result(result)

    assert len(result.candidates) == 2
    assert [call["duration_seconds"] for call in transport.calls] == [1.0, 1.0]
    assert [call["seed"] for call in transport.calls] == [42, 43]

    first = result.candidates[0]
    assert first.provider_kind == "generated"
    assert first.relative_path.endswith(".wav")
    assert first.provenance["source_type"] == "generated"
    assert first.provenance["generation"]["provider"] == "stability-audio"
    assert first.provenance["generation"]["model"] == "stable-audio-3"
    assert first.provenance["generation"]["prompt"] == request.intent
    assert first.provenance["generation"]["parameters"]["requested_duration_ms"] == 400
    assert first.provenance["generation"]["parameters"]["api_duration_seconds"] == 1.0
    assert entry_is_complete(first.provenance) is True

    serialized = json.dumps(first.provenance)
    assert "STABILITY_API_KEY" not in serialized
    assert "Bearer " not in serialized


def test_stability_provider_requires_explicit_paid_opt_in(tmp_path: Path):
    transport = FakeTransport()
    provider = StabilityAudioProvider(
        tmp_path / "generated",
        allow_paid=False,
        transport=transport,
    )

    with pytest.raises(StabilityAudioError, match="paid"):
        provider.provide(
            SourceRequest(
                request_id="impact",
                intent="impact",
                count=1,
            )
        )

    assert transport.calls == []


def test_stability_provider_provenance_exports_to_standard_ledger(tmp_path: Path):
    provider = StabilityAudioProvider(
        tmp_path / "generated",
        allow_paid=True,
        transport=FakeTransport(),
    )
    result = provider.provide(
        SourceRequest(
            request_id="impact",
            intent="impact",
            count=1,
            seed="fixture",
        )
    )

    ledger = write_provider_provenance_ledger(
        result,
        tmp_path / "provider-provenance.json",
    )
    report = validate_provenance_ledger(
        ledger,
        audio_root=result.artifact_root,
    )

    assert report["complete"] is True
    assert report["entries"] == 1


def test_stability_duration_rejects_over_api_limit():
    with pytest.raises(StabilityAudioError, match="exceeds"):
        _effective_duration_seconds(380_001)


def test_stability_describe_is_network_free(tmp_path: Path):
    provider = StabilityAudioProvider(tmp_path / "generated")

    description = provider.describe()

    assert description["provider_id"] == "stability-audio"
    assert description["capabilities"]["network"] is True
    assert description["capabilities"]["paid_generation"] is True
    assert description["capabilities"]["requires_explicit_paid_opt_in"] is True
    assert not (tmp_path / "generated").exists()


class FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None


def test_http_transport_polls_async_result_without_network():
    responses = [
        FakeResponse(
            202,
            json.dumps({"id": "a" * 64}).encode("utf-8"),
        ),
        FakeResponse(202, b""),
        FakeResponse(200, _wav_bytes(777)),
    ]
    requests = []
    sleeps = []

    def opener(request, timeout):
        requests.append(request)
        return responses.pop(0)

    transport = StabilityHTTPTransport(
        api_key="test-secret-key",
        poll_interval_seconds=0.01,
        max_wait_seconds=1,
        opener=opener,
        sleeper=lambda seconds: sleeps.append(seconds),
    )

    result = transport.generate(
        prompt="impact",
        duration_seconds=1.0,
        seed=42,
        steps=8,
        cfg_scale=1.0,
    )

    assert result.generation_id == "a" * 64
    assert result.audio_bytes.startswith(b"RIFF")
    assert [request.get_method() for request in requests] == ["POST", "GET", "GET"]
    assert sleeps == [0.01]

    post_body = requests[0].data.decode("utf-8", errors="ignore")
    assert "impact" in post_body
    assert "stable-audio-3" in post_body
    assert "test-secret-key" not in post_body
