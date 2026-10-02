# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work into a reproducible creative loop:

**listen → remember → inspect → hypothesize → plan → materialize → audition next**

## Current milestone: M2.5 Candidate Plan → Recipe Variation Materializer

M2.5 is the first M2.x milestone that creates real Recipe JSON from a human-authored experiment chain.

The flow is:

```text
M2.3 Variation Brief
        ↓
M2.4 Candidate Plan
        ↓
M2.5 Materialized Recipe Set

A = Control Recipe
B = Hypothesis Recipe
C = Contrast Recipe
```

The generated Recipes are saved for inspection only.

M2.5 does **not** mutate Candidate Board state, select a Candidate, or run a preference session.

## Materialized Recipe Set 0.1

A set contains:

```text
materialized_recipe_set_version = 0.1
materialization_id
materialization_semantics
candidate_plan
source_recipe
source_recipe_summary
experiment
variants[]
authority
```

Authority is fixed to:

```text
candidate_board_mutation = none
candidate_selection = none
source_generation = none
```

The Candidate Plan snapshot is embedded so the output remains self-describing.

## Materialization semantics

Current semantics ID:

```text
whole-recipe-scalar-v1
```

M2.5 intentionally supports only scalar changes that can be applied without inventing a target layer or source choice.

Supported dimensions:

```text
gain
offset
fade
```

Supported actions:

```text
increase
decrease
```

### Gain

Gain changes apply additively to every layer.

Example:

```text
Current
layer 1 gain 0.8
layer 2 gain 0.4

B plan
gain decrease 0.1 ratio

B materialized
0.7
0.3

C materialized
0.9
0.5
```

Scope:

```text
all_layers
```

### Offset

Offset changes apply the same integer millisecond delta to every layer.

A change that would create a negative offset is rejected instead of clamped.

### Fade

Fade changes apply to:

```text
processing.fade_out_ms
```

A negative result is rejected.

## Unsupported dimensions

A Candidate Plan may be structurally complete while M2.5 still cannot materialize it safely.

For example:

```text
layers add/remove
sources
other
```

need a target-selection contract that M2.5 does not yet have.

The Browser therefore shows:

```text
Materializer unsupported
```

instead of guessing which layer/source to add, remove, or replace.

## Source Recipe binding

Materialization receives a concrete current Recipe.

Before creating A/B/C, MGAL fingerprints it using the same M2.2 summary contract:

```text
recipe_sha256
layer_count
total_gain
earliest_offset_ms
latest_offset_ms
normalize
fade_out_ms
source_ids[]
```

Every source file is SHA-256 checked beneath the supplied audio root.

The resulting summary must exactly equal:

```text
Candidate Plan
  basis
    current_recipe
```

Therefore an old Plan cannot silently be applied to a different current Recipe.

## A / B / C output

### A · Control

A copies the source Recipe exactly except for a deterministic materialized Recipe ID.

No experiment change is applied.

### B · Hypothesis

B applies the exact M2.4 hypothesis change using `whole-recipe-scalar-v1`.

### C · Contrast

C applies the exact deterministic contrast change recorded in the Candidate Plan.

M2.5 never derives a new contrast itself. It materializes the already validated Plan.

## Recipe identities

Each Recipe receives a deterministic ID derived from:

- source Recipe ID
- Candidate Plan ID
- A/B/C slot

Each variant also stores:

```text
recipe_sha256
application
recipe
```

Application records:

```text
semantics
scope
dimension
action
amount
unit
```

## Workspace storage

Materializations are stored at:

```text
audio/
└── .mgal/
    └── materialized-recipe-sets/
        └── <materialization-hash>/
            ├── set.json
            ├── A-control.json
            ├── B-hypothesis.json
            └── C-contrast.json
```

ID form:

```text
materialized:<canonical payload SHA-256 prefix>
```

Saving the same materialization again is idempotent.

The split A/B/C Recipe files are verified against `set.json`; missing or modified split files invalidate the workspace materialization.

## Semantic validation

Validation independently recomputes A/B/C from:

```text
embedded Candidate Plan
+
embedded source Recipe
```

It checks:

- Candidate Plan validity
- Plan materialization readiness
- source Recipe validity
- source Recipe SHA binding
- full source Recipe summary equality with Plan basis
- experiment snapshot equality
- exact A/B/C transformation
- individual Recipe SHA-256
- authority boundary
- content-derived materialization ID

Rehashing a manually edited B Recipe does not make it valid because the expected Recipe is recomputed from the Plan.

## Source drift verification

```bash
mgal materialized-recipe-verify set.json \
  --audio-root ./audio
```

re-hashes the current source WAVs.

If a source file changed after materialization:

```text
same Recipe JSON
+
different source bytes
=
verification failure
```

## CLI

Materialize:

```bash
mgal candidate-plan-materialize \
  plan.json \
  current-recipe.json \
  --audio-root ./audio \
  --output recipe-set.json
```

List workspace sets:

```bash
mgal materialized-recipe-list \
  --audio-root ./audio
```

Verify:

```bash
mgal materialized-recipe-verify \
  recipe-set.json \
  --audio-root ./audio
```

The workspace split Recipe files are always written even when `--output` is used for an additional JSON copy.

## Browser workflow

Ready Candidate Plans now expose:

```text
[ Materialize recipes ]
```

After successful materialization:

```text
[ Recipes ready ]
```

The Materialized Recipe shelf displays:

```text
A · control · <recipe-id>
control · unchanged

B · hypothesis · <recipe-id>
all_layers · gain decrease 0.1 ratio

C · contrast · <recipe-id>
all_layers · gain increase 0.1 ratio
```

The Browser posts:

```text
POST /api/materialized-recipe-sets
```

with:

```text
plan_id
current_recipe
```

The server loads the saved Candidate Plan by content-addressed ID and rejects a current Recipe that no longer matches the Plan basis.

## HTTP API

```text
GET  /api/materialized-recipe-sets
POST /api/materialized-recipe-sets
```

GET lists valid workspace materializations.

POST materializes one saved Plan against the current Recipe.

## Candidate Board boundary

M2.5 creates Recipe artifacts but deliberately stops before audition integration.

It does not call or store:

```text
selected_candidate_id
candidate decision
Candidate Board mutation
Apply winner
Auto select
```

The Browser Materialize action does not alter `state.candidates`.

This keeps the next transition explicit:

```text
Materialized Recipe Set
        ↓
future audition bridge
        ↓
Candidate Board / Blind Preference
```

## M2.0 → M2.5

```text
M2.0 Decision Memory
What did I choose before?

M2.1 Context Pack
Which past observations matter now?

M2.2 Delta Inspector
How is the current Recipe different?

M2.3 Variation Brief
What do I want to try?

M2.4 Candidate Plan
What roles should the experiment contain?

M2.5 Recipe Materializer
What exact Recipe JSON represents each role?
```

## Current constraints

- scalar materializer supports gain/offset/fade only
- increase/decrease only
- gain is additive across all layers
- offset change applies to all layers
- fade is processing-level
- layer/source targeting is not implemented yet
- no automatic clamping for invalid negative offset/fade
- no Candidate Board import yet
- no audition directly from the Materialized Recipe shelf yet
- preserve[] remains historical human text, not an executable constraint
- no automatic Candidate selection or preference result

## Design principle

> Materialize only what the Plan states unambiguously.

M2.5 turns human experiment intent into exact Recipe artifacts while preserving the boundary before listening and selection.
