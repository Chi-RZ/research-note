# entry page — template

One `### Entry:` per set of order-independent same-code computations.
Rules: `project_memory/CLAUDE.md`.

---

```yaml
---
node: <node>            # must equal the containing folder
task: <one sentence — what this page does to which node on which instance>
---
```

### Entry: <what is run, on which instance>
- **Id:** <nn>.<mmm>
- **Status:** open | running | analyzed | closed
- **Date:** <YYYY-MM-DD HH:MM, creation>
- **Jobs:** <id>@<host>, <id>–<id>@<host>
- **Code:** `<repo>@<sha>` · `<domain lib>@<sha>`
- **Motivation:** <the source — a prior entry (linked), a code path at a commit, an absence in the record, a directive> found "<the fact, quoted, no evaluative words>"; <ONE question, one sentence, answerable by a number THIS run's Recipe produces — never a reason for running>?
- **Recipe:** {<knob>: <value>, <scanned knob>: [<v1>, <v2>, <v3>], seed: <seed>}
- **Facts:** We ran <the instance and how the jobs were laid out> with [<run script>](<link>); evidence [<log>](<link>).

  | <axis> | <arm A> | <arm B quoted from another entry> |
  |---|---|---|
  | <point> | <number this entry produced> | <number> `[1]` |

  <only what the table cannot hold — a wall time, an exit status, the provenance of a job id. Never a restatement of a number the table already carries.>

  ![<what the figure shows>](<figures/name.png>)
  *<caption: axes, units, what each series is>*
  [<plot script>](<link>)

- **Conclusion:** The result shows <X, one claim>, because <Y — every premise a reader could object to, and the detection floor when the evidence is a draw> — <answers | partly answers | does not answer> the motivation.
- **Refs:**
  `[1]` → [<entry name>](<page.md#entry-slug>) `<id>` — <the rows it supplies>

### Entry: <a follow-up decided after seeing the result above — its own entry, never a paragraph appended to the one it follows>
- **Id:** <nn>.<mmm+1>
- **Status:** open
- **Date:** <YYYY-MM-DD HH:MM>
- **Code:** `<repo>@<sha>`
- **Motivation:** [<the entry above>](<#entry-slug>) `<id>` found "<the number or fact its Conclusion established>"; <the next question>?
- **Recipe:** {<knobs>}
