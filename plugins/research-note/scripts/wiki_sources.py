#!/usr/bin/env python3
"""Emit the compilable material of this project's record, for research-note:wiki-compile.

The skill's grounding invariant is that every wiki claim traces to a cited
source, and its hard gate is that only a `closed` entry compiles. Both are
mechanical, so neither should cost the agent a pass over every page: this walks
the record once and prints exactly what may enter the wiki, with the tag to cite
it by, the entry id to trace it by, and a fingerprint of the text that entered.

What an entry contributes is its `Conclusion` TOGETHER WITH the question its
`Motivation` ends in. The Conclusion is a pointer sentence — it `answers` /
`partly answers` / `does not answer` *the motivation* — so lifted alone it
asserts a thing without saying what was asked. `partly answers` is the case that
breaks: detached from its question, which part was left is unrecoverable.
`Facts` do not travel; numbers stay in the record and are cited by tag.

Three identifiers, because they answer different questions:

  tag    `<node>/<group>: <entry name>`  how the wiki cites it — plain text,
         never a path, per the self-containment contract
  id     `<nn>.<mmm>`                    how a reader traces it:
         `git log --grep=<id>` is that entry's whole history (record contract)
  hash   sha256 of question + claim      whether the compiled text CHANGED

The hash earns its place against the id rather than duplicating it. A commit
carrying `Entry: 03.012` says something happened to that entry — a Status flip,
a job id, a table added to Facts — and almost none of those touch what the wiki
took. Closing forty entries at an objective's approval moved forty Statuses and
not one Conclusion; keyed on commits, every wiki page citing them would have
gone stale at once. The hash says whether the two sentences changed; the id then
says what happened. Reported together, a stale finding comes with its own
`git log --grep=` to explain itself.

The hash is over the extracted text, never over the file. A page holds many
entries — eleven, on the page this was written against — so a file hash would
mark every claim citing that page as stale when any one entry changed. A note
has no field structure and IS hashed whole, coarser on purpose: notes are
running scratch that changes constantly, and splitting one by section would be
inventing structure the source does not promise.

Usage:
  wiki_sources.py [--json] [PROJECT_DIR]

Entries the user has not closed are listed too, under `held`, with their status:
seeing the queue is how you judge whether asking for a closing pass is worth it.
They are never compilable. The gate is the gate, and there is no flag that opens
it.

There was one. `--include-analyzed` began as "list them, marked as such", and
0.25.3 changed it to set `compilable` on every source — "what a caller passing
it is asking for". The caller is an agent, and the gate exists precisely so an
agent cannot release the user's un-accepted judgement into the published layer.
By then the flag's stated job was already done without it: 0.25.3 also taught
main() to collect everything and split honestly, so a plain run lists the held
set. What remained was an override with no job, and it was removed rather than
repaired.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from projroot import nth_parent, resolve_root  # noqa: E402

ENTRY_HEAD_RE = re.compile(r"^#{2,4}\s+Entry:\s*(.+?)\s*$", re.M)
#: a field runs to the next `- **Key:**` line, so a wrapped Motivation survives
FIELD_RE = r"^- \*\*{}:\*\*(.*(?:\n(?!- \*\*).*)*)"
COMPILABLE = {"closed"}


def _field(body: str, key: str) -> str:
    m = re.search(FIELD_RE.format(key), body, re.M)
    return " ".join(m.group(1).split()) if m else ""


def _question(motivation: str) -> str:
    """The sentence the Motivation ends in — E5 requires it to be ONE question.

    Split on the last '; ' rather than on sentence punctuation: the quoted fact
    before it routinely contains full stops, and the contract's shape is
    `<source> found <fact>; <the question>?`. Falls back to the whole field
    when that does not land on a question, so a malformed Motivation degrades
    to carrying too much rather than to carrying nothing.
    """
    if not motivation:
        return ""
    tail = motivation.rsplit("; ", 1)[-1].strip()
    return tail if tail.endswith("?") else motivation.strip()


def _slug(name: str) -> str:
    """The GitHub-style anchor an objective page links an entry by."""
    s = re.sub(r"[^\w\s-]", "", name.lower())
    return re.sub(r"[\s_]+", "-", s).strip("-")


def entries(root: Path, include_analyzed: bool) -> list[dict]:
    out = []
    nodes = root / "project_memory" / "nodes"
    for page in sorted(nodes.rglob("*.md")):
        rel = page.relative_to(nodes)
        node = rel.parts[0]
        # `<node>/<group>: <entry name>` is the citation shape the wiki
        # contract names; a page directly under the node has no group.
        group = "/".join(rel.parts[1:-1])
        parts = ENTRY_HEAD_RE.split(page.read_text(encoding="utf-8"))
        for i in range(1, len(parts) - 1, 2):
            name, body = parts[i], parts[i + 1]
            status = _field(body, "Status")
            claim = _field(body, "Conclusion")
            if not claim:
                # Nothing concluded yet: not held, there is no text to hold.
                continue
            if status not in COMPILABLE and not include_analyzed:
                continue
            question = _question(_field(body, "Motivation"))
            out.append({
                "kind": "entry",
                "tag": f"{node}/{group}: {name}" if group else f"{node}: {name}",
                "id": _field(body, "Id"),
                "status": status,
                "compilable": status in COMPILABLE,
                "page": str(page.relative_to(root)),
                "slug": _slug(name),
                "question": question,
                "claim": claim,
                "hash": hashlib.sha256(
                    (question + "\n" + claim).encode()).hexdigest()[:16],
            })
    return out


def notes(root: Path) -> list[dict]:
    out = []
    for f in sorted((root / "project_memory" / "note").glob("*.md")):
        text = f.read_text(encoding="utf-8")
        out.append({
            "kind": "note",
            "tag": f"note/{f.stem}",
            "id": "",
            "status": "—",
            "compilable": True,
            "page": str(f.relative_to(root)),
            "lines": text.count("\n") + 1,
            # whole-file on purpose; see the module docstring
            "hash": hashlib.sha256(text.encode()).hexdigest()[:16],
        })
    return out


def main() -> int:
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = Path(argv[0]).resolve() if argv else resolve_root(nth_parent(HERE, 2))

    # Everything with a conclusion is COLLECTED; `compilable` stays keyed on
    # `closed`, in every output mode. There is no override and no flag that
    # opens the gate — see the Usage note above for the one there used to be.
    src = notes(root) + entries(root, include_analyzed=True)
    if "--json" in sys.argv:
        print(json.dumps(src, indent=2, ensure_ascii=False))
        return 0

    ready = [s for s in src if s["compilable"]]
    held = [s for s in src if not s["compilable"]]
    print(f"compilable: {len(ready)}   held (not closed): {len(held)}\n")
    for s in ready:
        ident = f" {s['id']}" if s["id"] else ""
        tail = f"  ({s['lines']} lines)" if s["kind"] == "note" else ""
        print(f"[{s['hash']}]{ident} {s['tag']}{tail}")
        if s["kind"] == "entry":
            print(f"    Q: {s['question'][:140]}")
            print(f"    A: {s['claim'][:140]}")
    if held:
        print("\nheld — the user has not closed these, so they do not compile:")
        for s in held:
            print(f"  [{s['status']:>8}] {s['id']} {s['tag'][:88]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
