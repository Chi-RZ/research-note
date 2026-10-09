"""Contract templates and project-specific appendices share one editable file.

Older projects may still have a separate rules file. It is read for one-time
compatibility, but new projects write directly below the project-rules heading.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
PLUGIN = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import contracts as ct  # noqa: E402

TEMPLATE = (PLUGIN / "templates/CLAUDE.md").read_text()
HEAD = ct.marker("CLAUDE.md") + TEMPLATE          # how every generated root contract begins


def said_of(proj: Path, **kw) -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    ct.sync(proj, PLUGIN, say=lambda s, w, d="": out.append((s, w, d)), **kw)
    return out


def states(said, contract="CLAUDE.md") -> list[str]:
    return [s for s, w, _ in said if w == f".claude/{contract}"]


@pytest.fixture()
def proj(tmp_path):
    root = tmp_path / "proj"
    (root / ".claude").mkdir(parents=True)
    return root


# --- render ------------------------------------------------------------------

# --- a fresh project ---------------------------------------------------------

def test_a_fresh_project_gets_four_editable_contracts_and_no_rules_files(proj):
    said = said_of(proj)
    for contract, (_, rules) in ct.CONTRACTS.items():
        assert (proj / ".claude" / contract).is_file()
        assert not (proj / ".research-note/rules" / rules).exists()
        assert ("generated", f".claude/{contract}") in {(s, w) for s, w, _ in said}
    text = (proj / ".claude/CLAUDE.md").read_text()
    assert text.startswith(HEAD) and text.endswith("instead.\n")


def test_sync_is_idempotent(proj):
    said_of(proj)
    before = {p: p.read_bytes() for p in proj.rglob("*") if p.is_file()}
    second = said_of(proj)
    assert all(s == "same" for s, w, _ in second if w.startswith(".claude/")), second
    assert {p: p.read_bytes() for p in proj.rglob("*") if p.is_file()} == before


def test_a_project_appends_below_the_heading_and_update_keeps_it(proj):
    said_of(proj)
    target = proj / ".claude/CLAUDE.md"
    target.write_text(target.read_text() + "\n## Mission\n\nA paragraph the project wrote.\n")
    said = said_of(proj)
    assert states(said) == ["same"]
    text = target.read_text()
    assert text.startswith(HEAD) and "A paragraph the project wrote." in text
    assert text.count("<!--") == 1


def test_dry_run_reports_and_writes_nothing(proj):
    said = said_of(proj, dry=True)
    assert states(said) == ["generated"]
    assert not (proj / ".claude/CLAUDE.md").exists()
    assert not (proj / ".research-note").exists()


# --- migration from the byte-prefix + appendix scheme ------------------------

def test_an_appendix_under_an_older_framework_text_is_migrated_too(proj):
    """0.1.9–0.2.3: the framework half has since moved AND the project appended.
    The old scheme refused here ('DRIFTED — port by hand'); the block itself is
    the seam that lets both halves be recovered."""
    older = "# Some older framework text\n\nthat has since changed.\n\n---\n\n" + ct.LEGACY_BOUNDARY_BLOCK
    (proj / ".claude/CLAUDE.md").write_text(older + "\n## Mission\n\nkeep me too\n")
    said = said_of(proj)
    assert states(said) == ["regenerated"]
    text = (proj / ".claude/CLAUDE.md").read_text()
    assert text.startswith(HEAD) and "keep me too" in text
    assert "Some older framework text" not in text


def test_a_boundary_file_with_no_appendix_is_plain_drift(proj):
    older = "# older\n\n" + ct.LEGACY_BOUNDARY_BLOCK
    (proj / ".claude/CLAUDE.md").write_text(older)
    said = said_of(proj)
    assert states(said) == ["regenerated"]
    assert not any(s == "migrated" for s, _, _ in said)


# --- pre-boundary files (before 0.1.9) ---------------------------------------

OLD_TEMPLATE = "# An older root contract\n\nshipped by some 0.1.x release.\n"


@pytest.fixture()
def plugin_with_history(tmp_path):
    """A plugin copy whose history.json also knows OLD_TEMPLATE."""
    import json, hashlib, shutil
    fake = tmp_path / "plugin"
    shutil.copytree(PLUGIN / "templates", fake / "templates")
    history = json.loads((fake / "templates/history.json").read_text())
    history["CLAUDE.md"].append({"bytes": len(OLD_TEMPLATE.encode()),
                                 "sha256": hashlib.sha256(OLD_TEMPLATE.encode()).hexdigest(),
                                 "commit": "test"})
    (fake / "templates/history.json").write_text(json.dumps(history))
    return fake


def said_with(proj: Path, plugin: Path, **kw):
    out = []
    ct.sync(proj, plugin, say=lambda s, w, d="": out.append((s, w, d)), **kw)
    return out


def test_a_pre_boundary_file_from_a_shipped_template_is_regenerated(proj, plugin_with_history):
    (proj / ".claude/CLAUDE.md").write_text(OLD_TEMPLATE)
    said = said_with(proj, plugin_with_history)
    assert states(said) == ["regenerated"]
    assert not any(s == "migrated" for s, _, _ in said)


def test_a_pre_boundary_appendix_is_recognised_by_the_shipped_hash_and_migrated(proj, plugin_with_history):
    """The template GREW since that release, so a line count could not see the
    appendix; the hash of the exact old text can."""
    (proj / ".claude/CLAUDE.md").write_text(OLD_TEMPLATE + "\n## Mission\nmine\n")
    said = said_with(proj, plugin_with_history)
    assert states(said) == ["regenerated"]
    assert (proj / ".claude/CLAUDE.md").read_text().rstrip().endswith("mine")


def test_a_pre_boundary_file_matching_no_shipped_template_is_a_conflict_until_forced(proj):
    (proj / ".claude/CLAUDE.md").write_text("# text this plugin never shipped\n" * 3)
    said = said_of(proj)
    assert states(said) == ["CONFLICT"]
    assert (proj / ".claude/CLAUDE.md").read_text().startswith("# text this plugin")
    said = said_of(proj, force=True)
    assert states(said) == ["regenerated"]
    assert (proj / ".claude/CLAUDE.md").read_text().startswith(HEAD)


def test_history_knows_every_current_template():
    """Release discipline: a template edit must be followed by
    `contracts.py record-history`, or a project on THIS version could not be
    recognised by the next one."""
    history = json.loads((PLUGIN / "templates/history.json").read_text())
    for contract, (template, _) in ct.CONTRACTS.items():
        digest = hashlib.sha256((PLUGIN / "templates" / template).read_bytes()).hexdigest()
        assert any(row["sha256"] == digest for row in history.get(contract, [])), \
            f"{template} changed — run: python3 scripts/contracts.py record-history"


def test_history_has_no_worktree_marker_for_a_committed_template():
    """A provisional marker must acquire its real commit on the next pass."""
    history = json.loads((PLUGIN / "templates/history.json").read_text())
    prefix = subprocess.run(
        ["git", "-C", str(PLUGIN / "templates"), "rev-parse", "--show-prefix"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    for contract, (template, _) in ct.CONTRACTS.items():
        committed = set()
        shas = subprocess.run(
            ["git", "-C", str(PLUGIN / "templates"), "log", "--format=%H", "--", template],
            capture_output=True, text=True, check=True,
        ).stdout.split()
        for sha in shas:
            blob = subprocess.run(
                ["git", "-C", str(PLUGIN / "templates"), "show", f"{sha}:{prefix}{template}"],
                capture_output=True, check=True,
            ).stdout
            committed.add(hashlib.sha256(blob).hexdigest())
        stale = [row["sha256"] for row in history.get(contract, [])
                 if row.get("commit") == "worktree" and row["sha256"] in committed]
        assert not stale, f"{contract} has committed templates still labelled worktree"


# --- a file edited in place --------------------------------------------------

def test_an_edit_inside_the_framework_section_is_a_conflict(proj):
    said_of(proj)
    target = proj / ".claude/CLAUDE.md"
    target.write_text(target.read_text().replace("## Layers", "## Layers (edited here)", 1))
    said = said_of(proj)
    assert states(said) == ["CONFLICT"]
    assert "(edited here)" in target.read_text()


def test_a_pre_generation_file_edited_in_place_is_a_conflict_until_forced(proj):
    """0.1.9–0.2.3 file whose boundary block itself was altered: neither shape
    fits, so no appendix can be told apart — left alone, diff command printed."""
    altered = TEMPLATE.replace("## Layers", "## Layers (edited here)", 1)
    (proj / ".claude/CLAUDE.md").write_text(altered + "\nsomething\n")
    said = said_of(proj)
    assert states(said) == ["CONFLICT"]
    detail = next(d for s, w, d in said if s == "CONFLICT")
    assert "render" in detail and "diff" in detail
    assert "(edited here)" in (proj / ".claude/CLAUDE.md").read_text(), "left alone"
    said = said_of(proj, force=True)
    assert states(said) == ["regenerated"]
    assert (proj / ".claude/CLAUDE.md").read_text().startswith(HEAD)


# --- the CLI, as the updater calls it ----------------------------------------

def test_the_cli_syncs_and_renders(proj):
    r = subprocess.run([sys.executable, str(SCRIPTS / "contracts.py"), "sync", str(proj),
                        "--plugin", str(PLUGIN)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert any(line.startswith("generated") for line in r.stdout.splitlines())
    r = subprocess.run([sys.executable, str(SCRIPTS / "contracts.py"), "render", str(proj),
                        "CLAUDE.md", "--plugin", str(PLUGIN)], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == (proj / ".claude/CLAUDE.md").read_text()


# --- a project's own contract file at a view path ----------------------------
# A directory holds ONE contract. Claude's own docs give `./CLAUDE.md` and
# `./.claude/CLAUDE.md` as two locations for one project file, so leaving both
# risks the framework half going unread — and two files instructing one
# directory is the wrong shape regardless of which one an agent picks up.

def test_a_projects_own_root_contract_becomes_the_project_section(proj):
    (proj.parent / "proj/CLAUDE.md").write_text("# House rules\n\nAlways run make test.\n")
    said = said_of(proj)
    assert ("adopted", "CLAUDE.md") in {(s, w) for s, w, _ in said}, said
    assert ("view", "CLAUDE.md") in {(s, w) for s, w, _ in said}, said

    root = proj / "CLAUDE.md"
    assert root.is_symlink() and os.readlink(root) == ".claude/CLAUDE.md"
    text = (proj / ".claude/CLAUDE.md").read_text()
    assert text.startswith(HEAD), "the framework half still comes first"
    assert text.rstrip().endswith("Always run make test.")
    assert ct.BOUNDARY in text


def test_adoption_is_idempotent_and_reports_nothing_the_second_time(proj):
    (proj / "CLAUDE.md").write_text("# House rules\n")
    said_of(proj)
    before = (proj / ".claude/CLAUDE.md").read_text()
    said = said_of(proj)
    assert not any(s in ("adopted", "view") for s, _, _ in said), said
    assert (proj / ".claude/CLAUDE.md").read_text() == before


def test_a_subtree_contract_of_its_own_is_adopted_under_the_declared_root(proj):
    config = json.loads((PLUGIN / "templates/project.json").read_text())
    config["roles"]["experiments"] = ["trials"]
    config["layers"]["experiments"]["paths"] = ["trials"]
    (proj / ".research-note").mkdir(exist_ok=True)
    (proj / ".research-note/project.json").write_text(json.dumps(config))
    (proj / "trials").mkdir()
    (proj / "trials/CLAUDE.md").write_text("Runs here are named after the rig.\n")

    said = said_of(proj)
    assert ("adopted", "trials/CLAUDE.md") in {(s, w) for s, w, _ in said}, said
    assert (proj / "trials/CLAUDE.md").is_symlink()
    assert "named after the rig" in (proj / ".claude/experiments-CLAUDE.md").read_text()
    assert "named after the rig" not in (proj / ".claude/CLAUDE.md").read_text()


def test_the_second_agents_view_is_a_conflict_when_it_says_something_else(proj):
    """Both root names present with DIFFERENT text: one becomes the project
    section, the other is left alone and reported — merging two texts is the
    user's call, not a guess."""
    (proj / "CLAUDE.md").write_text("# For Claude\n")
    (proj / "AGENTS.md").write_text("# For Codex, and different\n")
    said = said_of(proj)
    assert ("adopted", "CLAUDE.md") in {(s, w) for s, w, _ in said}
    assert any(s == "CONFLICT" and w == "AGENTS.md" for s, w, _ in said), said
    assert (proj / "AGENTS.md").is_file() and not (proj / "AGENTS.md").is_symlink()
    assert (proj / "AGENTS.md").read_text() == "# For Codex, and different\n"


def test_the_same_text_under_both_names_is_adopted_once(proj):
    (proj / "CLAUDE.md").write_text("# One set of rules\n")
    (proj / "AGENTS.md").write_text("# One set of rules\n")
    said = said_of(proj)
    assert [w for s, w, _ in said if s == "adopted"] == ["CLAUDE.md"]
    assert not any(s == "CONFLICT" for s, _, _ in said), said
    assert (proj / "AGENTS.md").is_symlink()
    assert (proj / ".claude/CLAUDE.md").read_text().count("One set of rules") == 1


def test_a_copied_generated_contract_contributes_only_its_own_section(proj):
    """Someone copied the contract instead of linking it, then wrote a rule in
    the copy. The framework text must not be folded into the project section."""
    said_of(proj)                                    # generate first
    generated = (proj / ".claude/CLAUDE.md").read_text()
    (proj / "CLAUDE.md").unlink(missing_ok=True)
    (proj / "CLAUDE.md").write_text(generated + "\nOne local rule.\n")

    said = said_of(proj)
    assert ("adopted", "CLAUDE.md") in {(s, w) for s, w, _ in said}, said
    text = (proj / ".claude/CLAUDE.md").read_text()
    assert text.count("path authority") == 1, "the framework half was duplicated"
    assert text.rstrip().endswith("One local rule.")


def test_dry_run_adopts_nothing(proj):
    (proj / "CLAUDE.md").write_text("# House rules\n")
    said_of(proj, dry=True)
    assert (proj / "CLAUDE.md").read_text() == "# House rules\n"
    assert not (proj / ".claude/CLAUDE.md").exists()
