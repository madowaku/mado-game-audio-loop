# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work from “find something and drop it in” into a reproducible loop:

**scan → audition → layer → mix → compare → save recipe → render → reuse**

## Current milestone: M0.4 Candidate Board

MGAL now supports a complete local A/B/C comparison loop.

It can:

- fork the current mix into Candidate A / B / C
- edit each candidate independently
- preview A/B/C directly from the board
- copy the active candidate into another candidate
- track lineage with revision-qualified parent refs such as `candidate-a@r1`
- show structural changes versus the immutable base recipe
- mark candidates as favorite, reject, or selected
- store a free-text decision reason
- export the full Candidate Board as JSON
- validate exported boards with `mgal validate-board`

The audio Recipe still stores the reproducible sound. The Candidate Board stores the reproducible decision.
## Quick start

\`\`\`bash
python -m pip install -e ".[dev]"
pytest
mgal serve ./audio
\`\`\`

The mixer opens at:

\`\`\`text
http://127.0.0.1:8765
\`\`\`

### Browser workflow

\`\`\`text
local WAV folder
      ↓
search + waveform + audition
      ↓
add 2–4 layers
      ↓
Preview mix
      ↓
gain / offset / mute / solo
      ↓
download recipe JSON
      ↓
deterministic WAV render
\`\`\`

If the recipe was downloaded to another folder, point the renderer back at the source library:

\`\`\`bash
mgal render ~/Downloads/heavy-sword-slash.json \
  --audio-root ./audio \
  --output ./output/heavy-sword-slash.wav
\`\`\`

Other useful commands:

\`\`\`bash
mgal --help
mgal scan ./audio
mgal validate recipe.json
mgal serve ./audio --no-browser
\`\`\`

## M0.4 persistence contract

**Persisted in Recipe**

- source path
- gain
- offset_ms

**Audition-only**

- mute
- solo

Mute and solo intentionally do not alter the saved recipe.

**Persisted in Candidate Board**

- base recipe
- A/B/C recipes
- candidate revision
- parent revision reference
- lineage events
- favorite / reject / selected decision
- decision reason
- active and selected candidate IDs

## Current constraints

M0.4 stays intentionally compact:

- WAV library only
- local machine only
- maximum four mixer layers
- browser UI has no cloud/CDN dependency
- offset range in the browser is 0–5000 ms
- no trimming, EQ, pitch, reverb, or waveform editing yet
- renderer currently expects 16-bit mono WAV layers at a shared sample rate

## Project layout

\`\`\`text
docs/           product and implementation specs
src/mgal/       Python package
src/mgal/web/   dependency-free browser mixer
fixtures/       deterministic test data and recipes
tests/          contract tests
\`\`\`

## Design principle

> Shorten the distance between “I imagine this sound” and “I can hear it in the game”.

AI generation remains a future source provider, not the core architecture.
