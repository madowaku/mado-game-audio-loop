# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work into a reproducible creative loop:

**provide → intake → audition → mix → compare → decide → evidence → replay → release**

## Current milestone: M1.3 Provider Intake / Audition Bridge

M1.3 connects Provider output to the Browser Audition Board.

The core flow is now:

```text
Provider Result
    ↓
provider-intake
    ↓
canonical normalization
    ↓
workspace registration
    ↓
workspace provenance merge
    ↓
Audition Board live catalog
```

The Browser Board can stay open while Provider candidates arrive.

## Workspace layout

An MGAL audio workspace now has two layers:

```text
audio/
├── incoming/
│   └── <intake-id>/
│       ├── candidate-01.wav
│       └── candidate-02.wav
└── .mgal/
    ├── provenance-ledger.json
    └── intakes/
        └── <intake-id>/
            ├── manifest.json
            ├── provider-result.json
            └── provenance-ledger.json
```

The visible WAV tree stays simple.

The hidden `.mgal` layer stores intake history and workspace provenance.

## Intake a saved Provider Result

```bash
mgal provider-intake ./provider-runs/heavy-slash.json \
  --audio-root ./audio \
  --intake-id heavy-slash-001
```

The command:

1. reloads and validates the saved Provider Result
2. normalizes every candidate to the M1.2 canonical profile
3. writes canonical WAVs below `audio/incoming/<intake-id>/`
4. writes an intake-scoped Provider Result
5. writes an intake-scoped Provenance Ledger
6. merges provenance into `audio/.mgal/provenance-ledger.json`
7. writes and verifies the intake manifest

Canonical profile:

```text
mgal-pcm16-mono-44100-v1
44.1 kHz
mono
16-bit PCM WAV
```

## Intake identity

If `--intake-id` is omitted, MGAL derives one from:

```text
request id
+
provider id
+
Provider Result SHA-256 prefix
```

The same Provider Result with the same intake ID is idempotent.

A repeated intake verifies existing artifacts and returns:

```json
{
  "reused": true
}
```

The same intake ID cannot silently point to a different Provider Result.

## Intake manifest

Each intake session records:

```text
intake_version
intake_id
provider_result_sha256
provider_id
provider_kind
request
normalization_profile_id
normalized_provider_result_sha256
candidate_count
candidates[]
```

Each candidate records:

- workspace-relative WAV path
- normalized source ID
- normalized SHA-256
- byte size
- source type
- generation metadata
- normalization lineage

The manifest is verified against the current WAV bytes before the workspace Ledger is updated.

## Workspace provenance

Every accepted candidate gets a workspace-relative provenance path.

Example:

```text
incoming/heavy-slash-001/01-impact-....wav
```

The central workspace Ledger is:

```text
audio/.mgal/provenance-ledger.json
```

It can later be used directly for strict Evidence creation.

Conflicting complete provenance for the same content-addressed source remains an error.

## Audition Board bridge

Run the Browser Board once:

```bash
mgal serve ./audio
```

Then intake new Provider Runs in another terminal.

The browser polls `/api/audio` every 2.5 seconds.

When the catalog changes, only the source list is refreshed.

New intake cards display:

- source type
- Provider ID
- intake ID
- generation Provider
- generation model
- prompt / intent
- normal audio metadata

Provider/intake/prompt text is searchable from the existing Find a sound box.

There is also a manual:

```text
↻ Refresh sources
```

button.

## Generated-audio path

A practical Stable Audio flow is now:

```bash
mgal source-provide \
  --provider stability \
  --artifact-root ./provider-raw/stability/heavy-slash \
  --allow-paid \
  --request-id heavy-slash \
  --intent "short stylized metallic sword slash" \
  --count 1 \
  --output ./provider-runs/heavy-slash.json

mgal provider-intake ./provider-runs/heavy-slash.json \
  --audio-root ./audio \
  --intake-id heavy-slash-001

mgal serve ./audio
```

If `mgal serve ./audio` is already running, the final command is unnecessary.

The new sound appears automatically.

## Why acquisition and intake remain separate

M1.3 does not combine paid generation and workspace registration into one irreversible command.

Instead:

```text
paid acquisition
      ↓
saved Provider Result
      ↓
free repeatable intake
```

This means a paid Provider Run can be re-intaken, re-normalized, or moved into another MGAL workspace without buying the audio again.

## Browser catalog metadata

The server enriches intake WAV rows with:

```text
intake_id
provider_id
provider_kind
request_id
intent
source_type
source_id
generation_provider
generation_model
prompt
normalization_profile_id
original_source_id
```

Ordinary local WAVs continue to work without intake metadata.

## Existing creative loop remains unchanged

Once a source is visible in the Board:

```text
Audition
  ↓
Add layer
  ↓
Live Mix
  ↓
A/B/C Candidate Board
  ↓
Human Select
  ↓
Evidence Bundle
  ↓
Replay / Relink
  ↓
Release Pack
```

Provider metadata informs the choice but never makes the choice.

## Useful commands

```bash
mgal provider-describe --provider stability

mgal source-provide \
  --provider stability \
  --artifact-root ./provider-raw/stability/run-001 \
  --allow-paid \
  --request-id impact \
  --intent "short metallic impact" \
  --count 1 \
  --output ./provider-runs/impact.json

mgal provider-intake ./provider-runs/impact.json \
  --audio-root ./audio \
  --intake-id impact-001

mgal serve ./audio

mgal bundle candidate-board.json \
  --audio-root ./audio \
  --provenance-ledger ./audio/.mgal/provenance-ledger.json \
  --require-provenance \
  --output ./evidence/session-001

mgal replay-bundle ./evidence/session-001 --audio-root ./audio
mgal release-pack ./evidence/session-001 --output ./release/final
```

## Current constraints

- intake accepts saved MGAL Provider Result JSON
- canonical audio profile remains fixed at 44.1kHz mono PCM16
- workspace catalog refresh uses lightweight polling, not WebSocket/SSE
- intake metadata is local JSON, not a database
- no Provider generation button inside the browser yet
- no automatic Candidate Board seeding from an intake session yet
- no archive/prune UI for old intake sessions yet

## Design principle

> Providers deliver possibilities. Intake makes them available. Humans decide what becomes the sound.

M1.3 closes the gap between generated/acquired audio and the place where the creator can actually listen to it.
