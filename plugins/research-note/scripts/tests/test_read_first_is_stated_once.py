"""The read-first list lives in the root contract and nowhere else.

Two skills had copied it instead of referencing it, and the copies had already
paid for themselves: `objective`'s re-plan step — the single point where the
framework decides what question to ask next — listed `_index.md` and the
touched nodes' conclusions and had silently lost the memories, which appear
nowhere else in that skill. A copy of a rule is a rule that drifts, and this
one drifted at the worst site in the system.

The shape that is correct, and what this test allows: a skill says "read-first
(root contract)" and then names what ITS OWN job needs on top — `correct` reads
the contested entry and its logs' headers, `objective` reads the objective page
and the entries it links. Those extras differ legitimately. The base does not.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
CONTRACT = ROOT / "templates" / "CLAUDE.md"
SKILLS = sorted((ROOT / "skills").glob("*/SKILL.md"))
MENTION = re.compile(r"read[- ]first", re.IGNORECASE)

# The four sources the base names. Naming them here is the point: if the
# contract drops one, this test says so rather than the record quietly
# losing a layer the way objective's copy lost the memories.
#
# `knowledge/index.md` without its root: the knowledge ROOT is declared per
# project (`roles.knowledge`, `wiki/` by default) so the contract writes
# `<knowledge-root>/knowledge/index.md`; the path INSIDE that root is the
# framework's and is what this test holds.
BASE = ["`_index.md`", "conclusions", "MEMORY.md", "knowledge/index.md"]


def bullet() -> str:
    """The read-first bullet, whitespace collapsed.

    It is hard-wrapped in the contract, so any phrase this test looks for can
    straddle a newline — asserting on the raw text tests the wrap, not the
    rule.
    """
    raw = next(b for b in CONTRACT.read_text().split("\n- ")
               if b.startswith("**Read-first"))
    return " ".join(raw.split())


@pytest.mark.parametrize("source", BASE)
def test_the_contract_names_every_source(source):
    assert source in bullet(), f"the read-first bullet no longer names {source}"


def test_both_entrances_get_their_own_question():
    """The bullet used to name two entrances and give only the entry's
    questions, which is why re-plan wrote its own list: the canonical one did
    not serve it."""
    b = bullet()
    assert "An entry asks" in b and "a phase asks" in b, b


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.parent.name)
def test_no_skill_keeps_its_own_copy_of_the_list(skill):
    """Detect the chain by its SHAPE, not by the words "read-first".

    The first version of this test looked for `_index.md` near a "read-first"
    mention, and it would have passed while the worst copy survived: objective's
    re-plan step never said "read-first" at all — it simply reproduced the list
    inline, which is exactly how it could quietly drop the memories and have
    nobody notice. What identifies the chain is `_index.md` standing next to the
    nodes' conclusions; a skill naming `_index.md` for some other purpose (the
    next free objective number is read off it) does not pair them.
    """
    lines = skill.read_text().split("\n")
    for i in range(len(lines)):
        window = " ".join(lines[i:i + 3])
        if "_index.md" in window and "conclusions" in window:
            pytest.fail(
                f"{skill.parent.name} keeps its own copy of the read-first list "
                f"near line {i+1}; say \"read-first (root contract)\" and add only "
                f"this job's own extras:\n  {window.strip()}")


def test_the_contract_answers_to_the_name_skills_call_it():
    """Skills and sibling contracts point at "the root contract"; the file that
    name refers to never used it, so the pointer led to a name its target did
    not answer to."""
    assert "root contract" in CONTRACT.read_text()


@pytest.mark.parametrize("name", ["plan", "objective", "analyze", "correct"])
def test_every_entrance_skill_carries_the_pointer(name):
    """A bare "read-first" resolves only because the contract happens to be in
    context. `analyze` — two entrances — carried no pointer at all."""
    text = (ROOT / "skills" / name / "SKILL.md").read_text()
    assert re.search(r"read[- ]first \(root\s+contract\)", text, re.IGNORECASE), (
        f"{name} names read-first without ever pointing at where the list lives")
