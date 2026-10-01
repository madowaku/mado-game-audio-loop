# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work from “find something and drop it in” into a reproducible loop:

**scan → audition → layer → compare → save recipe → render → reuse**

## M0.1 Local Audio Workbench

The first milestone deliberately avoids requiring an AI audio generator.

It focuses on:

- scanning local audio assets
- validating audio recipes
- rendering layered WAV output
- keeping the recipe reproducible
- establishing fixtures and tests for later browser UI work

## Quick start

```bash
python -m pip install -e ".[dev]"
mgal --help
mgal validate fixtures/recipes/sword_slash_heavy.json
pytest
```

## Project layout

```text
docs/       product and implementation specs
src/mgal/   Python package
fixtures/   deterministic test data and recipes
tests/      contract tests
```

## Design principle

> Shorten the distance between “I imagine this sound” and “I can hear it in the game”.

AI generation is treated as a future source provider, not as the core architecture.
