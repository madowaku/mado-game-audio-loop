# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work into a reproducible creative loop:

**provide → normalize → audition → mix → compare → decide → bundle → replay → provenance → release**

## Current milestone: M1.2 Provider Audio Normalizer

MGAL now normalizes Provider audio into one deterministic internal WAV profile before mixing and Evidence rendering.

The core rule is:

> **Keep the provider original. Mix the canonical derivative. Preserve the lineage between both.**

Canonical profile:

```text
profile_id   = mgal-pcm16-mono-44100-v1
sample rate  = 44,100 Hz
channels     = mono
sample width = 16-bit PCM
container    = WAV
```

This matches the current deterministic renderer contract and removes sample-rate/channel differences between Provider sources.

## Why M1.2 exists

A generated Provider may return stereo 44.1/48 kHz audio while older local assets may be mono 8/22/44.1 kHz.

Before M1.2:

```text
local 8k mono
+
generated 48k stereo
        ↓
renderer mismatch
```

After M1.2:

```text
local Provider Result
        ↓
Provider Audio Normalizer
        ↓
44.1k mono PCM16

generated Provider Result
        ↓
Provider Audio Normalizer
        ↓
44.1k mono PCM16

        ↓
same Layer Mixer / Recipe / Evidence renderer
```

## Normalize a saved Provider Result

Provider Result JSON is now reloadable.

```bash
mgal provider-normalize ./provider-runs/heavy-slash.json \
  --output-root ./audio/canonical/heavy-slash \
  --output ./provider-runs/heavy-slash-normalized.json \
  --provenance-output ./provider-runs/heavy-slash-normalized-provenance.json
```

The original Provider artifacts are not modified.

The normalized Provider Result points to the new canonical artifact root.

## Normalization behavior

### Already canonical

A 44.1kHz, mono, 16-bit PCM WAV uses a byte-preserving copy.

```text
original SHA-256 == normalized SHA-256
passthrough = true
algorithm = byte-preserving-copy
```

### Non-canonical PCM WAV

MGAL currently:

1. decodes PCM WAV samples
2. averages channels to mono
3. converts sample depth to signed 16-bit
4. linearly resamples to 44.1kHz
5. writes deterministic PCM16 mono WAV

```text
algorithm = channel-average+linear-resample+pcm16
```

Supported PCM sample widths are currently 8, 16, 24, and 32-bit integer WAV.

Compressed WAV is rejected.

## Original and normalized identities

The normalized artifact becomes the active source identity used by Recipes and Evidence.

Its provenance carries a normalization lineage:

```json
{
  "source_id": "sha256:<normalized>",
  "sha256": "<normalized>",
  "normalization": {
    "profile_id": "mgal-pcm16-mono-44100-v1",
    "passthrough": false,
    "original": {
      "source_id": "sha256:<original>",
      "sha256": "<original>",
      "bytes": 12345,
      "relative_path": "provider-original.wav"
    },
    "normalized": {
      "source_id": "sha256:<normalized>",
      "sha256": "<normalized>",
      "bytes": 6789,
      "sample_rate": 44100,
      "channels": 1,
      "sample_width": 2
    }
  }
}
```

So downstream Evidence can answer both:

- which exact canonical bytes were mixed
- which exact Provider bytes those canonical bytes came from

## Provenance validation

M0.8 provenance validation now understands normalization lineage.

It checks:

- normalization profile ID
- passthrough flag
- algorithm
- original source ID ↔ original SHA-256
- normalized source ID ↔ normalized SHA-256
- normalized identity ↔ top-level provenance identity

A broken lineage is rejected even if the top-level source hash is otherwise valid.

## Release lineage

`PROVENANCE_REPORT.json` now includes the normalization object.

A final Release Pack therefore retains:

```text
Release WAV
   ↓
canonical source SHA-256
   ↓
normalization lineage
   ↓
original Provider SHA-256
   ↓
provider generation / recording / origin metadata
```

## Stable Audio workflow

A practical generated-audio loop is now:

```bash
mgal source-provide \
  --provider stability \
  --artifact-root ./provider-raw/stability/heavy-slash \
  --allow-paid \
  --request-id heavy-slash \
  --intent "short stylized metallic sword slash" \
  --count 1 \
  --output ./provider-runs/heavy-slash.json \
  --provenance-output ./provider-runs/heavy-slash-raw-provenance.json

mgal provider-normalize ./provider-runs/heavy-slash.json \
  --output-root ./audio/canonical/generated/heavy-slash \
  --output ./provider-runs/heavy-slash-normalized.json \
  --provenance-output ./provider-runs/heavy-slash-normalized-provenance.json

mgal serve ./audio
```

Generating and normalizing are deliberately separate operations.

That means a paid Provider call can be reused and re-normalized without spending additional generation credits.

## Mixed local + generated workflow

Local assets can go through the same boundary.

```bash
mgal source-provide \
  --provider local \
  --audio-root ./raw-local \
  --provenance-ledger ./local-provenance.json \
  --request-id metal \
  --intent "metal" \
  --count 1 \
  --output ./provider-runs/metal.json

mgal provider-normalize ./provider-runs/metal.json \
  --output-root ./audio/canonical/local \
  --output ./provider-runs/metal-normalized.json \
  --provenance-output ./provider-runs/metal-normalized-provenance.json

mgal provenance-merge \
  ./provider-runs/metal-normalized-provenance.json \
  ./provider-runs/heavy-slash-normalized-provenance.json \
  --output ./combined-provenance.json
```

Now both sources share one renderer-safe format.

## Determinism

Normalization is deterministic for the same Provider artifact and profile.

CI verifies that repeated normalization produces the same normalized SHA-256.

Provider originals are also re-hashed before normalization through Source Provider Contract validation.

## Integration proof

CI includes an end-to-end fixture with intentionally incompatible inputs:

```text
local source:      8kHz mono PCM16
generated source: 48kHz stereo PCM16
         ↓
normalize both
         ↓
44.1kHz mono PCM16
         ↓
mixed selected Recipe
         ↓
strict Evidence Bundle
         ↓
output.wav = 44.1kHz mono PCM16
```

No network or paid generation is used in CI.

## Provider foundation remains stable

Source Provider Contract stays at version 1.0.

M1.2 is a transformation layer after acquisition, not a Provider-specific exception.

```text
Provider
   ↓
ProviderResult raw
   ↓
Normalizer
   ↓
ProviderResult canonical
   ↓
MGAL creative loop
```

## Current constraints

- canonical profile is fixed at 44.1kHz mono PCM16
- PCM WAV input only
- no FLAC/OGG/MP3 decode yet
- channel conversion is arithmetic averaging
- resampling uses deterministic linear interpolation, not studio-grade SRC
- no loudness normalization yet
- raw Provider artifacts are not embedded into Evidence, but their hashes remain in lineage
- normalizer outputs are separate files and do not overwrite originals

## Design principle

> Provider bytes are historical evidence. Canonical bytes are creative working material.

M1.2 lets MGAL mix heterogeneous sources while preserving exactly where every normalized sound came from.
