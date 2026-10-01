# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work from “find something and drop it in” into a reproducible loop:

**scan → audition → layer → mix → compare → save recipe → render → reuse**

## Current milestone: M0.3 Layer Mixer

MGAL now has a dependency-free local browser mixer for rapidly building layered game sound effects.

It can:

- scan a local WAV folder
- search, inspect waveforms, and audition individual sounds
- select up to four layers
- preview the selected layers simultaneously
- change gain while the mix is playing
- mute or solo layers while the mix is playing
- shift each layer with a millisecond offset
- export gain and offset into a reproducible recipe
- render a downloaded browser recipe against an explicit audio root

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

## M0.3 control contract

**Persisted in Recipe**

- source path
- gain
- offset_ms

**Audition-only**

- mute
- solo

Mute and solo intentionally do not alter the saved recipe. They are temporary listening tools for answering questions such as “what is the metal layer contributing?” or “does this whoosh work on its own?”

## Current constraints

M0.3 stays intentionally compact:

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
