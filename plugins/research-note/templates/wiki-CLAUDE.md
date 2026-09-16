# wiki — the knowledge side of the precipitated layer

Settled, condensed, **self-contained**. Together with `src/` (+`tests/`) this
is the publishable artifact: a future release snapshots `src + tests + wiki`
into a public repo — users get the functions AND the exploration logic behind
them.

On this branch the wiki is a **knowledge base only**: the node-organized
results view (`gen_wiki`, `wiki/data`, `wiki/pages`, `/wiki-lift`, `/paper`)
is deliberately parked — it lives on the `qec-dev` branch and can be
resurrected when a results view is wanted again.

## The self-containment contract (hard)

- Nothing under `wiki/` links outside `wiki/` — no `file://`, no relative
  paths into `project_memory/` or `experiments/`.
- References to the temp layer are **plain-text tags** (entry names, page
  refs like `<node>/<group>: <entry name>`, `experiments/<node>/impl/`) —
  a reader with lab access resolves a tag; a published copy dangles nothing.
- Everything the wiki needs is COPIED FORWARD by the pumps at lift time.
- Correctness auditing (logs, raw data, full narratives) lives in the temp
  layer, not here.

## `wiki/knowledge/` — the standalone knowledge base

A compiled view of what the project currently knows, written by
`research-note:wiki-compile` from two kinds of source: settled interpretation in
`project_memory/note/`, and the `Conclusion` of a **closed** entry. Pages are
organised by **thesis, not by source** — a source contributes claims to whatever
pages already argue them, and the skill creates or splits a page when no thesis
fits. So a page is not the projection of one file, and `<topic>` is not bound to
a node name or to any results view.

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
- **Linking** — (a) a number lives on ONE page, others link to it and never
  restate it; (b) the first cross-topic mention in a section links in place;
  (c) every page ends with `## Related`, 2-4 links each naming WHY related.
  Standard markdown links, never wikilinks.

English-only. Commit prefix: `wiki:`.

---

## This project's own rules

Everything above this line is framework text: `research-note:update` replaces it
with the plugin's copy whenever the two differ, so an edit made up there is lost
at the next update and a deletion up there comes back.

Add what this project decides for itself **below** this line. The updater
recognises an appendix by the framework half still matching byte for byte, and
leaves everything after it alone — it will say so, naming how many lines it kept.
If the framework text has also moved on, it refuses to copy at all and prints the
diff for you to port by hand, rather than carrying the update forward and dropping
your lines in the same stroke.

A rule here that would serve every project belongs in the plugin instead — say so
and it can be lifted into the template.
