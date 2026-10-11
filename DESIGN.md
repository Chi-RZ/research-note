# research-note — design

What this plugin is for, how a project is laid out, what each part of that
layout is responsible for, how it all reaches a cluster, how a person and the
agent share the work across interruptions, and how those responsibilities are
enforced. The README covers installing and using it; this file covers why it has
the shape it has.

---

## 1. The goal

The goal is: **every numerical fact — a number the code produced — is placeable
at the moment it is produced, by the agent that produced it, with no extra human
step.** Placeable means four things resolve from the record alone: the code (a
commit), the knobs (a recipe), the machine (an environment), and the description
(the entry it sits on — its motivation and its finding).

A second goal follows from letting an agent run for days: **an autonomous run
must be legible from a page, not from a transcript.** The user reads the
objective page and knows where the campaign stands. Sessions end, get compacted
and are thrown away; the page is what survives them.

A third follows from the first two: **the source code and the understanding are
distilled as the work proceeds, not after it.** A project that only accumulates
entries ends with a thousand true facts and nothing reusable. Condensation is
therefore an explicit pump with its own trigger (§7).

---

## 2. The layout

A project is one monorepo. The layout below is the default; a project declares
its own in `.research-note/project.json` (below), and **every path it does not
declare is the project's own, which the framework neither creates nor
validates**.

```
src/            §3  canonical, tested interfaces
tests/          §3  one test file per src file, mirrored
experiments/    §4  <node>/impl/     the frozen implementation
                    <node>/<group>/  how it is invoked, and its logs
                    tests/           experiment-level tests
project_memory/ §5  nodes/         the facts
                §6  objectives/    the intent channel
                §7  memory/shared/ what we learned, one fact per file
                §7  note/          interpretation, prose, per node
wiki/           §7  knowledge/ the standalone knowledge base
.agent/skills/  §7  where `memory-lift` lands a lifted method (§12)
.research-note/ §2  project.json the declared layout and integrations · state/ core
                    runtime state (old rules/ files are read-only migration input)
.claude/        §10 this project's bindings — contracts, hpc profile, hooks
.agents/ .codex/    the same bindings under the names the other agent reads (§12)
```

**Layers are told apart by path AND by commit prefix**, which is what makes the
separation mechanical rather than aspirational:

| prefix | may touch |
|---|---|
| `feat:` `fix:` `refactor:` | `src/` + `tests/` |
| `exp(<node>):` | `experiments/` |
| `memory:` | `project_memory/` |
| `wiki:` | `wiki/` |
| `agent:` | `.research-note/` `.claude/` `.agents/` `.agent/` `.codex/` — one prefix for every binding directory (§12) |
| `chore:` | nothing but root-level files — `.gitignore`, `pyproject.toml`, `uv.lock`, a root doc. The bucket for a commit that belongs to no layer |

The table is the default, not a requirement. `.research-note/project.json`
declares `roles` (which directories are the library, the tests, the
experiments, the knowledge base) and `layers` (which top-level paths each
commit prefix may touch), every managed path owned by exactly one layer, and
`project_config.py` is the single reader every consumer goes through. An
existing project therefore keeps `code/` and `trials/` where they are and
declares them, rather than moving them to earn the checks. Because the rules
live in the declaration, the hook that enforces them is framework text again
and an update can replace it — the earlier design put the table INSIDE
`commit-msg`, which made every project's hook a hand-edited fork that updates
had to diff and port around. A project with no declaration reads as the
standard layout.

---

## 3. `src/` and `tests/` — the abstraction layer

**Responsibility: hold the capabilities that outlive any one experiment, behind
a stable interface, with a test.**

Code arrives here one way: a **lift** (`research-note:lift`, §7), and what a lift
moves is a **function someone designed to be called** — never a file. The version
already running inside an experiment is the correctness reference: the `src/`
function is written afresh for reuse and its signature may look nothing like the
one it came from. Three rules keep it that way.

- **Discovery before writing** — search `src/INDEX.md`, then `experiments/` for
  prior art. A capability a second experiment needs is lifted, never copied.
  `INDEX.md` is a regenerated view — one row per capability: name and where it
  lives — and never edited by hand.
- **`tests/` mirrors `src/`**, one file per file, written first and updated in
  the same change.
- **`src/` changes ask the user first** — it is the one surface several agents
  work against at once, so the ask is the serializer.

---

## 4. `experiments/` — implementations and how they are run

**Responsibility: hold the code a result came from, frozen hard enough that the
result stays re-derivable.**

Under each node, `impl/` holds **the callable functions a `<group>/` invokes, plus
the declaration of which knobs exist** — never their values. `<group>/` holds the
invocation: run scripts, submit files, outputs, logs.

Keep that surface thin: a mechanism of any size splits into modules behind it. A
thin interface is what keeps a behaviour-preserving diff reviewable against its
validation entry, and a later lift a designed-API move rather than an untangling
job.

### Node identity — what forces a new one

A node is **frozen in behaviour**, not in bytes:

> **If some knob setting on the new code reproduces the old recorded result, it
> is the same node. If none does, it is a new node.**

An optional knob whose default reproduces every earlier cell stays in-node — that
default bound to the structure it came from, never restated as a literal, which
drifts and changes what every old recipe meant. A refactor or a result-preserving
optimisation stays in-node. A bug fix that moves a recorded number is a new node,
and the old one keeps standing under the entries that closed on it — what makes an
old result re-derivable rather than archived.

The claim covers **everything the node executes** — `impl/`, the `src/` it
imports, the pinned deps — not the `impl/` folder. A shared module is inside every
node importing it, and a folder rule watches none of them. Its evidence is a
**validation entry** naming the closed entry it replays, the recipe, and the number
it reproduced. Nothing here says how knobs are expressed, so the criterion survives
the next language.

**A recipe is one knob assignment**, supplied per run and recorded in the entry
that used it (§5) — text in the record, never executed, so any language's knobs
fit. Declaring them makes a changed key set a signature diff rather than a
silent divergence, and that diff is the prompt to ask the reproduce question.
Pre-declare the axes you mean to explore: skip it and a variant that is one
weight moved from 0 to 1 spawns a node, owing everything a node owes — a gate
and its pages.

### `<group>/` — invocation and outputs

One folder per problem instance the node's algorithm is run on, holding what
invokes it and the **outputs** that came back — four kinds, split by what each
is for:

```
<group>/  run + plot scripts                    committed
          figures/     what a person looks at   committed
          data/        what you read            not committed, never deleted
          checkpoint/  what you recompute from  not committed, stays on this machine
          logs/        what the run says        not committed — each headed with
                                                code SHA, dirty diff and machine
```
(`config/` for a Hydra pipeline and `submit/` for Slurm join them only where
those exist.)

A node opens with one group from the start, so its outputs sit at their final
path before the record cites them. A plot that spans groups sits at the node
root beside `impl/`, like the node-level page that reports it.

**`data/` is what you load to READ a result; `checkpoint/` is what you load to
PRODUCE one.** A table of energies goes in `data/`; the wavefunction it came from
is a checkpoint, however small. Role decides it, not size — the size difference is the
usual consequence. The split is what lets a result travel off the machine it was
computed on while the state behind it stays put, and it is the only handle any
transfer has: a filter that can only measure bytes cannot tell the two apart.

Scripts and figures are committed, so they reach any clone; results, state and
logs stay on the machine that made them. That is what forces the record to carry
the number itself rather than a pointer to it — a page quoting a value survives,
a link into `logs/` does not.

**The record, not the file, preserves a result.** A page quotes the number (§5)
and scripts are in git, so a result file may be rewritten — a rerun regenerates
it, and what the old run established stays on its entry. A checkpoint is
overwritten only by its own later state: step 500 supersedes step 400 of the
same run.

---

## 5. `project_memory/nodes/` — the facts

**Responsibility: per computation, hold why it was run, what it produced, and what
that means.** The first is fixed, the second moves only toward what happened, and only
the third is rewritten freely.

The record mirrors the code, node for node, and the name is the join:

```
experiments/<node>/impl/                the implementation
experiments/<node>/<group>/             its invocation and outputs
project_memory/nodes/<node>/            node.md, and node-level task pages
project_memory/nodes/<node>/<group>/    the task pages of one instance
```

`_index.md` is the roster, a regenerated view, never edited by hand — one row
per node, per entry and per objective (the section the next free `O<nn>` is
read from) — so read-first starts from one file and sees the goals, not just
the runs.

A node has two kinds of page:

| page | holds | written when |
|---|---|---|
| **`node.md`** | the code's own record — the gate, then every in-place edit's validation | the node is created, then whenever the impl changes and stays the same node (§4) |
| **task page** | one question's probes | a question starts that no existing page's title covers |

`node.md` sits at the node's root; a task page sits under the group of the
instance it probes, and a cross-group comparison sits at node level — the
framework reads only that grouping's existence, to find the node. A code change
lands as a validation entry on `node.md` or as a new node, and a change to shared
`src/` owes one on every node whose numbers it could move —
which is why those ask first (§3).

**A code entry is an entry.** Same fields, same rules, same portability; only the filing
differs. Its source is a code path at a commit, an absence, a directive, or the previous
validation — and taking the previous validation keeps the validations a chain from the
gate forward.

**One page for the node, not one per edit.** Every validation replays the same **reference
cell** — chosen at the gate — so its claim is "unchanged to within that history's spread",
and the weakest link bounds what the chain can claim.

`node.md` is that page, and it carries the same frontmatter as any page. Its first entry is the
**gate**: the node reproducing a reference its Motivation names — the parent cell it
forks from, or whatever independent number exists — so whether the node may be believed
is visible before any of its numbers are read. The same Motivation names the node it
supersedes, when there is one: the new node states it, the old is never edited.

**Where a new run goes:** if the page's title still describes it, another entry there;
if the title would have to be rewritten, a new page.

**Every page is a list of entries.** An entry is a set of computations answering one
question with one code at one recipe — a parameter scan is a single entry, one job per
point. A probe that exists only because another's result exists is a different entry.

### What may change, and what it drags with it

The requirement has two halves. What each field must HOLD — its shape, its
spelling, the form of its sentence — is the contract's, stated field by field in
`project_memory-CLAUDE.md` and enforced by `check_node_page.py`; it is not
restated here, because the copy an agent acts on should have no rival. What
belongs here is the other half, which no linter can decide: **when a field may
change, and what the change drags with it.** Rows are in the order they appear
on the page. **"Never" is about the fact, not about the line describing it**:
what a run did is fixed, the record of it is always correctable, and only the
second may cascade.

| field | when it changes |
|---|---|
| **Id** | Never |
| **Status**<br>**Date**<br>**Jobs** | `Status` advances, with two moves backward: a correction returns `closed` to `analyzed` (below), and resuming an interrupted procedure before it closed returns the entry to `running` with one more id on `Jobs:` — an interruption is not a state. `Jobs` only grows. `Date` never |
| **Code** | The commit never; a wrongly recorded SHA is corrected and cascades nowhere. Different code is a different entry, different *behaviour* a new node (§4) |
| **Motivation** | The question never — another question is another entry, including a control decided after seeing this result. The quoted fact moves whenever the RECORD of that fact is wrong: this entry misquoted its source, or the source was itself corrected later. The fact was always right; only the record of it can be wrong, and a description that misstates it is corrected wherever it sits |
| **Recipe** | The assignment never. A missing knob is backfilled and cascades nowhere; a wrong value is restated and cascades |
| **Facts** | May, toward more complete or more accurate. Backfilling cascades nowhere; correcting a number cascades along every `data` ref, transitively |
| **Conclusion** | May, freely; git holds the previous version. A changed datum reaches every conclusion whose `because` cited it (below) |
| **Refs** | Grows only |

### When the record and what happened disagree

**The record describes what happened. When the two disagree, the description moves.**
Everything else follows from that one line:

- **Numbers never change.** They are what happened. A later discovery changes what they
  mean, never that they were produced.
- **Descriptions change** — this entry's, and every other whose own description leaned on
  the same mistake. Nothing else moves.
- **An entry is never withdrawn and never deleted.** Nothing that happened un-happens, so
  there is no state for it; a probe that established nothing says so in its verdict.
- **A node's identity changes only when its behaviour changes** (§4). A free variable
  becoming a declared knob is neither a new node nor a correction: the old node's identity
  always included that freedom, and writing it down does not make the old numbers wrong.

The question at every correction is never "is this entry still valid" but **which part of
the description is now known to be wrong** — move that part, and nothing else.

A correction that reaches a closed entry returns it to `analyzed`. That alone blocks any
probe whose `Refs` name it and raises the objective's awaiting-review count. A correction
is its own commit, trailered `Correct: <id>` — the entry whose description moved.

---

## 6. `project_memory/objectives/` — the steering

**Responsibility: say what we are trying to find out, and where the route stands.**

**Principle: the page is the interface, not the session.** It shows the route as it stands
now and nothing else — every route it used to show is in git. It carries no fact of its own:
facts live on nodes, and an entry never links back here (§5), which is what lets everything
below the Goal be rewritten freely.

### What may change, and what it drags with it

What each part must HOLD is the contract's (`project_memory-CLAUDE.md`,
`check_objective_page.py`); what follows is the half that is this design's —
which parts the loop may rewrite, and which are the user's alone.

| part | when it changes |
|---|---|
| **id** | Never |
| **status**<br>**created** | `status` moves to `closed` by the user; `created` never |
| **Goal** | Only on explicit user instruction, recorded with hashes of the old and new Goal; an independent goal gets a new objective |
| **budget**<br>**wake-me-if**<br>**attention** | The user sets the first two, freely; the loop sets and clears `attention` |
| **Plan** | Freely — appended, rewritten, renumbered, dropped |
| **Verdict** | Freely, rewritten at milestones |

```
- [ ] **P<n> — <the question this phase asks>** (<cost>[ · needs: P<i>])
  - [entry name](page.md#entry-slug) `<id>` — <the role it plays in answering it> (<date>)
  - ▶ <what this settles for the Goal> one sentence
```

An entry's date is the day it concluded — not the entry's `Date` field, which is creation
(§5). While it runs it has none, which is how the phase shows where it stands. No figure
and no table: both belong to the entry that produced them.

**A phase is ONE question and as many entries as that question needed** — the measurement
plus whatever controls and diagnostics it turned out to want, including ones decided only
after seeing the first result. One entry is the common case, not the rule.
`needs:` makes the Plan a DAG, and every phase whose dependencies are met launches at once,
one agent each; absent, `needs:` means the phase above.

**An agent that finishes a phase does not take the next one from memory.** It writes its phase
back and re-reads the page: what runs next is whatever the Plan says after that write, and its
own result may have invalidated the phase it was about to take. With several agents running,
that write is the only thing the others see.

**Neither line carries a number or a mechanism.** Those are the entry's, one click away, and
repeating them here is how an objective starts owning facts. Both lines are route-relative —
an entry's role, a phase's bearing on the Goal — and both die with the goal, as the phase
does. `<cost>` is not an exception: spend is the route's own arithmetic over its runs, and no
entry states it.

A route the work backed out of says so in its reading — a phase that closed a direction settled
something. If it is no longer part of the route at all, the phase goes and git holds it.

The record bus maintains O8's review count before saving an objective and after
entry changes. The launcher does the same when a job changes an entry's status.
Count-only updates to clean objectives use separate Objective commits under the
record lock. They skip record lint only for this derived text, preserving other
Git hooks: O7/O13 may still require an authored phase review, and the count
update must not fabricate one. Pending edits are left to their owner; their
count refreshes on the next bus save. Failures are reported and the derived edit
is restored. O8 still checks saved counts independently.

An O7 review can leave the phase reading unchanged. `objective_state.py
review-phase` records a note and a fingerprint of the phase plus its full linked
conclusions, so a subsequent evidence change requires a new review. O4's
`approve-goal` command records the user's instruction and the exact Goal change;
it provides an audit trail, not independent proof of permission.

### What makes free rewriting safe

"Have we computed this" is never a question for this page. It is answered on the node
page, where read-first (§9) sends you anyway, and where entries are never deleted.

Two things follow, and neither is optional:

- **A route change is its own commit.** The decision is what a route is made of; landed in
  the same commit as an entry, it cannot be told apart from the data that prompted it.
- **A sample is a snapshot, never the head.** The current page pairs today's conclusions
  with the route walked under yesterday's. Each commit is internally consistent; the head
  is a reading surface. This holds whether or not conclusions ever settle.

---

## 7. Learning and condensation — `memory/`, `note/`, `wiki/`, and the pumps

**Responsibility: turn accumulated work into something reusable, on purpose.**

Two soft channels, split by mechanism rather than subject:

- **`memory/shared/`** — the agent's own memory, the harness's auto-memory
  pointed inside the repo so it is versioned with the project. Loaded into
  context at session start, so it stays one small fact per file: *does this
  change how the next run is set up?* `memory/claude/` and `memory/codex/` are
  symlinks onto it (§12): what one agent learns, the other has.
- **`note/`** — prose the people on the project read, written by user and agent
  together: what results mean, why a direction was taken or dropped, engineering
  experience. Content unconstrained, as long as the thinking needs.

**`wiki/`** is the published end, self-contained by contract — a page that needs
the record to make sense is not publishable. It lags on purpose: material arrives
only through a pump, and only once it has settled.

Its shape is DECLARED rather than emergent. `wiki/knowledge/SCHEMA.md` fixes
which pages exist and what each covers, derived once from the whole record and
edited deliberately afterwards; a source is routed into a declared page and a
source that fits nowhere is a proposal to change that file, which is the user's
to decide. The alternative was tried and withdrawn twice: a structure
re-derived at every compile takes the shape of whatever arrived last, which is
the record's shape and not the subject's. Pages are one of five types —
`concept`, `method`, `comparison`, `open`, `overview` — and there is no
`finding` type, because a result is evidence cited ON a page rather than a page
of its own. What enters must be reusable across sources: a one-off stays in the
record and is cited by tag, while what the one-off taught may enter.

**Condensation is always an explicit pump, never implicit.**

| pump | from → to | trigger | gate |
|---|---|---|---|
| `lift` | `experiments/` → `src/` | a SECOND consumer appears | what lifts is a designed API, never the literal code. Lands as a `feat:` plus an `exp(<node>):` |
| `wiki-compile` | `note/` and closed entries → `wiki/` | the user asks | the interpretation has settled; an entry must be `closed`; what compiles is its `Conclusion`; and it must route into a page `SCHEMA.md` already declares |
| `memory-lift` | `memory/` → the project's `.agent/skills/`, which both agents' skill directories are views of (§12) | the user asks | would it apply verbatim in a DIFFERENT project? |

Two of the three wait for the user, because an agent that generalises its own
habits into the framework compounds its own mistakes. `lift` is mechanical instead: the moment
a second experiment needs the same capability, copying is the mistake.

---

## 8. Remote support and running simulations

**Responsibility: let a job run wherever the compute is, and keep the record on
this side in step with it.**

**The remote is a compute service.** Code goes out, logs and data come back, and
the analysis happens here. No agent works there and no record lives there.

What follows is what must be true, not how to make it true. Clusters differ in
scheduler, filesystem, module system and tooling vintage, and a rule written
against one of them breaks on the next — so the mechanism is left to whoever
meets the machine. Where something is worth suggesting rather than requiring, it
says so.

### 1 — Which venues a project needs is settled at setup

A job runs on one of four combinations — this machine or another, with a
scheduler or without:

| | with a scheduler | without |
|---|---|---|
| **local** | hand it to the queue | launch it in the background |
| **remote** | hand it to the queue there | launch it in the background there |

Which of these a project will use is a question to answer while setting it up, by
looking at the machines it is actually going to run on — not one to find out when
a launch fails. Whichever apply return the same three things: an id that names the job, a log
that describes its own run, and something that can be asked later whether it is
still going. What is shared is the RECORDING contract, not the call — three
scripts serve the four venues with three argument shapes, and remote-with-a-
scheduler is reachable through two of them. That is a cost, and this section
states it rather than hiding it: a fix to queue placement or to log derivation
in one does not reach the other, which has happened.

### 2 — Three things are aligned before a job starts

| what | must match | why it is not covered by the others |
|---|---|---|
| the project's code | the local commit | the run has to be the code you have here |
| the environment spec | the file in the repo | the code alone does not say what it needs |
| a library you are developing | its commit | a lockfile pins a release; an edited library has only a commit |

What each machine **installed** from the spec is never compared against another
machine — one spec resolves to different bytes on different hardware, so equality
would fail on every run and mean nothing. Each machine is held to the spec, and
whatever still differs is recorded rather than aligned. A **second spec** is
allowed where a dependency exists on one platform only, provided it contains the
first: every package of the base at the same version, extras permitted.

*Suggested:* bring the far side up before checking it, so a host that is merely
behind is repaired rather than reported; and let a check that cannot establish
its premise say so, rather than report a failure it did not observe.

### 3 — Every job is recorded, then watched until it is settled

A job that exists and is on no entry is lost work, so the id lands on its entry
the same turn it is submitted. From then on the entry and the job stay in step —
that alignment is the whole requirement, and everything below is what it takes to
hold it.

Watching is a timer, not a single wait, and finishing is only one of the things
it asks:

- is it still running?
- did it die — out of memory, node failure, walltime — and should it be resubmitted?
- is it producing anything, or has it stalled with the process still alive?
- does the entry's status still describe what is actually happening?

The session that launched it owns this, since nothing on the far side can write
the record. It keeps at most one watcher for all objectives whose background
jobs it currently owns, repeating the objective scope in that watcher; a
foreground-only run needs none. The watcher changes only when that session's
objective set changes, never once per job. Behind it, the harvest hook reports
any J3 left unharvested for 15+ minutes into every session's next turn, unarmed.

### 4 — Results come back on their own, and are analysed here

When a job ends its logs and data are pulled back without anyone asking for them.
The state a run resumes from — checkpoints, large intermediates — stays where it
was made (§4); no transfer can tell that apart from a result by looking, so the
split is made when the file is named.

---

## 9. The workflow — the principles of the loop

**What we want: no number of interruptions costs the campaign its place.** A
person asks a question, changes their mind, edits a file by hand, walks away for
a day. None of that should end the run. The agent's place is on a page (§1, §6),
so after any interruption the move is the same one: re-read the page, and go on
from where it says the work stands.

- **The next move comes from the objective page, never from memory** (§6).
  Between actions the agent re-reads the Plan, and the next phase is decided
  from the concluded readings — the Plan is appended, rewritten or dropped to
  match before anything runs.

- **Read-first, at every entrance.** Which entrances, which sources, and what
  each asks are the root contract's, stated there once: a second copy lived
  here and had already fallen a source behind the original. What the principle
  buys: a recorded answer finishes the request or shrinks it to the part that
  is new, and what remains is an entry on an open page, a new page (§5), or a
  new node (§4) — and when §4 does not settle node-or-not, ask. No linter can
  run this check: a duplicate probe reaches a page only after its hours are
  spent.

- **Jobs are watched until settled (§8), and the record follows the same turn.**
  A job that ends lands on its entry — status, facts, conclusion — and on the
  phase that owns it, and the entry's follow-ups run without being asked. The
  skills that open and write records are the agent's to invoke unprompted; the
  asks of §3, §5 and §7 are the exceptions.

- **`wake-me-if` fires → the loop stops**, sets `attention:` and waits (§6).

- **A correction is applied at once** (§5): move the wrong description, walk the
  cascade the same turn, then continue under the rewritten page. **A question
  does not interrupt**: it is answered from the record and the open phase
  resumes — the answer is not the turn's deliverable.

- **A handover's first move is read-first.** Whatever the predecessor knew and
  did not write down is gone.

- **A file the person changed is re-read before the agent edits it**, and a
  change the agent did not make is asked about before it is built on or
  reverted.

---

## 10. How it is enforced

**Be strict about the finished record and permissive about the route to it.**
The framework checks claims that can be read from an artifact: required fields,
resolvable links, ownership of running work and internal consistency. It leaves
scientific judgment to the agent and reviewer. A gate exists where an otherwise
silent failure would make the record unreliable.

### 10.1 Contracts

Four editable contracts cover the project root, experiments, project memory and
wiki. Each contains a managed framework section followed by
`## Project-specific rules`. Claude reads the contract through `CLAUDE.md` and
Codex through `AGENTS.md`; both names point to the same file. Updates replace the
framework section and preserve project rules. An inseparable local edit stops the
update as a conflict instead of being overwritten.

The contracts state stable policy. Skills carry procedures for a particular
moment: planning, objective work, background submission, analysis, correction,
code lift, wiki compilation, memory lift, reorganization, setup and update.

### 10.2 Action-time reminders

Lifecycle hooks route new computational work into the record, attach submitted
jobs to their entry, lint a page after it is written and make newly created
worktrees sparse. Session start checks the current worktree and starts the
optional fixer only when the project enables it. The harvest reminder reports a
running entry only after all of its jobs have been terminal long enough to have
been missed.

Read-only commands take the cheap path. A reminder fires when its obligation is
created; normal operation does not depend on a periodic prompt.

### 10.3 Linters

The node/page linter protects the evidence record. Its core checks are:

- stable IDs and valid status transitions;
- required code, motivation, recipe, facts and conclusion fields;
- evidence links, figure links and referenced commits that remain reachable;
- one computation script per entry and one owner for recorded jobs;
- rosters, validation references and project language when enabled.

A numerical table is required when measurements exist. A failed start or another
run with no measurement may instead record the reason and its evidence. The
conclusion must answer the question and identify its basis and boundary, without
requiring a fixed English sentence. Dates do not determine entry numbering; IDs
only need to remain unique and stable.

The objective linter protects the control loop. It checks the Goal, Plan and
Verdict shape; phase and entry links; the plan DAG; globally unique objective
IDs; explicit authorization for a changed goal; and reviews of conclusions that
changed beneath an existing judgment. The awaiting-review count is maintained
by tooling and checked for consistency. Long verdicts receive a non-blocking
reminder.

These checks do not decide whether a conclusion is true, whether a probe was the
best probe, or whether two results agree scientifically. Those judgments belong
in the record. Exact diagnostic codes and command options live beside the
linters and their tests, which are the executable specification.

### 10.4 Gates

The record bus lints a page under a shared lock before it lands. Git hooks keep a
record commit on the default branch, enforce the project's declared commit
layers and keep `src/INDEX.md` aligned with reusable code. Existing project hooks
still run through a dispatcher; uninstall restores the prior hook path.

Recorded launchers require an entry and either an objective phase or an explicit
`NO_OBJECTIVE=1`. Formal runs launch from main, after code has landed. Setup does
not report success until the core wiring and both record views pass. Every gate
has a named emergency escape so a false positive can be handled explicitly
rather than encouraging users to remove the framework.

`worktree_retire.sh` is an explicit cleanup command. It refuses removal while a
process still has its current directory inside the worktree. Plain
`git worktree remove` is not wrapped, and worktrees are not deleted merely when
an agent session ends.

### 10.5 Optional services

The fixer is a background scanner that can surface missed work and reconcile job
state. It is disabled by default and runs only when the project enables it. The
HTML dashboard and editor extension are also optional. Linters, contracts, Git
hooks and the record itself remain the default core.

### 10.6 Several agents in one repository

**The record is serial; code can be parallel.** `project_memory/` and `wiki/`
live once in the main checkout. Record writes go through the shared bus and
lock. A framework-created worktree omits those directories, so an agent cannot
accidentally edit a stale copy.

One agent may edit a clean main checkout directly. Separate worktrees are used
when agents may edit code concurrently, main contains unrelated work, or a
change needs an isolated branch. Three agents can therefore work in three
worktrees while another session owns the record on main. Worktree branches land
by fast-forward after rebasing when needed, and a formal run is repeated from
the merged main state.

A session can complete one objective and then open another, or own several
active objectives when the work calls for it. Its monitor follows the session's
set of objective IDs and their running entries; the framework does not create
one daemon per objective.

---

## 11. Setup, update and diagnosis

`bootstrap_project.py` performs one idempotent installation. It creates the
record layout, contracts and agent views, project configuration, Git-hook
dispatcher, indexes and ignore rules, then runs a read-only acceptance check.
Existing source layouts and hooks are preserved. Dashboard, fixer, HPC and
editor support are persisted opt-ins; Claude and Codex project bindings are
core.

The setup skill handles decisions that a script cannot infer: directory roles,
the project's purpose, environment choices and optional integrations. Project
purpose belongs in `project_memory/note/` or an objective Goal, while durable
project-specific agent rules belong in the contracts' project section.

`update_projects.sh` updates the current project. It stages a shared release,
checks contract conflicts, switches both host bindings and Git hooks as one
transaction, verifies native host installation, then removes legacy project runtime copies.
A failure restores the previous managed files and pin. Framework-owned files may
be refreshed, project-owned files are untouched, and mixed files preserve their
project section. Setup reuses an existing pin; update is the operation that
changes it.

`doctor.sh` checks core wiring for every project and checks an optional
integration only when enabled or explicitly requested. It diagnoses; normal
setup does not run every diagnostic twice. Dry run remains available when a user
asks to preview setup or update.

The compatibility suite exercises empty and existing repositories, custom
layouts, inherited hooks, old-project migration, missing host CLIs, optional
services, rollback, worktrees and repeat runs. CI runs fast parser and policy
checks at the supported Python and shell endpoints, with real bootstrap, update
and rollback paths in one integration job.

---

## 12. Projects select shared releases

The record format is `v1`. Updating a pre-release project renames its old `v3`
marker to `v1` without changing records. Older schemas still need migration.

The record, linters and Git gates are host-neutral. The plugin package has one
core and two manifests because Claude and Codex keep separate registries and
caches. A test holds their versions equal.

Claude reads `CLAUDE.md`; Codex reads `AGENTS.md`. Each pair points to the same
contract, and their memory views point to the same shared memory. This avoids two
copies of project policy or learned context drifting apart.

`.research-note/plugin-lock.json` records the selected version, content digest
and source commit, branch and plugin dirty status when available. Immutable plugin content lives once per machine
at `~/.local/share/research-note/releases/<digest>/`, respecting XDG data paths.
Both project configurations select a content-specific marketplace; identical
content shares the same source and host cache across projects. No full plugin
copy lives in a new project's `.research-note/`.

Claude's native registry records project scope and its cache path. For local
marketplaces it may read directly from the immutable shared source. Codex's
project configuration selects the marketplace and plugin; native discovery loads
its own cache only in trusted projects. Setup/update verify available hosts and
report missing or untrusted hosts as pending. User-level enablement is unchanged.
The lock and configuration select a release, never the highest cache version.

An explicit update changes the current project's lock and switches Claude,
Codex, hooks and scripts together. Other projects and user-level installations
stay unchanged. Claude can reload plugins in place; Codex uses the new pin in a
new session. Existing sessions may keep the code they loaded at start.

A new clone must restore the exact locked release from matching plugin source;
run `python3 /path/to/plugin/scripts/project_runtime.py restore --source
/path/to/matching/plugin PROJECT_DIR`. It does not silently select a newer
release. A moved checkout with its snapshot present only needs `restore
PROJECT_DIR` to refresh its local paths. `--latest` fetches main,
`--version VERSION` fetches a release tag, and `--source` installs local working
files without GitHub. Installed files do not follow subsequent checkout edits.
Versions identify releases; content digests distinguish local builds with the
same version. A development cycle declares a prerelease version once (for
example `0.1.1-dev.1`); each local update includes current plugin edits without
rewriting that declaration. The maintainer merges dev and sets the formal
version before publishing main and its tag. Both sources use the same installer.
Shared releases and native caches are retained independently of
project updates because other projects may still select them.
