# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work from “find something and drop it in” into a reproducible loop:

**scan → audition → layer → mix → fork → compare → decide → bundle → verify → reuse**

## Current milestone: M0.5 Evidence Bundle

MGAL can now freeze a completed A/B/C sound-design decision into an inspectable evidence package.

The bundle records:

- the original intent
- every source file actually referenced by the Base Recipe or candidates
- source WAV metadata and SHA-256 fingerprints
- the full Candidate Board
- each candidate Recipe
- the selected Recipe
- the selected decision and reason
- a rendered WAV of the selected Recipe
- a manifest containing hashes and sizes for every payload file

This turns “B sounded best” into a durable artifact that answers:

- Which candidate was selected?
- Why was it selected?
- Which sources were involved?
- Which exact source bytes were used?
- What Recipe produced the final WAV?
- Has any evidence file changed since the bundle was created?

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

Verify it later:

```bash
mgal verify-bundle ./evidence/session-001
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

M0.5 stays intentionally compact:

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
