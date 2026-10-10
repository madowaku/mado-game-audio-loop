# MGAL-M2.6: Licensed Audio Pack Intake / Adaptive Music Bridge

## Goal and boundaries

This milestone adds an opt-in, local-only intake route for royalty-free or otherwise licensed
third-party audio ZIPs and a Godot 4 adapter for **three-level adaptive music**. It does not
replace the M2.5 Recipe Materializer, normalize purchased audio, import the sounds into
Candidate Board, or grant a license. MAF-M0.9's license-aware concepts inform the evidence
contract, but **no direct MAF integration is asserted**.

No vendor SDK, authentication, network request, or paid service is required.
No commercial audio is included in the repository or test fixtures.

### License policy

The operator reviews the actual grant/receipt, prepares a declaration, and supplies a local
evidence file. MGAL checks hashes and explicit scope; **it cannot independently determine
that the declaration is legally accurate**.

The declared use must be `embedded_game_only`. Standalone redistribution must be `false`.
A source archive or a Godot source project containing extracted audio must not be published.
For Ovani Sound specifically, consult the current FAQ and the terms accompanying the actual
download. Ovani requests audio be embedded in game builds and kept out of public Git repos:
<https://ovanisound.com/pages/faq>.

Never commit a receipt or personal purchasing information; the manifest saves its SHA-256
rather than the underlying evidence bytes. Store purchased ZIPs and receipts outside Git.

## 1. Prepare license evidence

Save the actual license terms as a local `license-terms.txt` file. A copy of the grant
text, or an independently retained license document, is suitable as long as it captures
what the operator reviewed. Store purchase proof separately and privately.

Calculate SHA-256:

```powershell
(Get-FileHash .\license-terms.txt -Algorithm SHA256).Hash.ToLower()
```

Create `declaration.json` **outside the repository**:

```json
{
  "licensed_audio_declaration_version": "0.1",
  "pack_name": "My reviewed music sampler",
  "publisher": "Publisher of this pack",
  "source_url": "https://example.org/original-download",
  "license_url": "https://example.org/license-terms",
  "reviewed_by": "human operator",
  "usage_scope": "embedded_game_only",
  "standalone_redistribution": false,
  "evidence_sha256": "replace_with_64_lowercase_hex_sha256"
}
```

Do not accept a blog post claiming that a pack is free as substitute for the actual license.
The workflow fails closed on missing evidence, edited evidence, missing fields, or unsupported
license scope.

## 2. Intake and verify

```powershell
python -m pip install -e ".[dev]"

mgal licensed-pack-intake C:\Private\Mixtape.zip `
  --audio-root C:\Private\mgal-workspace `
  --declaration C:\Private\declaration.json `
  --license-evidence C:\Private\license-terms.txt `
  --pack-id ovani-mixtape

mgal licensed-pack-verify `
  --audio-root C:\Private\mgal-workspace `
  --pack-id ovani-mixtape `
  --license-evidence C:\Private\license-terms.txt
```

Different ZIPs from the sampler (music and SFX) may be ingested separately with distinct
`--pack-id` values and the correct evidence for each grant.

Audio is stored only at:

```text
C:\Private\mgal-workspace\
  .mgal\private-packs\ovani-mixtape\
    manifest.json
    audio\...
```

The import is idempotent for an identical ZIP and declaration. A conflicting archive with
the same pack ID is rejected. Changing any imported file or the evidence file causes
verification to fail.

### ZIP / metadata constraints

- Audio formats: PCM WAV, OGG, MP3. Files are copied unchanged, not transcoded.
- Up to 4000 ZIP entries; up to 3 GiB declared total and 512 MiB per file.
- Absolute, parent traversal, duplicate, encrypted, and symlink ZIP members are rejected.
- Unsupported media formats remain outside the manifest. No automatic conversion.
- Only complete, unambiguous filename-token `low/medium/high` triplets are detected.
- 30s/60s short cuts are excluded from adaptive groups.
- Filename detection is best-effort. Inspect the resulting manifest before shipping.
- A Music ZIP with naming different from this heuristic may produce zero groups.
  Manual mapping and duration/beat-grid alignment are future work.

## 3. Godot adapter: metadata-only first

Make sure the project folder contains `project.godot`.

```powershell
mgal adaptive-music-godot `
  --audio-root C:\Private\mgal-workspace `
  --pack-id ovani-mixtape `
  --godot-project C:\Dev\MyGame `
  --license-evidence C:\Private\license-terms.txt
```

This creates **only**:

```text
MyGame/addons/mgal_adaptive_music/ovani-mixtape/
  bridge.json
  adaptive_music.gd
```

`bridge.json` contains `res://` paths and SHA references, **not** raw licensed data.
The command reports `ready_for_playback=false`.

## 4. Opt in to local licensed asset copy

```powershell
mgal adaptive-music-godot `
  --audio-root C:\Private\mgal-workspace `
  --pack-id ovani-mixtape `
  --godot-project C:\Dev\MyGame `
  --license-evidence C:\Private\license-terms.txt `
  --copy-licensed-audio
```

Only the three full-length intensity variants per detected group are copied to:

```text
MyGame/assets/mgal_licensed/ovani-mixtape/...
MyGame/assets/mgal_licensed/.gitignore
```

The `.gitignore` is installed before any copies. Existing tracked or conflicting files
are rejected. This reduces accidental upload risk, but **never** rely exclusively on
`.gitignore`: check `git status`, `git ls-files`, and game export contents before
publishing. Existing Git-tracked assets should be removed from Git history if previously
published; merely adding `.gitignore` will not undo disclosure.

A Godot project exported as a reusable source/template with copied raw files is **not**
the intended distribution format. Ship properly packed game exports only after your license
review, test Godot importer behavior, and validate the final package.

## 5. Use in Godot

Attach `adaptive_music.gd` to a Node in your scene or instantiate it from code, after
the project imports the copied audio. Example:

```gdscript
@onready var adaptive := $MGALAdaptiveMusic

func _ready() -> void:
    print(adaptive.available_tracks()) # choose a track ID from bridge.json
    adaptive.play_track("track-<id-from-bridge-json>", "low")

func on_enemy_spotted() -> void:
    adaptive.set_intensity("medium")

func on_boss_battle() -> void:
    adaptive.set_intensity("high")
```

The script uses two `AudioStreamPlayer` instances and a configurable crossfade.
It attempts approximate playback-position continuity within the same track; it does
**not** promise sample-accurate beat alignment, seamless musical bar transitions, automatic
loop regions, or the functionality of Ovani's proprietary integration plugins. Preview
each trio by ear, ensure Godot import/loop settings suit the music, and test a packaged game.

## Evidence and promotion boundaries

| Check | Required |
|---|---|
| Declared game-embedded use, no standalone re-distribution | Yes |
| Original evidence SHA-256 matches saved declaration | Yes, on each verify/export |
| ZIP path / size / link defense | Yes |
| Extracted audio hash and size match | Yes |
| Complete unambiguous intensity groups | Yes, to stage Godot |
| Explicit opt-in to copy audio into Godot | Yes |
| Automatic rights verification from provider | No |
| MAF provenance ledger synchronization | Future milestone |
| SFX → MGAL Candidate Board audition | Future milestone |
| Godot packaged-export QA (not merely script generation) | Future milestone |

## Tests

```bash
pytest -q tests/test_licensed_pack.py
pytest -q
```

Synthetic PCM WAVs are generated in memory, so tests cannot leak a commercial sample.
A live dogfood test needs the operator's own downloaded pack and Godot executable.
