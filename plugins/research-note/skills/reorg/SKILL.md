---
name: reorg
description: "Use when a capability in the reusable library layer belongs in another module, a file has grown several responsibilities, or a hasty lift now has a clear home. Non-breaking: the old path keeps working through a re-export."
---

# Reorg Skill

You are **moving** a capability within the project's reusable library layer.
Resolve the configured roots before choosing paths:

```bash
python3 "$PLUGIN/scripts/project_config.py" role libraries
python3 "$PLUGIN/scripts/project_config.py" role tests
python3 "$PLUGIN/scripts/project_config.py" role experiments
```

Select the roots containing the capability and its tests. Nothing changes
about what it does. The deliverable is code at the new path, a re-export at
the old path, updated tests, a regenerated capability index, and a passing
test suite.

This skill prescribes no language. Where it needs one — the re-export idiom,
the test runner — the authority is what the project already uses; the examples
below are Python because that is the common case, and the shape they show is
what to reproduce elsewhere.

## Core Rules

1. **Non-breaking by design.** Old paths keep working through a re-export —
   always, because you cannot know every experiment import without running
   them all. Experiment scripts are never modified by this skill; migration
   is opportunistic, outside it.
2. **One logical move per commit**, however small each — history stays
   searchable.
3. **Interface is frozen; implementation may improve.** The signature — name,
   parameters, defaults — the return type and the documented conventions stay.
   The internals may get cleaner. The test suite is the behavioural contract:
   if every existing test passes, callers keep working automatically.
4. **The re-export is permanent until explicitly retired.** Dropping
   re-exports is a separate later action the user decides.
5. **Dispatch discipline.** Tests follow the venue (root contract): on a Slurm
   cluster through the scheduler on a compute partition; on a bare server a
   quick foreground run.

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
- **From** where: current library path and line range.
- **To** where: target path in the same library root. It must already exist or be an obvious
  sibling of an existing file. A new subdirectory is the user's call.
- **Why**: one sentence on why the target home is better.

Confirm: does the target already import from the source in a way that would
become circular after the move? If yes, halt and ask.

### Step 2 — MOVE

Copy the definitions **verbatim** into the target. Place them logically —
beside related code, not at the end of the file. Update a docstring only
where it names the old path.

Regenerate the capability index (`gen_index.py --src`).

### Step 3 — RE-EXPORT

In the old file, replace the definition with the re-export (see the pattern
above). If other code in the old file called the moved name internally, point
those calls at the new path too.

### Step 4 — UPDATE TESTS

The test mirrors the new library location, per the project's 1-to-1 rule:
move the test to the path that mirrors the new source path, and update its
import. **Same assertions, same reference** — the logic is untouched.

If the old test file is left empty, delete it; if it still holds other tests,
leave those in place.

### Step 5 — VERIFY

Run the full relevant suite per the venue. Both the new test location AND any
test that reaches the code through the old path must pass. If one fails:

- an import error → fix the re-export line;
- a logic failure → something changed that shouldn't have. Revert to the
  verbatim copy and re-check.

A passing suite is the completion criterion for committing.

### Step 6 — COMMIT

One commit, prefix `refactor:`, staging the old file, the target file, both
test files, and the capability index — nothing else:

```
refactor: move <Name> <library-root>/<old> → <library-root>/<new>
```

## When to Halt and Ask

- The target path doesn't exist and creating it would establish a new
  subdirectory → ask first.
- The move would introduce a circular import → ask how to resolve.
- The capability has callers inside a declared library root, not just in experiments → list
  them and ask whether to update them or leave them on the re-export.
- The move would require a logic change to keep tests passing → ask; that
  usually means it needs a refactor first, which is a separate task.
- Tempted to change the signature while here → the interface stays frozen;
  an API change is a separate task.
