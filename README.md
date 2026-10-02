# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work into a reproducible creative loop:

**provide → intake → seed → audition → compare → decide → evidence → replay → release**

## Current milestone: M1.4 Intake Session → Candidate Seed

M1.4 turns one Provider intake session directly into a Candidate Board.

The shortest path is now:

```text
prompt
  ↓
Provider candidates
  ↓
provider-intake
  ↓
intake session
  ↓
Seed A/B/C
  ↓
direct candidate preview
  ↓
human selection
```

No manual Add layer step is required when the goal is simply to compare Provider alternatives.

## Seed contract

One intake session compiles into the existing Candidate Board 0.1 contract.

```text
intake candidate 1 → A
intake candidate 2 → B
intake candidate 3 → C
```

Rules:

- 1 source seeds A
- 2 sources seed A/B
- 3 sources seed A/B/C
- 4+ sources seed the first three
- each candidate starts as one layer
- gain = 1.0
- offset = 0 ms
- decision = undecided
- intake request intent becomes Board intent

The first intake source is also used as the immutable Base Recipe.

That keeps the existing Candidate Board lineage contract unchanged:

```text
Base
├── A r1
├── B r1
└── C r1
```

A equals the Base source. B/C record a one-source difference versus Base.

## CLI seed compiler

The browser is not the only way to use the feature.

```bash
mgal intake-seed-board \
  --audio-root ./audio \
  --intake-id heavy-slash-001 \
  --output ./boards/heavy-slash-candidates.json
```

The resulting JSON is validated by the same Python Candidate Board parser used by Evidence.

So this works immediately:

```bash
mgal validate-board ./boards/heavy-slash-candidates.json
```

After choosing a winner and saving the updated Board, it can enter the normal strict Evidence path.

## Browser session panel

Run:

```bash
mgal serve ./audio
```

Provider intakes appear in a dedicated section:

```text
PROVIDER INTAKES

heavy-slash-001
stability-audio · stable-audio-3 · 3 sources
short stylized metallic sword slash

[ Seed A/B/C from intake ]
```

The session panel groups WAVs by intake ID rather than showing only independent files.

For sessions with more than three sources, the UI clearly marks:

```text
first 3 seed
```

## Seed API

The browser uses the server-side compiler:

```text
GET /api/intakes/<intake-id>/seed-board
```

The response is a valid Candidate Board payload.

The browser then hydrates each Recipe source path back into the live audio catalog so existing Web Audio preview and mixer code can be reused.

There is no second Candidate Board implementation hidden in JavaScript.

## Candidate cards

After seeding, Candidate cards show the actual source file name.

Example:

```text
A   undecided
1 layer · 0 changes vs base
01-heavy-slash-....wav
[ Preview ]

B   undecided
1 layer · 1 change vs base
02-heavy-slash-....wav
[ Preview ]

C   undecided
1 layer · 1 change vs base
03-heavy-slash-....wav
[ Preview ]
```

The existing controls still work:

- Preview
- Edit
- Copy active
- Favorite
- Reject
- Select
- decision reason

Once seeded, the candidates are ordinary MGAL candidates.

## Board overwrite safety

If a Candidate Board is already active, all intake seed buttons are disabled.

MGAL does not silently replace comparison work.

Use:

```text
Clear board
```

to explicitly reset the current Board before seeding another intake session.

Manual `Fork A/B/C` remains available for layered mixes.

The two workflows coexist:

```text
single-source Provider comparison
→ Seed A/B/C from intake

layered sound-design comparison
→ Add layers → Fork A/B/C
```

## Full generated-audio flow

```bash
mgal source-provide \
  --provider stability \
  --artifact-root ./provider-raw/slash \
  --allow-paid \
  --request-id heavy-slash \
  --intent "short stylized metallic sword slash" \
  --count 3 \
  --output ./provider-runs/heavy-slash.json

mgal provider-intake ./provider-runs/heavy-slash.json \
  --audio-root ./audio \
  --intake-id heavy-slash-001

mgal serve ./audio
```

Then in the browser:

```text
Seed A/B/C from intake
        ↓
▶ Preview A
▶ Preview B
▶ Preview C
        ↓
★ Favorite / × Reject / ✓ Select
        ↓
Download board JSON
```

The prompt-to-comparison path is now extremely short.

## Why the seed is server-compiled

The seed compiler lives in Python because Candidate Board is an evidence-bearing contract.

That gives one source of truth for:

- Base Recipe
- candidate IDs
- labels
- revision
- parent Recipe
- lineage
- decisions
- source paths

The Browser only hydrates and edits the validated result.

## Existing Evidence chain stays unchanged

M1.4 adds no special intake-only Evidence format.

After seeding:

```text
Candidate Board 0.1
       ↓
Human Select
       ↓
Evidence Bundle
       ↓
Replay / Relink
       ↓
Release / Attribution Pack
```

Recipe source paths still point at canonical WAVs under the audio workspace, and workspace provenance remains available at:

```text
audio/.mgal/provenance-ledger.json
```

## Current constraints

- one intake seed uses at most three candidates
- seed order follows intake manifest order
- each seeded candidate initially contains one layer
- Base Recipe is candidate A's source
- intake seed does not automatically mark a winner
- existing Candidate Board must be cleared before another intake is seeded
- no automatic sequential A/B/C playback yet
- no browser-side Provider generation button yet

## Design principle

> A Provider gives alternatives. M1.4 turns those alternatives directly into a decision surface.

This closes the original prompt → candidates → listen → choose loop without bypassing MGAL's evidence model.
