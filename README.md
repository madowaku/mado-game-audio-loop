# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work into a reproducible creative loop:

**provide → audition → mix → compare → decide → bundle → replay → recover → provenance → release**

## Current milestone: M1.1 Generated Audio Adapter

MGAL now has a production generated-audio adapter for the Stability AI Stable Audio API.

The Provider boundary remains unchanged:

```text
text intent
    ↓
StabilityAudioProvider
    ↓
Stable Audio 3 API
    ↓
local WAV artifacts
    ↓
MGAL Source Provider Contract 1.0
    ├── SHA-256 identity
    ├── audio metadata
    └── provenance/license metadata
    ↓
Audition / Mix / Candidate Board / Evidence / Release
```

The adapter is deliberately thin. Stability-specific authentication, polling, model parameters, and API URLs stay inside the adapter. MGAL core still sees only normal SourceCandidates.

## Current Stable Audio API contract

M1.1 targets the hosted Stable Audio 3.0 text-to-audio endpoint documented by Stability AI:

- model: `stable-audio-3`
- asynchronous generation
- WAV output
- duration: 1–380 seconds
- steps: 4–8
- cfg scale: 1–25
- API key environment variable: `STABILITY_API_KEY`

At implementation time, Stability AI documents Stable Audio 3.0 at 26 credits per successful generation. Pricing can change, so check the official API docs before live use.

Official docs:

- https://platform.stability.ai/docs/api-reference
- https://platform.stability.ai/legal/terms-of-service

## Paid-generation safety

MGAL will not call the paid API unless the command explicitly includes:

```text
--allow-paid
```

For the Stability provider, omitted `--count` defaults to **1 candidate**, not the generic Provider default of 4.

This prevents an accidental four-generation paid request.

`--artifact-root` is also mandatory for live Stability generation so paid outputs cannot silently land in the repository root.

## API key setup

The key is read from the environment only. It is never accepted as a normal CLI argument and is never stored in Provider Result JSON or provenance.

PowerShell:

```powershell
$env:STABILITY_API_KEY="your-key-here"
```

The environment-variable name can be changed with:

```text
--api-key-env OTHER_ENV_NAME
```

## Describe without spending anything

```bash
mgal provider-describe --provider stability
```

This requires no key, creates no artifacts, and performs no network request.

The description exposes:

- network = true
- generates_audio = true
- paid_generation = true
- async_api = true
- model = stable-audio-3
- supported duration / steps / cfg-scale ranges
- explicit paid opt-in requirement

## Generate one game SFX candidate

A practical workspace layout is to generate directly underneath the folder already served by the Browser Audition Board:

```text
audio/
├── local/
└── generated/
    └── stability/
```

Generate:

```bash
mgal source-provide \
  --provider stability \
  --artifact-root ./audio/generated/stability \
  --allow-paid \
  --request-id heavy-slash \
  --intent "short stylized metallic sword slash, strong transient, game SFX" \
  --duration-ms 1000 \
  --seed 42 \
  --output ./provider-runs/heavy-slash.json \
  --provenance-output ./provider-runs/heavy-slash-provenance.json
```

Then:

```bash
mgal serve ./audio
```

The generated WAV is immediately visible to the existing Browser Audition Board because it is already inside the served audio tree.

## Short SFX requests

The Stable Audio API currently requires at least 1 second.

Therefore:

```text
requested duration = 400 ms
API duration       = 1.0 s
```

MGAL records both values in generation provenance:

```text
requested_duration_ms
api_duration_seconds
```

This avoids pretending the provider honored a shorter duration than the API supports.

## Seed behavior

Stable Audio uses seed 0 as a random-seed request.

MGAL preserves that behavior:

```text
--seed 0 → API seed 0
```

For a non-zero numeric seed and multiple candidates, MGAL increments the seed per candidate.

Arbitrary text seeds are deterministically converted into valid numeric API seeds.

## Async HTTP behavior

The adapter follows the API's asynchronous flow:

```text
POST text-to-audio
      ↓
202 + generation id
      ↓
GET /results/{id}
      ↓
202 while generating
      ↓
200 WAV bytes
```

Polling has configurable safety bounds:

```text
--poll-interval
--max-wait
```

CI tests this request/poll sequence with a fake HTTP transport. CI does not contact Stability AI and does not spend credits.

## Generated provenance

Every returned candidate immediately carries M0.8-compatible provenance.

Example fields:

```text
source_type = generated

generation.provider = stability-audio
generation.model = stable-audio-3
generation.prompt
generation.seed
generation.parameters.generation_id
generation.parameters.requested_duration_ms
generation.parameters.api_duration_seconds
generation.parameters.steps
generation.parameters.cfg_scale
generation.parameters.endpoint

license.status = terms
license.expression = Stability AI Terms of Service
license.url = official terms URL
```

API credentials are never persisted.

MGAL records the provider's terms declaration. It does not independently make a legal determination for a particular release.

## Merge generated and local provenance

A mixed game SFX may use both local and generated layers.

M1.1 adds:

```bash
mgal provenance-merge \
  ./local-provenance.json \
  ./provider-runs/heavy-slash-provenance.json \
  --output ./combined-provenance.json
```

Merge identity is `source_id = sha256:<hash>`.

Rules:

- unique sources are combined
- identical duplicate entries are accepted
- a complete entry replaces an unknown/incomplete duplicate
- conflicting complete entries are rejected instead of guessed

That combined Ledger can flow directly into strict Evidence:

```bash
mgal bundle candidates.json \
  --audio-root ./audio \
  --provenance-ledger ./combined-provenance.json \
  --require-provenance \
  --output ./evidence/session-001
```

## End-to-end generated-audio flow

```text
Prompt
  ↓
Stable Audio 3
  ↓
WAV + generation provenance
  ↓
Browser Audition Board
  ↓
Layer with local sounds
  ↓
A/B/C comparison
  ↓
Human select
  ↓
Merged Provenance Ledger
  ↓
Strict Evidence Bundle
  ↓
Replay / Relink
  ↓
Release / Attribution Pack
```

A CI integration fixture proves the generated candidate can be mixed with a local WAV and reach a strict Evidence Bundle.

## M1.0 Provider foundation

The common Provider contract remains version 1.0.

Every SourceCandidate still contains:

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

The Provider may acquire audio, but it may not select the winner, mutate a Recipe/Candidate Board, create Evidence, bypass provenance, or release audio directly.

## Live-smoke status

M1.1 implements the real HTTP adapter and validates its request/polling contract with mocked HTTP responses.

This milestone does **not** perform a paid live generation during CI or repository construction. A live smoke requires the operator's own Stability API key and explicit `--allow-paid`.

## Current constraints

- Stable Audio adapter currently targets `stable-audio-3`
- text-to-audio only
- WAV output only
- no audio-to-audio or inpainting yet
- no automatic trimming of the API's 1-second minimum
- generated Stable Audio WAVs may have channel/sample-rate characteristics that differ from older local MGAL fixtures
- Browser audition can handle generated WAVs, but deterministic offline rendering still requires layer formats compatible with the current renderer
- no provider registry/plugin discovery yet
- no automatic prompt compiler yet
- no live paid API call in CI

## Design principle

> Generation is an upstream candidate source, not the creative authority.

The generated sound enters the exact same human selection, evidence, provenance, replay, and release machinery as every other source.
