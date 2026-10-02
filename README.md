# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work into a reproducible creative loop:

**provide → intake → blind preference → archive → recover → promote → decision memory → evidence → release**

## Current milestone: M2.0 Preference Archive Promotion / Decision Memory

M2.0 turns selected Preference Archives into reusable decision evidence.

The boundary is deliberate:

```text
Preference Archive
= what happened in one blind listening session

Decision Memory
= only the sessions the creator explicitly chose to keep as reusable observations
```

Decision Memory does **not** choose the next Candidate.

It records observed pairwise choices so future tools can retrieve context without converting past taste into an automatic rule.

## Explicit promotion

Every Preference Archive remains ordinary history until the creator explicitly promotes it:

```bash
mgal decision-promote heavy-slash-review \
  --audio-root ./audio
```

Browser archives expose:

```text
[ Promote memory ]
```

After promotion:

```text
[ In memory ]
```

Promotion is independent from source recovery.

A structurally valid Preference Archive may be promoted even if its WAV files have moved and the archive is currently marked `recoverable`.

That is intentional:

```text
source availability
!=
historical decision validity
```

## Workspace storage

Decision Memory is stored at:

```text
audio/
└── .mgal/
    ├── decision-memory.json
    ├── preferences/
    └── preference-relinks/
```

Schema:

```text
decision_memory_version = 0.1
promotion_count
entry_count
promotions[]
entries[]
```

## Promotion records

One promotion records the archived session identity:

```text
archive_id
archive_evidence_sha256
candidate_board_sha256
intent
pair_count
winner_candidate_id
tie
applied_candidate_id
entry_ids[]
```

The canonical Preference Evidence SHA-256 is the promotion identity.

Promoting identical Evidence twice is idempotent.

Even if the same Evidence exists under another archive name, it is not counted twice.

## Pairwise Decision Memory entries

M2.0 intentionally does not collapse a session into a single taste score.

A three-pair Preference Session becomes three observations.

Example:

```text
pair 1
Candidate B preferred over Candidate A

pair 2
Candidate C preferred over Candidate A

pair 3
Candidate B preferred over Candidate C
```

Each entry records:

```text
entry_id
archive_id
archive_evidence_sha256
candidate_board_sha256
intent
pair_index
winner_alias
winner_candidate_id
loser_candidate_id
winner_recipe
loser_recipe
observed_differences
```

## Recipe summaries

Winner and loser Recipes are converted into relocatable summaries.

Each summary records:

```text
recipe_id
recipe_sha256
layer_count
total_gain
earliest_offset_ms
latest_offset_ms
normalize
fade_out_ms
source_ids[]
```

Source identity is content-addressed:

```text
sha256:<source-hash>
```

Filesystem paths are not used as Decision Memory identity.

## Observed differences

M2.0 derives deterministic pair differences:

```text
layer_count_delta
total_gain_delta
earliest_offset_ms_delta
latest_offset_ms_delta
fade_out_ms_delta
normalize_changed
shared_source_count
winner_only_source_count
loser_only_source_count
```

For example:

```text
Candidate B preferred over Candidate A

observed:
Δ layers           0
Δ total gain      +0.30
Δ earliest offset +25 ms
Δ fade              0 ms
```

These are observations about one comparison.

They are **not** converted into claims such as:

```text
"always use more gain"
"Candidate B style is better"
"auto-select this Recipe next time"
```

## Decision Memory UI

The Browser now includes:

```text
DECISION MEMORY

2 promoted sessions · 6 pairwise observations

Candidate B preferred over Candidate A
heavy-slash-review · pair 1 · crisp sword impact
observed Δ layers 0 · gain +0.3 · earliest offset +25ms
```

The UI currently shows the most recent observations.

It is a review surface, not an automatic recommender.

## API

```text
GET  /api/decision-memory
POST /api/preferences/<archive-id>/promote
```

The Preference Archive list is also enriched with:

```text
promotable
promoted
```

A recoverable archive can still be promotable.

A structurally corrupted archive cannot.

## CLI

Promote one archive:

```bash
mgal decision-promote heavy-slash-review \
  --audio-root ./audio
```

Inspect the full memory:

```bash
mgal decision-memory \
  --audio-root ./audio
```

Verify derived memory against the source Preference Archives:

```bash
mgal decision-memory-verify \
  --audio-root ./audio
```

Verification recompiles every promoted archive into its expected pairwise observations and requires exact entry equality.

This catches manual changes to:

- winner/loser identity
- Recipe summary
- Recipe fingerprint
- source fingerprints
- observed deltas
- promotion entry references

## Multi-session accumulation

Decision Memory accumulates multiple explicit promotions.

```text
Archive 001
  3 pair observations
       +
Archive 002
  3 pair observations
       =
Decision Memory
  2 promoted sessions
  6 observations
```

The summary also groups promotion counts by intent.

This is retrieval context, not a statistical quality ranking.

## Human-control boundary

M2.0 intentionally does not create:

```text
recommended_candidate
auto_select
preference_score
automatic Candidate ranking
automatic Apply winner
```

The flow remains:

```text
past blind session
      ↓
human chooses Promote
      ↓
Decision Memory observation
      ↓
future creator may inspect it
      ↓
new Candidate decision still belongs to the creator
```

## Relationship to Preference Archive

```text
Preference Archive
immutable session evidence

Preference Relink Map
current filesystem address book

Decision Memory
mutable collection of explicitly promoted observations
```

Source recovery and Decision Memory are orthogonal.

Moving files does not erase promoted decision evidence.

Promoting a session does not alter the archive, Candidate Board, Recipe, or source Relink Map.

## Current constraints

- Decision Memory is a local JSON artifact, not a database
- promotion is additive; demotion/removal UI is not implemented yet
- UI shows recent observations rather than full search/filter tooling
- observed Recipe features are intentionally small and deterministic
- no embedding/vector retrieval yet
- no inferred preference model
- no automatic Candidate recommendation
- no automatic Candidate selection
- Decision Memory is not cryptographically signed

## Design principle

> Preserve what the creator chose to remember without turning memory into authority.

M2.0 gives MGAL durable decision context while keeping new creative decisions explicitly human.
