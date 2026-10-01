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
      "source": "fixtures/audio/cloth.wav",
      "gain": 0.35,
      "offset_ms": 0
    },
    {
      "source": "fixtures/audio/metal.wav",
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

Add a browser UI for rapid source audition:

- filename
- duration
- simple waveform
- play / stop
- add-to-recipe

### MGAL-M0.3 Layer Mixer

Add:

- gain
- offset
- mute / solo
- 2–4 simultaneous layers
- live preview

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
