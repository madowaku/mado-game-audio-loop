# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work from “find something and drop it in” into a reproducible loop:

**scan → audition → layer → compare → save recipe → render → reuse**

## Current milestone: M0.2 Browser Audition Board

MGAL now includes a small local browser workbench for rapidly auditioning WAV files.

It can:

- scan a local audio folder
- show filename, duration, sample rate, and channel count
- draw lazy-loaded waveforms in the browser
- play and stop sounds without opening files one by one
- filter the library by filename/path
- select up to four candidate layers
- download a valid MGAL recipe draft

M0.2 intentionally stops before live mixing. Gain, offset, mute/solo, and simultaneous preview belong to M0.3.

## Quick start

```bash
python -m pip install -e ".[dev]"
pytest
```

Point MGAL at any folder containing WAV files:

```bash
mgal serve ./audio
```

The board opens at:

```text
http://127.0.0.1:8765
```

Useful CLI commands:

```bash
mgal --help
mgal scan ./audio
mgal validate recipe.json
mgal render recipe.json --output output.wav
mgal serve ./audio --no-browser
```

## Browser Audition Board flow

```text
local WAV folder
      ↓
browser catalog
      ↓
waveform + one-click audition
      ↓
search / shortlist
      ↓
select up to 4 layers
      ↓
download recipe JSON
      ↓
M0.3 Layer Mixer
```

## Project layout

```text
docs/           product and implementation specs
src/mgal/       Python package
src/mgal/web/   dependency-free browser UI
fixtures/       deterministic test data and recipes
tests/          contract tests
```

## Current constraints

M0.2 is deliberately small:

- WAV library only
- local machine only
- browser UI has no cloud dependency
- recipe draft uses relative source paths
- mixing controls are not yet exposed in the browser

## Design principle

> Shorten the distance between “I imagine this sound” and “I can hear it in the game”.

AI generation is treated as a future source provider, not as the core architecture.
