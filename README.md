# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work into a reproducible creative loop:

**provide → intake → blind preference → archive → replay → decide → evidence → release**

## Current milestone: M1.8 Preference Replay UI / Session Archive

M1.8 turns Preference Evidence into a durable local history that can be reopened and replayed from the Browser Audition Board.

The workspace now carries:

```text
audio/
└── .mgal/
    ├── provenance-ledger.json
    ├── intakes/
    └── preferences/
        └── <archive-id>/
            ├── manifest.json
            └── evidence.json
```

## Archive a completed Preference Session

After Reveal, the Browser action is:

```text
Archive + download
```

The Browser sends the session to:

```text
POST /api/preference-archive
```

The server:

1. compiles Preference Evidence 0.1
2. validates Candidate Board, mapping, pairs, votes and winner/tie
3. fingerprints every compared source WAV
4. verifies replay against the current workspace
5. writes a content-addressed archive session
6. returns the same Evidence for download

The older compile-only endpoint remains available:

```text
POST /api/preference-evidence
```

## Content-addressed archive identity

If no explicit archive ID is supplied, MGAL derives one from:

```text
<base-recipe-id>-<preference-evidence-sha256-prefix>
```

The hash is computed from canonical JSON.

Consequences:

- saving the exact same Evidence again reuses the same archive
- the same explicit archive ID cannot silently point to different Evidence
- applying a winner changes the Board snapshot and therefore creates a distinct archive from the pre-Apply session

## Archive manifest

Each session has a small manifest:

```text
preference_archive_version = 0.1
archive_id
evidence_sha256
candidate_board_sha256
candidate_count
pair_count
source_count
winner_candidate_id
tie
applied_candidate_id
```

The archive stores the full Preference Evidence separately as `evidence.json`.

Archive verification also rechecks all current source WAV hashes.

## CLI archive workflow

Archive an exported session:

```bash
mgal preference-archive ./preference-evidence.json \
  --audio-root ./audio
```

Optionally choose a stable name:

```bash
mgal preference-archive ./preference-evidence.json \
  --audio-root ./audio \
  --archive-id heavy-slash-review
```

List sessions:

```bash
mgal preference-list --audio-root ./audio
```

Replay one archived session:

```bash
mgal preference-replay-archive heavy-slash-review \
  --audio-root ./audio \
  --output ./replay-plan.json
```

## Preference Archive UI

The Browser now contains a local archive shelf:

```text
PREFERENCE ARCHIVE

heavy-slash-7a21c4...
3 pairs · 3 sources · winner candidate-b · applied candidate-b

[ Replay ]
```

The list is loaded from:

```text
GET /api/preferences
```

A broken archive remains visible with an error state rather than silently disappearing.

## Verified Replay

Opening an archive calls:

```text
GET /api/preferences/<archive-id>/replay
```

The server verifies the archived Evidence and all source fingerprints before returning a replay plan.

If a WAV changed, replay is rejected before playback.

The Browser Replay panel then shows:

```text
VERIFIED REPLAY

X = Candidate B
Y = Candidate A
Z = Candidate C

Pair 1 / 3

Y                 X
Candidate A       Candidate B

[ Play Y ]   vs   [ Play X ]

Recorded preference: X · Candidate B

[ Prev pair ] [ Next pair ]
```

## Exact Recipe replay

M1.7 replay returned source paths.

M1.8 additionally includes each side's embedded Candidate Recipe:

```text
left_recipe
right_recipe
```

The Browser hydrates those Recipe layers through the current audio catalog.

That preserves:

- source path
- layer gain
- layer offset
- multiple layers

So a manually designed layered Candidate can be replayed with the same Recipe parameters used during the archived comparison.

## Archive does not overwrite current work

Preference Replay is a separate Browser surface.

Opening an old session does not:

- replace the current Candidate Board
- change active Candidate decisions
- change the current Recipe
- Apply the archived winner
- rerun randomization

Replay is observational.

It reconstructs the recorded experiment.

## Invalid archive behavior

The archive list verifies each session.

If its Evidence is malformed or a referenced source WAV changed, the session is shown as invalid.

Example:

```text
heavy-slash-review
INVALID · preference replay source hash changed: incoming/...wav
```

The Replay button is not offered for invalid sessions.

## API surface

```text
POST /api/preference-evidence
  compile only

POST /api/preference-archive
  compile + validate + archive

GET /api/preferences
  list/verify archives

GET /api/preferences/<archive-id>/replay
  verify sources + return exact replay plan
```

## Relationship to main Evidence Bundle

Preference Archive and final Evidence Bundle have different roles.

```text
.mgal/preferences/
= reusable local decision history

Evidence Bundle
= frozen release/decision evidence
```

A Preference Evidence artifact can still be attached to the normal Bundle with:

```bash
mgal bundle candidate-board.json \
  --audio-root ./audio \
  --preference-evidence ./preference-evidence.json \
  --output ./evidence/session-001
```

## Current constraints

- archive is local JSON, not a database
- list operation verifies source hashes and may become heavier with very large archives
- archive deletion/pruning UI is not implemented
- archive tags/notes are not implemented
- Browser Replay does not auto-play the entire pair sequence
- replay requires original workspace-relative source paths
- Preference source relinking is not implemented yet
- archive has no wall-clock timestamp by design; identity is content-based

## Design principle

> A creative decision becomes more useful when its history can be reopened without changing the present.

M1.8 turns blind comparison Evidence into a navigable local decision archive.
