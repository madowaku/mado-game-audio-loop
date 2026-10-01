# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work from “find something and drop it in” into a reproducible loop:

**scan → audition → layer → mix → fork → compare → decide → bundle → replay → reuse**

## Current milestone: M0.6 Evidence Replay

MGAL can now prove that an Evidence Bundle is still reproducible against a current source library.

Replay verifies four linked layers:

- the Evidence Bundle payload set and manifest hashes
- the Candidate Board / selected Recipe / decision semantic chain
- every referenced source WAV against the stored source fingerprint
- a fresh deterministic render against the stored `output.wav`

A successful replay means the current source files can reproduce the selected sound byte-for-byte.
## Quick start

```bash
python -m pip install -e ".[dev]"
pytest
mgal serve ./audio
```

Build a mix in the browser, fork A/B/C, choose one candidate, and download the Candidate Board JSON.

Then build an Evidence Bundle:

```bash
mgal bundle ~/Downloads/heavy-slash-base-candidates.json \
  --audio-root ./audio \
  --output ./evidence/session-001
```

Verify bundle integrity later:

```bash
mgal verify-bundle ./evidence/session-001
```

Replay the evidence against the current source library:

```bash
mgal replay-bundle ./evidence/session-001 \
  --audio-root ./audio
```

Optionally save the regenerated WAV outside the bundle:

```bash
mgal replay-bundle ./evidence/session-001 \
  --audio-root ./audio \
  --output ./replays/session-001.wav
```

## Evidence Bundle layout

```text
evidence/session-001/
├── intent.json
├── source-index.json
├── candidate-board.json
├── candidates/
│   ├── 01-a-....json
│   ├── 02-b-....json
│   └── 03-c-....json
├── selected-recipe.json
├── decision.json
├── output.wav
└── manifest.json
```

### source-index.json

Only source files actually referenced by the Base Recipe or candidates are indexed.

Each entry includes:

```text
relative_path
sha256
bytes
duration_ms
sample_rate
channels
sample_width
frames
```

Source paths are resolved beneath `--audio-root`. Absolute paths and traversal outside that root are rejected.

### manifest.json

The manifest contains one entry for every payload file except the manifest itself:

```json
{
  "evidence_bundle_version": "0.1",
  "base_recipe_id": "heavy-slash-base",
  "selected_candidate_id": "heavy-slash-base-b",
  "file_count": 9,
  "files": [
    {
      "path": "decision.json",
      "sha256": "...",
      "bytes": 412
    }
  ]
}
```

`mgal verify-bundle` checks:

- manifest version
- manifest file count
- duplicate paths
- path traversal
- file existence
- file byte size
- SHA-256 content hash

Any changed payload file causes verification to fail.

## Evidence Replay contract

`mgal replay-bundle` first runs normal bundle verification, then:

1. validates the Candidate Board and selected candidate
2. confirms `manifest.json`, `candidate-board.json`, `selected-recipe.json`, and `decision.json` agree on the selected candidate
3. confirms the source-index path set exactly matches all sources referenced by the Base Recipe and candidates
4. verifies current source byte sizes and SHA-256 values
5. re-renders the selected Recipe in a temporary directory
6. compares regenerated WAV byte size and SHA-256 with stored `output.wav`

Replay output is read-only by default. `--output` may write a copy outside the Evidence Bundle.

This is an integrity and reproducibility check, not a cryptographic signature. A coordinated rewrite of the entire bundle and manifest is outside M0.6's authenticity guarantees.

## Candidate workflow

```text
local WAV library
      ↓
build one layered mix
      ↓
Fork A/B/C
      ↓
edit + preview candidates
      ↓
Favorite / Reject / Select
      ↓
record decision reason
      ↓
download Candidate Board
      ↓
mgal bundle
      ↓
Evidence Bundle
      ↓
mgal verify-bundle
```

## Useful commands

```bash
mgal --help
mgal scan ./audio
mgal validate recipe.json
mgal validate-board candidates.json
mgal bundle candidates.json --audio-root ./audio --output ./evidence/session-001
mgal verify-bundle ./evidence/session-001
mgal replay-bundle ./evidence/session-001 --audio-root ./audio
mgal render recipe.json --audio-root ./audio --output output.wav
mgal serve ./audio --no-browser
```

## Persistence layers

### Recipe

Reproduces the sound:

- source
- gain
- offset_ms
- processing

### Candidate Board

Reproduces the creative comparison:

- Base Recipe
- A/B/C Recipes
- revisions
- parent revision references
- lineage
- favorite / reject / selected state
- decision reasons

### Evidence Bundle

Freezes the decision into an auditable package:

- intent
- source fingerprints
- Candidate Board
- candidate Recipes
- selected Recipe
- decision
- rendered output
- payload manifest

## Current constraints

M0.6 stays intentionally compact:

- WAV library only
- local machine only
- maximum four mixer layers
- browser UI has no cloud/CDN dependency
- bundle creation requires exactly one selected candidate
- source audio itself is not copied into the bundle
- renderer currently expects 16-bit mono WAV layers at a shared sample rate
- no trimming, EQ, pitch, reverb, or waveform editing yet

## Project layout

```text
docs/           product and implementation specs
src/mgal/       Python package
src/mgal/web/   local browser workbench
fixtures/       deterministic test data and recipes
tests/          recipe, render, server, candidate, evidence, and UI tests
```

## Design principle

> Shorten the distance between “I imagine this sound” and “I can hear it in the game”.

AI generation remains a future source provider. The creative loop and its evidence remain the product.
