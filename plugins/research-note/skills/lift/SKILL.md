---
name: lift
description: Use when a capability inside one or more experiments should become a designed, tested interface in the project's reusable library layer. A second consumer appeared, or discovery found prior art before another local helper was written. Strictly additive.
---

# Lift Skill

You are promoting a **capability** into the project's reusable library layer.
Resolve the declared library, test, and experiment roots before choosing any
path:

```bash
python3 "$PLUGIN/scripts/project_config.py" role libraries
python3 "$PLUGIN/scripts/project_config.py" role tests
python3 "$PLUGIN/scripts/project_config.py" role experiments
```

Select the roots that contain the relevant code and its existing test
convention. The experiment implementation is a correctness reference, not the
artifact being moved. The deliverable is one new library module plus its
mirrored test.

This skill prescribes no domain vocabulary and no language. Where it needs a
convention — where tests live, how they are named and run, how two results are
compared — the authority is the project's own contract and its existing tests.
Read one before you write one.

## Core Rules

1. **Lift the capability, not the code.** The experiment script is a
   correctness reference. The library implementation is designed for reuse,
   so its API may differ from any single experiment's local form.
2. **Strictly additive.** No experiment script is modified and the
   experiment's local copy stays — it is the reference the test pinned
   against; it may drift later, which is fine because the canonical
   implementation now lives in the declared library root. Migration happens later,
   opportunistically, as its own `exp(<node>):` commit naming this one (the
   root contract's `feat:` + `exp:` pair).
3. **1-to-1 library↔test mirroring**, in whatever spelling the project already
   uses — one test file per source file, at the mirrored path, named the way
   its siblings are named.
4. **Equivalence-pinned tests.** Every lift's test suite includes at least one
   check that pins the new implementation against the reference on the same
   inputs, **at the smallest input the capability accepts** — the cheapest
   case that still exercises the thing; smallest-input equivalence is enough
   to pin correctness. Inline the reference in the test so it does not depend
   on the experiment file staying unchanged. Without it the lift has no
   anchor to the code that was known to work.
5. **Dispatch discipline.** Tests follow the venue (root contract): on a
   Slurm cluster through the scheduler on a compute partition; on a bare
   server a quick foreground run.
6. **One `feat:` commit** adds the library code, test, and regenerated
   capability index together.

## Workflow

Create one TodoWrite task per step.

### Step 1 — NAME the capability

State the capability as a **concept in the project's own terms**, not a
function name, and not a description of the code that happens to implement it.
A good name says what is computed and under which convention; it survives the
implementation being rewritten — an interface named for today's algorithm has
to be renamed when the method changes.

The test: a name is good if someone who never read the experiment could tell
whether a given function is an instance of it. "Lift `_helper_3`" fails that;
so does "lift the fast path".

The concept name fits in one sentence. If it doesn't, the lift is too big —
split it.

### Step 2 — SURVEY existing implementations

List every place the capability currently appears, in this order:

1. **Third-party libraries already in the project.** Especially the project's
   **domain library** — the dependency named at the top of the capability index,
   which holds canonical machinery that often subsumes whatever an experiment
   hand-rolled. Grep its source for the concept's vocabulary. If it provides a
   clean realization, the "lift" reduces to a convenience wrapper or — better
   — a one-line caller-side change that uses the library directly.

2. **Declared library roots** — grep for any existing realization, and read
   the first library root's `INDEX.md` for the function index.

3. **Declared experiment roots** — every place the capability appears, across
   all nodes.

For each occurrence record:
- File and approximate line range
- Form (top-level procedural, closure over locals, function with explicit args)
- Differences — parameterization, conventions, return type

The survey is what surfaces design decisions. If two experiments disagree
about a convention, that disagreement is resolved in the API design step,
not papered over.

Halt if:
- A canonical realization exists in the **domain library** (or another
  already-installed one) — the lift collapses to a thin wrapper or no wrapper.
- The capability already exists in a library root with a stable API → this is a
  *consolidation*, not a lift.
- The "capability" is really multiple distinct things → split into
  separate lifts.

### Step 3 — DESIGN the API

Propose:
- Function name(s) — one capability may decompose into 2–3 small functions
- Parameter list: explicit arguments, no closures over experiment-level state
- Return type
- Defaults and conventions, stated rather than implied
- Target path. The capability index is the authority on where each capability lives
  in THIS project — the framework prescribes no module taxonomy. Put the new
  capability where its siblings already are; if it has no siblings, that is a
  question for the user, not a new directory you create quietly.

**Halt for user approval before writing code.** The design step is the
high-leverage moment of the lift — five minutes of design review prevents
weeks of API churn.

### Step 4 — IMPLEMENT in the selected library root

Write the agreed API at the agreed path. Implementation may borrow
freely from the experiment's existing form, but:
- Replace closures over ambient state with explicit arguments — the closures
  are why the code was not already reusable.
- Replace inline procedural code with function bodies.
- Use the agreed conventions, not the experiment's idiosyncratic ones.
- Add a short docstring stating *what* the function computes and any
  convention a caller could get wrong — the ones invisible at the call site
  are exactly the ones to write down. One-line comments only where a
  well-named identifier does not already say it.

Regenerate the capability index (`gen_index.py --src`) — a generated view; the new
function's docstring first line becomes its row.

### Step 5 — TEST (mirrored, with equivalence check)

Create the mirrored test file. Required coverage:

**(a) Invariant test** — something the function promises independent of any
reference: a conserved quantity, a documented shape or type, a round trip that
returns what it started from, a known input whose answer is known.

**(b) Equivalence test (REQUIRED)** — at the smallest input the capability
accepts, compute the same quantity via the new library API and via a
self-contained inline reference (the relevant lines copied from the
experiment, or a minimal known-good implementation), then assert they agree.

Take the comparison idiom and its tolerance from the project's existing
tests; a tolerance looser than a sibling test's needs a sentence saying why.

Run per the venue. Passing is the completion criterion. If the equivalence
test fails, the lifted implementation has drifted from the reference — fix
the implementation, not the test, unless you have a deliberate and stated
reason for the divergence (documented in the docstring).

### Step 6 — COMMIT

One commit, in the main repo, staging the new source file, its test, and the
regenerated capability index:

```
feat: lift <capability description> → <library-root>/<path>
```

No experiment-side changes. Stop.

## When to Halt and Ask

- The capability decomposes into more than 3 functions → too big; split. Bugs
  hide in the seams between sub-capabilities.
- The survey reveals a genuine disagreement between experiment forms about a
  convention — not a design choice you can make alone; ask which is canonical.
- The destination doesn't exist and the right level is unclear → ask before
  creating new directories.
- The equivalence test fails after a careful implementation → the experiment's
  form may carry a hidden bug or an unstated convention; ask before "fixing"
  either side.
