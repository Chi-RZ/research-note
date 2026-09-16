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

A project is one monorepo. These paths are the framework's; **everything else in
the repo is the project's own, and the framework neither creates nor validates
it** — one project on this framework keeps `code/` (Julia sources),
`results_plot/` and `Paper/` beside
these as ordinary members of the repo.

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
| `agent:` | `.claude/` `.agents/` `.agent/` `.codex/` — one prefix for every agent-binding directory (§12) |
| `chore:` | nothing but root-level files — `.gitignore`, `pyproject.toml`, `uv.lock`, a root doc. The bucket for a commit that belongs to no layer |

The table is the default, not a requirement. A project declares its own
roots and layers in `.research-note/project.json` — `roles` (which directories
are the library, the tests, the experiments, the knowledge base) and `layers`
(which top-level paths each commit prefix may touch), every managed path owned
by exactly one layer, and `project_config.py` is the single reader every
consumer goes through: the commit-msg partition, the pre-commit index gate,
`gen_index.py`, the linters' N2 cross-check, doctor, the sparse clone and the
worktree patterns, `remote.sh pull`. An existing project therefore keeps
`code/` and `trials/` where they are and declares them, rather than moving
them to earn the checks. Because the rules live in the declaration, the hook
that enforces them is framework text again and an update can replace it — the
earlier design put the table INSIDE `commit-msg`, which made every project's
hook a hand-edited fork that updates had to diff and port around. A project
with no declaration reads as the standard layout.

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
per node (number, name, link), then one row per entry (id, name, status,
linked), then one row per objective (id, page, status, verdict first line) —
the section the next free `O<nn>` is read from — so read-first starts from one
file and sees the goals, not just the runs.

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
| **Goal** | **Never.** A different goal is a different objective |
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
the record. At most one watcher per objective — armed idempotently at the
objective loop's entry, scopes disjoint — never one per job; behind every
watcher, the harvest hook reports any J3 unharvested for 15+ minutes into
every session's next turn, unarmed.

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
  each asks are the root contract's, stated there once — and it says so, in the
  rule itself. A second copy lived here and had already fallen a source behind
  the original, which is the whole argument for the rule. What the principle
  buys is this: a recorded answer finishes the request or shrinks it to the part
  that is new, and what remains is an entry on an open page, a new page (§5), or
  a new node (§4) — and when §4 does not settle node-or-not, ask. No linter can
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

## 10. How it is enforced — six layers, softest first

**Principle: strict about what a finished record says, permissive about how the
agent got there.** A page that misses a field, contradicts its own evidence or
hides two probes in one entry is a defect a linter can name. Which order to
explore in, when to run a control, how to decompose a question — constraining
that buys nothing and costs the agent's judgment, which is the thing worth
having. **Gates on the artifact, guidance in the skills.**

The mechanisms form a ladder from "text you read" to "machine that refuses".
Where a mechanism sits on the ladder is decided by one test: a gate only where
the failure it prevents would be silent.

### 1 · Contract text — always loaded

Four files hold the doctrine, each governing one subtree. They live in `.claude/`
and are **symlinked** into the directory they govern, so the rules load themselves
when work happens there — one home, several views. Each is **generated**: the
plugin's template, then the project's own rules from `.research-note/rules/<x>.md`
(`root.md`, `experiments.md`, `record.md`, `wiki.md`), with a first line that
names both sources. The framework's text and the project's never share a file
that anyone edits, which is what lets an update replace the one without reading
the other out of it — the earlier scheme kept both in one file, told them apart
by the template being a byte-prefix of the copy, and had to refuse the moment
the framework half moved under a project's additions. A project still on
that scheme, or on one older, is carried over once: the plugin ships the length
and hash of every template version it ever released (`templates/history.json`),
so an old framework half is recognised exactly and whatever follows it moves
into the rules file — only a file matching no version is left alone, as a
conflict for a person:

| file | holds |
|---|---|
| `CLAUDE.md` (root) | the whole framework in one read: the layers and the pumps, node/page/entry, `src/` vs `experiments/`, where a job may run, how several agents share the repo, the commit prefixes and trailers, and what to do about a human's uncommitted edits |
| `experiments-CLAUDE.md` | the code side: what sits under a node, how a run is invoked and named, where its outputs and logs go, and interactive-versus-batch |
| `project_memory-CLAUDE.md` | the record side: the entry contract of §5, the objective contract of §6, and the same-turn job rules |
| `wiki-CLAUDE.md` | the self-containment contract — a wiki page makes sense without the record it came from — and the invariants that follow from it: grounding by plain-text tag, a view never an authority, `Status:`, `⚠ Contested:`, linking, the five page types declared in `SCHEMA.md`, and admission by reusability |

Rules that no machine can check live here and nowhere else — a rule that
belongs to exactly one of these files is never restated in another.

### 2 · Skills — loaded on invocation

Procedure, not doctrine — a skill can be departed from with a reason, which is
what distinguishes it from every layer below. Eleven, by the moment they serve;
the third column is where a person is in the loop, and the moments the loop
stops are §9's:

| | | opened by |
|---|---|---|
| **opening a record** | `plan` a node — gate included — or a page · `objective` a long goal and its loop | agent · **user**, at intake |
| **running and concluding** | `hpc-submit` any background launch, local or remote, Slurm or bare · `analyze` collect, write the conclusion, stop at `analyzed` | agent · agent |
| **when something is wrong** | `correct` — move the description now known to be wrong, and only that one (§5) | either |
| **condensing** | `lift` code into `src/` · `wiki-compile` a note or a closed entry into the wiki · `memory-lift` a memory into a skill · `reorg` move a `src/` capability without breaking a caller | agent, on a mechanical trigger · **user** · **user** · agent, but asks |
| **the machine itself** | `project-setup` a new project · `update` pull a plugin version into every project | **user** · **user** |

### 3 · Reminders — fire on the action, not on a schedule

| hook | when | what it says |
|---|---|---|
| `UserPromptSubmit` | every turn | the routing check: is this new work that must land in the record before compute? |
| `UserPromptSubmit` (harvest) | every turn, but speaks only when a `running` entry's jobs have ALL been terminal 15+ min with nobody harvesting | the forgotten/orphaned entries, tagged with the objective whose Plan links each; non-owners read-only |
| `PostToolUse` (submission) | only when the command MATCHED a submission | record, unprompted: the job id and both links land on the owning entry THIS turn |
| `PostToolUse` (record edit) | an Edit/Write landed on a record page | that page's linter runs, and the errors come back the same turn |
| `PostToolUse` (worktree) | only when a worktree was just created | make it SPARSE — no `project_memory/`, no `wiki/`, so the stale record copy a worktree would otherwise carry never exists |
| `SessionStart` | opening a framework project | start the fixer if it is not already up, and sparse the worktree this session sits in |

`PostToolUse` exits early on read-only commands, so the common case costs a
regex. A reminder fires on the turn where the obligation was incurred, never on
a schedule.

### 4 · Linters — decide on the file

**What a linter may decide is narrow, and the boundary is the point.** It reads
files. It cannot run code, so it cannot answer the question §4 asks — whether
some knob setting reproduces an old result. What it can do is refuse a record
that fails to *say* something:

| it can decide | it cannot decide |
|---|---|
| the fields are present and spelled one way | whether the conclusion is true |
| the links resolve and the anchors exist | whether the number is right |
| a live job is named by some entry | whether the entry should have been split |
| the Plan is a DAG and its links land on real entries | whether the phase asked a good question |

Whether a quoted number matches its log is the writer's check, made before
`analyzed` (the analyze skill's last step); the linter's part is that the log is
linked (`E7`), so a reader can repeat it.

**A claim the record must make gets a code; a judgement gets prose and a place
to write the answer.** The reproduce criterion is not checkable, but the
validation entry that carries it is — `V1`. A `closed` entry is released from
`E4`–`E9`, the checks that judge what a field SAYS: the user's ✓ accepted it as
it stood, and those bind while the entry is still the agent's to write, which
every entry is at `analyzed`. Everything else still binds — `E10` and
`E12`–`E15`, which judge only WHERE a line sits, and `E11` and `E16`, which ask
whether a claim can still be followed at all. A tick accepts a reading; it
cannot make an unreachable SHA reachable again.

**Every code, by what it protects:**

| | node pages | objective pages |
|---|---|---|
| **the tree joins up** | `N1` node.md's frontmatter, its `node:` matching the folder, and at least one `### Entry:` · `N2` an implementation exists under `experiments/<node>/` · `N3` the regenerated roster matches the tree · `FW` record version matches the linter | |
| **the entry says what it must** | `E1` id unique, in `Date` order · `E2` status ∈ the four states · `E3` date · `E4` `Code` names its commits · `E5` motivation in its form: source named, fact quoted, one question · `E6` recipe is a knob map · `E7` `Facts`: the sentence, the table, the evidence links · `E8` a displayed number this entry did not run has a `Refs` row · `E9` a conclusion once `analyzed`, in its form · `E10` one spelling, no retired field · `E11` one computation script per entry · `E12` every line sits inside a field · `E13` `Facts` holds no bare `Job — [log]` stanza · `E14` the Conclusion carries no link · `E15` the Conclusion ends at its verdict · `E16` a cited `<repo>@<sha>` is retrievable — landed on the default branch for this repo, resolvable for a pinned lib | `O1` frontmatter: id, status, created, budget, wake-me-if · `O2` Goal, Plan, Verdict, in order, nothing else |
| **a claim can be followed** | `P1` page frontmatter, its `node:` matching the folder, and at least one `### Entry:` · `P2` links and anchors resolve · `P3` figures render · `P4` a figure has a caption, embedded once · `P5` no page-level Jobs | `O3` links resolve and land on real entries |
| **work in flight has an owner** | `J1` an entry with jobs links an artifact · `J2` a live BATCH job is named by some entry — an interactive allocation is exempt, and so is one younger than the reuse tolerance · `J3` `J4` entry status against the queue, both directions · `J5` an entry that ran jobs left `Jobs:` empty · `J6` an id the Facts name (or a `Job` line anywhere) is missing from the field | `O8` the awaiting-review count matches the Plan |
| **the route stays honest** | `V1` a validation entry NAMES the entry it replays. That the recipe and the reproduced number are also there is the writer's, not the linter's: reading them is a judgement (§10.4's own boundary) | `O4` the Goal is byte-unchanged · `O5` the Plan is a DAG · `O6` a spawned probe appears on some plan · `O12` the id is unique across objectives/ · `O7` a reading is not older than the conclusions it reads · `O9` no figure and no table · `O10` no `attention:` on a CLOSED objective — that it is present while stopped is the loop's to honour, not a check · `O11` the Verdict stays the answer — bounded length · `O13` a phase's box matches the entries under it · `O14` an entry launched with jobs is named by some phase, the same turn |
| **project policy, opt-in** | `M1` one record language, where `framework.json` declares it | `M1` |

**When they run:**

| moment | what runs | what it costs to fail |
|---|---|---|
| **a record write** through the bus | the linter for that file's kind | the page does not land |
| **every scanner cycle** | both linters over the whole record | nothing is refused; findings become `attention:` |
| **a new project** | both, as bootstrap's acceptance gate | setup does not report success |
| **a version update** | both, after the contract files sync | the update reports it |
| **a page edit** | that page's linter, via the edit hook | the errors land in-context the same turn |

Checks that need the whole tree cost a walk of it, so the NODE linter puts
them behind `--cross` — the roster, a live job with no owner — and a single-page
write skips them. The OBJECTIVE linter has no such flag: `O6` and `O12` both
read every objective page, on every write. That is affordable because
`objectives/` is a handful of files where `nodes/` is hundreds, but it is a
different rule, not the same one.

### 5 · Gates — refuse the write

The reminders above inject text; these refuse. Each git hook carries a named
environment escape (`SKIP_RECORD_LINT`, `SKIP_SRC_INDEX`, …), because a gate
with no way past it gets disabled wholesale the first time it is wrong; the
escape has to be typed, which is the difference.

| gate | fires on | refuses |
|---|---|---|
| `commit-msg` (git hook) | every commit | a prefix off its layer; an `exp(<node>)` naming a node with no `experiments/<node>/`; a `nodes/` commit with no `Entry: <id>`; an `objectives/` commit with no `Objective: O<nn>`; one commit staging both — a route change is its own commit (§6) |
| `pre-commit` (git hook) | every commit | a `project_memory/` commit off the default branch; staging a record page that does not lint; a commit touching `src/` while `src/INDEX.md` is behind it (§3) |
| `record_sync.sh` (the record bus) | every record write | a page that does not lint, under a lock shared with the scanner |
| `bootstrap`'s acceptance gate | the end of setup | reporting success before the self-tests and both linters pass |
| every launcher's pre-flight | every recorded launch, all four venues | a launch with no `ENTRY` named; one naming an entry but no phase (`PHASE`/`ROLE`, or `NO_OBJECTIVE=1`) — `record_submit --check`, before anything runs; and a recorded launch from a linked worktree, whose logs die with it |
| `land_and_launch.sh` | landing and launching in one breath | a dirty branch, main onto itself, a branch that will not rebase cleanly — and it holds one lock across rebase → merge → launch, because main's WORKING TREE is what the launcher reads to build its header (§10, sharing the repo) |
| `worktree_retire.sh` | retiring a worktree | removal while any process still has its cwd inside. The one gate that is not reached by default: nothing wraps plain `git worktree remove` |

**How the two git hooks reach git without displacing the project's own.**
Setting `core.hooksPath` is the only way to ship a hook with a project, and it
has one well-known cost: git then ignores `.git/hooks/` entirely, so a
pre-commit framework, git-lfs or a hand-written pre-push that was already
installed stops running, silently. The hook directory therefore holds a
dispatcher, and every standard hook name in it is a link to that one file. The
dispatcher runs research-note's own check first — `research-note/pre-commit`,
`research-note/commit-msg`, a refusal there ends the event — and then hands the
event on to the hook directory that was active before install, with arguments,
stdin and exit code intact: `research-note.previousHooksPath` when the project
had a `core.hooksPath` of its own, else the repository's `.git/hooks/`. A hook
added there later runs too, because the target is resolved at run time, not at
install. The hook in flight is marked in the environment, so a forwarded hook
that runs git cannot re-enter the same hook, and a forward that resolves back to
the dispatcher's own directory stops. `githooks_install.py` lays all of it,
migrates the pre-dispatcher layout, `uninstall` puts `core.hooksPath` back, and
`status` is what doctor prints. The dispatcher is POSIX sh because macOS's
`/bin/sh` is bash 3.2.

### 6 · The scanner and the board — after the fact

A fixer (a session-started daemon; its own state in `.fixer/` — the record lock
and the rest of the CORE state are in `.research-note/state/`, so a project
without a fixer still has somewhere to lock) each cycle
pulls finished logs and data back (`remote.sh pull`), refreshes the remote queue
snapshot, runs both linters, regenerates the board, and where a page and the
world disagree raises `attention:`. **It repairs nothing** — status moves are
the watching session's (§8, §9); the record has one live instance with one
door. That is a SETTING, not a structural guarantee, and the distinction
matters: the cycle carries two agent tiers (`format`, `analyze`) and both ship
disabled in `fixer/config.json`, because the bus lints every write and every
venue records at launch, so an unattended agent has nothing left to repair.
Turning one on puts a second writer on the record — which is why it is off, and
why "it repairs nothing" is a line to re-read whenever that config changes.

The board is a **view, never a source**: `dashboard.html` is rewritten from the
pages every cycle and is gitignored. It renders the node roster, the attention
list, the live queue and the review backlog, and prints its own generation time
so a reader can tell an empty view from a stale one.

### The scripts these layers are made of

Every one is a separate process, so it reads the newest version on disk and
needs no reload to be current:

| | |
|---|---|
| `check_node_page.py`, `check_objective_page.py` | the two linters (layer 4) |
| `record_sync.sh` | the record bus — the one write path onto `project_memory/` |
| `record_submit.py` | the post-submit record for one launched job, called by the launcher |
| `remote.sh` | the whole cluster bridge (§8) |
| `lib_state.sh` | the shell twin of `project_config.state_dir()`: the core runtime state directory `.research-note/state/` — the record lock, the land lock, the harvest stamps, the bus's put backups — created with its nested `.gitignore` on first use; core state lives here and not in the fixer's `.fixer/` |
| `contracts.py` | generates the four contract files — the plugin's template plus the project's own `.research-note/rules/<x>.md` — carries an appendix from the old boundary scheme into the rules file once, and leaves a file edited in place alone with a CONFLICT line (layer 1) |
| `githooks_install.py` | lays the git hook directory — the dispatcher, research-note's own gates under it, one link per hook name — remembers the hook directory that was active before and forwards every event to it; `uninstall` restores it, `status` is doctor's view (layer 5) |
| `gen_index.py` | regenerates both rosters: `_index.md` and `src/INDEX.md` (`--record` / `--src` for one; the bus regenerates the record roster into the same commit) |
| `harvest_check.py` | the harvest safety net — J3, age-gated, objective-tagged; the hook's engine and the Monitor's poll |
| `gen_dashboard.py`, `watch_dashboard.sh` | the board, a regenerated view |
| `bootstrap_project.py`, `update_projects.sh`, `doctor.sh` | lay a project down, carry it to a new version, verify every wire either laid (§11) |
| `project_config.py` | reads and validates the project-owned layout, commit layers and optional features |
| `projroot.py` | resolves the project root one way for every script, loudly |
| `hook_dispatch.py` | the engine behind every hook of layer 3 — one process, one switch |
| `wiki_sources.py` | walks the record once for `wiki-compile`: the `closed` gate, the citation tag and the staleness hash in one pass (§7) |
| `land_and_launch.sh`, `worktree_retire.sh`, `worktree_sparse.sh` | the worktree transaction, the occupancy check, and the sparse checkout that keeps a worktree recordless |
| `lib_paths.sh` | one declaration of the developed libraries, serving both halves of §8.2 — the log header records them, the check compares them |
| `bump_lib.sh`, `julia_variants.py` | move an editable fork's pin; hold a Julia variant to containment (§8) |

### Cutting across all six — how several agents share one repo

**The record is serial, the code is parallel.**

- **One live record, one door.** `project_memory/` exists once, in the main
  checkout on the default branch — which therefore never switches branch. Writes
  go through the bus, which takes a baseline and refuses a concurrent edit rather
  than overwriting it. A worktree DOES carry a copy of the record — the full
  checkout at its branch point, stale from that moment on (since 0.13.45 an
  EnterWorktree-created worktree is made SPARSE — no `project_memory/`, no
  `wiki/`, the cluster clone's exclusion applied at home — so the copy
  survives only in hand-made worktrees) — and every mechanism ignores it: the bus and `record_submit` resolve the main checkout through the
  common git dir, and the harvest hook stays silent inside a worktree.
- **One entry, one writer.** Whoever launches a probe writes that entry — one
  writer per entry; one agent writes as many entries as it launched.
- **A code-editing agent gets its own worktree** — landing is `merge --ff-only`,
  so main only advances; a diverged branch rebases onto main first (never a
  back-merge — the commit-msg hook waves `Merge` subjects through unchecked,
  so a merge commit riding into main escapes the layer partition). Non-record
  main-side changes are handed to a main-checkout session, never carried on
  the branch. This stays a HARD gate (the background harness refuses shared-
  checkout edits), not doctrine: the failure it prevents — a formal run
  launched over another agent's half-edits — is recorded as legitimate and
  never fails loudly, which is exactly the gate criterion.
- **Formal runs launch from main.** A branch smoke certifies only the impl plus
  the `src/` it branched from, so "ready to run" means merged and re-smoked on
  the merged state.

---

## 11. Setup — one command

**Principle: a mechanical step belongs in a script; a judgment call belongs in
the skill.**

`bootstrap_project.py` lays down the core project in one idempotent run: the layout,
the five `.claude/` contract files (four `CLAUDE.md` siblings and
`framework.json`), core `settings.json`, the eight contract symlinks
(four files × the two names the two agents look for, §12), the
githooks — a dispatcher that runs research-note's gates and then the hooks the
project already had (§10.5) — with `core.hooksPath` set, the auto-memory wiring,
`.gitignore`, `_index.md`, the board, then the acceptance gate. The versioned
`.research-note/project.json` enables optional fixer, HPC, editor and
cross-agent support. Their setup persists the choice instead of changing only
one bootstrap run. The fixer is a detached daemon — earlier
versions installed a cron line BESIDE it, and two schedulers for one job
serialize on the same lock, so the second only ever loses the race, while
writing the user's global crontab to do it. HPC adds its environment, submit
templates and remote permissions only when enabled.

It deliberately leaves to the skill everything requiring judgment: the project's
mission paragraph, which domain libraries belong in log headers, the environment
pins.

`update_projects.sh` does the same for an upgrade — pins every scope and
*verifies by reading the pin file* rather than trusting a success line, syncs the
contract files, merges the permissions the template gained, then runs doctor and
the linters. It works from an **ownership table** (`project_config.OWNERSHIP`,
printed under `--dry-run`): every managed path has one owner — framework,
project, mixed, or runtime state — and the owner fixes what an update may do:
a framework file is regenerated or copied, a project file is never written, a
mixed file has the framework's half merged in and the project's kept, state is
left alone. A project from before the declaration is migrated ONCE, with every
integration on, and a disabled integration is retained exactly as it is rather
than repaired. What it cannot decide it counts and leaves: each `conflict` line
is a mixed file whose halves a person must sort, and nothing there is
overwritten. A Claude-only or Codex-only machine takes the same command; the
agent that is absent prints one line and the run carries on. The four contracts are regenerated by `contracts.py` (§10.1) —
a project's own rules live in `.research-note/rules/` and never share a file with
the framework's text, so there is nothing to tell apart; the
git hooks are refreshed through `githooks_install.py`, which keeps forwarding to
the project's pre-existing hooks and leaves a pre-declaration `commit-msg` alone
until its layer rows have moved into `.research-note/project.json`.
`doctor.sh` verifies every wire either script laid and prints the fix for
whatever is not yet true. It is split the way the project is: the CORE —
plugin root, project configuration, record layer, git hooks, the project's own
environment — is checked for every project; an integration (fixer, HPC, editor,
the other agent) only when `.research-note/project.json` enables it or the
caller names it (`--fixer`, `--hpc`, `--editor`, `--cross-agent`; `--core` for
the core alone). A disabled integration is neither started, required nor
reported broken — it is listed as not checked.

**The compatibility matrix.** `scripts/tests/test_compat_matrix.py` runs the
real bootstrap and the real updater against real repositories, one test per
row of the plan's release gate: an empty directory as a local-only project; an
existing repository with its own layout and its own hooks, before and after an
update; a project from before the declaration migrated once; a machine with no
agent CLI; the fixer and HPC present only when asked for; setup and update
re-run to no diff. It is what "works in a project research-note did not
create" means here, and a row that stops passing is a compatibility regression
by definition.

**Resource detection — what it does NOT do.** Setup detects the machine's SHAPE,
not its CAPACITY: whether pytest is installed, which editor extension
directories are present. It does not discover GPUs, partitions,
queue limits, node memory or account codes — `hpc.env` is hand-filled and the
`.slurm` templates ship with placeholders. The consequence is visible: doctor can
only *warn* that no partition is declared, because nothing ever looked. Closing
that would take a requirement-driven setup — asked-for resources deriving the
declarations — which is deliberately not built.

---

## 12. Two agents, one plugin

**Responsibility: let Claude and Codex work the same project, off one core, and
never let a machine end up half-updated.**

The framework is agent-neutral by construction — the record is files, the gates
are git hooks, the linters are processes — so the only thing that has to be
dual is the packaging. Everything below exists because the two CLIs keep
separate caches, separate registries and separate ideas of where a contract
lives.

**One core, two manifests.** `plugins/research-note/` is the package;
`.claude-plugin/plugin.json` and `.codex-plugin/plugin.json` are two views of
it. Two marketplaces declare it — `.claude-plugin/marketplace.json` as
`rzchi`, `.agents/plugins/marketplace.json` under the same name — and both
resolve to the same repository. One name on both sides is a convenience, not a
guarantee: the marketplace name is the INSTALLER's, whatever their
`marketplace add` registered, so every selector the framework builds is read
back from the agent's own registry rather than spelled. A test holds the two manifests to one version,
because equal names on different versions is the failure that is hardest to see
from inside either agent.

**One contract, two names.** Claude reads `CLAUDE.md`, Codex reads `AGENTS.md`.
Each of §10.1's four files is therefore symlinked twice into the directory it
governs — eight links, four targets, one home per rule. `memory/claude/` and
`memory/codex/` are symlinks onto `memory/shared/` for the same reason: what
one agent learns, the other has, and the alternative is two memories that
diverge on the same project.

**Skills follow each agent; scripts follow one pin.** A skill is loaded by the
CLI that owns it, from that CLI's own cache, and stays loaded until that session
reloads — there is no way to make one agent's session pick up the other's. Every
SCRIPT resolves through `research-note.pluginRoot`, a single git config per
project, so the linters, the bus, the launchers and the fixer are the same files
whichever agent is driving. That split is deliberate: the half that can be
version-skewed is the half a session can re-read, and the half that must not be
skewed is a path both sides share.

**Push is the channel, not the tidying step.** Each agent's marketplace is a
clone of the plugin's remote, so an unpushed commit is invisible to every one of
them — on the maintainer's own machine included. A maintainer edits a checkout,
commits, pushes; a user pulls; from `update_projects.sh` onward the two run the
identical command, deliberately, so the path everyone else is on stays exercised.

**Which agents to update is detected, never declared.** The updater looks for
each CLI on PATH and updates what it finds; a Claude-only, a Codex-only and a
both machine take the same command, and the missing side is reported rather than
failing the run. Where both are present it then requires PARITY — the same
version *and* the same source commit, since equal version labels on different
commits are not parity.

**Two asymmetries the code has to know about.** Claude keeps project-scoped
plugin rows and Codex does not, which is why project discovery goes through a
neutral registry (`~/.config/research-note/projects.json`) that bootstrap
maintains — otherwise a Codex-only machine could not find its own projects
without scanning `$HOME`. And Claude's native marketplace refresh may delete and
re-clone, which is correct for a downloaded marketplace and destructive when the
marketplace path is an editable checkout of your own repo; the updater advances
a clean git-backed Claude marketplace with `git pull --ff-only` instead, and
stops that side rather than cleaning it if it is dirty.
