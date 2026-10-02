import json
from pathlib import Path

from mgal.cli import main
from mgal.provenance import validate_provenance_ledger


def test_source_provide_fixture_generated_cli(tmp_path: Path, capsys):
    artifacts = tmp_path / "generated"
    result_json = tmp_path / "provider-result.json"
    provenance_json = tmp_path / "provider-provenance.json"

    code = main(
        [
            "source-provide",
            "--provider",
            "fixture-generated",
            "--artifact-root",
            str(artifacts),
            "--request-id",
            "impact",
            "--intent",
            "short impact",
            "--count",
            "2",
            "--duration-ms",
            "80",
            "--seed",
            "42",
            "--output",
            str(result_json),
            "--provenance-output",
            str(provenance_json),
        ]
    )

    assert code == 0
    payload = json.loads(result_json.read_text(encoding="utf-8"))
    assert payload["source_provider_contract_version"] == "1.0"
    assert payload["candidate_count"] == 2
    assert Path(payload["artifact_root"]) == artifacts.resolve()

    report = validate_provenance_ledger(
        provenance_json,
        audio_root=artifacts,
    )
    assert report["complete"] is True

    stdout = json.loads(capsys.readouterr().out)
    assert stdout["candidate_count"] == 2


def test_provider_describe_local_cli(tmp_path: Path, capsys):
    audio = tmp_path / "audio"
    audio.mkdir()

    code = main(
        [
            "provider-describe",
            "--provider",
            "local",
            "--audio-root",
            str(audio),
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["provider_id"] == "local-files"
    assert payload["provider_kind"] == "local_file"
    assert payload["capabilities"]["network"] is False
