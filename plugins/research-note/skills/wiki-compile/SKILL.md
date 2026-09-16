---
name: wiki-compile
description: Use when the user asks to compile source material (notes, closed record conclusions, documents) into the project's knowledge wiki, to query it, or to lint or reorganize it.
---

# research-note:wiki-compile

The wiki is a compiled view of what the project currently knows, organized by
TOPIC (not by source, not by time), maintained by the agent. Sources stay
where they live and are never edited. The human reads, asks, and reviews;
the agent files, merges, cross-links, and flags. The invariants every page
holds — grounding, view-never-authority, self-containment, `Status:`,
`⚠ Contested:`, the five types, admission, linking — are `wiki/CLAUDE.md`'s;
this skill is the procedure that satisfies them.

## Layout

```
wiki/knowledge/
├── SCHEMA.md     the declared page taxonomy — which pages exist and what each covers
├── index.md      the topic tree — the only entry point; every page listed
├── <topic>.md    one page per topic
└── log.md        append-only operation log
```

## The declared taxonomy

`SCHEMA.md` says which pages exist and what each covers. **A source is routed
into a declared page; it does not get to create one.** A source that fits
nowhere is either not reusable knowledge, or a proposal to change `SCHEMA.md` —
and the user decides which.

Derive the taxonomy ONCE, from the whole compilable record, at the first
compile; from then on edit it deliberately. Re-deriving it per compile is the
failure this replaces: twice, a wiki rebuilt from whatever had just arrived came
out shaped like the record rather than like the subject.

### Page types

| type | holds | does not hold |
|---|---|---|
| `concept` | one thing or idea in the subject: what it is, what it fixes, how it relates | procedure; head-to-head judgement |
| `method` | one procedure: what it does, what it needs, **what it costs** | whether it beats an alternative |
| `comparison` | one contrastive question: how X and Y differ, when to choose which | what X is — that is a `concept`, linked |
| `open` | unsettled questions and known limits | anything already settled |
| `overview` | routing only: links out to the pages of one cluster | content |

A result is evidence cited ON a concept, method or comparison — a wiki with
one page per result is the record with extra steps.

**Overview threshold** — a cluster of fewer than three pages gets no overview;
its line in `index.md` is its entry point. Overviews answer growth, not
tidiness.

### Admission

The test: *would this still be true if the run were repeated on other
hardware?* An operational number fails it and belongs in
`project_memory/memory/`; the thing the number taught — that a measurement on a
shared machine reports contention rather than requirement, say — passes it and
belongs on a page.

### Tags

Controlled. A new tag is declared in `SCHEMA.md` first, then used — freeform
tags decay into noise. Frequency proposes a tag; it does not establish one, and
`SCHEMA.md` is where a term seen often but deliberately NOT made a page is
written down with the reason.

## Page format

- **YAML frontmatter**, the same shape the record pages use so one parser
  reads both:

  ```yaml
  ---
  topic: <topic>
  type: concept             # one of the five declared in SCHEMA.md
  tags: [exactness]         # from SCHEMA.md's controlled list, never freeform
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
  id. Neither failure announces itself.

  `hash` is the fingerprint `wiki_sources.py` prints for the text that
  compiled — for an entry, its question plus its Conclusion; for a note, the
  whole file. It is what lets lint find a page whose source moved under it
  without re-reading anything. Take it from the script's output for the
  source you just used.
- Body: prose sections; **every paragraph carries its source citation(s)**,
  as plain-text tags — `<node>`, `<node>/<group>: <entry name>`,
  `note/<topic>`, `experiments/<node>/impl/`.
- `⚠ Contested:` blocks present BOTH sides with citations and never resolve.
- `Open:` section holds boundaries and unanswered questions.

## Operations

### compile (the default)

**Hard gate on the record: only `Status: closed` entries compile.** An
`analyzed` entry carries the agent's judgement and not yet the user's — only the
user closes, and the wiki is the published layer, so it deliberately lags the
lab. The gate has no override.

What compiles out of an entry is its **`Conclusion` together with the question
its `Motivation` ends in**. The Conclusion is a pointer sentence — it `answers`
/ `partly answers` / `does not answer` *the motivation* — so lifted alone it
asserts a thing without saying what was asked, and a `partly answers` loses the
only thing that said which part was left. The numbers in `Facts` do not travel;
they stay in the record and are cited by tag, per the hub rule below.

**Start from `scripts/wiki_sources.py`, not from the pages.** It walks the
record once and prints every compilable source with its tag, its id and its
hash — the gate, the citation and the staleness key in one pass. It also lists,
under `held`, the entries the user has not closed — so you can tell them
whether a closing pass is worth asking for.

**No `SCHEMA.md` yet? Derive it first, from ALL the sources at once**, and get
the user's assent before compiling a line. Read every compilable source, look
for the three signals — a term recurring across questions, several questions
sharing one subject, a contrastive question shape (`X against Y`) — and propose
the page list with a type for each and the signal that justified it. Then
compile into what was agreed.

Sources are processed ONE AT A TIME, serially. Per source:

1. **Triage** — read it; check `SCHEMA.md` and the candidate pages. Nothing
   genuinely new → append a `no material` line to the log and stop. Fails the
   admission test → `not reusable` line, and stop.
2. **Place** — merge claims into the declared page that covers them. **No
   declared page fits → STOP and ask**: this is either a source that does not
   belong in the wiki, or a proposal to change `SCHEMA.md`, and that is the
   user's call. **Split** a page that has outgrown one topic (≳150 lines, or
   two theses under one title) — also a `SCHEMA.md` change — repairing inbound
   links. New claim conflicts with page text: rewrite to the current best
   understanding when the old claim is superseded by its own source's
   standards; otherwise mark `⚠ Contested`.
3. **Ground** — verify every number, name and quote against the source
   before writing it; attach the citation.
4. **Cascade** — search other pages for the affected concepts; update them
   or add `[topic](topic.md)` cross-links (standard markdown — VSCode/GitHub
   previews must resolve them). Linking rules: (a) hub rule — a number lives
   on ONE page; other pages link to it, never restate it; (b) first
   cross-topic mention in a section links in place, to a section anchor when
   one fits; (c) every page ends with `## Related`, 2-4 links each carrying a
   clause naming WHY related; backlinks are never hand-maintained.
5. **Record** — update `index.md`; append one `log.md` line:
   `date | source | pages touched | disposition`.

When the pass ends, append one `gate` line naming every source the gate held
back — concluded but not closed — so the omission is visible rather than
silent. A reader who cannot see what was withheld cannot tell a thin page from
a thin subject.

### query

Answer from index → pages, citing pages. Writes nothing unless asked.

### lint

- **Safe fixes** (apply): missing/dead index rows; broken links repairable
  to exactly one target.
- **Against `SCHEMA.md`** (report): a page not declared there, a declared page
  that does not exist, a `type:` or `tags:` entry the schema does not list.
- **Reports** (never auto-fix facts): uncited claims; contradictions across
  pages; orphan pages; oversized pages. Append the result to the log.
- **Supersession** (report, never auto-fix): re-run `wiki_sources.py` and
  compare each page's `sources[].hash` against it.
  - hash differs → the source was rewritten after this page compiled. Report
    the page, the tag and `git log --grep=<id>`, which says what happened.
  - tag no longer compilable → the entry left `closed`. A correction returns
    every conclusion that cited a changed datum from `closed` to `analyzed`
    (record contract), so the record is saying this page now rests on a claim
    the user has withdrawn. Report it; the page's text stays until a person
    decides.

  This is the one failure a merge-based wiki cannot catch on its own: a
  CONTRADICTED claim collides with the new one at Place, but a claim whose
  source was simply rewritten or retracted has no challenger and would sit on
  the page indefinitely, correctly cited and no longer true.

## Rules

- **User-triggered only** (root contract, "Stop and ask").
- Never edit a source. One source at a time.
- **Condense, don't copy.** A note is a running scratch; what compiles is the
  settled understanding. Drop superseded readings, and **keep the negative
  results that settled** — "X was ruled out because ..." is knowledge.
- Design intent that became a node lifts through **that node's Motivation**,
  not through a wiki page that restates it.
- A human review sets `Status: reviewed`; any later machine edit resets it
  to `compiled`.
- Understanding that has no source yet is the human's note to write first,
  not the wiki's to invent.
