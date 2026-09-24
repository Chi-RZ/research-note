"""wiki_sources — the gate, the citation and the staleness key in one pass."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import wiki_sources as W


PAGE = """---
node: demo
task: the d grid
---

### Entry: closed one
- **Id:** 07.001
- **Status:** closed
- **Motivation:** The parent found "2.8e-3"; does d5 hold it?
- **Conclusion:** The result shows d5 holds, because the draw sits inside the spread — answers the motivation.

### Entry: open one
- **Id:** 07.002
- **Status:** analyzed
- **Motivation:** The gate found "1.0"; does d7 hold it?
- **Conclusion:** The result shows d7 holds, because it does — answers the motivation.
"""


def project(tmp_path, page=PAGE, group="grid"):
    d = tmp_path / "project_memory" / "nodes" / "demo"
    (d / group).mkdir(parents=True) if group else d.mkdir(parents=True)
    ((d / group if group else d) / "page.md").write_text(page)
    (tmp_path / "project_memory" / "note").mkdir(parents=True)
    (tmp_path / "project_memory" / "note" / "demo.md").write_text("settled prose\n")
    return tmp_path


def test_include_analyzed_shows_the_held_ones_marked(tmp_path):
    got = W.entries(project(tmp_path), include_analyzed=True)
    assert {e["id"]: e["compilable"] for e in got} == {"07.001": True, "07.002": False}


def test_the_question_travels_with_the_claim(tmp_path):
    """A Conclusion lifted alone says a thing is true without saying what was asked."""
    e = W.entries(project(tmp_path), include_analyzed=False)[0]
    assert e["question"] == "does d5 hold it?"
    assert "2.8e-3" not in e["question"]          # the quoted fact is provenance, not the question


def test_tag_carries_the_group_when_there_is_one(tmp_path):
    assert W.entries(project(tmp_path), False)[0]["tag"] == "demo/grid: closed one"
    assert W.entries(project(tmp_path / "b", group=""), False)[0]["tag"] == "demo: closed one"


def test_hash_is_over_the_fields_not_the_file(tmp_path):
    """A page holds many entries; a file hash would make one edit stale them all."""
    before = W.entries(project(tmp_path), False)[0]["hash"]
    # touch a DIFFERENT entry on the same page
    edited = PAGE.replace("does d7 hold it?", "does d9 hold it?")
    after = W.entries(project(tmp_path / "b", page=edited), False)[0]["hash"]
    assert before == after

    # and the entry's own Conclusion does move it
    own = PAGE.replace("because the draw sits inside the spread", "because it does not")
    assert W.entries(project(tmp_path / "c", page=own), False)[0]["hash"] != before


def test_a_note_is_hashed_whole(tmp_path):
    n = W.notes(project(tmp_path))
    assert len(n) == 1 and n[0]["tag"] == "note/demo" and n[0]["compilable"]
    assert len(n[0]["hash"]) == 16


def test_the_held_count_is_not_structurally_zero(tmp_path, capsys):
    """`held` was filtered out before it could be counted.

    main() split ready/held over a list the gate had already emptied, so the
    report could only ever say "held (not closed): 0" — while an analyzed entry
    with a written conclusion sat outside the wiki, unmentioned. A coverage line
    that cannot be non-zero is worse than no coverage line.
    """
    root = project(tmp_path)
    sys.argv = ["wiki_sources.py", str(root)]
    W.main()
    out = capsys.readouterr().out
    assert "held (not closed): 1" in out, out
    assert "07.002" in out, out
    assert "07.001" in out, out


def test_nothing_on_the_command_line_can_promote_a_held_entry(tmp_path, capsys):
    """The gate has no override, and this is the test that says so.

    It replaces one that asserted the opposite. `--include-analyzed` set
    `compilable` on every source, added in 0.25.3 as "what a caller passing it
    is asking for" — which read the caller as a person. It is an agent, and the
    gate exists precisely so an agent cannot release the user's un-accepted
    judgement into the published layer. Three documents then disagreed at once:
    this module's own docstring said "they are NOT compilable", the skill said
    the flag "shows what the gate is holding back", and the code promoted.

    So the assertion is over ARGV, not over one call: no command line reaches a
    state where a non-closed entry compiles. The old flag is still passed here
    on purpose — reintroducing it has to fail.
    """
    root = project(tmp_path)
    for argv in (["wiki_sources.py", str(root)],
                 ["wiki_sources.py", str(root), "--include-analyzed"]):
        sys.argv = argv
        W.main()
        out = capsys.readouterr().out
        assert "compilable: 2" in out, (argv, out)        # one entry plus the note
        assert "held (not closed): 1" in out, (argv, out)

    # --json bypasses the ready/held split entirely, so it needs its own check:
    # it reported `"compilable": true` for held entries under the same override.
    sys.argv = ["wiki_sources.py", str(root), "--json", "--include-analyzed"]
    W.main()
    rows = json.loads(capsys.readouterr().out)
    held = [r for r in rows if r.get("id") == "07.002"]
    assert held, rows
    assert held[0]["compilable"] is False, held
