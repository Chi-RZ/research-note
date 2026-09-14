# node.md — template

Entries only: the gate first, then one validation per in-place edit.
Rules: `project_memory/CLAUDE.md`.

---

```yaml
---
node: <node>            # must equal the containing folder
task: <one sentence — validate this frozen impl: the gate, then each in-place edit>
---
```

### Entry: <node> gate on <the reference instance>
- **Id:** <nn>.001
- **Status:** analyzed | closed
- **Date:** <YYYY-MM-DD HH:MM>
- **Jobs:** <id>@<host>
- **Code:** `<repo>@<sha>`
- **Motivation:** <the reference — the parent cell this node forks from, an exact solution, an established gated node; a superseding node also names the node it supersedes here> found "<the reference number>"; does the fresh impl reproduce it?
- **Recipe:** {<the reference cell's knobs>}
- **Facts:** We ran <the reference cell> with [<run script>](<link>); evidence [<log>](<link>).

  | <quantity> | <value> |
  |---|---|
  | <this impl> | <number> |
  | <the reference> | <number> `[1]` |

- **Conclusion:** The result shows the impl reproduces <the reference>, because <the draw sits inside the reference history's spread> — answers the motivation.
- **Refs:**
  `[1]` → [<the reference entry>](<link>) `<id>` — <the reference value>

### Entry: <the in-place edit> validation
- **Id:** <nn>.<mmm>
- **Status:** analyzed | closed
- **Date:** <YYYY-MM-DD HH:MM>
- **Jobs:** <id>@<host>
- **Code:** `<repo>@<the edited commit>`
- **Motivation:** [<the entry it replays>](<./node.md#entry-slug>) `<id>` found "<its number>"; does <the edit — a refactor, a perf pass, a new defaulted knob left unset> leave it unchanged?
- **Recipe:** {<the replayed recipe, unchanged>}
- **Facts:** We replayed <the reference cell> on the edited impl with [<run script>](<link>); evidence [<log>](<link>).

  | <quantity> | <value> |
  |---|---|

- **Conclusion:** The result shows the edit is behaviour-preserving, because <the draw sits inside the reference history's spread> — answers the motivation.
