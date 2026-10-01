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

## Later provider architecture

\`\`\`text
SourceProvider
  ├── LocalFileProvider
  ├── GeneratedAudioProvider
  ├── RecordedAudioProvider
  └── RecipeProvider
\`\`\`

Future AI audio generation plugs into this boundary instead of owning the workflow.

## North star

MGAL exists to shorten the distance between:

> “I imagine this sound”

and:

> “I can hear it in the game.”
