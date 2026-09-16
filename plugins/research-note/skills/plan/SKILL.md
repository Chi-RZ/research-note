---
name: plan
description: Use when a new NODE or a new task PAGE has to be created — naming, impl, page frontmatter, the roster, and the gate a node passes before any research page opens. Appending an entry to an open page needs no skill.
---

# research-note:plan

How to bring a node or a page into existence so every join key lines up.
**What** to open — node, page, entry, phase — is the root contract's decision
("The record"), not this skill's.

## Step 0 — Read-first (root contract)

The consequence specific to planning: a page that already covers the task is
a page you do not open.

## Open a new node

When the identity criterion (root contract: does some knob setting reproduce
the old recorded result?) does not settle node-or-not, **ask the user** — once
entries close on the new node the split is permanent.

1. **Name it after the mechanism**, not the experiment or the result:
   `peps_sma_clifford`, not `peps_v2` or `clifford_test`. The name is the
   global join key (node folder, page folder, `experiments/`), and it names the
   algorithm — the problem instance it runs on names the group.
2. **Create the impl and the first group** — `experiments/<node>/impl/` and
   `experiments/<node>/<group>/` with the run script, laid out per
   `experiments/CLAUDE.md`. Pre-declare the knobs you mean to explore, so
   small variants stay recipe-space. The group exists from the start, so the
   node's outputs sit at their final path before the record cites them.
3. **Create `project_memory/nodes/<node>/node.md`** — frontmatter (`node:`
   equal to the containing folder, `task:`; `N1` checks both), then entries
   only. Its first entry is the **gate** (below), whose Motivation names the
   parent it forks from — or the node it supersedes; the old node is never
   edited.
4. **Regenerate the roster**: `gen_index.py` adds the row and assigns the node
   its number — the `<nn>` of every entry id on it.

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
investigate, tell the user — the threshold stands as written. A fix that edits
the impl before any entry closes is the node still being born — say so; after
an entry closes, the identity criterion decides between a validation entry and
a new node.

## Open a new page

Create the page at the level its task lives on:

- **Grouped task** (a scan or campaign belonging to one problem instance) →
  `project_memory/nodes/<node>/<group>/<page>.md`, under the same group name the
  instance carries in `experiments/`.
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
- **A new goal whose results will rewrite the plan** → `research-note:objective`.
