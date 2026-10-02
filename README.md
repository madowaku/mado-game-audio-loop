# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work from “find something and drop it in” into a reproducible creative loop:

**scan → audition → mix → compare → decide → bundle → replay → recover → trace provenance**

## Current milestone: M0.8 Provenance / License Ledger

MGAL now tracks not only **what bytes produced a sound**, but also **where those bytes came from**.

Every source WAV can be associated with a content-addressed provenance record:

```text
WAV bytes
   ↓
SHA-256
   ↓
source_id = sha256:<hash>
   ↓
provenance / origin / license / generation / recording metadata
```

The key design rule is:

> **Path is a hint. SHA-256 is identity.**

That means provenance survives the M0.7 case where files are moved or renamed.

## Create a ledger

Scan a WAV library:

```bash
mgal provenance-scan ./audio \
  --output ./provenance-ledger.json
```

Initial entries are deliberately conservative:

```json
{
  "source_type": "unknown",
  "license": {
    "status": "unknown"
  }
}
```

MGAL does not guess origin or legal rights.

## Fill provenance

### Free-library source

```bash
mgal provenance-set ./provenance-ledger.json metal.wav \
  --source-type free_library \
  --creator "Example Creator" \
  --title "Metal Hit" \
  --origin-url "https://example.invalid/sound" \
  --license-status declared \
  --license-expression "CC0-1.0" \
  --license-url "https://example.invalid/license" \
  --attribution "Example Creator"
```

### Self-recorded source

```bash
mgal provenance-set ./provenance-ledger.json cloth.wav \
  --source-type recorded \
  --license-status owned \
  --recorded-by "madowaku" \
  --recorded-at "2026-10-02" \
  --device "portable recorder"
```

### Generated source

```bash
mgal provenance-set ./provenance-ledger.json generated-impact.wav \
  --source-type generated \
  --license-status terms \
  --license-expression "provider-terms" \
  --license-url "https://example.invalid/terms" \
  --provider "ExampleProvider" \
  --model "ExampleModel" \
  --prompt "short stylized metallic impact" \
  --seed "42"
```

Generation fields are provider-neutral on purpose. Future audio-generation adapters can populate the same ledger contract.

## Validate the ledger

Structure only:

```bash
mgal validate-ledger ./provenance-ledger.json
```

Also verify that current files still match their recorded fingerprints:

```bash
mgal validate-ledger ./provenance-ledger.json \
  --audio-root ./audio
```

The report distinguishes structurally valid entries from **complete provenance entries**.

An entry is complete when:

- `source_type` is known
- license status is known
- `declared` / `terms` licenses have an expression
- generated sources include provider, model, and prompt
- recorded sources include recorded-by

MGAL records these declarations. It does not independently determine whether a license is legally sufficient for a particular use.

## Supported source types

```text
unknown
free_library
recorded
generated
procedural
purchased
commissioned
other
```

## License status vocabulary

```text
unknown
declared
owned
terms
```

These are provenance states, not legal opinions.

## Strict Evidence Bundle

A normal bundle remains backward compatible.

To embed provenance for the sources actually referenced by the Candidate Board:

```bash
mgal bundle candidates.json \
  --audio-root ./audio \
  --provenance-ledger ./provenance-ledger.json \
  --output ./evidence/session-001
```

For release-quality evidence, require complete provenance:

```bash
mgal bundle candidates.json \
  --audio-root ./audio \
  --provenance-ledger ./provenance-ledger.json \
  --require-provenance \
  --output ./evidence/session-001
```

Strict mode rejects the bundle before writing anything if referenced sources have incomplete provenance.

## Evidence layout

With provenance enabled:

```text
evidence/session-001/
├── intent.json
├── source-index.json
├── provenance-ledger.json
├── candidate-board.json
├── candidates/
├── selected-recipe.json
├── decision.json
├── output.wav
└── manifest.json
```

`provenance-ledger.json` contains only entries used by that Evidence Bundle.

Each source in `source-index.json` also receives a stable content identity:

```json
{
  "relative_path": "metal.wav",
  "sha256": "...",
  "source_id": "sha256:..."
}
```

The embedded ledger is matched by `source_id`, not filename.

## Evidence provenance policy

When `--require-provenance` is used, `manifest.json` records:

```json
{
  "provenance_required": true
}
```

Later `verify-bundle` and `replay-bundle` recompute provenance completeness from the actual entries.

They do not trust a stored `complete: true` flag by itself.

## M0.7 relinking still works

Historical evidence remains immutable:

```text
Evidence source identity = SHA-256
Filesystem location      = relink-map.json
Provenance identity      = same SHA-256
```

So this remains valid:

```bash
mgal recover-sources ./evidence/session-001 \
  --search-root ./audio-reorganized \
  --output ./relinks/session-001.json

mgal replay-bundle ./evidence/session-001 \
  --audio-root ./audio-reorganized \
  --relink-map ./relinks/session-001.json
```

Moving a file does not change its provenance identity.

## Useful commands

```bash
mgal provenance-scan ./audio -o provenance-ledger.json
mgal provenance-set provenance-ledger.json metal.wav --source-type free_library ...
mgal validate-ledger provenance-ledger.json --audio-root ./audio

mgal scan ./audio
mgal serve ./audio
mgal validate recipe.json
mgal validate-board candidates.json

mgal bundle candidates.json --audio-root ./audio --output ./evidence/session-001
mgal bundle candidates.json --audio-root ./audio --provenance-ledger provenance-ledger.json --require-provenance --output ./evidence/session-001

mgal verify-bundle ./evidence/session-001
mgal replay-bundle ./evidence/session-001 --audio-root ./audio
mgal recover-sources ./evidence/session-001 --search-root ./audio-new --output ./relinks/session-001.json
```

## Persistence layers

### Recipe

Reproduces the sound.

### Candidate Board

Reproduces the comparison and human decision.

### Provenance Ledger

Explains where source bytes came from and what usage declaration accompanies them.

### Evidence Bundle

Freezes the selected creative decision, fingerprints, scoped provenance, and rendered output.

### Relink Map

Maps immutable historical source identities to their current filesystem locations.

## Current constraints

M0.8 intentionally remains small:

- WAV library only
- provenance metadata is user-declared
- MGAL does not provide legal advice or independently verify license terms
- ledger validation against `--audio-root` expects current `path_hint` locations
- generated-source metadata is provider-neutral
- source audio itself is not copied into Evidence Bundles
- renderer still expects 16-bit mono WAV layers at one sample rate
- no cryptographic signing yet
- no trimming, EQ, pitch, reverb, or waveform editing yet

## Design principle

> Shorten the distance between “I imagine this sound” and “I can safely reproduce how it was made.”

AI generation remains a future Source Provider. Provenance is now ready for it.
