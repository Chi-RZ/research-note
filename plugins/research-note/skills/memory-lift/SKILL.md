---
name: memory-lift
description: Use when the user asks to promote a project_memory/memory/ entry — a working habit, method or verification strategy — into a skill. Only knowledge that would apply verbatim in a DIFFERENT project lifts. User-triggered only.
---

# research-note:memory-lift <memory entry or file>

The method analogue of `research-note:lift` (code, experiments → src) and
`research-note:wiki-compile` (interpretation): this pumps **working method**
from `project_memory/memory/` into the project-independent agent layer,
`.agent/skills/`.

## The gate (apply before writing anything)

Ask of the candidate entry: **would this apply, verbatim, in a different
research project under the same framework?**

- References this project's nodes, environments, metrics, or paths → NOT
  liftable as-is. Either generalize it (strip the project specifics into an
  example) or decline and say why.
- Encodes a general procedure (how to verify, how to submit, how to debug a
  class of failure) → liftable.
- When in doubt, ask the user — the lift decision is theirs.

## Steps

1. Read the source entry in `project_memory/memory/` and any pages it
   references, so the generalization is faithful.
2. Check `.agent/skills/` for an existing skill that should ABSORB this
   knowledge — extending an existing skill is the default; a new skill needs a
   distinct trigger.
3. Write the skill: `.agent/skills/<name>/SKILL.md`, or an edit to an existing
   one. Frontmatter is `name` plus a `description` that says WHEN to reach for
   it — the one sentence always in context, and the only thing that decides
   whether the skill fires — then the procedure. The plugin's own skills are
   the worked examples. Bootstrap exposes that one directory to both agents
   through the `.claude/skills` and `.agents/skills` symlinks, so one copy
   serves both. The skill text carries ZERO references to this project.
4. Trim the source memory entry to a one-line pointer at the skill — the
   knowledge now lives in the agent layer; a duplicate drifts.
5. Two commits in the monorepo, the second naming the first hash:
   - `agent: lift <topic> from project memory into <skill>`
   - `memory: point <entry> at the lifted skill (<hash>)`
