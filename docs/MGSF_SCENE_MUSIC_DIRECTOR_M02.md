# MGSF Scene Music Director M0.2: Living Music Pipeline

Status: **implementation in review / no real provider or Godot listening evidence**.

This milestone bridges manual BGM creation and an auditable local game-audio loop. It does not access BGMクリエーター's private APIs, purchase credits, confirm licenses, select winners or claim an actual Godot playtest.

## Requirements

- Python 3.11+ and a local checkout of https://github.com/madowaku/mado-game-audio-loop.
- Install with: python -m pip install -e ".[dev]"
- FFmpeg (https://ffmpeg.org/) with ffmpeg, ffprobe, and libvorbis on PATH.
- Godot 4.x, optional for opening generated preview projects.
- A BGM file that the human has downloaded and has permission to use in evaluation. Never commit source audio to this repository.

## End-to-end commands

A local BGM file is the starting point. In this example the operator downloads village.mp3 manually.

~~~bash
mgal-music ingest ./village.mp3 \
  --workspace ./audio \
  --scene-id cozy_village \
  --provider bgmcreator \
  --origin-url https://bgmcreator.cotorano.com/ja

# Choose source region by listening to the ORIGINAL first.
mgal-music prepare ./audio/scene-music/cozy_village/manifest.json \
  --candidate A --start 10 --end 50 --crossfade 0.35
mgal-music prepare ./audio/scene-music/cozy_village/manifest.json \
  --candidate B --start 12 --end 52 --crossfade 0.75

# Preview project generation is NOT proof that Godot ran.
mgal-music godot-preview ./audio/scene-music/cozy_village/manifest.json --candidate A

# Source and derived-file hash consistency only:
mgal-music verify ./audio/scene-music/cozy_village/manifest.json

# Start an actual listening session after installing Godot 4.
godot --editor --path ./audio/scene-music/cozy_village/godot-preview/A
~~~

Run python -m mgal.scene_music instead of mgal-music when using a source checkout without installing the console script.

## Layout

~~~text
audio/
└── scene-music/
    └── cozy_village/
        ├── manifest.json
        ├── original/
        │   └── source.mp3
        ├── processed/
        │   ├── A/
        │   │   ├── loop.ogg
        │   │   └── boundary-preview.wav
        │   └── B/
        │       ├── loop.ogg
        │       └── boundary-preview.wav
        └── godot-preview/
            └── A/
                ├── music.ogg
                ├── main.gd
                ├── main.tscn
                └── project.godot
~~~

- The original is copied once and fingerprinted with SHA-256. A different upload under the same scene ID is rejected.
- Each A/B/C candidate is immutable. Use another candidate slot for a different trim or crossfade.
- loop.ogg is a 48 kHz stereo Ogg Vorbis export. An optional circular crossfade joins the end and beginning; the output period is approximately end - start - crossfade seconds.
- boundary-preview.wav contains a brief tail-then-head excerpt for evaluating the join. **This is not evidence of seamless musical phrasing.**
- Godot 4's AudioStreamOggVorbis is configured with loop=true in a generated AudioStreamPlayer scene.
- verify detects missing or altered source, candidate, and Godot-scaffold assets using stored hashes. **Integrity PASS does not mean release approval.**
- The manifest starts with commercial_use_allowed=null, rights.reviewed=false, selected_candidate=null, and godot_playtest_verified=false.

## Human listening checklist

1. Play each candidate in Godot long enough to hear the transition at least three times.
2. Listen for clicks, abrupt harmony changes, unnatural beat placement, and listener fatigue.
3. Keep a human note of A/B/C preference, scene fit, and listening conditions.
4. Check the provider's current terms yourself and attach a dated evidence URL or document before any commercial distribution.
5. Do not promote to the MGAL SFX Candidate Board. Its current recipe semantics are for effects, not full-length music.
6. Attach real Godot runner/playtest evidence to a later milestone before marking engine verification passed.

## Verification and limits

The tests use generated synthetic tones, not claimed real provider music. They verify source immutability, real FFmpeg output duration (when binaries are available), multiple candidates, source drift, path traversal, immutable Godot scaffold, and CLI smoke behavior.

M0.2 is not a final music authoring suite:
- No direct provider API integration and no circumvention of provider limits.
- No automatic loop-point/music-bar detection.
- No browser UI, no auto winner selection, no automatic upload to Shared Brain.
- No validated Godot runtime session in this milestone.
- No automatic commercial licensing determination.
- No guarantees that crossfades are musically seamless.

Next milestone M0.3 should add a single Godot A/B/C listening scene with a logged human preference session, loop-boundary metrics, and explicit release-provenance gates.
