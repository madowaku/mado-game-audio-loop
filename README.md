# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work into a reproducible creative loop:

**provide → intake → seed → randomized blind preference → decide → evidence → release**

## Current milestone: M1.6 Randomized Blind / Preference Session

M1.6 removes another comparison bias: the meaning of A/B/C itself.

A Preference Session temporarily remaps Candidates to random aliases:

```text
Candidate A ─┐
Candidate B ─┼─ random mapping → X / Y / Z
Candidate C ─┘
```

The mapping is hidden until Reveal.

## Randomized identity

When a session starts, MGAL:

1. takes up to three current Candidates
2. shuffles their mapping to X/Y/Z
3. generates every unique pair
4. shuffles pair order
5. randomly swaps left/right position inside each pair

Browser randomness comes from `window.crypto.getRandomValues()`.

For three Candidates, one session contains exactly three pairwise votes:

```text
X vs Y
X vs Z
Y vs Z
```

The order and left/right presentation are randomized per session.

## Pairwise preference

The Preference panel shows only random aliases before Reveal.

```text
Which sound do you prefer?

X                 Y
[ Play X ]   vs   [ Play Y ]
[ Prefer X ]      [ Prefer Y ]
```

Keyboard shortcuts during an unrevealed session:

```text
1           play left alias
2           play right alias
←           prefer left alias
→           prefer right alias
R           reveal, but only after all pairs are voted
P           close Preference Session
Esc         stop current audio
```

Normal Candidate navigation shortcuts are intercepted during pairwise voting so arrow keys cannot accidentally reveal or navigate the underlying Board.

## Identity sealing

Before Reveal, the UI hides:

- original A/B/C identity
- source filenames/paths
- Provider/intake/prompt context
- Candidate lineage and structural delta
- previous Favorite/Reject/Selected badges
- Edit and Copy controls
- decision controls and reason text

The Candidate cards themselves are rendered in randomized X/Y/Z order.

Reveal-before-completion is not allowed.

Board and Recipe download are disabled before Reveal so the user cannot accidentally inspect the underlying Candidate IDs or source paths through exported JSON.

Blind mode cannot be turned off during the hidden phase.

Normal A→B→C sequence and Prev/Next navigation are also disabled until Reveal.

## Reveal

After every pair is voted, Reveal becomes available.

MGAL shows:

```text
X = Candidate B · 2 wins
Y = Candidate A · 1 win
Z = Candidate C · 0 wins
```

The original Candidate labels and normal Board controls return.

## Preference winner

Scores are simple pairwise win counts.

For three Candidates:

```text
2 wins / 1 win / 0 wins → single winner
1 win / 1 win / 1 win → tie
```

A tie never applies a Candidate decision automatically.

Even with a single winner, MGAL still does not change the Board until the user presses:

```text
Apply winner
```

Only then is the winning Candidate assigned the existing durable decision:

```text
selected
```

No new score/rating field is added to Candidate Board 0.1.

## Persistence boundary

Preference Session state is intentionally transient:

```text
X/Y/Z mapping
pair order
left/right order
votes
win counts
Reveal state
```

None of those fields enter Candidate Board JSON.

If the user closes the Preference Session without Apply winner, the durable Candidate Board remains unchanged.

If Apply winner is pressed, only the normal `selected` decision changes.

## Relationship to M1.5

M1.5 Blind mode hides source context while preserving A/B/C labels.

M1.6 Preference mode goes further:

```text
M1.5
A / B / C known
source identity hidden

M1.6
A / B / C mapping hidden
source identity hidden
pair order randomized
left/right order randomized
```

Both modes work with Intake-seeded Candidates and manually-forked layered Candidates.

## Current constraints

- Preference Session uses at most three Candidates
- all pairwise comparisons are one vote each
- win count is unweighted
- no undo/back button for a submitted pair vote yet
- session mapping and votes are lost on page reload
- no Preference Session JSON export yet
- no loudness matching yet
- no automatic statistical significance claim is made

## Design principle

> Randomize what the ear should not know. Persist only what the creator deliberately decides.

M1.6 turns blind audition into an explicit pairwise preference experiment without changing MGAL's evidence-bearing Candidate Board contract.
