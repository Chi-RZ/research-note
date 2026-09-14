---
name: plan
description: Use when a new NODE or a new task PAGE has to be created — naming, the impl contract, page frontmatter, the roster, and the gate a new node must pass before any research page opens. Appending an entry to an open page needs no skill.
---

# research-note:plan

The record-object manual: how to bring a node or a page into existence so every
join key lines up. **What** to open — node, page, entry, phase — is decided by
the root contract's layer table, not here.

## Step 0 — Read-first (root contract)

Run it as the root contract states it; the list is there, not here. The
consequence specific to planning: a page that already covers the task is a page
you do not open.

## Open a new node

When the identity criterion (root contract: does some knob setting reproduce
the old recorded result?) does not settle node-or-not, **ask the user** — once
entries close on the new node the split is permanent.

1. **Name it after the mechanism**, not the experiment or the result:
   `peps_sma_clifford`, not `peps_v2` or `clifford_test`. The name is the
   global join key (node folder, page folder, `experiments/`), and it names the
   algorithm — the problem instance it runs on names the group.
2. **Create the impl** under `experiments/<node>/impl/` — the callable
   functions a run script invokes, plus a declaration of **which knobs exist**
   and never their values. A knob may carry a default only if it is bound to the
   structure it came from, never restated as a literal. Pre-declare the axes
   you mean to explore, so small variants stay recipe-space. Follow whatever
   form this project already uses; the framework fixes neither the language
   nor the file.
   Open the node's first group beside it — `experiments/<node>/<group>/`, named
   for the problem instance this node first runs on — and put the run script
   there. A node opens with one group from the start, so its outputs sit at
   their final path before the record cites them.
3. **Create `project_memory/nodes/<node>/node.md`** — the same frontmatter as
   any page (`node:` equal to the containing folder, `task:`), then entries
   only; `N1` checks both. Its first entry is the **gate** (below). The gate's
   Motivation names the parent it forks from — or the node it supersedes; the
   old node is never edited.
4. **Regenerate the roster**: `gen_index.py` adds the row and assigns the node
   its number — the `<nn>` of every entry id on it. Never hand-edit
   `_index.md`.

## The gate

A node may not be believed before its first entry shows it reproducing a
reference. Three things must hold before a research page opens:

1. **The impl is correct** — on the smallest meaningful instance it matches
   the most rigorous reference available (ED where enumerable, an analytic
   limit, the parent cell it forks from, an established gated node) to a
   tolerance written down BEFORE the run.
2. **The knobs behave** — each declared knob, moved alone on a small instance,
   changes the result in the direction the mechanism claims.
3. **Production-scale runtime is sane** — extrapolated from the small runs.
   If not, stop and report.

`references/benchmark_knowledge.md` (in this skill) holds the reference ladder
per task type; when nothing matches, ask the user how to verify this node type
and add an entry there afterwards.

Pre-write the whole ladder on `node.md` as `### Entry:` sections before any
heavy compute — each with `- **Id:**`, `- **Status:** open`, Date, Code,
Motivation (the pass criterion belongs in its question), Recipe — then execute
one step at a time through the lifecycle. A failed criterion: stop,
investigate, tell the user — never loosen the threshold after seeing the
number. A fix that edits the impl before any entry closes is the node still
being born — say so; after an entry closes, the identity criterion decides
between a validation entry and a new node.

## Open a new page

Create the page at the level its task lives on:

- **Grouped task** (a scan or campaign belonging to one problem instance) →
  `project_memory/nodes/<node>/<group>/<page>.md`, under the same group name the
  instance carries in `experiments/`. The grouping folder is the project's, not
  the framework's.
- **Node-level task** (a cross-group comparison) →
  `project_memory/nodes/<node>/<page>.md`. A comparison page is owned by the
  node at its centre; its own entries run only that node — a rival needing a
  fresh run gets that entry on the rival's own page, cited here by id.

```yaml
---
node: <node>          # must equal the containing folder
task: <one sentence — what this page is doing to which node on which instance>
---
```

Name the file after the task — an instance name (`heis_tri.md`) for a "run it on
this one" page, a campaign name for a tuning page.

## Then place the work

- **Serves an active objective's Goal** → a phase on that objective's Plan;
  its loop picks it up.
- **A new goal whose results will rewrite the plan** → route to
  `research-note:objective`.
