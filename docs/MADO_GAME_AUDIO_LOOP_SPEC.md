# MADO_GAME_AUDIO_LOOP_SPEC.md

Version: 0.1  
Status: Draft  
Project: \`mado-game-audio-loop\`  
Codename: MGAL

## One sentence

Game SFX should be a reproducible creative loop, not a folder-diving chore.

## Core loop

\`\`\`text
Intent
  ↓
Source
  ↓
Layer / Transform
  ↓
Audition
  ↓
Mix / Compare
  ↓
Select
  ↓
Recipe
  ↓
Render
  ↓
Game
  ↓
Evidence
\`\`\`

## Product principles

1. **Search less, compose more.**
2. **One-shot generation is not the goal.**
3. **Human taste stays in the loop.**
4. **Audio is a recipe, not just a WAV file.**
5. **AI generators are providers, not the core.**

## Primary user

A solo or small-team game developer who can build the game but currently chooses or places sound effects ad hoc.

## Core data model

A recipe is the source of truth.

\`\`\`json
{
  "recipe_version": "0.1",
  "id": "sword-slash-heavy-001",
  "intent": "heavy metallic sword slash",
  "layers": [
    {
      "source": "cloth.wav",
      "gain": 0.55,
      "offset_ms": 0
    },
    {
      "source": "metal.wav",
      "gain": 0.80,
      "offset_ms": 25
    },
    {
      "source": "whoosh.wav",
      "gain": 0.40,
      "offset_ms": 10
    }
  ],
  "processing": {
    "normalize": true,
    "fade_out_ms": 80
  }
}
\`\`\`

## Milestones

### MGAL-M0.1 Local Audio Workbench

Established:

- Python package and CLI
- recipe validation
- WAV scanner
- deterministic layered renderer
- fixtures and tests

### MGAL-M0.2 Browser Audition Board

Established:

- safe local HTTP server
- WAV metadata API
- filename/path search
- lazy waveform rendering
- one-click audition
- shortlist of up to four layers
- recipe draft download
- path traversal protection

### MGAL-M0.3 Layer Mixer

Goal:

**Turn the shortlist into a playable sound recipe before leaving the browser.**

Run:

\`\`\`bash
mgal serve ./audio
\`\`\`

Mixer flow:

\`\`\`text
candidate sounds
      ↓
selected layers
      ↓
Web Audio buffer cache
      ↓
sample-accurate scheduled starts
      ↓
per-layer gain nodes
      ↓
live mute / solo / gain
      ↓
offset rescheduling
      ↓
recipe JSON
\`\`\`

#### Controls

Each selected layer exposes:

- **Gain**: linear gain, 0.00× to 2.00×
- **Offset**: 0–5000 ms
- **Mute**: temporary audition exclusion
- **Solo**: temporary audition isolation
- **Remove**: remove layer from candidate mix

Transport:

- Preview mix
- Replay mix
- Stop
- global Stop all for individual auditions and mix playback

#### Persistence contract

Saved to Recipe:

\`\`\`text
source
gain
offset_ms
\`\`\`

Not saved:

\`\`\`text
mute
solo
\`\`\`

Mute and solo are listening tools, not creative source-of-truth decisions.

#### Live behavior

- gain changes update the active GainNode without restarting playback
- mute/solo update active GainNodes without restarting playback
- offset changes re-schedule the mix because source start time cannot be moved after scheduling
- decoded AudioBuffers are cached for waveform display and repeated mix previews

#### Downloaded Recipe rendering

Browser recipes use paths relative to the served audio root.

Therefore:

\`\`\`bash
mgal render recipe.json \
  --audio-root ./audio \
  --output output.wav
\`\`\`

The optional \`--audio-root\` makes recipe placement independent from source placement.

#### M0.3 acceptance

- 2–4 layers can be previewed together
- gain is audible live
- mute/solo are audible live
- offset changes affect the next scheduled mix
- downloaded recipe preserves gain and offset
- renderer can resolve a downloaded recipe with \`--audio-root\`
- browser JavaScript passes syntax checking in CI
- Python contract tests remain green

### MGAL-M0.4 Candidate Board

Established:

- fork the active mix into A/B/C candidates
- edit each candidate independently
- direct candidate preview without loading it into the mixer
- copy the active candidate into another candidate
- structural change count versus the immutable Base Recipe
- favorite / reject / selected decisions
- free-text decision reasons
- revision-qualified lineage refs such as `candidate-a@r1`
- Candidate Board JSON export
- Python-side Candidate Board validation

Candidate Board contract:

```text
Base Recipe
   ├── A r1
   ├── B r1
   └── C r1

Copy A@r1 → B

Base Recipe
   ├── A r1
   ├── B r2  parent=A@r1
   └── C r1
```

Each candidate stores `id`, `label`, `parent_recipe_id`, `revision`, `lineage`, embedded `recipe`, and `decision`.

Allowed decision states are `undecided`, `favorite`, `reject`, and `selected`. At most one candidate may be selected.

CLI validation:

```bash
mgal validate-board candidate-board.json
```

Validation covers recipe structure, unique candidate IDs, selected-candidate consistency, lineage ordering, latest lineage revision, and latest lineage parent source.

### MGAL-M0.5 Evidence Bundle

Goal:

**Freeze a completed Candidate Board decision into an auditable local evidence package.**

Command:

\`\`\`bash
mgal bundle candidate-board.json \\
  --audio-root ./audio \\
  --output ./evidence/session-001
\`\`\`

Output:

\`\`\`text
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
\`\`\`

Bundle creation requires one selected candidate.

#### Source evidence

MGAL indexes only source WAV files referenced by the Base Recipe or candidates.

Each source entry records:

- relative path
- SHA-256
- byte size
- duration
- sample rate
- channels
- sample width
- frame count

Sources must resolve beneath the supplied audio root. Absolute source paths and traversal outside the root are rejected.

#### Decision evidence

\`decision.json\` records:

- selected candidate ID
- label
- selected status
- human decision reason
- parent revision reference
- candidate revision
- lineage events

#### Render evidence

\`output.wav\` is rendered from the selected candidate Recipe during bundle creation.

This ties the human decision, Recipe, source fingerprints, and final audible artifact together.

#### Manifest

\`manifest.json\` contains the path, byte count, and SHA-256 of every bundle payload file except itself.

Verification:

\`\`\`bash
mgal verify-bundle ./evidence/session-001
\`\`\`

Verification checks:

- supported bundle version
- manifest file count
- duplicate manifest paths
- relative-path containment
- file existence
- byte size
- SHA-256 content hash

#### M0.5 acceptance

- Candidate Board with one selected candidate can be bundled
- Candidate Board without a selected candidate is rejected
- referenced source WAVs are fingerprinted
- candidate Recipes are exported separately
- selected Recipe is exported
- selected decision and lineage are exported
- selected Recipe renders to output.wav
- manifest covers all bundle payload files
- verify-bundle succeeds on untouched evidence
- verify-bundle detects payload tampering
- output paths cannot escape intended roots
- Python tests and browser JavaScript checks remain green

### MGAL-M0.6 Evidence Replay

Goal:

**Prove that a saved Evidence Bundle can still be reproduced from the current source library.**

Command:

```bash
mgal replay-bundle ./evidence/session-001 \
  --audio-root ./audio
```

Optional regenerated output:

```bash
mgal replay-bundle ./evidence/session-001 \
  --audio-root ./audio \
  --output ./replays/session-001.wav
```

Replay stages:

```text
Evidence Bundle
   ↓
strict manifest verification
   ↓
semantic chain validation
   ↓
source-index ↔ Candidate Board source-set validation
   ↓
current source SHA-256 verification
   ↓
selected Recipe re-render
   ↓
stored output.wav ↔ replayed WAV hash comparison
```

Semantic chain validation requires:

- manifest selected candidate ID matches Candidate Board
- selected-recipe ID and Recipe body match the selected Board candidate
- decision selected candidate ID matches
- decision status is `selected`
- decision reason, parent, revision, and lineage match the selected Board candidate

Source replay requires the exact source path set from the Candidate Board. Missing, extra, changed-size, or changed-hash source files fail replay.

The regenerated WAV must match stored `output.wav` in byte size and SHA-256.

The Evidence Bundle is read-only during replay. Optional replay output must be outside the bundle.

M0.6 verifies integrity and reproducibility. It does not provide cryptographic signing or provenance authenticity against a coordinated rewrite of the whole bundle.

#### M0.6 acceptance

- untouched bundle + original sources replays byte-identically
- changed source hash is detected
- missing source is detected
- untracked bundle payload is detected
- rehashed but semantically inconsistent decision evidence is detected
- selected Recipe must match Candidate Board
- source-index source set must match Candidate Board
- optional replay output is written only outside the Evidence Bundle
- Python tests and browser JavaScript checks remain green

### MGAL-M0.7 Source Recovery / Relink

Goal:

**Recover reproducible Evidence Replay after source WAV files have been moved or renamed, without modifying historical evidence.**

Recovery command:

```bash
mgal recover-sources ./evidence/session-001 \
  --search-root ./audio-reorganized \
  --output ./relinks/session-001.json
```

Replay with recovered sources:

```bash
mgal replay-bundle ./evidence/session-001 \
  --audio-root ./audio-reorganized \
  --relink-map ./relinks/session-001.json
```

Core rule:

```text
Evidence paths remain immutable.
Current filesystem paths live only in relink-map.json.
```

Recovery algorithm:

```text
source-index entry
      ↓
try original relative path
      ↓
if invalid:
filter current WAVs by byte size
      ↓
SHA-256 compatible candidates
      ↓
0 matches  → missing
1 match    → relinked
2+ matches → ambiguous
```

A direct match keeps status `direct`.

A unique moved/renamed hash match gets status `relinked`.

Multiple identical matches are not guessed. They produce an incomplete map with `status=ambiguous` and a list of candidate paths.

The map records:

- relink map version
- Evidence Bundle manifest SHA-256
- logical source count
- resolved / ambiguous / missing counts
- complete flag
- per-source logical source path
- resolution status
- current target path
- expected SHA-256
- expected byte size
- all hash matches

Relink-map safety:

- map file must be stored outside the Evidence Bundle
- target paths must be relative to the supplied search root
- targets are revalidated by byte count and SHA-256 at replay time
- incomplete maps cannot be used
- map source set must equal the Candidate Board source set
- map is bound to the Evidence Bundle via manifest SHA-256
- a map for another bundle is rejected

Renderer integration:

```text
Recipe logical source
      ↓
source_overrides
      ↓
validated current physical source
```

The renderer receives source overrides in memory. Recipe JSON and Candidate Board JSON are not mutated.

Replay result remains valid only if the freshly rendered WAV matches stored `output.wav` byte-for-byte.

#### M0.7 acceptance

- moved and renamed sources can be found by stored SHA-256
- original paths are preferred when still valid
- unique hash matches auto-relink
- duplicate hash matches are marked ambiguous
- missing hashes are marked missing
- incomplete maps are rejected by replay
- relink targets are re-hashed before use
- relink maps are bound to the originating Evidence Bundle
- relink maps cannot be written inside Evidence Bundles
- replay through a complete relink map reproduces stored output byte-identically
- historical Recipe and Evidence files remain unchanged
- Python tests and browser JavaScript checks remain green

### MGAL-M0.8 Provenance / License Ledger

Goal:

**Bind source provenance and license declarations to content fingerprints before generated, recorded, purchased, and free-library assets are mixed together at scale.**

Core identity:

```text
path_hint = human convenience
sha256    = source identity
source_id = sha256:<hash>
```

A central ledger entry stores:

```text
source_id
sha256
bytes
path_hint
source_type
origin
license
generation
recording
notes
audio metadata
```

Supported source types:

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

License status vocabulary:

```text
unknown
declared
owned
terms
```

These values are user/provider declarations. MGAL does not infer legal rights.

Create a ledger:

```bash
mgal provenance-scan ./audio \
  --output provenance-ledger.json
```

Update one source:

```bash
mgal provenance-set provenance-ledger.json metal.wav \
  --source-type free_library \
  --creator "Creator Name" \
  --origin-url "https://..." \
  --license-status declared \
  --license-expression "CC0-1.0"
```

Generated-source example:

```bash
mgal provenance-set provenance-ledger.json generated.wav \
  --source-type generated \
  --license-status terms \
  --license-expression "provider-terms" \
  --provider "Provider" \
  --model "Model" \
  --prompt "short metallic slash" \
  --seed "42"
```

Validate:

```bash
mgal validate-ledger provenance-ledger.json \
  --audio-root ./audio
```

Completeness rules:

- source type is not unknown
- license status is not unknown
- declared/terms licenses have a non-empty expression
- generated sources have provider, model, and prompt
- recorded sources have recorded_by

Evidence integration:

```bash
mgal bundle candidates.json \
  --audio-root ./audio \
  --provenance-ledger provenance-ledger.json \
  --require-provenance \
  --output ./evidence/session-001
```

The bundle receives a scoped `provenance-ledger.json` containing only referenced source fingerprints.

`source-index.json` includes `source_id=sha256:<hash>` for every source.

If a ledger is supplied it must cover every referenced fingerprint. Metadata may be incomplete only when strict provenance is not requested.

Strict provenance is preflighted before the Evidence directory is created.

The Evidence manifest records:

```json
{
  "provenance_required": true
}
```

Bundle verification recomputes:

- entry_count
- expected source count
- source IDs from source-index SHA-256 values
- complete/incomplete counts
- complete status

It does not trust provenance summary fields without recomputation.

Path moves do not change provenance identity. M0.7 relink maps alter only current physical source resolution, while embedded provenance remains tied to the historical fingerprint.

#### M0.8 acceptance

- WAV library can be scanned into a content-addressed ledger
- unknown provenance is explicit, never guessed
- ledger entries can record free-library origin and declared license
- recorded entries can record recorder/date/device
- generated entries can record provider/model/prompt/seed
- ledger validation detects source hash drift
- Evidence source-index records source_id
- Evidence can embed only referenced provenance entries
- a supplied ledger must cover every referenced fingerprint
- strict bundle rejects incomplete provenance before writing output
- strict policy is persisted in manifest
- verify/replay recompute provenance completeness
- relink/replay continues to work because identity is content-based
- Python tests and browser JavaScript checks remain green

### MGAL-M0.9 Release / Attribution Pack

Goal:

**Turn a verified Evidence Bundle into a compact shipping artifact containing the final WAV and release-facing attribution/provenance metadata.**

Command:

```bash
mgal release-pack ./evidence/session-001 \
  --output ./release/heavy-slash
```

Optional release name:

```bash
mgal release-pack ./evidence/session-001 \
  --name "Heavy Slash Final" \
  --output ./release/heavy-slash
```

Output:

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

Release source scope:

```text
Candidate Board sources != Release sources

Release sources =
only source fingerprints referenced by selected Recipe
```

This prevents rejected/base-only experimental sources from leaking into release attribution.

Release requirements:

- Evidence Bundle must pass `verify-bundle`
- Evidence Bundle must include provenance-ledger.json
- every source used by selected Recipe must have complete provenance
- release output must be outside the Evidence Bundle

ATTRIBUTION.txt is a human-readable release credit/provenance document.

LICENSE_SUMMARY.json stores recorded source/license declarations.

PROVENANCE_REPORT.json contains only final selected source identities and metadata.

RECIPE.json is the final selected Recipe.

EVIDENCE_REF.json records:

- Evidence manifest SHA-256
- selected candidate ID
- selected Recipe ID
- Evidence output WAV SHA-256

RELEASE_MANIFEST.json records:

- release pack version
- release name
- selected candidate ID
- selected Recipe ID
- Evidence manifest SHA-256
- final source count
- every payload path / byte size / SHA-256

Verification:

```bash
mgal verify-release ./release/heavy-slash
```

Verification checks both byte integrity and semantic consistency:

- payload set equals Release Manifest
- all payload byte sizes and SHA-256 values match
- exactly one final WAV exists
- Recipe ID matches manifest
- License Summary and Provenance Report source sets match
- source counts match
- selected candidate and Recipe IDs agree across reports
- Evidence reference manifest hash matches Release Manifest
- final WAV hash equals Evidence output hash

The Release Pack is evidence-bound but does not mutate historical Evidence.

M0.9 does not make legal determinations. It packages the provenance/license declarations already recorded by M0.8.

#### M0.9 acceptance

- verified Evidence can produce a Release Pack
- Release Pack includes one final WAV
- only selected Recipe source identities appear in release provenance/attribution
- rejected/base-only source identities are excluded
- incomplete selected-source provenance blocks release packaging
- missing provenance blocks release packaging
- output inside Evidence Bundle is rejected
- Evidence manifest SHA-256 is recorded
- final WAV is bound to Evidence output SHA-256
- Release Manifest hashes all payload files
- verify-release detects payload tampering
- verify-release detects semantic drift even after a payload hash is recomputed
- Python tests and browser JavaScript checks remain green

### MGAL-M1.0 Source Provider Contract

Goal:

**Make audio acquisition replaceable while keeping MGAL's audition, human selection, evidence, provenance, replay, and release machinery unchanged.**

```text
SourceRequest
    ↓
SourceProvider
    ↓
ProviderResult
    ├── artifact_root
    └── SourceCandidate[]
            ├── WAV artifact
            ├── SHA-256 identity
            ├── audio metadata
            └── provenance
```

Contract version: `source_provider_contract_version = 1.0`.

SourceRequest fields:

- request_id
- intent
- count
- hints[]
- duration_ms?
- seed?

Provider-specific API configuration remains adapter-local.

ProviderResult fields:

- source_provider_contract_version
- provider_id
- provider_kind
- artifact_root
- request
- candidates[]

`artifact_root` is an absolute runtime directory. Candidate relative paths must remain beneath it.

SourceCandidate fields:

- candidate_id
- provider_id
- provider_kind
- relative_path
- source_id
- sha256
- bytes
- duration_ms
- sample_rate
- channels
- sample_width
- frames
- provenance

Identity invariant:

```text
candidate bytes SHA-256
      ==
candidate.sha256
      ==
candidate.source_id identity
      ==
provenance.sha256
      ==
provenance.source_id identity
```

Reserved provider kinds:

```text
local_file
generated
recorded
recipe
other
```

M1.0 implements `SourceProvider` Protocol, `LocalFileProvider`, `FixtureGeneratedProvider`, Provider Result validation, capability description, Result JSON export, Provenance Ledger export, and CLI execution.

Local provider example:

```bash
mgal source-provide \
  --provider local \
  --audio-root ./audio \
  --provenance-ledger provenance-ledger.json \
  --request-id slash \
  --intent "heavy metallic slash" \
  --hint metal \
  --count 4
```

Explicit hints are strict. No explicit match returns zero candidates.

Fixture-generated example:

```bash
mgal source-provide \
  --provider fixture-generated \
  --artifact-root ./generated \
  --request-id impact \
  --intent "short impact" \
  --count 3 \
  --duration-ms 120 \
  --seed 42
```

The fixture provider is deterministic, offline, and not production audio generation.

Provider validation checks contract version, provider kind and ID, artifact root, request bounds, candidate count and IDs, path containment, artifact existence, byte size, SHA-256, source ID, audio metadata, provenance schema, and provenance fingerprint consistency.

Provider provenance can be exported as a standard M0.8 Ledger with `--provenance-output`.

Authority boundary:

A Provider may acquire/create audio candidates, but must not choose winners, mutate Recipes or Candidate Boards, create/rewrite Evidence, bypass provenance, or release audio directly.

#### M1.0 acceptance

- common SourceRequest / ProviderResult / SourceCandidate contracts exist
- LocalFileProvider returns real local WAV candidates
- local provider can attach M0.8 provenance by fingerprint
- unknown provenance remains explicit
- explicit hints return zero instead of unrelated candidates
- fixture-generated provider returns deterministic WAV candidates
- generated fixture includes provider/model/prompt/seed provenance
- Provider Result is bound to an absolute artifact root
- path escape and artifact tampering are rejected
- malformed provenance is rejected
- Provider Result can emit a standard Provenance Ledger
- CLI can write Result JSON and Provenance Ledger JSON
- Python tests and browser JavaScript checks remain green

### MGAL-M1.1 Generated Audio Adapter

Goal:

**Connect one real generated-audio service to Source Provider Contract 1.0 without giving the service authority over MGAL's human-selection or evidence loop.**

M1.1 implements `StabilityAudioProvider` for the hosted Stability AI Stable Audio 3.0 text-to-audio API.

Adapter boundary:

```text
SourceRequest
    ↓
StabilityAudioProvider
    ↓
Stable Audio HTTP API
    ↓
local WAV
    ↓
SourceCandidate
    ├── content fingerprint
    ├── audio metadata
    └── generation provenance
```

Provider ID:

```text
stability-audio
```

Provider kind:

```text
generated
```

Model:

```text
stable-audio-3
```

The adapter uses the documented async flow:

```text
POST /v2beta/audio/stable-audio/text-to-audio
    ↓
202 generation id
    ↓
GET /v2beta/audio/results/{id}
    ↓
202 / 200 WAV
```

Current API constraints encoded by M1.1:

- duration: 1–380 seconds
- steps: 4–8
- cfg scale: 1–25
- WAV output
- seed range compatible with Stable Audio API
- seed 0 retains API random-seed semantics

A request shorter than one second is generated at one second and both requested/effective durations are retained in provenance.

Authentication:

```text
STABILITY_API_KEY
```

The key is read only from the environment and is never serialized.

Paid-call guard:

```bash
mgal source-provide \
  --provider stability \
  --artifact-root ./audio/generated/stability \
  --allow-paid \
  --request-id impact \
  --intent "short metallic impact" \
  --count 1
```

Without `--allow-paid`, generation fails before the API key is loaded or a network request is made.

For CLI use, Stability defaults to one candidate when `--count` is omitted.

`--artifact-root` is mandatory for live generation.

Capability inspection is free and networkless:

```bash
mgal provider-describe --provider stability
```

Generation provenance includes:

- source type generated
- Stability provider ID
- model
- prompt
- effective seed
- generation ID
- requested duration
- API duration
- steps
- cfg scale
- API endpoint
- current terms URL
- explicit note that API credentials are not stored

HTTP transport behavior is unit-tested with injected fake responses. CI performs no paid API request.

#### Provenance merge bridge

Generated Provider provenance can be merged with local-source provenance:

```bash
mgal provenance-merge \
  local-provenance.json \
  generated-provenance.json \
  --output combined-provenance.json
```

Merge identity is content-addressed `source_id`.

Merge rules:

- unique entries are combined
- identical duplicates are accepted
- complete metadata replaces an incomplete duplicate
- conflicting complete entries fail

This enables mixed local/generated Recipes to use `--require-provenance`.

#### Integration proof

M1.1 CI includes an end-to-end fixture:

```text
mock Stable Audio candidate
      +
local WAV
      ↓
merged Provenance Ledger
      ↓
mixed selected Recipe
      ↓
strict Evidence Bundle
      ↓
verify-bundle success
```

#### M1.1 acceptance

- real Stable Audio 3 text-to-audio HTTP adapter exists
- async start/poll flow is implemented
- API key is environment-only
- API key is never written to Provider Result or provenance
- paid call requires explicit opt-in
- Stability CLI defaults to one candidate
- live generation requires explicit artifact root
- duration API bounds are enforced
- sub-second requests record the one-second provider floor
- seed 0 semantics are preserved
- WAV response is validated before becoming a candidate
- generated SourceCandidate satisfies Provider Contract 1.0
- generated provenance is complete under M0.8 rules
- Provider provenance can be merged with local provenance
- local + generated mixed Recipe reaches strict Evidence in CI
- CI uses no network and spends no provider credits
- Browser JavaScript checks remain green

### MGAL-M1.2 Provider Audio Normalizer

Goal:

**Normalize heterogeneous Provider WAV artifacts into one deterministic renderer-safe format while preserving original content identity and provenance lineage.**

Canonical profile:

```text
profile_id = mgal-pcm16-mono-44100-v1
WAV
PCM signed 16-bit
mono
44,100 Hz
```

Pipeline:

```text
raw ProviderResult
      ↓
validate original artifact/hash/provenance
      ↓
Provider Audio Normalizer
      ↓
canonical WAV
      ↓
normalized ProviderResult
      ↓
Layer Mixer / Recipe / Evidence
```

Original Provider artifacts are never overwritten.

CLI:

```bash
mgal provider-normalize provider-result.json \
  --output-root ./audio/canonical \
  --output normalized-provider-result.json \
  --provenance-output normalized-provenance.json
```

Provider Result JSON can be loaded back into the typed Source Provider Contract and is revalidated against its artifact root before normalization.

Transformation behavior:

- canonical input uses byte-preserving copy
- multi-channel PCM is averaged to mono
- integer PCM 8/16/24/32-bit is converted to signed PCM16
- non-44.1kHz PCM is deterministically linearly resampled to 44.1kHz
- compressed WAV is rejected

Normalized provenance becomes content-addressed to the normalized bytes and retains:

```text
normalization.profile_id
normalization.passthrough
normalization.algorithm
normalization.original.candidate_id
normalization.original.source_id
normalization.original.sha256
normalization.original.bytes
normalization.original.relative_path
normalization.original audio format
normalization.normalized.source_id
normalization.normalized.sha256
normalization.normalized.bytes
normalization.normalized audio format
```

The top-level provenance `source_id` and `sha256` always identify the normalized artifact.

M0.8 provenance validation verifies normalization lineage and ensures the normalized lineage identity matches the top-level entry.

M0.9 `PROVENANCE_REPORT.json` carries normalization metadata into release artifacts.

Determinism:

The same raw Provider artifact and normalization profile must produce the same normalized SHA-256.

Mixed-format integration proof:

```text
8k mono local
+
48k stereo generated
      ↓
normalize each
      ↓
44.1k mono PCM16
      ↓
one mixed Recipe
      ↓
strict Evidence Bundle
      ↓
deterministic 44.1k mono output.wav
```

#### M1.2 acceptance

- persisted Provider Result JSON can be loaded and revalidated
- canonical normalization profile is explicit and versioned
- stereo/multi-channel PCM can normalize to mono
- 8/16/24/32-bit integer PCM decode path exists
- non-44.1k audio deterministically resamples to 44.1k
- already canonical audio preserves bytes
- Provider originals are not modified
- normalized Provider Result passes Source Provider Contract validation
- normalized provenance is a standard valid Ledger entry
- original and normalized hashes are both retained
- broken normalization lineage is rejected
- normalized provenance reaches Release provenance reports
- mixed local/generated incompatible formats render through strict Evidence
- CLI emits normalized Result JSON and Provenance Ledger
- CI uses no network and spends no provider credits
- Browser JavaScript checks remain green

### MGAL-M1.3 Provider Intake / Audition Bridge

Goal:

**Turn a saved Provider Result into normalized, provenance-registered workspace candidates that appear in the Browser Audition Board without restarting the server.**

Intake pipeline:

```text
saved Provider Result
      ↓
validate Provider Contract
      ↓
M1.2 normalize
      ↓
audio/incoming/<intake-id>/
      ↓
intake manifest
      ↓
workspace Provenance Ledger
      ↓
/api/audio enrichment
      ↓
Browser Audition Board
```

CLI:

```bash
mgal provider-intake provider-result.json \
  --audio-root ./audio \
  --intake-id heavy-slash-001
```

Workspace metadata:

```text
audio/.mgal/
├── provenance-ledger.json
└── intakes/
    └── <intake-id>/
        ├── manifest.json
        ├── provider-result.json
        └── provenance-ledger.json
```

Canonical WAVs are written to:

```text
audio/incoming/<intake-id>/
```

Intake ID behavior:

- explicit `--intake-id` may be supplied
- otherwise derived deterministically from request ID, provider ID, and Provider Result SHA-256 prefix
- identical repeated intake is idempotent
- reuse verifies current intake WAV hashes
- same intake ID with a different Provider Result is rejected

The intake manifest records:

- intake version
- intake ID
- raw Provider Result SHA-256
- provider ID / kind
- SourceRequest snapshot
- canonical normalization profile
- normalized Provider Result SHA-256
- candidate count
- workspace-relative candidate paths
- candidate source IDs / hashes / sizes
- source type
- generation metadata
- normalization lineage

Transactional ordering:

The intake session and canonical WAVs are verified before the shared workspace Ledger is mutated.

If intake construction fails before commit, the newly created intake/session files are removed.

Workspace provenance entries use paths relative to the served audio root.

Browser bridge:

`build_catalog()` loads valid intake manifests and enriches matching WAV rows with:

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

Audition Board cards render Provider/intake badges and prompt context.

Search indexes the intake metadata.

Catalog refresh:

- manual Refresh sources button
- automatic 2.5-second polling
- UI rerenders the source list only when a catalog signature changes
- no server restart required after intake

Acquisition remains separate from intake.

This is intentional for paid providers:

```text
paid Provider call
      ↓
saved immutable Provider Result
      ↓
repeatable local intake
```

A saved paid generation can therefore be re-intaken without another provider charge.

#### M1.3 acceptance

- Provider Result can be intaken with one CLI command
- intake performs canonical normalization automatically
- canonical files land beneath the configured audio root
- intake manifest is content-bound to the raw Provider Result
- intake candidate hashes are verified before workspace commit
- workspace Ledger uses audio-root-relative paths
- workspace Ledger merges new candidate provenance
- repeated identical intake is idempotent
- intake ID collision with different input is rejected
- audio catalog enriches intake candidates with Provider metadata
- ordinary WAVs remain supported without intake metadata
- Browser Board renders source/provider/intake context
- Browser search includes prompt and Provider context
- Browser Board detects new intake candidates without restart
- manual catalog refresh remains available
- Python tests and Browser JavaScript checks remain green

### MGAL-M1.4 Intake Session → Candidate Seed

Goal:

**Compile an intake session directly into a valid Candidate Board so Provider alternatives can be compared without manually adding each WAV as a layer first.**

Seed mapping:

```text
intake source 1 → Candidate A
intake source 2 → Candidate B
intake source 3 → Candidate C
```

Cardinality:

- 1 intake source → A
- 2 intake sources → A/B
- 3 intake sources → A/B/C
- 4+ intake sources → first three only

Every seeded candidate starts with:

```text
one layer
gain = 1.0
offset_ms = 0
decision = undecided
revision = 1
```

The intake request intent becomes Candidate Board intent.

Candidate A's source is also compiled into the immutable Base Recipe.

All seeded candidates use normal `fork` lineage from that Base Recipe.

No Candidate Board schema version change is required.

#### Seed compiler

Python contract:

```text
build_intake_candidate_seed(audio_root, intake_id)
```

The compiler:

1. resolves the intake manifest safely beneath `.mgal/intakes`
2. verifies intake WAV hashes
3. reads request intent and candidate order
4. selects at most three sources
5. builds Base Recipe and Candidate A/B/C Recipes
6. compiles revision/parent/lineage fields
7. validates the result with `parse_candidate_board()`

CLI:

```bash
mgal intake-seed-board \
  --audio-root ./audio \
  --intake-id heavy-slash-001 \
  --output candidate-board.json
```

#### Browser API

```text
GET /api/intakes/<intake-id>/seed-board
```

The endpoint returns the exact server-compiled Board payload.

The Browser hydrates Recipe layer source paths back to catalog Sound objects and reuses the existing Candidate Board preview/mixer code.

#### Intake session UI

The Browser groups catalog rows by intake ID and renders an intake session panel with:

- intake ID
- Provider/model
- source count
- prompt/intent
- Seed A, A/B, or A/B/C action
- `first 3 seed` notice when intake has more than three sources

Seeded Candidate cards display their source filename.

#### Overwrite safety

When `state.candidates.length > 0`, intake seed buttons are disabled.

A dedicated `Clear board` action explicitly resets:

- Candidate Board
- active candidate
- Base Recipe
- selected layers

Only then can another intake session be seeded.

Manual layered-mix `Fork A/B/C` remains unchanged.

#### M1.4 acceptance

- intake manifest can compile into Candidate Board 0.1
- compiled Board passes Python Candidate Board validation
- one-source intake seeds A only
- two-source intake can seed A/B
- three-source intake seeds A/B/C
- four-plus-source intake is capped at first three
- Board intent comes from intake request intent
- Base Recipe uses first seeded source
- every candidate has valid fork lineage
- CLI can write a seed Board JSON
- Browser exposes intake sessions as grouped comparison sources
- Browser seed action uses server-compiled Board
- seeded candidate Recipes hydrate to live catalog sounds
- Candidate cards show seeded source filenames
- active Board disables other intake seed actions
- Clear board explicitly re-enables intake seeding
- manual Fork A/B/C workflow remains available
- Python tests and Browser JavaScript checks remain green

### MGAL-M1.5 Blind / Sequential Audition

Goal:

**Reduce visual/provider bias during Candidate comparison and make A/B/C decisions possible with minimal pointer interaction.**

Audition-only state:

```text
blindMode
sequenceRunning
sequenceIndex
sequenceTimer
playbackToken
```

None of these fields enter Candidate Board JSON.

#### Blind mode

Blind mode preserves Candidate labels and decision controls while hiding:

- source filename/path
- Provider/intake badges
- prompt/intent context
- Candidate source summary
- Candidate lineage metadata
- structural delta text
- mixer layer names
- intake session metadata

Blind mode is Browser UI state only.

#### Sequential audition

```text
A
 ↓ playback complete
350 ms
 ↓
B
 ↓ playback complete
350 ms
 ↓
C
 ↓
stop
```

Sequence behavior:

- always starts from the first Candidate
- plays each Candidate once
- does not loop
- waits for all Candidate layers to finish
- manual Candidate preview cancels sequence
- previous/next navigation cancels sequence
- Stop/Escape cancels sequence
- stale completion callbacks are ignored through playback-token invalidation

#### Navigation controls

Browser controls:

```text
Blind: On/Off
A→B→C sequence
Previous Candidate
Next Candidate
active position indicator
```

Previous/next navigation activates and previews the target Candidate.

#### Keyboard contract

Outside editable controls:

```text
Space       preview/replay active Candidate
ArrowLeft   previous Candidate + preview
ArrowRight  next Candidate + preview
F           toggle favorite
X           toggle reject
S           toggle selected
B           toggle blind mode
Q           start/stop sequence
Escape      stop audition
```

Keyboard handling ignores events originating inside input, textarea, select, or contenteditable elements, and ignores Ctrl/Cmd/Alt modified shortcuts.

Decision shortcuts call the same Candidate decision function used by UI buttons.

#### Persistence boundary

Candidate Board serialization remains version 0.1.

The following are intentionally absent from board payloads:

- blind mode
- sequence state
- playback index
- keyboard state
- timing state

Only durable human decisions remain persisted.

#### M1.5 acceptance

- Blind mode can be toggled only when Candidates exist
- Blind mode hides source/provider/prompt/lineage context
- Candidate A/B/C labels remain visible
- Blind mode does not modify Board/Recipe persistence
- sequential audition plays Candidates in A/B/C order
- sequence stops after the final Candidate
- layered Candidate completion waits for all voices
- manual preview cancels sequence
- previous/next navigation previews the target Candidate
- playback token prevents stale completion callbacks from advancing a newer session
- keyboard shortcuts implement preview/navigation/decision/blind/sequence/stop
- typing in form controls does not trigger audition shortcuts
- keyboard decisions reuse favorite/reject/selected logic
- Clear board resets Blind/Sequential state
- Intake-seeded and manually-forked Boards use the same audition controls
- Python tests and Browser JavaScript syntax checks remain green

### MGAL-M1.6 Randomized Blind / Preference Session

Goal:

**Hide Candidate position identity as well as source/provider context, collect randomized pairwise preferences, then require an explicit Reveal and Apply step before any durable Candidate decision changes.**

Session-only state:

```text
mapping[]
pairs[]
pairIndex
votes[]
revealed
applied
```

Candidate Board schema remains 0.1 and contains none of these fields.

#### Random mapping

Up to three Candidates are shuffled into aliases:

```text
X
Y
Z
```

Randomness uses Browser `crypto.getRandomValues()`.

Candidate card display order follows the randomized alias mapping before Reveal.

#### Pair schedule

Every unique pair is generated exactly once.

For three Candidates:

```text
3 choose 2 = 3 pair votes
```

The pair list is shuffled and each pair independently randomizes left/right presentation.

#### Hidden phase

Before Reveal:

- random alias replaces A/B/C label
- source/provider/prompt/lineage context remains hidden
- existing Candidate decision badge is replaced by neutral `blind`
- Edit/Copy controls are hidden
- decision buttons and reason field are hidden
- Blind cannot be disabled
- normal sequence and Previous/Next are disabled
- Board and active Recipe download are disabled

Preference keyboard contract:

```text
1           play left
2           play right
ArrowLeft   vote left
ArrowRight  vote right
R           Reveal after all votes
P           close session
Escape      stop audio
```

Preference keyboard handling intercepts arrows before normal Candidate navigation.

#### Vote aggregation

Each submitted pair records one winner in transient session state.

Win count is computed per Candidate.

A winner exists only when exactly one Candidate has the highest win count.

A three-way `1/1/1` cycle is treated as a tie.

#### Reveal

Reveal is disabled until all pairwise votes are complete.

Reveal displays alias-to-Candidate mapping and win counts and restores ordinary Candidate identity/context.

#### Apply boundary

`Apply winner` is enabled only when:

- Reveal has occurred
- all pairs are voted
- exactly one Candidate has the top win count
- the result has not already been applied

Applying changes only the existing Candidate decision state:

```text
winner.decision = selected
```

Any previously selected Candidate is reset to undecided.

Ties are never auto-applied.

Closing a session without Apply preserves the durable Board.

#### M1.6 acceptance

- session requires at least two Candidates
- up to three Candidates receive randomized X/Y/Z aliases
- Browser crypto source is used for shuffling
- pair schedule covers every unique pair once
- pair order is randomized
- left/right placement is randomized
- underlying A/B/C identity is hidden before Reveal
- previous Candidate decisions are hidden before Reveal
- Board/Recipe export is disabled before Reveal
- ordinary Blind toggle cannot expose identity before Reveal
- normal sequence and navigation are disabled before Reveal
- pairwise vote keyboard shortcuts override normal navigation
- Reveal is unavailable until all pairs are voted
- Reveal maps aliases back to Candidates and shows win counts
- unique top win count enables Apply winner
- tie leaves Apply winner disabled
- Apply winner uses existing selected decision contract
- Preference state is absent from Board serialization
- closing without Apply leaves durable Candidate decisions unchanged
- Python tests and Browser JavaScript syntax checks remain green

### MGAL-M1.7 Preference Session Evidence / Replay

Goal:

**Persist a completed randomized blind Preference Session as a separately validated evidence artifact and reconstruct the exact comparison schedule later against fingerprint-verified audio.**

Preference Evidence schema:

```text
preference_session_version = 0.1
candidate_board_sha256
candidate_board
mapping[]
pairs[]
votes[]
scores[]
winner_candidate_id
tie
applied_candidate_id
source_index
```

#### Server-side compilation

Browser export uses:

```text
POST /api/preference-evidence
```

Input contains:

- current Candidate Board payload
- randomized mapping
- pair schedule
- votes
- revealed flag
- applied Candidate ID or null

The Python compiler requires Reveal before compilation.

It validates Candidate Board 0.1 first.

#### Mapping contract

Evidence accepts two or three Candidates.

Aliases must be exactly:

```text
2 candidates → X / Y
3 candidates → X / Y / Z
```

Aliases and Candidate IDs must both be unique and must reference Candidates in the embedded Board.

#### Pair contract

Pair count must equal:

```text
n * (n - 1) / 2
```

Every unordered Candidate pair must appear exactly once.

Left/right order is preserved exactly as experienced.

Duplicate or missing pairs are invalid.

#### Vote contract

Evidence requires exactly one vote per pair.

Each vote must identify a winner that belongs to the corresponding pair.

Loser identity is recomputed and validated.

#### Result contract

Scores are recomputed from votes.

A winner exists only when exactly one Candidate has the maximum win count.

`winner_candidate_id` and `tie` must match recomputation.

If `applied_candidate_id` is non-null:

- it must equal the unique winner
- the embedded Candidate Board must select that same Candidate

#### Candidate Board binding

The embedded Board is serialized canonically with sorted JSON keys and compact separators.

SHA-256 becomes:

```text
candidate_board_sha256
```

Validation recomputes and checks the fingerprint.

#### Source index

Every unique WAV source referenced by compared Candidate Recipes is resolved safely beneath the audio root.

Evidence records:

```text
relative_path
sha256
bytes
```

Absolute paths and traversal outside the audio root are rejected.

#### Browser export

After Reveal, `Download evidence` becomes enabled.

Before Reveal the action stays disabled.

Browser sends the transient session to the Python compiler and downloads only the compiler result.

#### CLI validation

```bash
mgal validate-preference preference-evidence.json
```

#### Replay

```bash
mgal replay-preference preference-evidence.json \
  --audio-root ./audio \
  --output replay-plan.json
```

Replay:

1. validates Preference Evidence schema
2. verifies every source byte size
3. verifies every source SHA-256
4. reconstructs Candidate sources from the embedded Board
5. returns the recorded X/Y/Z mapping
6. returns pairs in original order and left/right placement
7. attaches the recorded winner to each pair
8. returns final winner/tie and Apply state

No new randomization occurs during replay.

#### Main Evidence Bundle bridge

`mgal bundle` accepts:

```text
--preference-evidence <path>
```

When supplied:

- Preference Evidence is validated before bundling
- applied winner, if present, must match current Board selection
- artifact is copied as `preference-session.json`
- normal Bundle manifest fingerprints it
- `verify-bundle` revalidates Preference logic

#### M1.7 acceptance

- completed revealed session can compile into Preference Evidence 0.1
- incomplete/unrevealed session is rejected
- Board snapshot receives deterministic SHA-256 binding
- mapping aliases and Candidate IDs are validated
- every unique pair must occur exactly once
- every pair requires exactly one consistent vote
- score totals are recomputed
- winner/tie are recomputed
- Apply winner must agree with embedded Board selection
- compared WAV paths are safely resolved under audio root
- compared WAV SHA-256 and byte counts are recorded
- Browser downloads server-compiled Evidence after Reveal
- CLI validates standalone Preference Evidence
- Replay detects modified WAV bytes
- Replay reconstructs exact mapping/pair/left-right/vote order
- replay plan can be written as JSON
- Preference Evidence can be included in normal Evidence Bundle
- Bundle verify revalidates Preference Evidence semantics
- Preference state still does not enter Candidate Board serialization
- Python tests and Browser JavaScript syntax checks remain green

### MGAL-M1.8 Preference Replay UI / Session Archive

Goal:

**Store completed Preference Evidence as content-addressed workspace history and replay the exact recorded comparison in the Browser after source-integrity verification.**

Workspace layout:

```text
audio/.mgal/preferences/<archive-id>/
├── manifest.json
└── evidence.json
```

Archive schema:

```text
preference_archive_version = 0.1
archive_id
evidence_sha256
candidate_board_sha256
candidate_count
pair_count
source_count
winner_candidate_id
tie
applied_candidate_id
```

#### Archive identity

Default archive ID:

```text
<base-recipe-id>-<canonical-evidence-sha256-prefix>
```

Preference Evidence is hashed from canonical sorted/compact JSON.

Identical Evidence is idempotent and reuses the existing archive.

An explicit archive ID that already points at different Evidence is rejected.

#### Archive commit

Before writing a new archive MGAL:

1. validates Preference Evidence 0.1
2. verifies all source byte sizes and SHA-256 values
3. reconstructs replay data
4. creates the archive directory
5. writes evidence.json
6. writes manifest.json
7. verifies the complete archive

#### CLI

```bash
mgal preference-archive preference.json \
  --audio-root ./audio \
  [--archive-id session-name]

mgal preference-list --audio-root ./audio

mgal preference-replay-archive session-name \
  --audio-root ./audio \
  [--output replay-plan.json]
```

#### Local server APIs

```text
POST /api/preference-evidence
POST /api/preference-archive
GET  /api/preferences
GET  /api/preferences/<archive-id>/replay
```

The compile-only M1.7 endpoint remains supported.

The standard Browser export path uses compile+archive.

#### Archive list

`list_preference_archives()` scans manifest-bearing sessions.

Valid sessions return summary fields plus source-verification status.

Invalid sessions return:

```json
{
  "archive_id": "...",
  "ok": false,
  "error": "..."
}
```

They remain visible for diagnosis.

#### Replay plan enrichment

M1.8 replay pairs include:

```text
left_alias
left_candidate_id
left_sources
left_recipe

right_alias
right_candidate_id
right_sources
right_recipe

winner_alias
winner_candidate_id
```

Embedding the Candidate Recipe in the plan allows Browser replay of layered Candidates with original gain and offset settings.

#### Browser Archive shelf

Audition Board loads archive summaries at startup and can refresh manually.

Each valid archive provides a Replay action.

Invalid archives display their verification error and do not expose Replay.

#### Browser Verified Replay panel

Opening a replay:

1. refreshes the current audio catalog
2. requests verified replay from the server
3. stores the replay plan as transient Browser state
4. shows archived alias mapping
5. opens pair 1
6. permits previous/next pair navigation
7. permits independent left/right playback
8. displays the recorded winner for the current pair

Playback hydrates `left_recipe.layers` or `right_recipe.layers` with the existing audio catalog and reuses the normal Web Audio layer renderer.

#### Non-mutating boundary

Archive replay never mutates:

- current Candidate Board
- Candidate decisions
- active Recipe
- Preference Archive Evidence
- selected winner

It is an observational replay surface.

#### M1.8 acceptance

- Preference Evidence can be archived under `.mgal/preferences`
- archive identity is deterministic when no ID is supplied
- repeated identical archive is idempotent
- explicit ID collision with different Evidence is rejected
- archive manifest binds Evidence and Candidate Board fingerprints
- archive verification rechecks source WAV fingerprints
- invalid source changes make archive verification fail
- invalid archive remains visible in list result
- CLI can archive, list, and replay workspace sessions
- server exposes archive/list/replay APIs
- Browser standard Evidence action archives and downloads
- Browser lists archived Preference Sessions
- Browser refuses Replay when server verification fails
- Replay returns exact historical pair order and left/right placement
- Replay returns embedded Candidate Recipes
- layered gain/offset survive archive replay
- Browser can navigate previous/next recorded pairs
- Browser can independently replay left/right Recipe
- Browser displays recorded pair winner and final winner/tie
- Replay does not mutate current Candidate Board state
- existing M1.7 standalone Preference Evidence validation remains supported
- Python tests and Browser JavaScript syntax checks remain green

### MGAL-M1.9 Preference Source Recovery / Portable Archive

Goal:

**Recover archived Preference sources by exact byte fingerprint after files move or are renamed, without mutating historical Preference Evidence or Candidate Recipes.**

Historical source identity remains:

```text
relative_path
sha256
bytes
```

Archive metadata validation is separated from current source availability. A valid archive may therefore be recoverable even when its historical source paths no longer exist.

#### Preference Relink Map 0.1

```text
preference_relink_version
archive_id
archive_evidence_sha256
candidate_board_sha256
search_root = "."
source_count
resolved_count
ambiguous_count
missing_count
complete
mappings[]
```

Each mapping contains `source`, `status`, `target`, `sha256`, `bytes`, and `matches`.

Resolution algorithm:

1. prefer the historical relative path when byte size and SHA-256 still match
2. otherwise recursively scan WAV files under search root
3. group by byte size before hashing
4. one hash match → `relinked`
5. multiple hash matches → `ambiguous`
6. no hash match → `missing`

Ambiguous matches are never guessed.

Default Relink Map location:

```text
audio/.mgal/preference-relinks/<archive-id>.json
```

Relink Maps live outside immutable Preference Archive directories.

Map loading requires exact archive ID, Evidence fingerprint, Candidate Board fingerprint, and source set equality. Every target must remain beneath search root and retain expected byte size and SHA-256.

#### Portable replay

```bash
mgal preference-recover <archive-id> \
  --audio-root ./workspace \
  --search-root ./current-library

mgal preference-replay-archive <archive-id> \
  --audio-root ./workspace \
  [--search-root ./current-library] \
  [--relink-map relink.json]
```

`--audio-root` identifies the workspace containing `.mgal/preferences`. `--search-root` identifies the current source library and may be elsewhere.

Replay tries direct historical paths first. If they fail, a validated Preference Relink Map can supply source overrides.

Archived Recipes are never rewritten. Returned replay-plan Recipes are remapped in memory to resolved current paths while gain, offset, processing, mapping, pair order, and votes remain unchanged.

Replay reports:

```text
source_status = direct | relinked
relink_map
source_resolution[]
```

#### Portable archive list

Archive listing distinguishes:

```text
ok=true,  source_status=direct
ok=true,  source_status=relinked
ok=false, recoverable=true, source_status=unresolved
ok=false, recoverable=false  # archive metadata/evidence corruption
```

#### Browser recovery

```text
POST /api/preferences/<archive-id>/recover
```

The Browser searches the served audio root, stores the default Relink Map, refreshes the audio catalog and archive list, and enables Replay only after complete unique recovery.

Incomplete recovery reports ambiguous and missing counts and leaves the archive recoverable.

#### M1.9 acceptance

- archive metadata remains verifiable when historical source paths disappear
- historical direct path is preferred when still valid
- same-size filtering occurs before SHA-256 hashing
- unique fingerprint match relinks
- duplicate fingerprint matches are ambiguous
- absent fingerprint match is missing
- incomplete recovery never guesses
- Relink Map is bound to archive, Evidence, and Candidate Board fingerprints
- Relink Map source set exactly matches archived source index
- relink target drift is rejected
- replay supports a source root different from archive workspace root
- replay remaps Recipe sources only in memory
- recovered replay preserves gain and offset
- archive list exposes direct/relinked/recoverable state
- CLI supports recovery and portable replay
- Browser exposes Recover sources
- Browser Replay reports SHA-256 relink status
- existing Preference Evidence and Archive formats remain immutable and compatible
- Python tests and Browser JavaScript syntax checks remain green

### MGAL-M2.0 Preference Archive Promotion / Decision Memory

Goal:

**Promote selected Preference Archives into a durable, cross-session collection of pairwise decision observations without allowing past observations to automatically choose future Candidates.**

#### Storage

```text
audio/.mgal/decision-memory.json
```

Schema:

```text
decision_memory_version = 0.1
promotion_count
entry_count
promotions[]
entries[]
```

#### Explicit promotion

```bash
mgal decision-promote <archive-id> \
  --audio-root ./audio
```

Only explicit promotion adds an archive to Decision Memory.

Promotion depends on Preference Archive/Evidence integrity, not current WAV source availability.

A source-unresolved but structurally valid archive remains promotable.

#### Promotion identity

Promotion is deduplicated by canonical Preference Evidence SHA-256.

The same Evidence promoted repeatedly or through another archive alias produces one promotion.

Promotion records:

```text
archive_id
archive_evidence_sha256
candidate_board_sha256
intent
pair_count
winner_candidate_id
tie
applied_candidate_id
entry_ids[]
```

#### Pairwise entries

Each archived vote becomes one Decision Memory entry.

A three-Candidate all-pairs Preference Session therefore contributes three entries, including when the overall session result is a cyclic tie.

Entry fields:

```text
entry_id
archive_id
archive_evidence_sha256
candidate_board_sha256
intent
pair_index
winner_alias
winner_candidate_id
loser_candidate_id
winner_recipe
loser_recipe
observed_differences
```

#### Recipe summary

Recipe summaries are content-oriented and relocatable:

```text
recipe_id
recipe_sha256
layer_count
total_gain
earliest_offset_ms
latest_offset_ms
normalize
fade_out_ms
source_ids[]
```

`source_ids` use `sha256:<hash>` identities derived from Preference Evidence source-index entries.

No current filesystem path is required.

#### Observed differences

For every pair MGAL derives:

```text
layer_count_delta
total_gain_delta
earliest_offset_ms_delta
latest_offset_ms_delta
fade_out_ms_delta
normalize_changed
shared_source_count
winner_only_source_count
loser_only_source_count
```

All deltas are winner minus loser.

These are stored observations, not learned rules or quality scores.

#### Internal validation

Decision Memory validation requires:

- supported version
- promotion_count equals promotions length
- entry_count equals entries length
- unique entry IDs
- unique promoted Evidence fingerprints
- every promotion entry reference exists
- each entry belongs to exactly one promotion
- no unreferenced entries
- observed differences recompute exactly from stored Recipe summaries

#### Archive-backed verification

```bash
mgal decision-memory-verify \
  --audio-root ./audio
```

Verification recompiles each promoted archive and requires the stored promotion and pairwise entries to equal the newly derived archive result.

Source WAV availability is not required because Preference Evidence already carries content fingerprints and Recipe snapshots.

#### Memory view

```bash
mgal decision-memory \
  --audio-root ./audio
```

Returns:

```text
summary
promotions
entries
```

Summary includes promotion count, entry count, and promotion counts grouped by intent.

#### Browser API

```text
GET  /api/decision-memory
POST /api/preferences/<archive-id>/promote
```

Preference Archive list rows expose:

```text
promotable
promoted
```

Promotion state is matched by Preference Evidence SHA-256.

#### Browser UI

The Preference Archive shelf adds:

```text
Promote memory
In memory
```

The Decision Memory panel displays:

- promoted session count
- pairwise observation count
- recent winner/loser observations
- archive and intent context
- deterministic Recipe deltas

It explicitly states that observations do not auto-select Candidates.

#### Human-control boundary

M2.0 does not define or persist:

```text
recommended_candidate
auto_select
preference_score
automatic Candidate ranking
automatic Apply winner
```

Decision Memory is evidence available to future workflows, not authority over future choices.

#### M2.0 acceptance

- a valid Preference Archive can be explicitly promoted
- promotion can succeed without current source WAV paths
- promotion is idempotent by Preference Evidence fingerprint
- multiple distinct promoted archives accumulate
- every pairwise vote becomes one memory entry
- overall tie sessions still preserve individual pair observations
- Recipe summaries use content source IDs rather than filesystem paths
- deterministic Recipe fingerprints are stored
- observed winner-minus-loser differences are stored
- Decision Memory validates counts, references, uniqueness, and derived differences
- Decision Memory can be verified exactly against source Preference Archives
- CLI supports promote/view/verify
- Browser archive shelf exposes explicit promotion
- recoverable archives remain promotable
- Browser shows promoted state by Evidence fingerprint
- Browser Decision Memory shows observation counts and recent pairwise entries
- promotion does not mutate Preference Archive, Candidate Board, Recipe, or Relink Map
- no automatic recommendation or selection field is introduced
- Python tests and Browser JavaScript syntax checks remain green

## Next provider adapters

\`\`\`text
SourceProvider
  ├── LocalFileProvider          implemented
  ├── StabilityAudioProvider     implemented
  ├── RecordedAudioProvider      future
  └── RecipeProvider             future
\`\`\`

The Source Provider boundary now exists. Production generated, recorded, and recipe adapters can implement it without changing MGAL core.

## North star

MGAL exists to shorten the distance between:

> “I imagine this sound”

and:

> “I can hear it in the game.”
