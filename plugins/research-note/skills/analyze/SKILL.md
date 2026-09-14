---
name: analyze
description: Use when an entry's jobs have completed — collect the results, write the Facts and the Conclusion into that entry, flip its Status to analyzed, and open the follow-up probe the conclusion calls for.
---

# research-note:analyze

Wrap up ONE **entry** on a page after its jobs finish. Run by the session that
submitted them — the owner, holding the recipe, the pre-registered criterion
and the reason the probe existed.

Arguments: the page (`<node>/<task>`) + the entry.

**J3 on your own entry is a prompt, not a fault.** It says the jobs went
terminal while the entry still reads `running` — which, if you are the owner
about to analyze them, is exactly the truth. Leave the Status alone, do the
analysis, and write Facts + Conclusion + `analyzed` in one go. (J3 on someone
ELSE's entry is READ-ONLY state: the write belongs to the owning session,
and picking up an orphan requires the user saying so — then read-first
(root contract) and take it the same way.)

## 1. Load

Read the page, the target entry, and the data and logs its `Jobs:` field
points at. Stop only if the entry is already `analyzed` or `closed`.

## 2. Write the Facts

**First answer one question, out loud, before writing anything: is the result a
NUMBER or a SHAPE?**

- **A number** — a value met a threshold, two routes agreed to 1e-9, a bound
  held. The table carries it whole. No figure is owed.
- **A shape** — how something moves along an axis: a convergence order, a
  scaling exponent, a saturation, a crossover, a growth with L. **Then the
  entry owes a figure, and you make it NOW** — run the folder's `plot_*.py`,
  or write one. A scan's curve IS its result.

Answer it before the table, because the answer decides what you are producing;
answered afterwards it is always "a number", since the table is already there.

Measured on the project this was written against: **71 entries, 71 tables,
ZERO figures** — while 46% of the Conclusions said "converges", "exponent",
"scales", "grows with L". Every one of those is a shape, argued in one
sentence, with nothing a reader can check. The guidance to add a figure was
already here, as a clause at the end of this paragraph, and it lost 71 times to
a table that was required. That is why this is a question now and not a clause.

**Now the Facts.** `We ran <the instance and how the jobs were laid out>
[script]; evidence <links>.` The sentence never announces what the table holds
— the table is required and speaks for itself. Then the table, at the
aggregation the Conclusion will cite; then the figure, if you owed one.

**Why now and not later:** `data/` is not committed. A rerun regenerates it,
and the numbers that made this shape are gone. The plot is cheap while the run
is on disk and impossible a month after.

**Every number matches its log — check it now, before `analyzed`.** This is
the writer's check; the linter can only verify the log is linked. A quoted
number carries the `[n]` of the entry that ran it, with its `Refs` row.

Modified a plot script here? `git add` it, and see the backfill rule below.

## 3. Write the Conclusion — the verdict is yours

You designed this probe and declared what would count. `The result shows <X>,
because <Y> — <verdict> the motivation.` One claim, one reason, one
verdict, and the sentence ENDS at the verdict (E15); the `because` states any premise a reader could object to, and the
detection floor when the evidence is a draw. Do not stop to ask what it means:
that judgement is the work.

A run that concluded nothing writes exactly that — `does not answer the
motivation`, its reason inside the `because` — and goes to `analyzed` like
any other. A result that
crosses the objective's budget: write the conclusion, then stop and ask.

`closed` is never yours. Writing a conclusion is "I measured, I judge";
closing is "I accept" — the user's.

## 4. Record it

Flip `Status:` to `analyzed`. The field shapes and the E7/E9 checks live in
`project_memory/CLAUDE.md` — the authority; this file does not restate it.

Then ask: **did this yield a transferable lesson?** If yes, one fact into
`project_memory/memory/shared/` (≤2–3 lines, a node/page ref). Results stay on
the page; only method travels.

Commit through the record bus, with the entry's trailer:

```
record_sync.sh -m "memory: <node>/<task> <id> analyzed — <verdict>

Entry: <id>" <page>
```

## 5. Then take the next step yourself

If the conclusion raises a question a new probe answers, **open a new entry on
the same page** — its Motivation naming this conclusion as source — and launch
it, after read-first (root contract): a follow-up is the easiest place in the
whole framework to re-derive a number the record already holds. A probe the verdict called for
gets its own entry, never a paragraph appended to the one you just concluded.
(A new *page* still needs `research-note:plan`; a new entry does not.)

**If the entry you concluded is on an objective's Plan, the follow-up joins
some plan in the same turn** (O6): the SAME phase when it serves that phase's
question, however late it was decided; a new phase with `needs: P<n>` when it
starts a new one. Then re-read the objective page — your result may have
changed what runs next.

## Rules

- **Interpret here, run in step 5.** Fresh numbers mean a fresh entry,
  launched through `research-note:hpc-submit`.
- **Correcting an existing conclusion** (a wrong reading, a script bug, an
  impl fault) is its own surgery — invoke `research-note:correct`.
- Every numeric claim quotes a value printed verbatim in a linked log.
- **Backfill on plot-script changes:** a modified plot script makes every
  figure it already produced stale. `grep` its output names under
  `project_memory/nodes/`, regenerate each, and land the lot in one follow-up
  commit.
