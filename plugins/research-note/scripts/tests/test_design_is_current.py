"""DESIGN.md's census tables against the machine they describe.

DESIGN.md is the only document here that nothing watched. It ships to no
project, no script reads it, no test touched it — and both linters cite it back
("Codes (DESIGN.md §10)"), which makes it normative without making it checked.
It went 28 releases without an edit and was found, by audit, to be missing O14,
six scripts, a hook and four gates, while three separate rosters of the lint
codes disagreed with each other.

The distinction that decides what belongs here: across those 28 releases the
tables' ROW LABELS never went wrong — the six protection classes still classify
correctly — and the CELLS drifted every time. Classification is the design's own
work and no test can grade it. Enumeration is a census of things the code
already holds, and a census is exactly what a test can hold to its source.

So these tests pin the enumerations and leave the prose alone. A new lint code,
script, skill or hook now turns a table red instead of quietly outdating it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2]
DESIGN = PLUGIN.parents[1] / "DESIGN.md"

pytestmark = pytest.mark.skipif(
    not DESIGN.is_file(),
    reason="DESIGN.md lives in the plugin's source repo, not in an installed cache")


def rows(marker: str) -> list[str]:
    """The data rows of the first table at or after the line starting `marker`."""
    lines = DESIGN.read_text(encoding="utf-8").splitlines()
    try:
        i = next(n for n, l in enumerate(lines) if l.startswith(marker))
    except StopIteration:
        pytest.fail(f"DESIGN.md no longer has a line starting {marker!r} — "
                    f"the table moved or was renamed; fix this test with it")
    while not lines[i].lstrip().startswith("|"):
        i += 1
    out = []
    while i < len(lines) and lines[i].lstrip().startswith("|"):
        out.append(lines[i])
        i += 1
    return out[2:]                                   # past header + separator


def emitted(linter: str) -> set[str]:
    """The codes a linter can actually print.

    Read past the module docstring on purpose: that docstring is a THIRD roster
    of the same codes, and at the time of writing it stopped at O12 while the
    file implemented O13 and O14. Reading it would pin DESIGN to a copy that is
    itself stale.
    """
    src = (PLUGIN / "scripts" / linter).read_text(encoding="utf-8")
    body = src.split('"""', 2)[-1]
    return set(re.findall(r'(?:f?")((?:[EPJNVOM]\d+|FW))[ "]', body))


def test_every_lint_code_is_in_the_code_table_and_nothing_else_is():
    """Both directions: a new code must be classified, a retired one must go.

    One direction alone is not enough. Missing O14 is how an agent learns a rule
    exists only by failing it; a code listed after the check was removed sends
    someone hunting for an enforcement that is not there.
    """
    documented = set(re.findall(
        r"`((?:[EPJNVOM]\d+|FW))`",
        "\n".join(rows("**Every code, by what it protects:**"))))
    live = emitted("check_node_page.py") | emitted("check_objective_page.py")
    assert live - documented == set(), (
        f"emitted by a linter, absent from DESIGN §10's code table: "
        f"{sorted(live - documented)}")
    assert documented - live == set(), (
        f"in DESIGN §10's code table, emitted by no linter: "
        f"{sorted(documented - live)}")


def test_every_script_is_in_the_script_table_and_nothing_else_is():
    """21 on disk, 15 named — `land_and_launch.sh` and `worktree_retire.sh`
    among the missing, which are two of the framework's own gates."""
    named = set(re.findall(
        r"`([\w.]+\.(?:py|sh))`",
        "\n".join(rows("### The scripts these layers are made of"))))
    disk = {p.name for p in (PLUGIN / "scripts").iterdir()
            if p.suffix in (".py", ".sh")}
    assert disk - named == set(), f"on disk, unlisted: {sorted(disk - named)}"
    assert named - disk == set(), f"listed, not on disk: {sorted(named - disk)}"


def test_every_skill_is_in_the_skill_table():
    """One direction only: the table's cells also carry prose in backticks, so
    requiring the reverse would read `src/` as a skill."""
    named = set(re.findall(r"`([a-z-]+)`", "\n".join(rows("| | | opened by |"))))
    disk = {p.name for p in (PLUGIN / "skills").iterdir() if p.is_dir()}
    assert disk - named == set(), f"shipped, undocumented: {sorted(disk - named)}"


def test_the_hook_table_has_a_row_per_wired_hook():
    """Counted, not matched by name: two hooks share the `UserPromptSubmit`
    event and two share `PostToolUse`, so the event name cannot identify a row.
    The count is what catches the sixth hook DESIGN did not know about."""
    h = json.loads((PLUGIN / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    h = h.get("hooks", h)
    wired = sum(len(m.get("hooks", [])) for arr in h.values() for m in arr)
    documented = len(rows("| hook | when | what it says |"))
    assert wired == documented, (
        f"hooks.json wires {wired} commands; DESIGN §10.3's table has "
        f"{documented} rows")
