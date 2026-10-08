---
name: analyze
description: Use when an entry's jobs have finished — write its Facts and Conclusion, flip it to analyzed, and open the follow-up its verdict calls for.
---

# research-note:analyze

Wrap up ONE entry after its jobs finish, as the session that submitted them —
the owner holds the recipe, the pre-registered criterion and the reason the
probe existed. Field shapes and the E-codes: `project_memory/CLAUDE.md`.

Arguments: the page (`<node>/<task>`) + the entry.

**J3 on your own entry is a prompt, not a fault**: the jobs went terminal while
the entry still reads `running`, which is exactly the truth while you analyze
them. Leave the Status alone and write Facts + Conclusion + `analyzed` in one
go. J3 on someone ELSE's entry is read-only — the write belongs to the owning
session; picking up an orphan needs the user's say-so, then read-first (root
contract) and the same steps.

## 1. Load

Read the page, the entry, and the data and logs its `Jobs:` field points at —
done when every log the field names has been opened. An entry already
`analyzed` or `closed` ends the skill here.

## 2. Write the Facts

**Ask first, out loud: is the result a NUMBER or a SHAPE?**

- **A number** — a value met a threshold, two routes agreed to 1e-9, a bound
  held. The table carries it whole; no figure is owed.
- **A shape** — how something moves along an axis: a convergence order, a
  scaling exponent, a saturation, a crossover, growth with L. **The entry owes
  a figure, made NOW** — run the folder's `plot_*.py`, or write one. A scan's
  curve IS its result.

Asked after the table exists, the answer is always "a number": on the project
this was written against, 71 entries carried 71 tables and zero figures while
46% of their Conclusions said "converges", "exponent", "scales", "grows with
L". And `data/` is not committed — a rerun regenerates it; the plot is cheap
while the run is on disk and impossible a month later.

Then the Facts in the record contract's shape: the sentence (instance, job
layout, script, evidence links), the table at the aggregation the Conclusion
will cite, the figure if owed. **Every number matches its log — the writer's
check, before `analyzed`;** a quoted number carries the `[n]` of the entry
that ran it, with its `Refs` row.

Modified a plot script? `git add` it, and see the backfill rule below.

## 3. Write the Conclusion — the verdict is yours

State the answer to the Motivation, its evidence, and the limits on the claim.
Keep the conclusion concise; wording and sentence order are flexible. Include
any premise a reader could dispute and the detection floor when the evidence
is a draw. A run with no answer explains why and still goes to `analyzed`.
A run with no measurements uses the record contract's `Measurements: none`
exception with a reason and evidence, rather than an empty results table.
A result that crosses the objective's budget: write the conclusion, then stop
and ask.

`closed` is the user's (root contract, "Stop and ask").

## 4. Record it

Flip `Status:` to `analyzed`. Then ask: **did this yield a transferable
lesson?** If yes, one fact into `project_memory/memory/shared/` (2–3 lines, a
node/page ref). Results stay on the page; only method travels.

Commit through the record bus, with the entry's trailer:

```
record_sync.sh -m "memory: <node>/<task> <id> analyzed — <verdict>

Entry: <id>" <page>
```

## 5. Take the next step yourself

A question the conclusion raises that a new probe answers gets **a new entry
on the same page** — its Motivation naming this conclusion as source —
launched after read-first (root contract): a follow-up is the easiest place in
the framework to re-derive a number the record already holds. A new *page*
still needs `research-note:plan`; a new entry does not.

**On an objective's Plan, the follow-up joins some plan in the same turn**
(O6): the SAME phase when it serves that phase's question, however late it was
decided; a new phase with `needs: P<n>` when it starts a new one. Then re-read
the objective page — your result may have changed what runs next.

## Rules

- **Interpret here, run in step 5.** Fresh numbers mean a fresh entry,
  launched through `research-note:hpc-submit`.
- **Correcting an existing conclusion** (a wrong reading, a script bug, an
  impl fault) is `research-note:correct`.
- Every numeric claim quotes a value printed verbatim in a linked log.
- **Backfill on plot-script changes:** a modified plot script makes every
  figure it produced stale. `grep` its output names under
  `project_memory/nodes/`, regenerate each, and land the lot in one follow-up
  commit.
