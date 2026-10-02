# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work into a reproducible creative loop:

**provide → audition → remember → retrieve context → inspect current deltas → decide again**

## Current milestone: M2.2 Current Recipe / Decision Context Delta Inspector

M2.2 compares the Recipe being edited now with the past winner and loser Recipes returned by an M2.1 Decision Context Pack.

The boundary remains observational:

```text
Current Recipe
      +
Decision Context Pack
      ↓
Delta Inspector
      ↓
facts about differences
      ↓
creator decides what they mean
```

MGAL does not compute which past Recipe the current sound is "closer to", does not rank Candidates, and does not mutate the current Recipe.

## Why this exists

M2.1 can answer:

> Which past blind-listening observations are relevant to this intent?

M2.2 adds:

> How is what I am making now structurally different from those past winner and loser Recipes?

For every returned observation MGAL shows two neutral comparisons:

```text
Current − Past winner
Current − Past loser
```

The direction is always explicit.

## Delta Inspector Pack 0.1

A saved Inspector Pack contains:

```text
delta_inspector_version = 0.1
delta_inspector_id
context_pack_id
decision_memory_sha256
query
current_recipe_document
current_recipe
inspection_count
inspections[]
usage
```

Authority boundary:

```json
{
  "usage": {
    "role": "observation_only",
    "selection_effect": "none",
    "mutation_effect": "none"
  }
}
```

Python validation and the Browser both enforce this boundary.

## Current Recipe summary

The current Recipe is validated with the normal MGAL Recipe contract and summarized as:

```text
recipe_id
recipe_sha256
intent
layer_count
total_gain
earliest_offset_ms
latest_offset_ms
normalize
fade_out_ms
source_ids[]
```

Current source files are hashed from the active audio root.

Source identity is content-based:

```text
sha256:<content hash>
```

So source overlap is based on identical bytes, not matching filenames.

## Neutral delta fields

For each past reference Recipe:

```text
direction = current_minus_reference
layer_count_delta
total_gain_delta
earliest_offset_ms_delta
latest_offset_ms_delta
fade_out_ms_delta
normalize_changed
shared_source_count
current_only_source_count
reference_only_source_count
```

Example:

```text
Current − past winner B

Δ layers          +1
Δ total gain      -0.15
Δ earliest offset +10 ms
Δ latest offset   +25 ms
Δ fade            -20 ms

sources
shared             1
current-only       1
reference-only     0
```

These values are measurements, not advice.

## No closeness score

M2.2 intentionally does not create:

```text
similarity_score
closer_to
recommended_candidate
candidate_ranking
preference_score
auto_select
apply_winner
```

It also does not color one reference as "better" or automatically copy settings from a past winner.

Past winner/loser labels are historical facts from the archived listening session, not instructions for the current Recipe.

## Browser workflow

After loading an M2.1 Context Pack:

```text
[ Load memory context ]
[ Download context pack ]

[ Inspect current deltas ]
[ Download delta inspector ]
```

The Browser sends:

```text
POST /api/decision-context-inspect
```

with:

```json
{
  "context_pack": { "...": "..." },
  "current_recipe": { "...": "..." }
}
```

The Python server:

1. validates the Context Pack
2. requires its Decision Memory fingerprint to still be current
3. validates the current Recipe
4. safely resolves every current source beneath the audio root
5. hashes current source bytes
6. builds the current Recipe summary
7. compares it separately with every past winner and loser summary
8. returns an observation-only Inspector Pack

## Browser display

The Inspector panel looks conceptually like:

```text
CURRENT RECIPE · OBSERVATION ONLY

Current current-slash
2 layers · total gain 1.3

metal-archive · pair 1

Current − past winner · candidate-b
Δ layers +1 · gain +0.4 · earliest -20ms
sources shared 1 / current-only 1 / reference-only 0

Current − past loser · candidate-a
Δ layers +1 · gain +0.7 · earliest +5ms
sources shared 0 / current-only 2 / reference-only 1
```

Both reference blocks use the same visual treatment.

There is no "winner-like" or "loser-like" verdict.

## Current Recipe staleness

Inspector results are tied to the exact current Recipe and current source bytes.

If the creator changes:

- active Candidate
- selected layers
- gain
- offset
- current Intent/Context

the Browser marks the existing Inspector stale and disables its download.

The creator must explicitly run **Inspect current deltas** again.

## Source drift

A saved Inspector Pack contains both:

```text
current_recipe_document
current_recipe.recipe_sha256
current_recipe.source_ids
```

Verification re-hashes the current source WAV files.

Therefore:

```text
Inspector generated
      ↓
current source file replaced
      ↓
same Recipe JSON
      ↓
Inspector verification fails
```

The comparison is bound to the bytes that were actually present.

## CLI

Build an Inspector Pack from a saved M2.1 Context Pack and Recipe:

```bash
mgal decision-context-inspect \
  ./context/heavy-metallic-slash.json \
  ./current-recipe.json \
  --audio-root ./audio \
  --output ./context/heavy-metallic-slash-delta.json
```

Verify it later:

```bash
mgal decision-context-inspect-verify \
  ./context/heavy-metallic-slash-delta.json \
  --audio-root ./audio
```

Verification rebuilds:

- current Decision Memory fingerprint
- deterministic Context retrieval
- current Recipe summary
- current source SHA-256 identities
- every winner/loser delta
- Inspector content-derived ID

and requires exact equality.

## Inspector identity

The Inspector gets:

```text
delta:<canonical payload SHA-256 prefix>
```

Changing any of these changes the ID:

- Decision Memory
- Context query/result
- current Recipe document
- current source content identity
- calculated deltas

## Relationship to M2.1

```text
M2.1 Context Pack
= which past observations are relevant?

M2.2 Delta Inspector
= how does the current Recipe differ from each of them?
```

Neither layer answers:

```text
What should I choose?
```

That remains a new listening decision.

## Current constraints

- Recipe comparison uses the small deterministic feature set already present in Decision Memory
- total gain is a structural sum, not psychoacoustic loudness
- source overlap is exact SHA-256 identity only
- no waveform similarity or embedding similarity
- no perceived-timbre distance
- no closeness score
- no automatic Recipe mutation
- no automatic copy-from-winner
- Inspector requires current source files to be available
- Browser uses the currently active Recipe/Candidate as Current
- stale Inspector Packs must be regenerated after Memory, Context, Recipe, or source changes

## Design principle

> Show the difference. Do not decide what the difference means.

M2.2 lets the creator compare the present with remembered listening evidence while keeping interpretation and action human.
