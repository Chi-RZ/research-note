# project_memory — the record

Record format: v1

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
├── _index.md              the node + entry + objective roster — regenerated (gen_index.py)
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

- **Id** (E1): node number from `_index.md`, then a per-node sequence, unique
  across the complete `project_memory/nodes/` tree and never reused.
  Both zero-padded, assigned at creation, never reused or renumbered to match
  dates; backfilled records may have earlier dates.
- **Status** (E2): the four states, nothing else. **Date** (E3): creation,
  never changes.
- **Code** (E4): the newest commit at submission touching `<library-root>`, the node's
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
  `Recipe`, or of the table. Numerical results require a table. If a run produced no measurements, add
  `- **Measurements:** none — <reason>`; Facts still describes the failure or
  interruption and links its evidence. Otherwise the sentence does not
  announce what it holds — the sentence carries the instance, the job layout,
  the script and the evidence links, and prose after the table carries only
  what the table cannot: a wall time, an exit status, the provenance of a job
  id. Every number matches its log — the writer's check before `analyzed`. A mean, ratio or spread stands beside the values it was computed
  from, here or one `Refs` hop away. Unmarked means this entry produced it; a
  quoted number carries the `[n]` of the entry that RAN it, and every `[n]`
  has a `Refs` row. Grows only toward more complete or more accurate.
- **Conclusion** (E9): state what the result establishes, why, how fully it
  answers the Motivation, and the relevant limits. Keep it concise and scoped
  to that question. State any premise a reader could dispute, and the detection
  floor when the evidence is a draw. Wording and sentence order are flexible;
  no English suffix is required (E15 retired). The linter checks presence and
  placeholders; the analyzing agent reviews the reasoning. Rewritten freely;
  git holds previous versions.
- **One computation script per entry** (E11). A probe that exists only because
  another's result exists is a different entry.
- **An entry is its fields and nothing else** (E12). Every line either opens a
  field or is indented under the one it continues — the table, the figure, the
  job's log link, a long field's line-wrap. A paragraph left between the fields
  reads as an entry whose Facts are missing, because a reader and every check
  here look for content under the key that owns it. E12 binds at every status,
  like E10 and unlike E4-E9: those judge what a field SAYS and stop at the
  user's ✓, while this one judges only WHERE a line sits.
- **Evidence and interpretation each stay in their field** (E13, E14).
  `Facts:` holds no standalone `Job <id> — [log](…)` stanza — a log link
  belongs in the sentence's `evidence <links>` clause, or rides `- **Jobs:**`
  as an indented continuation (which is what `record_submit` writes). The
  `Conclusion:` carries no link — an artifact is `Facts:`'s, a borrowed entry
  a `Refs:` `[n]`. Boundaries and reasoning stay in the Conclusion.
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
stands. An entry is never withdrawn and never deleted. A correction is its own
commit (trailer under Commits).

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
without them (`NO_OBJECTIVE=1` for a run that serves none).

Every submission, the same turn: the id onto the owning entry's `Jobs:` field
(ranges allowed, `63902601–04`; host tags, `@t6`), and the log's repo-relative
link into the entry. A job belongs to its entry; there is no page-level table.
An empty `- **Jobs:**` is never silent: a `running` entry with no ids — or a linked launcher log with none —
is J5, and an id the Facts name — or a `Job <id> —` line anywhere — missing
from the field is J6, because the field is what every watcher, waiter and
board reads. (Motivation and Refs quote OTHER entries' ids as provenance;
those belong exactly where they are.)

The launching session watches its own background or batch jobs. It keeps at
most one watcher for all objectives it currently owns, repeating `--for O<nn>`
for each scope; foreground-only work needs none. It analyses completed jobs
in-session. The fixer scans and raises `attention:`; it repairs nothing.

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
  user's; unchanged after intake unless the user explicitly authorizes a
  revision (O4). Record that instruction and the exact old/new Goal hashes
  with `objective_state.py approve-goal <page> --instruction '<user instruction>'`
  after editing, then save through the record bus. This records authorization
  already given; it is not permission for the agent to change the goal.
- **`## Plan`** — one block per phase:

```
- [ ] **P<n> — <the question this phase asks>** (<cost>[ · needs: P<i>])
  - [entry name](page.md#entry-slug) `<id>` — <the role it plays in answering it> (<date>)
  - ▶ <what this settles for the Goal> one sentence
```

  A changed conclusion requires re-reading its owning phase (O7). If the
  reading still holds, keep it and run
  `objective_state.py review-phase <page> P<n> --note '<review finding>'`.
  The review binds to the current reading and full linked conclusions; a later
  change invalidates it. Save the updated page through the record bus.

  **The box flips when every entry under the phase has concluded (O13)**,
  linted in both directions — the step that gets skipped, because unlike the ▶
  line it carries no judgement: ▶ is rewritten in place while the phase runs,
  the box is the phase's state, and a Plan that under-reports itself misleads
  its only reader.

  **The entry line goes on its phase in the same turn as the submission
  (O14)** — not when the job returns: the launcher has already written the job
  id onto the entry, so the machine knows what the page does not, and the
  omission is invisible from the session whose own context holds the truth. A
  `running` or `analyzed` entry carrying jobs, on a page this Plan links, that
  no phase names, fails the objective page.

  An entry line's date is the day it concluded — unlike the entry's own
  `Date`, which is creation; while it runs it has none. Neither line carries a
  number, a mechanism, a figure or a table — those are the entry's, one click
  away (O9). `needs:` makes the Plan a DAG (O5); absent, it means the phase
  above. A follow-up spawned by a live phase joins some plan (O6).

- **`## Verdict`** — answer, key boundaries, and derived review count (O8, O11):

  ```
  **<the answer against the Goal>** <at most two more sentences, each a
  conclusion — a boundary, a caveat — never reasoning> <N> entries await review.
  ```

  The reasoning is in the phases. Over ten non-empty lines triggers an advisory
  to move detail there; it does not block a save. The record bus maintains the
  awaiting-review count on objective saves and after entry changes; the launcher
  also refreshes it when recording jobs. Clean dependent objectives receive a
  separate count-only commit. A page with pending authored edits is left alone
  and refreshed on its next record-bus save. This never closes an entry or
  changes a phase reading. O8 still checks the count against the linked statuses.

## Language

If the project declares `record_language` in `.claude/framework.json`, the
linter holds the record to it (M1).

---

## Project-specific rules

Write rules for this project's record below this heading. This section belongs
to the project and is kept when the plugin updates the framework section above.
A rule that would serve every project belongs in the plugin template instead.
