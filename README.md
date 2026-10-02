# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work into a reproducible creative loop:

**listen → remember → inspect → hypothesize → plan → materialize later**

## Current milestone: M2.4 Variation Brief → Candidate Plan Compiler

M2.4 converts a human-authored M2.3 Variation Brief into a deterministic experiment plan.

It still does **not** generate or mutate Recipes.

The flow is:

```text
Variation Brief
      ↓
Candidate Plan

A = Control
B = Hypothesis
C = Contrast
```

The plan answers:

> Which three experimental roles should we prepare next?

It does not yet answer:

> What exact Recipe JSON should each role use?

That is intentionally reserved for a later materialization milestone.

## Candidate Plan 0.1

Top-level fields:

```text
candidate_plan_version = 0.1
plan_id
variation_brief_id
basis
experiment
variants[]
unresolved_slots[]
ready_for_materialization
authority
```

Authority is fixed to:

```text
recipe_materialization = none
candidate_generation = none
candidate_selection = none
```

## A / B / C roles

### A · Control

A preserves the current Recipe conceptually.

```text
slot       A
role       control
resolution resolved
change     null
derivation preserve_current_recipe
```

M2.4 does not embed a generated control Recipe.

### B · Hypothesis

B carries the exact human-authored planned change from the Variation Brief.

```text
slot       B
role       hypothesis
resolution resolved
derivation human_variation_brief
change     <exact planned_change>
hypothesis <exact human hypothesis>
```

The compiler does not rewrite the human hypothesis.

### C · Contrast

C is only auto-resolved when the planned action has an unambiguous mechanical inverse:

```text
increase ↔ decrease
add      ↔ remove
```

The amount and unit are preserved.

Example:

```text
Brief:
gain decrease 0.10 ratio

C:
gain increase 0.10 ratio
```

The derivation is recorded as:

```text
deterministic_inverse_v1
```

## Manual contrast boundary

Actions such as:

```text
hold
replace
toggle
custom
```

do not have one universally correct experimental opposite.

MGAL does not invent one.

Instead:

```text
C
role       contrast
resolution manual_required
change     null
```

and:

```text
ready_for_materialization = false
unresolved_slots = ["C"]
```

This lets the plan expose uncertainty before Recipe generation begins.

## Experiment snapshot

The Plan carries:

```text
hypothesis
listening_for
planned_change
preserve[]
```

The B variant must exactly equal this planned change.

The C variant is recomputed from it during validation.

That means a hand-edited Plan cannot silently alter B or C semantics even if its content hash is recomputed.

## Content-addressed storage

Plans are stored at:

```text
audio/
└── .mgal/
    └── candidate-plans/
        └── <plan-hash>.json
```

Plan ID:

```text
plan:<canonical payload SHA-256 prefix>
```

Compiling the same Variation Brief again produces the same Plan and reuses the existing file.

## CLI

Compile:

```bash
mgal candidate-plan-compile \
  brief.json \
  --audio-root ./audio \
  --output plan.json
```

List:

```bash
mgal candidate-plan-list \
  --audio-root ./audio
```

Validate:

```bash
mgal candidate-plan-validate \
  plan.json
```

## Browser workflow

Saved Variation Brief cards now expose:

```text
[ Compile plan ]
```

After compilation:

```text
[ Plan ready ]
```

or, when C cannot be derived safely:

```text
[ Plan needs C input ]
```

The Candidate Plan shelf displays:

```text
A · control
resolved · no change

B · hypothesis
resolved · gain decrease 0.1 ratio

C · contrast
resolved · gain increase 0.1 ratio
```

or an explicit:

```text
C · contrast
manual_required · no change
```

No materialize/apply/select action exists in this milestone.

## HTTP API

```text
GET  /api/candidate-plans
POST /api/candidate-plans
```

POST accepts:

```json
{
  "brief_id": "brief:..."
}
```

The server loads the saved content-addressed Variation Brief, compiles the Plan, validates it, stores it, and returns the Plan plus storage result.

## Standalone validation

Candidate Plan validation checks:

- exactly three variants
- exact A-control / B-hypothesis / C-contrast order
- planned-change dimension/action/unit contract
- A has no change
- B equals the human planned change exactly
- C equals deterministic inverse when safe
- C remains manual_required when inversion is unsafe
- unresolved_slots matches unresolved variants
- ready_for_materialization matches unresolved state
- shared listening target is preserved
- content-derived Plan ID is correct
- no materialized Recipe or Candidate selection field exists

## Automatic-action prohibition

Candidate Plans reject fields such as:

```text
generated_recipe
materialized_recipe
selected_candidate_id
recommended_candidate
candidate_ranking
preference_score
auto_select
apply_winner
```

M2.4 therefore stops at a design document.

## M2.0 → M2.4

```text
M2.0 Decision Memory
What did I choose before?

M2.1 Context Pack
Which past choices matter now?

M2.2 Delta Inspector
How is the current Recipe different?

M2.3 Variation Brief
What do I want to try next?

M2.4 Candidate Plan
What experimental roles should we prepare?
```

The next step can finally materialize those roles into real Recipes while retaining this audit trail.

## Current constraints

- only three fixed slots: A/B/C
- C auto-contrast supports increase/decrease/add/remove only
- non-invertible C requires later human resolution
- Plan does not include materialized Recipe JSON
- Plan does not edit Candidate Board
- Plan does not select or rank Candidates
- no execution lifecycle yet
- no automatic materialization from Plan

## Design principle

> Plan the experiment before changing the artifact.

M2.4 creates a clean seam between human intention and future Recipe generation.
