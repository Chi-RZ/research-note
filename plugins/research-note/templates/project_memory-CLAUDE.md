# project_memory — the record

Record format: v3

The root contract says what a node, a page and an entry ARE, and when to open
each. This file is the format: the exact fields, the exact shapes. The linters
(`check_node_page.py`, `check_objective_page.py`) are the final word on all of
it — the edit hook runs them on every page you touch; keep pages green. The
version line above is checked against the linter and `framework.json` (FW).
Page templates — an entry page, a node.md, an objective page — sit in
`.claude/examples/`; fill their slots.

## Layout

```
project_memory/
├── _index.md              the node + entry + objective roster — regenerated (gen_index.py), never hand-edited
├── nodes/<node>/
│   ├── node.md            the gate first, then one validation per in-place edit
│   ├── <page>.md          a task page at node level
│   └── <group>/<page>.md  the task pages of one instance
├── objectives/<slug>.md   one per goal — the route's interface
├── note/<node>.md         understanding, prose — the user's, or written after
│                          discussing it with them; NEVER agent-initiated, and
│                          never a home for what did not fit somewhere else
├── memory/shared/         shared agent memory, one fact per file + MEMORY.md
├── memory/claude -> shared  compatibility view for Claude Code
├── memory/codex -> shared   compatibility view for Codex
└── _archive/              superseded record, kept verbatim for provenance
```

A comparison belongs to the node at its centre, as a page under it. Its entries
run only that node; a rival needing its own run gets an entry on its own page,
cited here by id.

## The entry

```
### Entry: <what is run, on which instance>
- **Id:** <nn>.<mmm>
- **Status:** open | running | analyzed | closed
- **Date:** YYYY-MM-DD HH:MM
- **Jobs:** <id>@<host>, ...
- **Code:** `<repo>@<sha>` · `<domain lib>@<sha>`
- **Motivation:** <source> found <the fact, quoted>; <the question, one sentence>?
- **Recipe:** {<knob>: <value>, ...}
- **Facts:** We ran <the instance and how the jobs were laid out> [script];
  evidence <links>.

  | the table — required, at the aggregation the Conclusion cites |

  ![the figure, where the shape carries what the numbers do not](...)
  *caption: axes, units, what each series is*

- **Conclusion:** The result shows <X>, because <Y> — <verdict> the motivation.
- **Refs:**
  `[1]` → [entry name](page.md#entry-slug) `<id>` — <the rows it supplies>
```

Header fields are `- **Key:** value`, one spelling only (E10). Field rules:

- **Id** (E1): node number from `_index.md`, then a per-node sequence in `Date`
  order. Both zero-padded, assigned at creation, never reused.
- **Status** (E2): the four states, nothing else. **Date** (E3): creation,
  never changes.
- **Code** (E4): the newest commit at submission touching `src/`, the node's
  `impl/` and the env's run script — one `<repo>@<sha>` per repo. Excludes
  `plot_*.py` and `figures/`.
- **Motivation** (E5): the source is checkable without agreeing with an
  interpretation — a prior entry, a code path at a commit, an absence in the
  record, a directive. The fact is quoted inline; the link is optional. No
  evaluative words in the fact. Never a link into `objectives/`. **It ends in
  ONE question, and the question is answerable by a number THIS run's Recipe
  produces** — a reason for running is not a question, and a field that asks
  nothing cannot decide what the Conclusion may contain, which is how a
  Conclusion grows four parallel claims. The question never changes — another
  question is another entry, including a control decided after seeing this
  result.
- **Recipe** (E6): every knob this run assigned — a map, never prose. An entry
  with jobs records one.
- **Facts** (E7, E8): no interpretation; never a restatement of `Code`, of
  `Recipe`, or of the table. The table is required, so the sentence does not
  announce what it holds — the sentence carries the instance, the job layout,
  the script and the evidence links, and prose after the table carries only
  what the table cannot: a wall time, an exit status, the provenance of a job
  id. Every number matches its log — the writer's check before `analyzed`. A mean, ratio or spread stands beside the values it was computed
  from, here or one `Refs` hop away. Unmarked means this entry produced it; a
  quoted number carries the `[n]` of the entry that RAN it, and every `[n]`
  has a `Refs` row. Grows only toward more complete or more accurate.
- **Conclusion** (E9): one claim, one reason, one verdict — `answers` /
  `partly answers` / `does not answer` the motivation, and the sentence ends
  there: what a `partly` leaves un-run is the Facts' to state and the
  `because`'s to bound, and a `does not answer`'s reason is part of its
  `because`. **One SENTENCE with three slots, not
  three bullets**: the Conclusion IS the entry's interpretation, so what belongs
  in it is whatever bears on the Motivation's question — and an observation that
  answers a question the Motivation did not ask goes to `Facts` if it is a
  measurement, or to its own entry if answering it needs a run. The `because`
  states any premise a reader could object to — the yardstick, the baseline,
  the assumed comparability, whatever a skeptic would deny first — and the
  detection floor when the evidence is a draw. Rewritten freely; git holds the
  previous version.
- **One computation script per entry** (E11). A probe that exists only because
  another's result exists is a different entry.
- **An entry is its fields and nothing else** (E12). Every line either opens a
  field or is indented under the one it continues — the table, the figure, the
  job's log link, a long field's line-wrap. A paragraph left between the fields
  reads as an entry whose Facts are missing, because a reader and every check
  here look for content under the key that owns it. E12 binds at every status,
  like E10 and unlike E4-E9: those judge what a field SAYS and stop at the
  user's ✓, while this one judges only WHERE a line sits.
- **Evidence and interpretation each stay in their field** (E13, E14, E15).
  `Facts:` holds no standalone `Job <id> — [log](…)` stanza — a log link
  belongs in the sentence's `evidence <links>` clause, or rides `- **Jobs:**`
  as an indented continuation (which is what `record_submit` writes). The
  `Conclusion:` carries no link — an artifact is `Facts:`'s, a borrowed entry
  a `Refs:` `[n]` — and it ENDS at its verdict: what follows the verdict is a
  `because`'s to hold, a Fact's to state, or its own entry's to answer.
  Placement checks like E10/E12 — they bind at every status, `closed` included.
- **A cited SHA is retrievable** (E16). `Code:`'s claim is only as good as
  the commit it names: for THIS repo the SHA must have LANDED — be an
  ancestor of the default branch — because a worktree branch's SHAs are
  provisional (a rebase rewrites them, an abandoned branch takes them with
  it); for a pinned lib it degrades to "the SHA uv.lock pins", which a clone
  can always fetch. Record the SHA at submission from main, not from a
  branch that has not landed yet.
- **Links are repo-relative**, never `file://` (P2, P3). A figure carries a
  caption and is embedded once (P4).

## node.md

The same frontmatter as any page (`node:` = the folder, `task:`). Entries
only. The first is
the **gate**: the node reproducing a reference its Motivation names — the
parent cell it forks from, or whatever independent number exists. The same
Motivation names the node it supersedes, when there is one; the old node is
never edited. Every later entry is a **validation** of an in-place edit: its
Motivation links the entry it replays (V1), its Recipe and Facts carry the
recipe and the number it reproduced.

## Corrections

**The record describes what happened. When the two disagree, the description
moves.** Numbers never change; descriptions do — this entry's, and, elsewhere,
two things the same grep finds: every conclusion whose `because` cited the
changed datum, which returns from `closed` to `analyzed` the same turn, and
every Motivation that QUOTES it, whose quote is corrected while its question
stands. An entry is never withdrawn and never
deleted. A correction is its own commit, trailered `Correct: <id>`.

## Lifecycle

| | |
|---|---|
| `open` | created, not launched |
| `running` | jobs in the queue — **and analysis in progress**, deliberately the same state: both mean someone is on it |
| `analyzed` | concluded, awaiting review. A definitive negative counts |
| `closed` | user-reviewed, terminal |

Only the user closes. Approval cascades: a ✓ at objective or task granularity
closes every analyzed entry that step references.

**An interruption is not a state.** The Motivation keeps the question as asked,
the Facts say how far the run actually got and why it stopped, and the verdict
is honest about the difference — `partly answers`, or `does not answer`, with
the reason in the `because`. Before `closed`, resuming the same procedure
rejoins the entry: one more id on `Jobs:`, status back to `running`. After
`closed`, any continuation is the NEXT entry, citing the closed one —
expecting to continue is a reason not to close yet.

## Jobs

**A launch names the phase it serves.** `PHASE=P<n>` and `ROLE="<what this
entry does for it>"` on the launcher; `record_submit` writes the Plan line
itself, in the same lock as the job row, and the pre-flight REFUSES to launch
without them (`NO_OBJECTIVE=1` for a run that serves none). The line used to be
left to a later turn, and a job that runs for hours reliably swallows it — the
phase then shows nothing under it, and an objective-scoped watcher cannot see
the entry at all.

Every submission, the same turn: the id onto the owning entry's `Jobs:` field
(ranges allowed, `63902601–04`; host tags, `@t6`), and the log's repo-relative
link into the entry. Link the log the instant it exists. A job belongs to its
entry; there is no page-level table (P5). An empty `- **Jobs:**` is never
silent: a `running` entry with no ids — or a linked launcher log with none —
is J5, and an id the Facts name — or a `Job <id> —` line anywhere — missing
from the field is J6, because the field is what every watcher, waiter and
board reads. (Motivation and Refs quote OTHER entries' ids as provenance;
those belong exactly where they are.)

The launching session watches its own jobs — at most one watcher per
objective, scopes disjoint, never one per job — and analyses them in-session. The fixer scans and raises `attention:`; it
repairs nothing.

## Commits

A `nodes/` commit carries an `Entry: <id>` trailer (a correction:
`Correct: <id>`); an `objectives/` commit carries `Objective: O<nn>`; one
commit never stages both — a route change is its own commit.
`git log --grep=<id>` is that thing's whole history.

## The objective page

Frontmatter: `id: O<nn>` first — the next free number, read off
`_index.md`'s Objectives section; unique across `objectives/` (O12) — then
`status: active | closed`, `created`,
`budget`, `wake-me-if`, and `attention: <what stopped the loop>` present only
while the loop is stopped. The user sets `budget` and `wake-me-if` freely; the
loop sets and clears `attention`; the user closes `status`.

Three sections, in order, nothing else (O2):

- **`## Goal`** — the question and what would count as answering it. The
  user's, byte-immutable after intake (O4).
- **`## Plan`** — one block per phase:

```
- [ ] **P<n> — <the question this phase asks>** (<cost>[ · needs: P<i>])
  - [entry name](page.md#entry-slug) `<id>` — <the role it plays in answering it> (<date>)
  - ▶ <what this settles for the Goal> one sentence
```

  **The box flips when every entry under the phase has concluded (O13)** —
  and it is the step that gets skipped, because unlike the ▶ line it carries no
  judgement and says nothing new. The two are not the same act: ▶ is written
  and rewritten in place while the phase runs; the box is the phase's state,
  and the page is what the user reads instead of the session, so a Plan that
  under-reports itself misleads its only reader. Linted in both directions.

  **The entry line goes on its phase in the same turn as the submission
  (O14)** — not when the job returns. A long run opens a gap between launching
  and having something to say, and the line is what gets lost in it: the
  launcher has already written the job id onto the entry, so the machine knows
  what the page does not, and the omission is invisible from the session whose
  own context holds the truth. A `running` or `analyzed` entry carrying jobs,
  on a page this Plan links, that no phase names, fails the objective page.

  An entry line's date is the day it concluded — unlike the entry's own
  `Date`, which is creation; while it runs it has none. Neither line carries a
  number, a mechanism, a figure or a table — those are the entry's, one click
  away (O9). A phase is ONE question and as many entries as it needed.
  `needs:` makes the Plan a DAG (O5); absent, it means the phase above. The
  Plan is rewritten freely — appended, renumbered, dropped; git holds every
  route it used to show. A follow-up spawned by a live phase joins some plan
  (O6).

- **`## Verdict`** — in this form, and nothing else (O8, O11):

  ```
  **<the answer against the Goal>** <at most two more sentences, each a
  conclusion — a boundary, a caveat — never reasoning> <N> entries await review.
  ```

  The reasoning is in the phases.

## Language

If the project declares `record_language` in `.claude/framework.json`, the
linter holds the record to it (M1).
