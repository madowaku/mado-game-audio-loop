# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work into a reproducible creative loop:

**listen → compare → remember → inspect → hypothesize → vary deliberately**

## Current milestone: M2.3 Human Hypothesis / Variation Brief

M2.3 introduces the boundary between observation and the next experiment.

M2.2 can show:

```text
Current Recipe
vs
Past winner
vs
Past loser
```

M2.3 does not decide what to do with those differences.

Instead, the creator explicitly writes a hypothesis:

```text
Observation
    ↓
Human hypothesis
    ↓
Variation Brief
    ↓
future experiment
```

No Recipe is generated or mutated at this milestone.

## Variation Brief 0.1

A Variation Brief contains:

```text
variation_brief_version = 0.1
brief_id

basis
  delta_inspector_id
  context_pack_id
  decision_memory_sha256
  query
  current_recipe
  reference

human_input
  authorship = human_explicit
  hypothesis
  listening_for
  planned_change
  preserve[]

authority
```

Authority is fixed to:

```json
{
  "recipe_mutation": "none",
  "candidate_selection": "none",
  "candidate_generation": "none"
}
```

The Brief is an experiment plan, not an executable mutation.

## Human authorship

MGAL does not infer or auto-write the hypothesis from Delta Inspector values.

The creator must supply:

- a non-empty hypothesis
- a non-empty listening target
- one planned change
- optional conditions to preserve
- optional Inspector reference

Example:

```text
Hypothesis:
Reducing gain may leave more room for the transient.

Listen for:
A clearer attack without losing metallic weight.

Planned change:
gain
decrease
0.10 ratio

Preserve:
source set
layer count
```

## Planned change contract

Supported dimensions:

```text
layers
gain
offset
fade
normalize
sources
other
```

Supported actions:

```text
increase
decrease
hold
add
remove
replace
toggle
custom
```

Optional amount/unit validation includes:

```text
gain   → ratio
offset → ms
fade   → ms
layers → count
```

This records intended experimental direction only.

M2.3 does not apply the change.

## Inspector reference

A Brief may be general:

```text
reference = null
```

or explicitly point to one comparison in the current Delta Inspector:

```text
entry_id
role = past_winner | past_loser
```

When a reference is selected, the Brief freezes:

- archive ID
- source intent
- pair index
- candidate ID
- referenced Recipe summary
- Current-minus-reference delta

The reference must exist inside the supplied Inspector Pack.

A fabricated entry ID is rejected.

## Historical behavior

Delta Inspector is a live observation surface and may become stale as Current Recipe or Context changes.

Variation Brief has a different role.

Once saved, it records:

> At this exact observation point, this is what the creator wanted to try next.

Therefore a saved Brief does not become invalid merely because the current Recipe later changes.

Its content-derived ID binds it to the historical basis and human input.

## Content-addressed storage

Briefs are stored at:

```text
audio/
└── .mgal/
    └── variation-briefs/
        └── <brief-hash>.json
```

ID form:

```text
brief:<canonical payload SHA-256 prefix>
```

Saving identical content again is idempotent.

The same Brief is reused rather than duplicated.

## Browser workflow

After a fresh M2.2 Delta Inspector exists, the Browser enables:

```text
HUMAN HYPOTHESIS
Variation Brief
```

The creator can choose:

- General current Recipe
- one past winner
- one past loser

and enter:

```text
Hypothesis
Listen for
Dimension
Action
Amount
Unit
Change note
Preserve
```

Then:

```text
[ Save Variation Brief ]
```

The Browser sends:

```text
POST /api/variation-briefs
```

with the current Inspector and explicit human input.

The Browser independently rejects a response unless:

```text
human_input.authorship == human_explicit
recipe_mutation == none
candidate_selection == none
candidate_generation == none
```

## Saved Brief shelf

The Browser loads:

```text
GET /api/variation-briefs
```

and shows stored hypotheses with their planned dimension/action and optional reference role.

The list is historical. Saving a Brief does not change the current Recipe.

## CLI

Create a Brief from a saved Inspector Pack and a human-input JSON file:

```bash
mgal variation-brief-create \
  inspector.json \
  human-input.json \
  --audio-root ./audio \
  --output brief.json
```

Example human-input file:

```json
{
  "hypothesis": "Reducing gain may improve attack clarity.",
  "listening_for": "A sharper transient without losing body.",
  "planned_change": {
    "dimension": "gain",
    "action": "decrease",
    "amount": 0.1,
    "unit": "ratio",
    "note": "Change gain only."
  },
  "preserve": [
    "source set",
    "layer count"
  ],
  "reference": {
    "entry_id": "decision:...",
    "role": "past_winner"
  }
}
```

List workspace Briefs:

```bash
mgal variation-brief-list \
  --audio-root ./audio
```

Validate a Brief:

```bash
mgal variation-brief-validate   brief.json
```

## Automatic-action prohibition

Variation Brief validation rejects fields such as:

```text
generated_recipe
recommended_candidate
auto_select
candidate_ranking
preference_score
similarity_score
apply_winner
```

M2.3 also intentionally has no:

```text
Apply variation
Generate Candidate
Copy past winner
Auto-edit Recipe
```

Those would cross into a later execution milestone.

## M2.0 → M2.3

```text
M2.0
Decision Memory
"What did I choose before?"

M2.1
Context Pack
"Which past choices are relevant now?"

M2.2
Delta Inspector
"How is the current Recipe different?"

M2.3
Variation Brief
"What do I, the human, want to try next?"
```

This creates a clean seam between evidence and action.

## Current constraints

- one planned change object per Brief
- preserve conditions are human-authored text labels
- no generated Candidate or Recipe
- no automatic interpretation of Inspector deltas
- no LLM-written hypothesis
- no executable patch plan yet
- no Brief status lifecycle such as planned/running/completed yet
- Brief storage is local JSON
- Briefs are content-addressed but not cryptographically signed

## Design principle

> Observation can suggest a question. Only the creator turns it into an experiment.

M2.3 gives that experiment a durable, explicit contract without handing execution authority to the system.
