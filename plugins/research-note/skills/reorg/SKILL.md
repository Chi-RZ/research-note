---
name: reorg
description: Use when a capability already in src/ belongs somewhere else — it sits in the wrong module, a file has grown several unrelated responsibilities, or a lift placed it hastily and the right home is now clear. Strictly non-breaking — the old path keeps working through a re-export.
---

# Reorg Skill

You are **moving** a capability to a better home inside `src/`. Nothing
changes about what it does. The deliverable is: real code at the new path, a
re-export at the old path, updated tests, a regenerated `src/INDEX.md` — and a
passing test suite.

This skill prescribes no language. Where it needs one — the re-export idiom,
the test runner — the authority is what the project already uses; the examples
below are Python because that is the common case, and the shape they show is
what to reproduce elsewhere.

## Core Rules

1. **Non-breaking by design.** Old paths keep working through a re-export.
   Experiment scripts are never modified by this skill.
2. **One logical move per commit.** Never bundle two unrelated moves in
   one commit, even if both are small.
3. **Interface is frozen; implementation may improve.** The signature — name,
   parameters, defaults — the return type and the documented conventions must
   not change. The internals may get cleaner. The test suite is the behavioural
   contract: if every existing test passes, callers keep working automatically.
4. **The re-export is permanent until explicitly retired.** Do not schedule its
   removal here. Dropping re-exports is a separate later action the user
   decides.
5. **Dispatch discipline.** Tests follow the venue (root contract): on a Slurm
   cluster through the scheduler on a compute partition — never the login node;
   on a bare server a quick foreground run is the right call.

## The re-export pattern

At the old path, the definition is replaced by an import of the new one, so
every existing caller resolves to the moved code. In Python:

```python
from <new.module.path> import <Name>  # noqa: F401
```

If the old file exported several names and only some are moving, re-export
only those — leave the rest defined where they are.

If the entire old file is moving, replace its contents with a marked
whole-module re-export:

```python
# moved to <new.module.path> — kept for backwards compatibility
from <new.module.path> import *  # noqa: F401,F403
```

In another language, use that language's own re-export or forwarding idiom and
keep the two properties that matter: **the old path still resolves**, and
**the code exists once**. A copy at both paths is not a re-export — it is a
second implementation that will drift.

## Workflow

Create one TodoWrite task per step.

### Step 1 — IDENTIFY

State precisely:
- **What** is moving: which names, or the whole file.
- **From** where: current `src/` path and line range.
- **To** where: target `src/` path — it must already exist or be an obvious
  sibling of an existing file. Do not create new subdirectories without asking.
- **Why**: one sentence on why the target home is better.

Confirm: does the target already import from the source in a way that would
become circular after the move? If yes, halt and ask.

### Step 2 — MOVE

Copy the definitions **verbatim** into the target. Do not rewrite anything.
Place them logically — beside related code, not at the end of the file. Update
a docstring only where it names the old path.

Regenerate `src/INDEX.md` (`gen_index.py`) — never hand-edit it.

### Step 3 — RE-EXPORT

In the old file, replace the definition with the re-export (see the pattern
above). If other code in the old file called the moved name internally, point
those calls at the new path too.

### Step 4 — UPDATE TESTS

The test must mirror the new `src/` location, per the project's 1-to-1 rule:
move the test to the path that mirrors the new source path, and update its
import. **Do not change the test logic** — same assertions, same reference.

If the old test file is left empty, delete it; if it still holds other tests,
leave those in place.

### Step 5 — VERIFY

Run the full relevant suite per the venue. Both the new test location AND any
test that reaches the code through the old path must pass. If one fails:

- an import error → fix the re-export line;
- a logic failure → something changed that shouldn't have. Revert to the
  verbatim copy and re-check.

Do not commit until the suite passes.

### Step 6 — COMMIT

One commit, prefix `refactor:`, staging the old file, the target file, both
test files, and `src/INDEX.md` — nothing else:

```
refactor: move <Name> src/<old> → src/<new>
```

## What This Skill Does NOT Do

- **Does not change behaviour.** Logic, defaults and return types are frozen
  during a reorg.
- **Does not modify experiment scripts.** Old imports keep resolving.
- **Does not drop re-exports.** That is a separate, later, user-decided step.
- **Does not bundle multiple moves.** Each logical move is its own commit.
- **Does not create new `src/` subdirectories** without user approval.

## When to Halt and Ask

- The target path doesn't exist and creating it would establish a new
  subdirectory → ask first.
- The move would introduce a circular import → ask how to resolve.
- The capability has callers *inside* `src/`, not just in experiments → list
  them and ask whether to update them or leave them on the re-export.
- The move would require a logic change to keep tests passing → ask; that
  usually means it needs a refactor first, which is a separate task.

## Anti-Patterns

| Tempting move | Why it's wrong |
|---|---|
| "While I'm here, change the signature" | The interface stays frozen. Implementation improvements are fine; API changes are not. |
| "Skip the re-export — nobody imports the old path" | You cannot know every experiment import without running them all. Always re-export. |
| "Bundle the re-export removal with the move" | Moving and retiring are separate steps; re-exports age out when the user decides, not when the mover feels tidy. |
| "Move, and also update one experiment to the new path" | Out of scope. Migration is opportunistic, outside this skill. |
| "Two small moves in one commit" | One logical move, one commit — history stays searchable. |
| "Copy it to the new path and leave the old definition too" | Two definitions drift. The old path holds a re-export, never a duplicate. |
