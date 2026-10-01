# MADO_GAME_AUDIO_LOOP_SPEC.md

Version: 0.1  
Status: Draft  
Project: `mado-game-audio-loop`  
Codename: MGAL

## One sentence

Game SFX should be a reproducible creative loop, not a folder-diving chore.

## Core loop

```text
Intent
  ↓
Source
  ↓
Layer / Transform
  ↓
Audition
  ↓
Compare
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
```

## Product principles

1. **Search less, compose more.**
2. **One-shot generation is not the goal.**
3. **Human taste stays in the loop.**
4. **Audio is a recipe, not just a WAV file.**
5. **AI generators are providers, not the core.**

## Primary user

A solo or small-team game developer who can build the game but currently chooses or places sound effects ad hoc.

## M0 goal

Create a local workbench that can:

- scan local audio
- validate a recipe
- rapidly audition candidate sounds
- combine 2–4 layers
- control gain and offset
- render deterministic WAV output
- preserve enough metadata to reproduce the result

## Non-goals for v0.x

- DAW replacement
- music composition
- mastering suite
- mandatory cloud generation
- automatic creative judgment
- full Unity/Godot/CRIWARE integration

## Core data model

A recipe is the source of truth.

```json
{
  "recipe_version": "0.1",
  "id": "sword-slash-heavy-001",
  "intent": "heavy metallic sword slash",
  "duration_target_ms": 450,
  "layers": [
    {
      "source": "cloth.wav",
      "gain": 0.35,
      "offset_ms": 0
    },
    {
      "source": "metal.wav",
      "gain": 0.30,
      "offset_ms": 25
    }
  ],
  "processing": {
    "normalize": true,
    "fade_out_ms": 80
  }
}
```

## Milestones

### MGAL-M0.1 Local Audio Workbench

Deliverables:

- Python package
- CLI
- recipe schema + validation
- WAV scanner
- deterministic WAV renderer
- fixture recipe
- tests

Acceptance:

- `mgal --help` works
- `mgal validate <recipe>` succeeds for the fixture
- `mgal scan <folder>` indexes WAV metadata
- `mgal render <recipe> --output <wav>` emits a WAV file
- tests pass without network access

### MGAL-M0.2 Browser Audition Board

Goal:

**Replace “open files one by one” with a fast local visual audition surface.**

Run:

```bash
mgal serve ./audio
```

Architecture:

```text
audio root
   │
   ├── WAV metadata scanner
   │
   ├── safe local audio endpoint
   │
   └── dependency-free browser UI
            │
            ├── search
            ├── waveform
            ├── play / stop
            ├── shortlist
            └── recipe draft
```

Browser features:

- filename and relative path
- duration
- sample rate and channel count
- lazy-loaded waveform
- play / stop
- stop-all
- filename/path filtering
- add/remove candidate layer
- maximum four candidate layers
- intent field
- download recipe JSON

Security boundary:

- server binds to `127.0.0.1` by default
- audio requests are resolved beneath the configured audio root
- path traversal outside the audio root is rejected
- UI has no external CDN/runtime dependency

M0.2 acceptance:

- `mgal serve <folder>` launches the board
- `GET /api/audio` returns indexed WAVs
- a WAV can be played in the browser
- visible WAVs receive waveform previews
- search filters the candidate board
- up to four sources can be added to a recipe draft
- recipe JSON can be downloaded
- server path traversal has a contract test

Not included in M0.2:

- simultaneous layer playback
- gain controls
- offset controls
- mute / solo
- waveform trimming
- server-side recipe persistence

Those belong to M0.3.

### MGAL-M0.3 Layer Mixer

Add:

- gain
- offset
- mute / solo
- 2–4 simultaneous layers
- live preview
- browser-side recipe mutation

### MGAL-M0.4 Candidate Board

Add A/B/C candidate comparison and human decisions:

- favorite
- reject
- selected
- free-text reason

### MGAL-M0.5 Evidence Bundle

Persist:

```text
evidence/<session>/
  intent.json
  source-index.json
  recipe.json
  output.wav
  decision.json
```

## Later provider architecture

```text
SourceProvider
  ├── LocalFileProvider
  ├── GeneratedAudioProvider
  ├── RecordedAudioProvider
  └── RecipeProvider
```

Future AI audio generation should plug into this boundary.

## North star

MGAL exists to shorten the distance between:

> “I imagine this sound”

and:

> “I can hear it in the game.”
