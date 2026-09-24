"""Skill text and linter agree on every lint-code name a recipe greps.

A waiter is `until lint | grep -q <code>; do sleep; done` — grep a code the
linter never emits and the loop spins silently forever, indistinguishable from
"still running". The rename that armed this (R2 -> J3 in the 0.13.0 v3
rewrite) was hand-synced into the skill text and happened to be synced right;
nothing checked it, and waiters written from the pre-rename text spun until an
unrelated fallback fired. This test makes the next rename a red test instead
of a silent spin: every lint-code token used on a grep line inside any skill's
fenced bash is asserted to exist in a linter's published code list.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LINTERS = [ROOT / "scripts" / "check_node_page.py",
           ROOT / "scripts" / "check_objective_page.py"]
CODE = re.compile(r"\b(E\d+|P\d+|J\d+|N\d+|V\d+|M\d+|O\d+|R\d+|FW)\b")


def known_codes() -> set[str]:
    out: set[str] = set()
    for f in LINTERS:
        out |= set(CODE.findall(f.read_text(encoding="utf-8")))
    return out


def grep_code_tokens() -> dict[str, set[str]]:
    """skill name -> code tokens appearing on grep lines in its bash fences."""
    hits: dict[str, set[str]] = {}
    for skill in sorted((ROOT / "skills").glob("*/SKILL.md")):
        text = skill.read_text(encoding="utf-8")
        for fence in re.findall(r"```(?:bash|sh)\n(.*?)```", text, re.S):
            for line in fence.splitlines():
                if line.lstrip().startswith("#"):
                    continue          # prose may cite a retired code's history
                if "grep" not in line:
                    continue
                toks = set(CODE.findall(line))
                if toks:
                    hits.setdefault(skill.parent.name, set()).update(toks)
    return hits


def test_every_grepped_code_is_one_a_linter_emits():
    known = known_codes()
    unknown = {skill: sorted(toks - known)
               for skill, toks in grep_code_tokens().items() if toks - known}
    assert not unknown, (
        f"skill recipes grep lint codes no linter knows: {unknown} — "
        f"a waiter built from that line spins silently forever")
