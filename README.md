# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work from “find something and drop it in” into a reproducible creative loop:

**scan → audition → mix → compare → decide → bundle → replay → recover → trace provenance → release**

## Current milestone: M0.9 Release / Attribution Pack

MGAL can now turn a verified Evidence Bundle into a compact, release-ready audio package.

The Release Pack contains only the final selected sound and the metadata needed to explain where it came from.

```text
Evidence Bundle
      ↓
verify evidence
      ↓
selected Recipe only
      ↓
selected source fingerprints only
      ↓
complete provenance only
      ↓
Release / Attribution Pack
```

## Build a Release Pack

```bash
mgal release-pack ./evidence/session-001 \
  --output ./release/heavy-slash
```

Optionally choose the final WAV filename:

```bash
mgal release-pack ./evidence/session-001 \
  --name "Heavy Slash Final" \
  --output ./release/heavy-slash
```

Example output:

```text
release/heavy-slash/
├── heavy-slash-final.wav
├── ATTRIBUTION.txt
├── LICENSE_SUMMARY.json
├── PROVENANCE_REPORT.json
├── RECIPE.json
├── EVIDENCE_REF.json
└── RELEASE_MANIFEST.json
```

## What ships

### Final WAV

The final WAV is copied from the verified Evidence Bundle `output.wav`.

It is not re-rendered during release packaging.

### ATTRIBUTION.txt

Human-readable source credits and provenance declarations for sources that are actually used by the final selected Recipe.

Sources that appeared only in rejected/base candidates are excluded.

### LICENSE_SUMMARY.json

Machine-readable summary of the recorded license declarations for final sources.

It includes:

- source ID
- source type
- origin / creator / source URL
- license status / expression / URL
- attribution text
- generation metadata
- recording metadata

MGAL records declarations. This summary is not a legal determination.

### PROVENANCE_REPORT.json

Release-scoped provenance report bound to final selected source fingerprints.

### RECIPE.json

The final selected MGAL Recipe.

### EVIDENCE_REF.json

Links the release back to the Evidence Bundle:

```json
{
  "evidence_ref_version": "0.1",
  "evidence_manifest_sha256": "...",
  "selected_candidate_id": "...",
  "selected_recipe_id": "...",
  "evidence_output_sha256": "..."
}
```

### RELEASE_MANIFEST.json

Hashes and sizes every release payload and records the originating Evidence manifest SHA-256.

## Verify before shipping

```bash
mgal verify-release ./release/heavy-slash
```

Verification checks:

- release manifest file set, byte sizes, and SHA-256 values
- exactly one final WAV
- Recipe ID ↔ release manifest
- License Summary ↔ Provenance Report source set
- source counts
- selected candidate / Recipe semantic consistency
- Evidence reference ↔ release manifest
- final WAV SHA-256 ↔ Evidence output SHA-256

So even if a metadata file is edited and its manifest hash is recomputed, semantic mismatches can still fail verification.

## Release source selection

M0.9 deliberately uses the **selected Recipe**, not the whole Candidate Board.

Example:

```text
Base candidate used metal.wav
Rejected candidate used cloth.wav
Selected candidate uses impact.wav + whoosh.wav

Release Pack sources:
✓ impact.wav
✓ whoosh.wav
✗ metal.wav
✗ cloth.wav
```

This keeps shipping attribution aligned with what is actually in the released sound.

## Provenance gate

A Release Pack requires embedded provenance in the Evidence Bundle.

Every source used by the selected Recipe must have complete provenance according to M0.8 rules.

This means an Evidence Bundle may be useful for internal experimentation with incomplete provenance, while release packaging remains strict.

## Evidence remains immutable

Release output must be outside the Evidence Bundle.

```text
evidence/session-001/   historical evidence, read-only
release/heavy-slash/    shipping artifact
```

MGAL refuses to create the Release Pack inside the Evidence directory.

## End-to-end release flow

```bash
mgal provenance-scan ./audio -o provenance-ledger.json

mgal provenance-set provenance-ledger.json impact.wav \
  --source-type free_library \
  --license-status declared \
  --license-expression "CC-BY-4.0" \
  --attribution "Impact by Creator"

mgal bundle candidates.json \
  --audio-root ./audio \
  --provenance-ledger provenance-ledger.json \
  --require-provenance \
  --output ./evidence/session-001

mgal replay-bundle ./evidence/session-001 \
  --audio-root ./audio

mgal release-pack ./evidence/session-001 \
  --output ./release/heavy-slash

mgal verify-release ./release/heavy-slash
```

## Useful commands

```bash
mgal serve ./audio
mgal scan ./audio

mgal provenance-scan ./audio -o provenance-ledger.json
mgal provenance-set provenance-ledger.json impact.wav ...
mgal validate-ledger provenance-ledger.json --audio-root ./audio

mgal validate recipe.json
mgal validate-board candidates.json

mgal bundle candidates.json --audio-root ./audio --provenance-ledger provenance-ledger.json --require-provenance --output ./evidence/session-001
mgal verify-bundle ./evidence/session-001
mgal replay-bundle ./evidence/session-001 --audio-root ./audio
mgal recover-sources ./evidence/session-001 --search-root ./audio-new --output ./relinks/session-001.json

mgal release-pack ./evidence/session-001 --output ./release/heavy-slash
mgal verify-release ./release/heavy-slash
```

## Persistence layers

### Recipe

Reproduces the sound.

### Candidate Board

Reproduces the comparison and human decision.

### Provenance Ledger

Explains where source bytes came from and what usage declaration accompanies them.

### Evidence Bundle

Freezes the historical creative decision, source fingerprints, provenance, and rendered output.

### Relink Map

Maps historical source identities to current filesystem locations.

### Release Pack

Packages only the final WAV and the release-facing attribution/provenance chain.

## Current constraints

M0.9 intentionally remains compact:

- one final WAV per Release Pack
- WAV only
- release packaging requires complete provenance for final selected sources
- provenance/license metadata is user-declared
- MGAL does not independently verify legal sufficiency
- Release Pack does not copy raw source WAVs
- Release Pack is a directory, not ZIP packaging yet
- no cryptographic signing yet

## Design principle

> Evidence explains how the sound was made. Release Pack explains what is actually shipping.

AI generation remains a future Source Provider. Its provider/model/prompt/terms metadata already fits the same release path.
