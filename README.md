# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work into a reproducible creative loop:

**provide → intake → blind preference → archive → decision memory → retrieve context → create again**

## Current milestone: M2.1 Decision Memory Retrieval / Context Pack

M2.1 makes explicitly promoted Decision Memory useful during a new sound-design task without turning memory into an automatic recommender.

The flow is:

```text
Current intent
     ↓ explicit retrieval
Decision Memory
     ↓ deterministic intent match
Context Pack
     ↓ reference only
creator listens / edits / decides
```

The Context Pack can inform the creator. It cannot choose, rank, copy, select, or apply a Candidate.

## Context Pack 0.1

Top-level fields:

```text
decision_context_pack_version = 0.1
context_pack_id
retrieval_strategy
decision_memory_sha256
query
memory_snapshot
matched_entry_count
returned_entry_count
truncated
observations[]
usage
```

Authority boundary:

```json
{
  "usage": {
    "role": "reference_only",
    "selection_effect": "none"
  }
}
```

Both Python validation and the Browser UI enforce this boundary.

## Deterministic retrieval strategy

Current strategy:

```text
intent-token-overlap-v1
```

The query and each promoted observation's source intent are normalized with Unicode NFKC and case folding.

Retrieval terms include:

- Unicode word tokens with length >= 2
- a small English stop-word exclusion
- CJK contiguous runs
- CJK 2-grams for Japanese/Chinese/Korean intents

Examples:

```text
query:
metallic sword impact

memory:
crisp metallic sword impact

matched:
metallic
sword
impact
```

Japanese intent fragments also remain searchable through CJK 2-gram overlap.

## What match values mean

Context observations record:

```text
exact_intent
matched_terms[]
match_count
query_term_count
source_term_count
```

These are retrieval metadata only.

They are **not**:

```text
Candidate quality
preference strength
confidence
taste score
recommendation score
```

The retrieval order is deterministic:

1. exact intent first
2. more matched terms first
3. source intent
4. archive ID
5. pair index
6. entry ID

No randomness is used.

## Zero-match behavior

MGAL does not fill an empty result with unrelated memories.

```text
query: underwater bubble

Decision Memory:
- crisp metallic sword impact
- soft wooden UI tap

result:
0 observations
```

This prevents old decisions from leaking into unrelated work merely because some context is available.

## CLI

Retrieve context:

```bash
mgal decision-context "heavy metallic slash" \
  --audio-root ./audio \
  --limit 6
```

Write a portable JSON Context Pack:

```bash
mgal decision-context "heavy metallic slash" \
  --audio-root ./audio \
  --limit 6 \
  --output ./context/heavy-metallic-slash.json
```

Verify that a saved pack still matches current Decision Memory:

```bash
mgal decision-context-verify \
  ./context/heavy-metallic-slash.json \
  --audio-root ./audio
```

## Memory snapshot binding

Each Context Pack records:

```text
decision_memory_sha256
```

The hash covers the complete canonical Decision Memory used during retrieval.

Therefore:

```text
Context Pack generated
      ↓
another archive gets promoted
      ↓
Decision Memory changes
      ↓
old Context Pack = stale
```

`decision-context-verify` rejects a stale pack instead of pretending it still represents the current memory set.

The Context Pack itself also has a deterministic:

```text
context:<sha256-prefix>
```

identity derived from its payload.

## Browser workflow

The Intent field now has:

```text
[ Load memory context ]
[ Download context pack ]
```

Loading is explicit. MGAL does not query Decision Memory on every keystroke.

The Browser calls:

```text
GET /api/decision-context?intent=<current-intent>&limit=6
```

A result appears beside the current Recipe work:

```text
MEMORY CONTEXT · REFERENCE ONLY

3 of 3 matching observations

memory-b preferred over memory-a
metal-archive · crisp metallic sword impact
matched metallic, sword, impact
observed Δ gain +0.3 · earliest offset +25ms
```

There are no Candidate-action buttons in this panel.

## Intent-change staleness

If the creator edits Intent after loading Context:

```text
Intent changed.
Reload context before using this pack.
```

The Browser marks the displayed pack stale and disables Context Pack download.

It does not silently auto-retrieve a different set.

This preserves an explicit relationship between:

```text
the intent the creator asked about
and
the observations shown beside it
```

## Observation payload

Each returned observation carries the promoted Decision Memory facts required for inspection:

```text
entry_id
archive_id
archive_evidence_sha256
source_intent
match metadata
pair_index
winner_candidate_id
loser_candidate_id
winner_recipe
loser_recipe
observed_differences
```

Recipe summaries still use SHA-256 source identities rather than filesystem paths.

## Automatic-action prohibition

Context Pack validation rejects fields named:

```text
recommended_candidate
auto_select
preference_score
candidate_ranking
```

M2.1 also does not introduce:

```text
copy winner to Candidate
apply past winner
auto fork
auto mix
auto source selection
```

The Browser independently checks:

```text
usage.role == reference_only
usage.selection_effect == none
```

before displaying a server result.

## Relationship to M2.0

```text
M2.0 Decision Memory
= the observations the creator explicitly chose to remember

M2.1 Context Pack
= a small deterministic subset relevant to the current intent
```

Decision Memory is durable workspace state.

Context Pack is a query result bound to one Memory snapshot and one intent.

## Current constraints

- retrieval is lexical, not semantic embedding search
- there is no stemming or synonym expansion
- CJK support is deterministic 2-gram matching, not language-specific morphology
- retrieval uses Decision Memory intent text only
- Context Pack does not retrieve raw WAV files
- no automatic weighting from repeated wins
- no time decay or recency bonus
- no learned taste model
- Browser limit is currently fixed at 6
- stale Context Packs must be regenerated after Decision Memory changes

## Design principle

> Let memory answer “what happened before?” without answering “what should I choose now?”

M2.1 gives the creator relevant past evidence at the moment of creation while leaving the new decision open.
