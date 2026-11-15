# MGSF Scene Music Director M0.1

Status: **incubation / integration contract** (2026-11-15). This is an adopted design, not evidence of a completed live BGM generation or Godot playtest.

## Purpose
Turn game scene intent into a reproducible, human-approved BGM sourcing workflow. Reuse MADO Game Audio Loop's listen/compare/evidence philosophy rather than developing another music-generation platform.

## Providers and authority
- Entry point: [BGMクリエーター](https://bgmcreator.cotorano.com/ja), external browser tool.
- No officially confirmed public API contract: **do not automate sign-in, scrape endpoints, bypass limits, or assume direct API access**.
- Human uses the provider UI, downloads a track, and registers the local artifact.
- Provider prices, usage limits, output formats, and licensing are **unverified operational inputs** until checked against the current official UI and terms.
- Never equate provider marketing or a model license with permission to redistribute generated tracks. Record the exact terms URL/version and the operator's commercial-use determination before shipping.
- Never store credentials or external audio binaries in Git.

## M0.1 workflow
1. **Intent:** Creative Intent Engine or human supplies scene_id, gameplay_context, emotional_arc, intensity, duration_target_s, loop_required, and avoid_tags.
2. **Direction:** Music Director proposes a concise card/UI selection brief and three variations: A control, B emotional alternative, C arrangement alternative.
3. **Generate:** Human manually enters settings in BGMクリエーター and downloads the result, following limits and provider policy.
4. **Ingest:** Store original media outside the repo. Capture SHA-256, file size, format, duration, source/provider, human operator, retrieval time, selection settings, license review, and whether audio is direct provider output.
5. **Finish:** Make non-destructive edits using local free tools (e.g. ffmpeg, Audacity) where needed. Keep original immutable, export an Ogg Vorbis/WAV engine candidate, and document processing.
6. **Loop check:** Inspect the join audibly for click and musical timing. Do not confuse a technically seamless crossfade with a musically seamless loop.
7. **Godot audition:** Wire an AudioStreamPlayer in a test scene; confirm actual playback and loop in a recorded engine run.
8. **Evaluate:** Compare A/B/C blind when possible for fit, fatigue, transition, emotional match, and technical quality. Record listener identity/date and explicit human selection. No automatic promotion.

## Minimal manifest (JSON)
See `fixtures/scene_music_director_m01.example.json`.
- `provenance`: provider URL, acquisition method, timestamp and creator/operator
- `rights`: terms URL, reviewed date, commercial-use decision, evidence
- `source`: path, SHA-256, byte count, duration, encoding
- `processing`: operations and output hash
- `playtest`: Godot project, tested scene, evidence path, verified status
- `decision`: human review, A/B/C preference and rationale

Unfilled values remain `null`. Do not invent source hashes, licensing receipts, playable previews, or successful tests.

## Integration boundary
- Existing MADO Game Audio Loop primarily handles **SFX recipe/layer** mechanics. Do **not** feed a full-length MP3 into its SFX Recipe materializer without a deliberate schema and evaluation extension.
- This M0.1 deliverable is the BGM **intent/asset provenance/loop/playtest contract**, not a claim of completed integration with MGAL's Candidate Board.
- Shared Brain gets a small decision record only after human evaluation.
- Creative Intent Engine owns scene meaning; audio tools own sound artifacts; Godot owns in-engine verification.

## Acceptance gates
| Gate | Pass condition | M0.1 status |
|---|---|---|
| Intent | Three distinct scene briefs | fixture only |
| Provider access | Human confirms current official UI and terms | HOLD |
| Generation | At least one real provider artifact + SHA receipt | HOLD |
| Conversion | Original preserved; converted track hash + playback inspection | HOLD |
| Seamless loop | Recorded loop-point audition without click or jarring phrase break | HOLD |
| Godot | Real run, clip playback and loop evidence | HOLD |
| Licensing | Current terms review for intended distribution | HOLD |
| Selection | Human signs off on selected scene track | HOLD |

## First dogfood scenes
- `cozy_village`: peaceful, welcoming, light acoustic / gentle plucked instruments, no dramatic percussion.
- `mystery_forest`: curious, softly uncanny, sparse textures, restrained tension.
- `quiet_rest_stop`: safe, spacious, restorative, low fatigue for repeated listening.

## Next engineering increment
Add a tiny local CLI to validate the manifest, hash audio, convert through an available ffmpeg installation, and produce a Godot test scene. Implement source SHA validation before any selection or export workflow. Keep integrations optional and offline-first.
