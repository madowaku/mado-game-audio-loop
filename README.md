# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work from “find something and drop it in” into a reproducible loop:

**scan → audition → layer → mix → fork → compare → decide → bundle → replay → recover → reuse**

## Current milestone: M0.7 Source Recovery / Relink

MGAL can now recover Evidence Replay after source WAV files have been moved or renamed.

The Evidence Bundle remains immutable.

Instead of rewriting old Recipes or source-index paths, MGAL creates an external `relink-map.json` that says:

```text
logical evidence path          current physical path

metal.wav                  →   archive/sfx/metal_03.wav
impact.wav                 →   combat/impact_final.wav
```

Recovery uses the original source fingerprints from `source-index.json`.

## Quick start

```bash
python -m pip install -e ".[dev]"
pytest
mgal serve ./audio
```

A normal evidence flow is:

```bash
mgal bundle candidates.json \
  --audio-root ./audio \
  --output ./evidence/session-001

mgal replay-bundle ./evidence/session-001 \
  --audio-root ./audio
```

If the library is later reorganized and replay fails:

```bash
mgal recover-sources ./evidence/session-001 \
  --search-root ./audio-reorganized \
  --output ./relinks/session-001.json
```

Then replay through the recovered map:

```bash
mgal replay-bundle ./evidence/session-001 \
  --audio-root ./audio-reorganized \
  --relink-map ./relinks/session-001.json
```

Optionally write a fresh replayed WAV outside the Evidence Bundle:

```bash
mgal replay-bundle ./evidence/session-001 \
  --audio-root ./audio-reorganized \
  --relink-map ./relinks/session-001.json \
  --output ./replays/session-001.wav
```

## Recovery behavior

MGAL scans `--search-root` recursively for WAV files.

For each source fingerprint in the Evidence Bundle:

1. try the original relative path first
2. if it no longer matches, filter candidate WAVs by byte size
3. SHA-256 only the size-compatible candidates
4. classify the source as:
   - `direct`
   - `relinked`
   - `ambiguous`
   - `missing`

A unique SHA-256 match is relinked automatically.

Example result:

```json
{
  "relink_map_version": "0.1",
  "complete": true,
  "resolved_count": 2,
  "ambiguous_count": 0,
  "missing_count": 0,
  "mappings": [
    {
      "source": "metal.wav",
      "status": "relinked",
      "target": "archive/sfx/metal_03.wav",
      "sha256": "...",
      "bytes": 24812,
      "matches": ["archive/sfx/metal_03.wav"]
    }
  ]
}
```

## Ambiguous matches

If two current files have the same expected bytes and SHA-256, MGAL does not guess.

```text
metal.wav
  ├── archive/metal.wav
  └── backup/metal-copy.wav

status = ambiguous
complete = false
```

The generated map lists both matches.

The user can remove the duplicate or explicitly edit the external map to one validated target, then mark the mapping resolved.

An incomplete map cannot be used for replay.

## Relink-map safety contract

A relink map is deliberately external to the Evidence Bundle.

MGAL enforces:

- relink map output must be outside the Evidence Bundle
- relink targets must stay beneath the supplied search/audio root
- targets must still match stored byte count and SHA-256 when loaded
- the map's logical source set must match the Candidate Board source set
- the map contains the SHA-256 of the Evidence Bundle `manifest.json`
- a map created for another Evidence Bundle is rejected

This keeps:

```text
Evidence = immutable historical truth
Relink map = current filesystem address book
```

## Evidence Replay with relinking

Replay still performs the full M0.6 chain:

```text
Evidence Bundle
      ↓
manifest integrity
      ↓
Candidate / Recipe / Decision semantics
      ↓
logical source set
      ↓
relink-map resolution
      ↓
current source SHA-256
      ↓
selected Recipe render
      ↓
stored output.wav comparison
      ↓
BYTE IDENTICAL
```

The Recipe itself is never rewritten.

## Evidence Bundle layout

```text
evidence/session-001/
├── intent.json
├── source-index.json
├── candidate-board.json
├── candidates/
├── selected-recipe.json
├── decision.json
├── output.wav
└── manifest.json

relinks/
└── session-001.json
```

The relink file is intentionally not inside `evidence/session-001/`.

## Useful commands

```bash
mgal --help
mgal scan ./audio
mgal validate recipe.json
mgal validate-board candidates.json
mgal bundle candidates.json --audio-root ./audio --output ./evidence/session-001
mgal verify-bundle ./evidence/session-001
mgal replay-bundle ./evidence/session-001 --audio-root ./audio
mgal recover-sources ./evidence/session-001 --search-root ./audio-new
mgal recover-sources ./evidence/session-001 --search-root ./audio-new --output ./relinks/session-001.json
mgal replay-bundle ./evidence/session-001 --audio-root ./audio-new --relink-map ./relinks/session-001.json
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
- lineage
- decisions and reasons

### Evidence Bundle

Freezes the historical decision:

- intent
- source fingerprints
- Candidate Board
- selected Recipe
- decision
- rendered output
- payload manifest

### Relink Map

Resolves historical logical source names to current physical files:

- source
- target
- status
- SHA-256
- byte size
- match candidates
- bound Evidence Bundle manifest hash

## Current constraints

M0.7 stays intentionally compact:

- WAV library only
- local machine only
- maximum four mixer layers
- recovery searches one root per command
- automatic recovery requires a unique SHA-256 match
- source audio itself is not copied into the Evidence Bundle
- renderer currently expects 16-bit mono WAV layers at a shared sample rate
- no cryptographic signing yet
- no trimming, EQ, pitch, reverb, or waveform editing yet

## Design principle

> Shorten the distance between “I imagine this sound” and “I can hear it in the game”.

AI generation remains a future source provider. The creative loop, its evidence, and its replayability remain the product.
