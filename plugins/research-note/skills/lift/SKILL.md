---
name: lift
description: Use when a capability implemented inside one or more experiments should become a designed, tested interface in src/ — a second consumer has appeared, or discovery turned up prior art that should be canonicalized before you write another local helper. Interface design, not file moving; strictly additive.
---

# Lift Skill

You are promoting a **capability** into `src/`. The experiment's existing
implementation is a reference for correctness, not the artifact being
moved. The deliverable is a new `src/` module plus a mirrored test —
nothing else changes.

This skill prescribes no domain vocabulary and no language. Where it needs a
convention — where tests live, how they are named and run, how two results are
compared — the authority is the project's own contract and its existing tests.
Read one before you write one.

## Core Rules

1. **Lift the capability, not the code.** The experiment script is a
   correctness reference. The src implementation is designed for reuse,
   so its API may differ from any single experiment's local form.
2. **Strictly additive.** No experiment scripts are modified by this
   skill. Old code keeps working unchanged.
3. **1-to-1 src↔test mirroring**, in whatever spelling the project already
   uses — one test file per source file, at the mirrored path, named the way
   its siblings are named. The project contract states the rule; the existing
   tests show the form.
4. **Equivalence-pinned tests.** Every lift's test suite must include at least
   one check that pins the new implementation against the reference on the
   same inputs, **at the smallest input the capability accepts** — the
   cheapest case that still exercises the thing, not a production-scale run.
   Inline the reference in the test so it does not depend on the experiment
   file staying unchanged.
5. **Dispatch discipline.** Tests follow the venue (root contract): on a
   Slurm cluster through the scheduler on a compute partition — never the
   login node; on a bare server a quick foreground run is the right call.
6. **One `feat:` commit** here: `feat: lift <capability> → src/<path>` adds
   src + test (+ regenerated `src/INDEX.md`) together. This skill is strictly
   additive — no experiment changes now; when an experiment later adopts the
   interface, that lands as its own `exp(<node>):` commit naming this one
   (the root contract's `feat:` + `exp:` pair).

## Workflow

Create one TodoWrite task per step.

### Step 1 — NAME the capability

State the capability as a **concept in the project's own terms**, not a
function name, and not a description of the code that happens to implement it.
A good name says what is computed and under which convention; it survives the
implementation being rewritten.

The test: a name is good if someone who never read the experiment could tell
whether a given function is an instance of it. "Lift `_helper_3`" fails that;
so does "lift the fast path".

The concept name should fit in one sentence. If it doesn't, the lift is
probably too big — split it.

### Step 2 — SURVEY existing implementations

List every place the capability currently appears, in this order:

1. **Third-party libraries already in the project.** Especially the project's
   **domain library** — the dependency named at the top of `src/INDEX.md`,
   which holds canonical machinery that often subsumes whatever an experiment
   hand-rolled. Grep its source for the concept's vocabulary.
   If it provides a clean realization, the "lift" reduces to a convenience
   wrapper or — better — a one-line caller-side change that uses the library
   directly. **Do not re-implement what the domain library already gives you.**

2. **`src/`** — grep for any existing realization, and read `src/INDEX.md`
   for the function index.

3. **`experiments/`** — every place the capability appears, across all nodes.

For each occurrence record:
- File and approximate line range
- Form (top-level procedural, closure over locals, function with explicit args)
- Differences — parameterization, conventions, return type

The survey is what surfaces design decisions. If two experiments disagree
about a convention, that disagreement must be resolved in the API design step,
not papered over.

Halt if:
- A canonical realization exists in the **domain library** (or another
  already-installed one) — the lift collapses to a thin wrapper or no wrapper.
- The capability already exists in `src/` with a stable API → this is a
  *consolidation*, not a lift.
- The "capability" is really multiple distinct things → split into
  separate lifts.

### Step 3 — DESIGN the API

Propose:
- Function name(s) — one capability may decompose into 2–3 small functions
- Parameter list: explicit arguments, no closures over experiment-level state
- Return type
- Defaults and conventions, stated rather than implied
- Target path. `src/INDEX.md` is the authority on where each capability lives
  in THIS project — the framework prescribes no module taxonomy. Put the new
  capability where its siblings already are; if it has no siblings, that is a
  question for the user, not a new directory you create quietly.

**Halt for user approval before writing code.** The design step is the
high-leverage moment of the lift — getting it wrong cheaply at this stage
is much better than refactoring after the lift lands.

### Step 4 — IMPLEMENT in src/

Write the agreed API at the agreed path. Implementation may borrow
freely from the experiment's existing form, but:
- Replace closures over ambient state with explicit arguments.
- Replace inline procedural code with function bodies.
- Use the agreed conventions, not the experiment's idiosyncratic ones.
- Add a short docstring stating *what* the function computes and any
  convention a caller could get wrong — the ones that are invisible at the
  call site are exactly the ones to write down.
- No multi-paragraph docstrings; no comments restating what well-named
  identifiers already convey.

Regenerate `src/INDEX.md` (`gen_index.py`) — it is a generated view,
never hand-edited; the new function's docstring first line becomes its row.

### Step 5 — TEST (mirrored, with equivalence check)

Create the mirrored test file. Required coverage:

**(a) Invariant test** — something the function promises independent of any
reference: a conserved quantity, a documented shape or type, a round trip that
returns what it started from, a known input whose answer is known.

**(b) Equivalence test (REQUIRED)** — at the smallest input the capability
accepts, compute the same quantity via the new src API and via a
self-contained inline reference (the relevant lines copied from the
experiment, or a minimal known-good implementation), then assert they agree.

Take the comparison idiom and its tolerance from the project's existing
tests rather than inventing one; a tolerance looser than a sibling test's
needs a sentence saying why.

Run per the venue — through the scheduler on a cluster, foreground on a bare
server.

Must pass before committing. If the equivalence test fails, the lifted
implementation has drifted from the reference — fix the implementation, not
the test, unless you have a deliberate and stated reason for the divergence
(in which case document it in the docstring).

### Step 6 — COMMIT

One commit, in the main repo, staging the new source file, its test, and the
regenerated `src/INDEX.md`:

```
feat: lift <capability description> → src/<path>
```

No experiment-side changes. Stop.

## What This Skill Does NOT Do

- **Does not modify experiment scripts.** Old code keeps working. Migration
  is opportunistic and happens outside this skill.
- **Does not delete the experiment's local copy.** The experiment's version
  is the reference the test pinned against; it may drift later, which is fine
  because the canonical implementation now lives in `src/`.
- **Does not enforce equivalence at production scale.** Smallest-input
  equivalence is enough to pin correctness.
- **Does not invoke other skills.** Brainstorming, planning and writing plans
  are separate. The lift is a focused mechanical-with-design-step operation.

## When to Halt and Ask

- The capability decomposes into more than 3 functions → too big; split.
- The survey reveals a genuine disagreement between experiment forms about a
  convention — not a design choice you can make alone; ask which is canonical.
- The destination doesn't exist and the right level is unclear → ask before
  creating new directories.
- The equivalence test fails after a careful implementation → the experiment's
  form may carry a hidden bug or an unstated convention; ask before "fixing"
  either side.

## Anti-Patterns

| Tempting move | Why it's wrong |
|---|---|
| "Skip the equivalence test — the function obviously works" | The equivalence test is the link to the reference; without it the lift has no anchor to the code that was known to work |
| "Lift this 200-line procedural section all at once" | Too big; bugs hide in the seams between sub-capabilities. Split. |
| "Also rewrite the experiment to use the new API" | Out of scope. Migration happens later, opportunistically. |
| "Skip the design step — the API is obvious" | Almost never true. Five minutes of design review prevents weeks of API churn. |
| "Keep the closures so it matches the experiment exactly" | The closures are why the code wasn't already reusable. Parameterize properly. |
| "Name it after the algorithm it currently uses" | The name outlives the implementation; an interface named for today's method has to be renamed when the method changes |
