# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work into a reproducible creative loop:

**provide → audition → mix → compare → decide → bundle → replay → recover → trace provenance → release**

## Current milestone: M1.0 Source Provider Contract

MGAL now has a stable boundary for bringing audio candidates into the system.

> **Providers supply candidates. MGAL owns the creative loop.**

```text
SourceRequest
    ↓
SourceProvider
    ↓
ProviderResult
    ├── artifact_root
    ├── provider identity
    ├── request echo
    └── SourceCandidate[]
          ├── playable WAV reference
          ├── SHA-256 source identity
          ├── audio metadata
          └── provenance/license metadata
```

Before M1.0, MGAL assumed sources already existed in a local WAV folder. M1.0 makes acquisition replaceable while leaving the mixer, Candidate Board, Evidence, Replay, Provenance, and Release machinery unchanged.

## Contract version

`source_provider_contract_version = 1.0`

A Provider Result contains `provider_id`, `provider_kind`, an absolute `artifact_root`, the echoed `SourceRequest`, and zero or more candidates.

### SourceRequest

- `request_id`
- `intent`
- `count` from 1 to 32
- optional `hints`
- optional `duration_ms`
- optional `seed`

Provider-specific API settings are deliberately not part of SourceRequest. Future adapters keep those details behind the Provider boundary.

### SourceCandidate

Every candidate contains:

```text
candidate_id
provider_id
provider_kind
relative_path
source_id
sha256
bytes
duration_ms
sample_rate
channels
sample_width
frames
provenance
```

The physical artifact is resolved as `artifact_root / relative_path`. The path must stay inside the artifact root.

Candidate identity follows the existing M0.8 rule:

```text
path = address
SHA-256 = identity
source_id = sha256:<hash>
```

MGAL re-hashes candidate files during Provider Result validation. Candidate bytes, candidate `sha256`, candidate `source_id`, provenance `sha256`, and provenance `source_id` must agree.

## Provenance is part of the Provider contract

A Provider does not return only a WAV. Every candidate carries a valid M0.8 provenance entry.

Generated adapters should return provider/model/prompt/seed/parameters and license declarations at acquisition time. Recorded adapters should return recorder/date/device metadata at acquisition time. Local files without known provenance remain explicitly `unknown` rather than being guessed.

Provider Results can also emit a normal Provenance Ledger:

```bash
mgal source-provide ... \
  --provenance-output provider-provenance.json

mgal validate-ledger provider-provenance.json \
  --audio-root <provider-artifact-root>
```

## LocalFileProvider

Describe it:

```bash
mgal provider-describe \
  --provider local \
  --audio-root ./audio
```

Run it:

```bash
mgal source-provide \
  --provider local \
  --audio-root ./audio \
  --provenance-ledger ./provenance-ledger.json \
  --request-id heavy-slash \
  --intent "heavy metallic sword slash" \
  --hint metal \
  --hint whoosh \
  --count 4 \
  --output ./provider-runs/heavy-slash.json \
  --provenance-output ./provider-runs/heavy-slash-provenance.json
```

Explicit hints are strict. If `--hint metal` finds no matching path, the Provider returns zero candidates instead of unrelated audio.

## FixtureGeneratedProvider

M1.0 includes a deterministic offline generated-audio fixture so the contract can be exercised before a real model is connected.

```bash
mgal source-provide \
  --provider fixture-generated \
  --artifact-root ./generated-fixture \
  --request-id impact \
  --intent "short stylized metallic impact" \
  --count 3 \
  --duration-ms 120 \
  --seed 42 \
  --output ./provider-runs/impact.json \
  --provenance-output ./provider-runs/impact-provenance.json
```

It uses no network, writes deterministic WAV fixtures, returns `provider_kind=generated`, and records provider/model/prompt/seed provenance. It is not a production audio generator.

## Provider validation

MGAL validates:

- contract version
- supported provider kind
- provider identity consistency
- absolute existing artifact root
- request bounds and candidate count
- unique candidate IDs
- candidate path containment
- candidate file existence
- byte size and SHA-256
- source ID derivation
- audio metadata basics
- full provenance schema
- provenance fingerprint consistency

If a Provider writes a candidate and the file changes before validation, the Result fails.

## Provider kinds

```text
local_file
generated
recorded
recipe
other
```

M1.0 implements a real `LocalFileProvider` and a contract-only `FixtureGeneratedProvider`. Production generated, recorded, and recipe adapters come next.

## Adapter authority boundary

A production Provider may acquire or create candidate audio. It must not:

- select the winning candidate
- mutate Recipes
- mutate Candidate Boards
- create or rewrite Evidence Bundles
- bypass provenance/license metadata
- release audio directly

Provider-specific credentials and network behavior stay adapter-local. Human taste and release authority remain downstream.

## Existing pipeline remains unchanged

```text
Provider candidate
      ↓
Browser Audition Board
      ↓
Layer Mixer
      ↓
A/B/C Candidate Board
      ↓
Evidence Bundle
      ↓
Replay / Relink
      ↓
Provenance / License
      ↓
Release / Attribution Pack
```

## Useful commands

```bash
mgal provider-describe --provider local --audio-root ./audio

mgal source-provide --provider local --audio-root ./audio --request-id slash --intent "heavy slash" --hint metal --count 4

mgal source-provide --provider fixture-generated --artifact-root ./generated --request-id impact --intent "short impact" --count 3 --seed 42

mgal serve ./audio
mgal bundle candidates.json --audio-root ./audio --provenance-ledger provenance-ledger.json --require-provenance --output ./evidence/session-001
mgal replay-bundle ./evidence/session-001 --audio-root ./audio
mgal release-pack ./evidence/session-001 --output ./release/final
mgal verify-release ./release/final
```

## Current constraints

- WAV artifacts only
- local search is filename/path based
- fixture generated provider is test infrastructure
- no provider registry or plugin discovery yet
- no automatic Provider-candidate import into the Browser Board yet
- no remote credentials or API logic in MGAL core
- no Provider gets authority to select or release audio

## Design principle

> Acquisition is replaceable. Taste, evidence, and provenance stay stable.

The next production adapter can now plug into a boundary that already preserves the rest of the creative chain.
