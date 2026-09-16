---
name: correct
description: Use when a recorded result is contested — a conclusion read wrong, a suspected or confirmed script bug, or an impl fault. Classifies the tier, moves the descriptions now known wrong, walks the cascade and the owning phases, and ends with both linters green.
---

# research-note:correct

The user says what is wrong in physics terms ("this 0.45 looks like a
zero-point mix-up"); this skill turns that into the record surgery the
correction doctrine (`project_memory/CLAUDE.md`, "Corrections") prescribes.
The doctrine is the WHAT; this is the order of operations, because the surgery
spans several pages.

Arguments: the contested entry (or phase) + what the review found.

## 0. Read before cutting

Read-first (root contract), then: the contested entry, its logs' headers
(SHA, dirty diff), the scripts they name, and every phase that links the
entry. A suspicion rather than a finding: settle what CAN be settled without
compute — code reading is free and a code fact is decisive.

## 1. Classify the tier

| The problem is… | Tier |
|---|---|
| the reading of correct numbers | **misread** |
| not yet established | **suspicion** |
| a bug in the run/diagnostic script | **script bug** |
| a bug in the node's impl | **impl fault** |

Unsure between script and impl → the node identity criterion decides (root
contract): can any knob setting on the fixed code reproduce the recorded
number? Yes → the node stands and the edit owes a validation entry; no → the
fix is a new node. Still unsure → ask; once entries close on a new node the
split is permanent.

## 2. Execute the tier

- **misread** — rewrite the Conclusion in place. Nothing else moves.
- **suspicion** — open diagnostic entries; they JOIN the contested phase (a
  bug hunt contests an answer, it does not open a question). Re-enter at
  step 1 with their conclusions.
- **script bug** — the entry keeps its numbers (they are what happened) and
  its Conclusion is rewritten to what the run actually measured ("artifact of
  bug B in `<script>`"). Fix the code; the re-run is a NEW entry whose
  Motivation names this entry and the fixing commit. Launch via hpc-submit.
- **impl fault** — a node event, not a correction: the fixed code is a new
  node (`research-note:plan`), whose gate's Motivation names the node it
  supersedes — the old node is never edited, and it keeps standing under the
  entries that closed on it.

## 3. Walk the cascade — yours, same turn

You hold the context; nobody else can do this correctly later.

1. **Every description that leaned on the changed datum moves**: grep
   `project_memory/nodes/` for links to the corrected entry's anchor and for
   its id. For each: Facts stay; a conclusion whose `because` cited the old
   claim is rewritten, and a `closed` one returns to `analyzed`; a Motivation
   that QUOTES the datum has its quote corrected while its QUESTION stands
   (E5) — where the corrected number makes the question pointless, the
   Conclusion's verdict and `because` say so. Re-run a descendant only if its
   own numbers consumed the contaminated output.
2. **Update every owning phase**: the ▶ reading is rewritten where it stood on
   the moved conclusion (O7); the correction's own entries join their phase
   (O6).
3. **Recount the Verdict's awaiting-review count** (O8) — your restatements
   changed it.

## 4. Commit and verify

Every page through the record bus. The correction is its own commit, trailered
`Correct: <id>` — `git log --grep='Correct:'` is the project's list of
reversals; cascade edits on other entries carry their own `Entry: <id>`.

**Done = both linters green** over the touched pages and objectives —
`check_node_page.py --cross` and `check_objective_page.py`. The O6/O7/O8
fires along the way are the checklist; a remaining one is a step you skipped.

## Rules

- Numbers never change; descriptions move — this entry's, and every one whose
  own description leaned on the same mistake. Nothing else.
- Not the owner of the numbers? Trace, never invent: where the links run out,
  write the named hole, not a plausible bridge.
