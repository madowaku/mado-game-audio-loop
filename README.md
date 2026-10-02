# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work into a reproducible creative loop:

**provide → intake → blind preference → preference evidence → replay → final evidence → release**

## Current milestone: M1.7 Preference Session Evidence / Replay

M1.7 preserves the evaluation process from M1.6 without polluting Candidate Board 0.1.

The durable split is now:

```text
Candidate Board
= what the creator finally selected

Preference Session Evidence
= how the randomized blind comparison was conducted
```

## Preference Session Evidence 0.1

After all pair votes are complete and Reveal has happened, the Browser enables:

```text
Download evidence
```

The Browser sends the revealed session plus the current Candidate Board snapshot to the local MGAL server.

The server validates the session and fingerprints the actual WAV files before returning the evidence JSON.

Top-level format:

```text
preference_session_version = 0.1
candidate_board_sha256
candidate_board
mapping
pairs
votes
scores
winner_candidate_id
tie
applied_candidate_id
source_index
```

## What is captured

### Candidate Board snapshot

The complete Candidate Board used when Evidence is compiled is embedded.

A canonical JSON SHA-256 binds the session to that exact Board snapshot.

### Randomized mapping

```text
X → candidate-b
Y → candidate-a
Z → candidate-c
```

The exact random alias mapping is preserved.

### Pair schedule

Every comparison stores its actual order and left/right placement:

```text
pair 0
left  = Y / candidate-a
right = X / candidate-b

pair 1
left  = Z / candidate-c
right = Y / candidate-a
```

Replay never generates fresh randomness.

It reuses this recorded schedule.

### Votes

Each pair records:

- pair index
- winner alias
- winner Candidate ID
- loser Candidate ID

Scores are recomputed from votes during validation rather than blindly trusted.

### Result

Evidence stores:

```text
winner_candidate_id
tie
applied_candidate_id
```

`applied_candidate_id` may remain null if the creator revealed the result but chose not to Apply winner.

If it is present, it must:

- equal the unique preference winner
- equal the selected Candidate in the embedded Board

## Audio fingerprints

The compiler resolves every source referenced by the compared Candidates beneath the configured audio root.

For each unique source it stores:

```text
relative_path
sha256
bytes
```

This means Preference Replay can detect a sound file that was replaced after the listening session.

## Browser evidence compilation

The Browser does not author the final evidence document itself.

It POSTs the transient session to:

```text
POST /api/preference-evidence
```

The Python compiler performs:

1. Candidate Board validation
2. X/Y/Z mapping validation
3. complete pair-combination validation
4. vote-to-pair identity validation
5. score and winner recomputation
6. Apply-winner consistency validation
7. source path safety checks
8. WAV byte/hash fingerprinting

Only then is the downloadable Evidence JSON returned.

## CLI validation

```bash
mgal validate-preference ./heavy-slash-preference-evidence.json
```

Example report:

```json
{
  "ok": true,
  "candidates": 3,
  "pairs": 3,
  "winner_candidate_id": "heavy-slash-b",
  "tie": false,
  "applied_candidate_id": "heavy-slash-b",
  "sources": 3
}
```

## Preference Replay

```bash
mgal replay-preference ./heavy-slash-preference-evidence.json \
  --audio-root ./audio \
  --output ./replay-plan.json
```

Replay first verifies every source byte count and SHA-256.

If a compared WAV changed, replay fails.

On success it reconstructs:

```text
mapping
exact pair order
left/right alias placement
Candidate IDs
source paths for each side
recorded winner for each pair
final winner / tie
whether the winner was applied
```

The output is a deterministic replay plan.

## Attach Preference Evidence to normal Evidence Bundle

Preference Evidence can remain standalone or be included in the normal MGAL Evidence Bundle:

```bash
mgal bundle candidate-board.json \
  --audio-root ./audio \
  --preference-evidence ./heavy-slash-preference-evidence.json \
  --output ./evidence/session-001
```

The bundle stores:

```text
preference-session.json
```

and includes it in the existing manifest hash/size protection.

`verify-bundle` also revalidates the Preference schema and result logic.

If Preference Evidence says a winner was applied, that Candidate must match the Bundle's selected Candidate.

## Evidence boundaries

M1.7 does not move raw Preference state into Candidate Board.

Candidate Board stays focused on durable creative state:

```text
Recipes
lineage
Favorite / Reject / Selected
decision reason
```

Preference Evidence separately records the listening experiment:

```text
random mapping
pair schedule
votes
score result
Reveal outcome
Apply outcome
audio fingerprints
```

## Tamper detection

Validation rejects, among other things:

- changed embedded Candidate Board snapshot
- duplicate pair combinations
- missing pair combinations
- winner alias that does not match the pair
- incorrect loser identity
- forged score totals
- forged winner/tie flag
- Apply winner that disagrees with Board selection
- duplicate source index paths
- changed source WAV bytes during replay

## Current constraints

- Preference Evidence must be compiled after Reveal
- incomplete sessions are not evidence
- replay produces a verified replay plan, not browser auto-play yet
- Preference Evidence has its own 0.1 schema and no migration tooling yet
- source relinking for Preference Replay is not implemented yet
- session timing and number of listens are not recorded
- browser page reload still discards a session that was not exported

## Design principle

> Final choice and evaluation process are both evidence, but they are different kinds of evidence.

M1.7 preserves the blind listening experiment while keeping Candidate Board clean and reusable.
