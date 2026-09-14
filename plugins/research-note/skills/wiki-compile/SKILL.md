---
name: wiki-compile
description: Use when source material (notes, record conclusions, documents) should enter the project's self-organizing knowledge wiki, when asked to lift knowledge into the wiki, or when the wiki needs linting or reorganizing.
---

# research-note:wiki-compile

## Overview

The wiki is a compiled view of what the project currently knows, organized by
TOPIC (not by source, not by time), maintained by the agent. Sources stay
where they live and are never edited. The human reads, asks, and reviews;
the agent files, merges, cross-links, and flags.

**Grounding invariant:** every claim on a wiki page is traceable to a cited
source — locate in the source before you write. **The wiki is a view, never
an authority:** sources and records never cite wiki pages back.

## Layout

```
wiki/knowledge/
├── index.md      the topic tree — the only entry point; every page listed
├── <topic>.md    one page per topic
└── log.md        append-only operation log
```

## Page format

- **YAML frontmatter**, the same shape the record pages use so one parser
  reads both:

  ```yaml
  ---
  topic: <topic>
  status: compiled          # or `reviewed` — a human approved this revision
  updated: YYYY-MM-DD       # the date the KNOWLEDGE changed, not the file
  sources:
    - tag:  "gaussray_tn/local_cost: per-amplitude cost of the two routes"
      id:   "03.014"        # entries only; `git log --grep=<id>` is its history
      hash: 8cc257a700144c46
    - tag:  "note/gaussray_tn"
      hash: 83eda19d31de1e82
  ---
  ```

  **Quote both `tag` and `id`, always.** An entry tag contains `": "` — the
  `<node>: <entry name>` shape — which ends a plain YAML scalar and makes the
  whole block unparseable. And an id like `03.010` is a valid YAML float: it
  loads as `3.01`, colliding with `03.01` and breaking any lookup keyed on the
  id. Neither failure announces itself; the first raises only when something
  finally parses the file, and the second never raises at all.

  `hash` is the fingerprint `wiki_sources.py` prints for the text that
  compiled — for an entry, its question plus its Conclusion; for a note, the
  whole file. It is what lets lint find a page whose source moved under it
  without re-reading anything. Do not hand-compute it; take it from the
  script's output for the source you just used.
- Body: prose sections; **every paragraph carries its source citation(s)**,
  and a citation is a **plain-text tag, never a path or a link** — `<node>`,
  `<node>/<group>: <entry name>`, `note/<topic>`, `experiments/<node>/impl/`.
  Nothing under `wiki/` may link outside it (`wiki/CLAUDE.md`, hard): a reader
  with lab access resolves a tag, and a published copy dangles nothing.
- `⚠ Contested:` blocks present BOTH sides with citations and never resolve.
- `Open:` section holds boundaries and unanswered questions.

## Operations

### compile (the default)

**Hard gate on the record: only `Status: closed` entries compile.** An
`analyzed` entry carries the agent's judgement and not yet the user's — only the
user closes, and the wiki is the published layer, so it deliberately lags the
lab. Never relax this.

What compiles out of an entry is its **`Conclusion` together with the question
its `Motivation` ends in**. The Conclusion is a pointer sentence — it `answers`
/ `partly answers` / `does not answer` *the motivation* — so lifted alone it
asserts a thing without saying what was asked, and a `partly answers` loses the
only thing that said which part was left. The numbers in `Facts` do not travel;
they stay in the record and are cited by tag, per the hub rule below.

**Start from `scripts/wiki_sources.py`, not from the pages.** It walks the
record once and prints every compilable source with its tag, its id and its
hash — which is the gate, the citation and the staleness key in one pass,
instead of one read per page. It also lists, under `held`, the entries the user
has not closed — so you can tell them whether a closing pass is worth asking
for. Nothing promotes those; the gate has no override.

Sources are processed ONE AT A TIME, serially. Per source:

1. **Triage** — read it; check the index and candidate pages. Nothing
   genuinely new → append a `no material` line to the log and stop.
2. **Place** — merge claims into the page with the same thesis; **create**
   a page when no thesis fits; **split** a page that has outgrown one topic
   (≳150 lines, or two theses under one title), repairing inbound links.
   New claim conflicts with page text: rewrite to the current best
   understanding when the old claim is superseded by its own source's
   standards; otherwise mark `⚠ Contested`.
3. **Ground** — verify every number, name and quote against the source
   before writing it; attach the citation.
4. **Cascade** — search other pages for the affected concepts; update them
   or add `[topic](topic.md)` cross-links (standard markdown, not wikilinks — VSCode/GitHub previews must resolve them). Linking rules: (a) hub rule — a
   number lives on ONE page; other pages link to it, never restate it;
   (b) first cross-topic mention in a section links in place, to a section
   anchor when one fits; (c) every page ends with `## Related`, 2-4 links
   each carrying a clause naming WHY related; backlinks are never
   hand-maintained.
5. **Record** — update `index.md`; append one `log.md` line:
   `date | source | pages touched | disposition`.

### query

Answer from index → pages, citing pages. Writes nothing unless asked.

### lint

- **Safe fixes** (apply): missing/dead index rows; broken links repairable
  to exactly one target.
- **Reports** (never auto-fix facts): uncited claims; contradictions across
  pages; orphan pages; oversized pages. Append the result to the log.
- **Supersession** (report, never auto-fix): re-run `wiki_sources.py` and
  compare each page's `sources[].hash` against it.
  - hash differs → the source was rewritten after this page compiled. Report
    the page, the tag and `git log --grep=<id>`, which says what happened.
  - tag no longer compilable → the entry left `closed`. A correction returns
    every conclusion that cited a changed datum from `closed` to `analyzed`
    (record contract), so the record is saying this page now rests on a claim
    the user has withdrawn. Report it; do not quietly delete the page's text.

  This is the one failure a merge-based wiki cannot catch on its own. A claim
  that is CONTRADICTED gets caught at Place, where the new claim collides with
  the old. A claim whose source was simply rewritten or retracted has no
  challenger, so without this check it sits on the page indefinitely, correctly
  cited and no longer true.

## Rules

- **User-triggered only** — never compile into the wiki unprompted. The
  wiki is the published layer, and an agent that generalises its own
  readings compounds its own mistakes (root contract, "Stop and ask").
- Never edit a source. Never compile two sources concurrently.
- **Condense, don't copy.** A note is a running scratch; what compiles is the
  settled understanding. Drop superseded readings, and **keep the negative
  results that settled** — "X was ruled out because ..." is knowledge.
- Design intent that became a node lifts through **that node's Motivation**,
  not through a wiki page that restates it.
- A human review sets `Status: reviewed`; any later machine edit resets it
  to `compiled`.
- **When NOT to use:** writing understanding that has no source yet (that is
  the human's note to write first), or citing wiki pages from records.
