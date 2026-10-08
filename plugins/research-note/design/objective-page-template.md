# objective page — template

Rules: `project_memory/CLAUDE.md`.

---

```yaml
---
id: O<nn>
status: active | closed
created: <YYYY-MM-DD>
budget: "<how much may be spent, and how the loop checks it at each launch>"
wake-me-if: "<what must wake the user> | budget exceeded"
# attention: <what stopped the loop — present only while it is stopped>
---
```

## Goal

<The ask, in the user's words — one or two sentences.>

<What would count as answering it: the measurable, the instances, the shot and
seed budget — one or two sentences. The target table, when a reference exists:>

| <axis> | <reference values> |
|---|---|

**Constraints (user, <date>).**

- <bald constraint — no explanation>

## Plan

- [x] **P1 — <the question this phase asks>** (<cost>)
  - [<entry name>](<page.md#entry-slug>) `<id>` — <the role it plays in answering it, no number> (<date it concluded>)
  - ▶ <what this settles for the Goal — one sentence, no number, no mechanism>

- [ ] **P2 — <the next question>** (<cost> · needs: P1)
  - [<entry name>](<page.md#entry-slug>) `<id>` — <the role — a running entry has no date yet>

## Verdict

**<the answer against the Goal>** <at most two more sentences, each a
conclusion — a boundary, a caveat — never reasoning> 0 entries await review.

<!-- The record bus maintains the review count; author the answer and boundaries. -->
