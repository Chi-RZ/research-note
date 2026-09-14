---
name: memory-lift
description: Use when the user asks to promote a project_memory/memory/ entry (a working habit, method, or verification strategy) into the agent layer as a skill. The gate is project-independence — only knowledge that would apply verbatim in a DIFFERENT research project lifts; project-bound knowledge stays in memory/. User-triggered only.
---

# research-note:memory-lift <memory entry or file>

The method analogue of `research-note:lift`: `research-note:lift` pumps code (experiments → src),
`research-note:wiki-compile` pumps interpretation — this
skill pumps **working method** (project_memory/memory/ → .agent/skills/).
The agent layer is project-independent; this pump is what keeps hard-won
process knowledge from being trapped in one project.

## The gate (apply before writing anything)

Ask of the candidate entry: **would this apply, verbatim, in a different
research project under the same framework?**

- References this project's nodes, environments, metrics, or paths → NOT
  liftable as-is. Either generalize it (strip the project specifics into an
  example) or decline and say why.
- Encodes a general procedure (how to verify, how to submit, how to debug a
  class of failure) → liftable.
- When in doubt, ask the user — the lift decision is theirs; this skill is
  only invoked on their request anyway.

## Steps

1. Read the source entry in `project_memory/memory/` (and any pages it
   references, to make sure the generalization is faithful).
2. Check `.agent/skills/` for an existing skill that should ABSORB this
   knowledge instead of a new skill being created — extending an existing
   skill is the default; a new skill needs a distinct trigger.
3. Write the skill per `superpowers:writing-skills` conventions
   (`.agent/skills/<name>/SKILL.md`, or an edit to an existing SKILL.md).
   Bootstrap exposes that one directory to both agents through
   `.claude/skills` and `.agents/skills` symlinks; never write a second copy.
   The skill text must carry ZERO references to this project.
4. Trim the source memory entry to a one-line pointer at the skill (the
   knowledge now lives in the agent layer; a duplicate drifts).
5. Two commits in the monorepo, the second naming the first hash:
   - `agent: lift <topic> from project memory into <skill>` (the shared agent layer)
   - `memory: point <entry> at the lifted skill (<hash>)`
