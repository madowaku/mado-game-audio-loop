# MADO Game Audio Loop

MADO Game Audio Loop (MGAL) turns game SFX work into a reproducible creative loop:

**provide → intake → seed → blind audition → compare → decide → evidence → release**

## Current milestone: M1.5 Blind / Sequential Audition

M1.5 makes the Candidate Board usable as an ear-first comparison surface.

```text
A
↓
B
↓
C
↓
human decision
```

Blind mode hides source identity and Provider context during the first listen.

## Blind mode

Blind mode hides:

- source filenames and paths
- Provider / intake badges
- prompt and intent context
- Candidate source summaries
- Candidate lineage metadata
- structural delta text
- live mixer layer names
- intake session metadata

A/B/C labels remain visible. Decision controls remain visible.

Blind is audition-only state. It is never written into Candidate Board JSON, Recipe JSON, Evidence, or Release artifacts.

## Sequential audition

Use:

```text
▶ A→B→C
```

MGAL plays each Candidate once:

```text
A finishes
  ↓
350 ms gap
  ↓
B finishes
  ↓
350 ms gap
  ↓
C finishes
  ↓
stop
```

For layered Candidates, MGAL waits until all scheduled layers have ended before advancing.

Stopping playback cancels the sequence. Manual Candidate preview or previous/next navigation also cancels the running sequence.

## Candidate navigation

The audition toolbar includes:

```text
Blind: On/Off
▶ A→B→C
← Prev
Next →
A · 1/3
```

Previous/next navigation activates and immediately previews the target Candidate.

## Keyboard-first audition

When focus is not inside an input, textarea, select, or editable field:

```text
Space       replay active Candidate
← / →       previous / next Candidate + preview
F           toggle Favorite
X           toggle Reject
S           toggle Select
B           toggle Blind mode
Q           start / stop A→B→C sequence
Esc         stop audition
```

Keyboard shortcuts do not fire while writing a decision reason or editing Recipe controls.

## Decision integration

M1.5 does not introduce a second scoring system.

Keyboard actions call the same Candidate decision contract already used by buttons:

```text
undecided
favorite
reject
selected
```

At most one Candidate remains selected because the existing Candidate Board logic is reused.

## Playback safety

Audition playback uses a playback token so a stale completion callback from an older playback cannot advance a newer sequence.

Transient audition state is:

```text
blindMode
sequenceRunning
sequenceIndex
sequenceTimer
playbackToken
```

None of it enters Board persistence.

## M1.4 intake seed fits directly

A generated-audio loop can now be:

```text
Provider intake
     ↓
Seed A/B/C
     ↓
Blind: On
     ↓
Q
     ↓
A → B → C
     ↓
F / X / S
```

The creator can hear generated alternatives before looking at which file, seed, or Provider produced them.

## Existing workflow remains

Blind/Sequential works for both:

```text
Intake → Seed A/B/C
```

and:

```text
Add layers → Fork A/B/C
```

Layered Candidates can also be blind/sequentially auditioned.

## Current constraints

- sequential order is fixed to A → B → C
- inter-Candidate gap is fixed at 350 ms
- no randomized blind order yet
- A/B/C labels remain visible in Blind mode
- Candidate loudness is not automatically matched
- Blind mode is local UI state only
- keyboard shortcuts are browser-only
- no persisted audition-session analytics yet

## Design principle

> Hide the story of the sound long enough to hear the sound itself.

M1.5 turns the Candidate Board from a visual comparison tool into a fast listening instrument.
