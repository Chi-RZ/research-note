# wiki — the knowledge side of the precipitated layer

Settled, condensed, **self-contained**. Together with the libraries and their
tests this is the publishable artifact: a future release snapshots
`<library-root>` + `<test-root>` + this knowledge base into a public repo —
users get the functions AND the exploration logic behind them.

`<knowledge-root>` below is the directory this file is linked into — `wiki/`, or
whatever `roles.knowledge` declares in `.research-note/project.json`. The
`knowledge/` subtree inside it is the framework's.

## The self-containment contract (hard)

- Nothing under `<knowledge-root>` links outside it — no `file://`, no relative
  paths into `project_memory/` or an experiment root.
- References to the temp layer are **plain-text tags** (entry names, page
  refs like `<node>/<group>: <entry name>`, `<experiment-root>/<node>/impl/`) —
  a reader with lab access resolves a tag; a published copy dangles nothing.
- Everything the wiki needs is COPIED FORWARD by the pumps at lift time.
- Correctness auditing (logs, raw data, full narratives) lives in the temp
  layer, not here.

## `<knowledge-root>/knowledge/` — the standalone knowledge base

A compiled view of what the project currently knows, written by
`research-note:wiki-compile` from two kinds of source: settled interpretation in
`project_memory/note/`, and the `Conclusion` of a **closed** entry. Pages are
organised by **thesis, not by source**, so a page is not the projection of one
file and `<topic>` is not bound to a node name or to any results view.

Which pages exist is DECLARED, in `<knowledge-root>/knowledge/SCHEMA.md`, and a source is
routed into one of them. A source that fits nowhere is not a new page: it is
either not reusable knowledge, or a proposal to change that file, and the user
decides which. The schema is derived once from the whole record and edited
deliberately thereafter — a structure re-derived at every compile comes out
shaped like the record rather than like the subject.

Invariants the wiki holds, whoever writes it:

- **Grounding** — every claim traces to a cited source, and the citation is a
  plain-text tag (the self-containment contract above), never a path or a link.
- **A view, never an authority** — sources and records never cite wiki pages
  back, and where a page disagrees with the entry it compiled from, the entry
  is what is true. The first half binds the writer, the second the reader:
  read-first reaches this base at every entrance, and a compiled page that has
  drifted from its source must not be what a decision rests on.
- **`Status:`** is `compiled` (machine-written) or `reviewed` (a human approved
  this revision); any later machine edit resets `reviewed` to `compiled`.
- **`⚠ Contested:`** blocks present BOTH sides with citations and never resolve.
- **Type** — every page is one of five, declared in `SCHEMA.md` and carried in
  its frontmatter: `concept`, `method`, `comparison`, `open`, `overview`. There
  is no `finding` type: a result is evidence cited ON a page, never a page.
- **Admission** — what enters is reusable across sources. A one-off — this
  machine's free memory, this seed, what a queue was doing on Tuesday — stays
  in the record and is cited by tag; what the one-off TAUGHT may enter. The
  test is whether it would still be true on other hardware.
- **Linking** — (a) a number lives on ONE page, others link to it and never
  restate it; (b) the first cross-topic mention in a section links in place;
  (c) every page ends with `## Related`, 2-4 links each naming WHY related.
  Standard markdown links, never wikilinks.

English-only.

---

## Project-specific rules

Write rules for this project's wiki below this heading. This section belongs to
the project and is kept when the plugin updates the framework section above. A
rule that would serve every project belongs in the plugin template instead.
