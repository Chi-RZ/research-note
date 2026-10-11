---
name: objective
description: Use when the user hands over a multi-task research goal spanning sessions — intake onto a durable objective page, run the phase loop, or report status. A single probe is research-note:plan.
---

# research-note:objective

The user states a goal once and the loop does the decomposing, launching,
reviewing and re-planning. **All durable state lives on the objective page**
(`project_memory/objectives/<slug>.md`, format in `project_memory/CLAUDE.md`):
sessions are stateless workers — a fresh session resumes exactly from the
page, and the user watches the page, not the conversation.

Three modes: `new` (guided intake), `run` (the loop), `status` (report only).
Re-planning is a step INSIDE the loop, not a further mode.

## research-note:objective new — guided intake

The user writes nothing; they answer. Ask, at most, and one round only:

1. **The goal, in their words.**
2. **What counts as success** — then make it concrete yourself: quantitative
   (reference + tolerance) where a reference exists, a settled qualitative
   verdict otherwise; which instances; the statistics that make the claim
   stand (sample budget sized to the effect, repeat policy). Reflect it back.
3. **budget and wake-me-if** — propose defaults, they set them:
   `budget: <per-run and total>`; `wake-me-if: success met | 2 consecutive
   phases settle nothing | budget exceeded`.

Their answers become `## Goal` (user-controlled after intake, O4). Frontmatter:
`id: O<nn>` first — the next free number, READ OFF `_index.md`'s Objectives
section (regenerate with gen_index.py if stale; a project's FIRST objective
finds no section and takes O01; O12 refuses a duplicate) — then
`status: active`, `created`, `budget`, `wake-me-if`. Read-first (root
contract), then draft the initial `## Plan` as phase blocks — at intake a
phase is its header only:

```
- [ ] **P<n> — <the question this phase asks>** (<cost>[ · needs: P<i>])
```

`## Verdict` starts empty but present. Write the page through the record bus:
`scripts/record_sync.sh -m "memory: …

Objective: O<nn>" <files>`; a session that cannot edit the checkout edits a
SCRATCH COPY under /tmp and hands it over with `record_sync.sh put -m "…" -b
<sha256|new> <page> <scratch-copy>`, `-b` naming the version it started from.
Execution starts only on `run`, after the user confirms the Goal.

## research-note:objective run [slug] — the loop

**Resume, always first**: read the page, then re-sync it against ground truth
(the task pages' entry statuses, live jobs) — a session that died
mid-iteration leaves the page at most one iteration stale.

**Cover outstanding background work, second.** Foreground-only work needs no
Monitor. When this session owns background or batch jobs, keep ONE persistent
Monitor for all of its active objectives (poll every 2-5 min). A resumed
session re-derives those objective ids from their running entries; repeat
`--for` once per objective:

```bash
# PLUGIN resolved INSIDE the poll (a path baked in at arming freezes this
# watcher on that version). Each --for scope is computed by the script per
# poll — never a grep frozen at arming. Reasons in full: hpc-submit,
# "Watch".
PLUGIN="$(git config --get research-note.pluginRoot 2>/dev/null)"
[ -d "$PLUGIN" ] || { echo "Restore this project’s plugin lock before running tools" >&2; exit 2; }
bash "$PLUGIN/scripts/remote.sh" queue >/dev/null 2>&1   # only if the project declares a remote
python3 "$PLUGIN/scripts/harvest_check.py" --min-age 0 --for O<nn> --for O<mm>
```

Later launches under an already covered objective require no change. Replace
the Monitor only when this session's set of objective ids changes, and stop it
when none of those objectives has background work outstanding. The
turn-boundary harvest hook stays as the net behind it (entries unharvested for
15+ min, project-wide).

**Re-plan, whenever the Plan is exhausted or a finding invalidated it.** The
gate: is the Goal still the goal? An agent-proposed change to the success criterion needs the user's decision.
For an explicit user revision of this objective, edit Goal and record the
authorization with `objective_state.py approve-goal <page> --instruction
'<user instruction>'`, then save through the bus. A separate goal routes to `new`. Read-first (root contract), plus this objective's
own page and the entries it links — never from conversation memory. The Plan
is rewritten freely; a phase that closed a direction keeps its reading, a
phase no longer on the route goes, and git holds it.

**The page is a two-way interface.** Re-read it before EVERY write-back: the
user may have edited it while jobs ran, and their edits are ground truth —
frontmatter and Goal are theirs outright. `status: closed` → stop and finalize
the Verdict.

Each iteration:

1. **Take ALL ready phases** — every unchecked phase whose dependencies
   (`needs:`, or the phase above when absent) are met launches at once, one
   agent each. Pre-launch contract, checked per entry BEFORE spending compute:
   (a) the operating point can DISCRIMINATE the expected effect — statistical
   s.e. against claimed size; (b) the reference or baseline exists at the same
   instance and recipe, or is scheduled alongside; (c) the sample budget makes
   the error bar small against the expected effect; (d) the predicted result
   lies inside physical bounds; (e) the repeat/seed policy is declared and
   sized against the KNOWN run-to-run scatter — an effect smaller than that
   scatter needs replicates or it is not a result; (f) the record does not
   already hold this point — read-first, the one item no linter can check. A
   task failing the contract is redesigned, not launched.
2. **Place the work in the record yourself.** The root contract's layer table
   is the decision — and you make it without narrating it: the entry's
   Motivation IS where the reasoning lands. `research-note:plan` only to
   CREATE a node (gate included) or a page; a new entry on an open page needs
   no skill; every launch via hpc-submit. A dependency update first maps its
   diff to this objective's imports and claims, then runs only the smallest
   affected test or sentinel; the root contract owns when that expands. A
   node-or-not decision the criterion does not settle, and a budget overrun,
   STOP the loop and ask.
3. **The entry line is written by the launcher.** Given `PHASE=P<n>` and
   `ROLE="<the role it plays>"`, `record_submit` writes
   `- [entry name](page.md#entry-slug) \`<id>\` — <role>` into the phase block
   in the same lock as the job row, idempotently, and commits it with its own
   `Objective: O<nn>` trailer.

   Still YOURS the same turn: the phase's `▶` reading, if this launch changes
   it. Write the entry line by hand only when the launcher reported it did
   not — `NO_OBJECTIVE=1`, an ambiguity it refused to guess, or a run that
   reached the record another way — and then through the record bus, trailers
   as usual (`Entry: <id>` / `Objective: O<nn>`, never both in one commit).
4. **Watch your own jobs** — a foreground run stays in this turn. A background
   or batch launch joins this session's existing Monitor scope, creating or
   replacing that one Monitor only when its objective-id set changes. Each
   wake: analyze THAT entry in-session (research-note:analyze), write it back;
   the Monitor stays armed while owned background work remains. The fixer
   never analyzes on the loop's behalf; if the loop dies with work in flight
   it stamps `attention:` so a dead loop never looks live, and the harvest
   hook shows the orphans to whoever comes next.
5. **Review, at phase granularity**: re-read the key numbers from cells/logs;
   compare against the phase's question.
6. **Write back the review, then re-read the page before taking the next
   phase** — its own result may have invalidated the phase it was about to
   take, and with several agents running the write is the only thing the
   others see. The entry line gains its date — the day it concluded; the ▶
   line is written or rewritten in place, one sentence, no number, no
   mechanism, no figure, no table (O9). **The checkbox flips when all the
   phase's entries concluded** (O13, linted in both directions) — the ▶ line
   gets written every time and the box is the step that gets skipped. At
   milestones update `## Verdict`; the record bus maintains its review count
   (O8). O11 is a length reminder. When a changed entry conclusion leaves the
   phase reading valid, record the completed review with
   `objective_state.py review-phase <page> P<n> --note '<review finding>'` (O7)
   and save through the bus.
   **A probe the analysis spawned joins some plan** (O6): the SAME phase when
   it serves that phase's question — a control or diagnostic decided after the
   first result included — or a new phase with `needs: P<n>` when it starts a
   new one.
7. Loop. `wake-me-if` fires → stop: write the Verdict line saying why, set
   `attention: <one line — what needs the user>`, commit, and remove this
   objective from the session Monitor's scope; stop the Monitor if its scope
   is now empty. The harvest hook covers the pause. The same stop applies when
   the user closes the objective. Clear `attention:` and restore its scope if
   background work remains when the loop resumes; only the user sets
   `status: closed`.

## research-note:objective status [slug]

Read-only: report Plan progress (checked / in flight / ready / waiting on
dependencies), Verdict against the Goal, awaiting-review count. No launches,
no page edits.

## Rules

- The page is the ONLY durable state; every write goes through the record bus,
  which serializes, lints and commits — an iteration is not done until its
  write-back landed.
- **Keep what the machine did; replace what only we believed.** Entry lines,
  checkboxes, user ✓s stay; readings and the Verdict are always shown in their
  current version only.
- A direction decided in conversation is not recorded until it is on the page.
  Before its entries exist that home is the phase header; once they exist it
  is each entry's Motivation. Interpretation prose goes to `note/<node>.md`.
- Review cascades: the user's ✓ on a phase closes every analyzed entry on its
  entry lines — one approval, one batch.
- A closed work list (a benchmark grid, a seed re-run — no finding rewrites
  it) runs the same loop with the re-plan step idle; a finding that would
  rewrite the list proves it was a full objective — stop and say so.
