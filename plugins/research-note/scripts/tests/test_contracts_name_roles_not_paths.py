"""A contract may not hardcode a directory the project is free to declare.

The four contracts are loaded into every session, so a literal `src/` there is
read as an instruction. For a project that declared `code/` it is a wrong
instruction, and the failure is silent: the agent writes the file where the
contract said and no gate objects, because the gate reads the declaration.

So the contracts write `<library-root>`, `<test-root>`, `<experiment-root>` and
`<knowledge-root>`, and the root contract resolves all four in one paragraph.
Everything the framework fixes — `project_memory/` and its subtree, `.claude/`,
the conventions inside a node — stays literal, and this test does not touch it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2]
TEMPLATES = PLUGIN / "templates"
CONTRACTS = ["CLAUDE.md", "experiments-CLAUDE.md", "project_memory-CLAUDE.md",
             "wiki-CLAUDE.md"]
DECLARED = ("src", "tests", "experiments", "wiki")
PLACEHOLDERS = ("<library-root>", "<test-root>", "<experiment-root>",
                "<knowledge-root>")
#: the one sentence allowed to name the defaults — it is what maps the
#: placeholders onto real directories
DEFAULTS_SENTENCE = "for a project that declares nothing"
#: and the one sentence a subtree contract uses to say which root it governs
GOVERNS_SENTENCE = "the directory this file is linked into"


def offenders(text: str) -> list[tuple[int, str]]:
    """(line number, line) for every literal declared-root path.

    A path already qualified by a placeholder (`<experiment-root>/tests/`) or by
    another path segment is not a top-level reference, hence the lookbehind.
    """
    bad = []
    pattern = re.compile(r"(?<![\w/<>-])(" + "|".join(DECLARED) + r")/")
    for n, line in enumerate(text.splitlines(), 1):
        if any(marker in line for marker in
               (DEFAULTS_SENTENCE, GOVERNS_SENTENCE, "roles.")):
            continue
        if pattern.search(line):
            bad.append((n, line.strip()))
    return bad


@pytest.mark.parametrize("contract", CONTRACTS)
def test_no_contract_hardcodes_a_declared_root(contract):
    found = offenders((TEMPLATES / contract).read_text(encoding="utf-8"))
    assert not found, (
        f"{contract} names a directory the project may redeclare:\n"
        + "\n".join(f"  line {n}: {line}" for n, line in found)
        + f"\nUse one of {', '.join(PLACEHOLDERS)}.")


def test_the_root_contract_resolves_every_placeholder_it_uses():
    """A placeholder is only readable if one paragraph says what it resolves to,
    and names the command that prints it."""
    text = (TEMPLATES / "CLAUDE.md").read_text(encoding="utf-8")
    for placeholder in PLACEHOLDERS:
        assert placeholder in text, f"the root contract never uses {placeholder}"
    assert ".research-note/project.json` is the path authority" in text
    assert "project_config.py` role" in text or "project_config.py\" role" in text
    assert DEFAULTS_SENTENCE in text, "the defaults are named nowhere"


@pytest.mark.parametrize("contract", ["experiments-CLAUDE.md", "wiki-CLAUDE.md"])
def test_each_subtree_contract_says_which_root_it_governs(contract):
    """These two are symlinked into every declared root of their role, so the
    file has to say that `<x-root>` means the directory it was reached through."""
    text = (TEMPLATES / contract).read_text(encoding="utf-8")
    assert "the directory this file is linked into" in text, contract
    assert "roles." in text, f"{contract} never names the key that declares it"


def test_the_framework_fixed_paths_are_still_literal():
    """The other half of the rule: what cannot move must not read as negotiable,
    or a project starts declaring a record path that schema 1 refuses."""
    text = (TEMPLATES / "CLAUDE.md").read_text(encoding="utf-8")
    assert "`project_memory/`" in text
    assert "never\nmoves" in text or "never moves" in text
    assert "paths.record" not in text, (
        "schema 1 pins the record at project_memory/ (project_config."
        "validate_config); presenting it as configurable invites a config that "
        "cannot validate")
