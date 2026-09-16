"""gen_index: the roster's `what it is` column.

The column is filled from each impl's `DESCRIPTION`, and its failure mode is
silence — a description the reader cannot parse yields the em dash, so the
column empties with nothing raised and nothing logged. That happened once, to
every node of a project whose impls write the description as the parenthesised
implicit concatenation Python offers for long strings. These tests pin the
spellings that must keep working.

The `## Domain libraries` section fails the same silent way and matters more:
it is the pointer the root contract's discovery rule sends every agent to
BEFORE writing any new code, and it is emitted only when hpc.env spells its
declaration a way this script recognises. When the declaration moved to
`LIB_<name>_LOCAL` the reader was left on the legacy spellings, so the section
simply stopped being written and the next regeneration deleted it from a
committed INDEX.md. These tests pin both spellings and the precedence.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent


@pytest.fixture()
def gen(tmp_path, monkeypatch):
    """Load gen_index with ROOT pointed at a scratch project."""
    spec = importlib.util.spec_from_file_location(
        "gen_index_under_test", SCRIPTS / "gen_index.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    return mod


def write_impl(root: Path, node: str, body: str) -> None:
    d = root / "experiments" / node / "impl"
    d.mkdir(parents=True)
    (d / "__init__.py").write_text(body, encoding="utf-8")


def test_single_line_description(gen, tmp_path):
    write_impl(tmp_path, "n", 'DESCRIPTION = "min-sum BP followed by OSD-CS"\n')
    assert gen.one_liner("n") == "min-sum BP followed by OSD-CS"


def test_parenthesised_description_is_joined(gen, tmp_path):
    """The spelling that silently emptied the column: a long description written
    as implicit concatenation inside parentheses."""
    write_impl(tmp_path, "n", 'DESCRIPTION = (\n'
                              '    "Edge-B DMRG and measurements: edge spectra "\n'
                              '    "and observables of the ladder\'s B edge.")\n')
    assert gen.one_liner("n") == (
        "Edge-B DMRG and measurements: edge spectra and observables of "
        "the ladder's B edge.")


def test_triple_quoted_description_collapses_to_one_line(gen, tmp_path):
    """The roster is a table row, so whatever the source spelling, the value has
    to come back without newlines."""
    write_impl(tmp_path, "n", 'DESCRIPTION = """first line\nsecond line"""\n')
    assert gen.one_liner("n") == "first line second line"


def test_other_assignments_are_not_mistaken_for_it(gen, tmp_path):
    write_impl(tmp_path, "n", 'BUILD_KNOBS = ("max_iter",)\n'
                              'DESCRIPTION = "the real one"\n'
                              'OTHER = "not this"\n')
    assert gen.one_liner("n") == "the real one"


def test_unparseable_impl_still_answers_the_simple_spelling(gen, tmp_path):
    """A partial edit or a shim should degrade the column, not break the run."""
    write_impl(tmp_path, "n", 'DESCRIPTION = "still readable"\n'
                              'def broken(:\n')
    assert gen.one_liner("n") == "still readable"


def test_missing_impl_and_missing_description_give_the_dash(gen, tmp_path):
    assert gen.one_liner("absent") == "—"
    write_impl(tmp_path, "n", 'BUILD_KNOBS = ("max_iter",)\n')
    assert gen.one_liner("n") == "—"


# --- the `## Domain libraries` pointer ---------------------------------------

def write_env(root: Path, text: str, name: str = "hpc.env") -> None:
    d = root / ".claude"
    d.mkdir(exist_ok=True)
    (d / name).write_text(text, encoding="utf-8")


def test_no_hpc_env_emits_no_section(gen, tmp_path):
    assert gen._domain_libs() == ""


def test_lib_local_declaration_is_the_pointer(gen, tmp_path):
    write_env(tmp_path, "LIB_qecbench_LOCAL=/Users/me/src/qecbench\n"
                        "LIB_qecbench_h200=/home/me/src/qecbench\n")
    out = gen._domain_libs()
    assert "## Domain libraries" in out
    assert "`/Users/me/src/qecbench`" in out
    assert "/home/me/src/qecbench" not in out, "the remote column is not this machine's"


def test_every_declared_lib_is_listed_once_in_order(gen, tmp_path):
    write_env(tmp_path, "LIB_alib_LOCAL=/src/a\n"
                        "LIB_blib_LOCAL=/src/b\n"
                        "LIB_alib_h200=/remote/a\n")
    out = gen._domain_libs()
    assert "`/src/a`, `/src/b`" in out


def test_a_lib_name_may_contain_underscores(gen, tmp_path):
    write_env(tmp_path, "LIB_my_lib_LOCAL=/src/my_lib\n")
    assert "`/src/my_lib`" in gen._domain_libs()


def test_commented_declarations_are_not_read(gen, tmp_path):
    """The shipped template documents the spelling in commented examples; a
    project that has not filled them in has declared nothing."""
    write_env(tmp_path, "#LIB_mylib_LOCAL=/Users/me/src/mylib\n"
                        "#LIB_mylib_hpc=/home/me/src/mylib\n")
    assert gen._domain_libs() == ""


def test_a_remote_only_declaration_is_not_this_machine(gen, tmp_path):
    write_env(tmp_path, "LIB_qecbench_h200=/home/me/src/qecbench\n")
    assert gen._domain_libs() == ""


def test_legacy_spellings_still_answer(gen, tmp_path):
    write_env(tmp_path, "DOMAIN_LIB_DIR=/src/legacy\n")
    assert "`/src/legacy`" in gen._domain_libs()
    write_env(tmp_path, 'DOMAIN_LIBS="/src/legacy2"\n')
    assert "`/src/legacy2`" in gen._domain_libs()


def test_lib_declarations_win_over_a_stale_legacy_line(gen, tmp_path):
    """A migrating project may carry both for a version; the new spelling is the
    one its push gate and log headers already read."""
    write_env(tmp_path, "DOMAIN_LIB_DIR=/src/legacy\n"
                        "LIB_qecbench_LOCAL=/src/current\n")
    out = gen._domain_libs()
    assert "`/src/current`" in out and "legacy" not in out


def test_hpc_local_env_declarations_are_read_too(gen, tmp_path):
    write_env(tmp_path, "LIB_qecbench_LOCAL=/src/adhoc\n", name="hpc.local.env")
    assert "`/src/adhoc`" in gen._domain_libs()


# --------------------------------------------------------------------------
# The Objectives roster section — read-first sees the goals, and the section
# is where the next free O<nn> is read from.
# --------------------------------------------------------------------------

OBJ_PAGE = """---
id: {oid}
status: {status}
created: 2026-08-01
budget: 40 GPUh
wake-me-if: "budget exceeded"
{attention}---

## Goal

The question.

## Plan

- [ ] **P1 — q** (1 GPUh)

## Verdict

**{verdict}** 0 entries await review.
"""


def _roster_project(root, gen, monkeypatch):
    (root / "project_memory" / "nodes").mkdir(parents=True)
    (root / "project_memory" / "objectives").mkdir()
    monkeypatch.setattr(gen, "NODES", root / "project_memory" / "nodes")
    monkeypatch.setattr(gen, "OBJECTIVES", root / "project_memory" / "objectives")
    monkeypatch.setattr(gen, "INDEX", root / "project_memory" / "_index.md")


def test_objectives_section_lists_id_status_and_verdict(gen, tmp_path, monkeypatch):
    _roster_project(tmp_path, gen, monkeypatch)
    (tmp_path / "project_memory" / "objectives" / "knee.md").write_text(
        OBJ_PAGE.format(oid="O02", status="active", attention="",
                        verdict="The knee sits at s6000."), encoding="utf-8")
    (tmp_path / "project_memory" / "objectives" / "older.md").write_text(
        OBJ_PAGE.format(oid="O01", status="closed", attention="",
                        verdict="Settled."), encoding="utf-8")
    gen.gen_node_roster()
    idx = (tmp_path / "project_memory" / "_index.md").read_text(encoding="utf-8")
    assert "## Objectives" in idx
    o1 = idx.index("| O01 |"); o2 = idx.index("| O02 |")
    assert o1 < o2, "sorted by id"
    assert "[knee](objectives/knee.md)" in idx
    assert "The knee sits at s6000." in idx
    assert "| closed |" in idx and "| active |" in idx


def test_a_verdict_cut_mid_bold_sheds_its_markers(gen, tmp_path, monkeypatch):
    """The cell truncates the Verdict's first line, so a ** pair the page
    balances is unbalanced in the cell and renders as literal asterisks —
    seen on a real record the first time the section generated (0.13.37)."""
    _roster_project(tmp_path, gen, monkeypatch)
    (tmp_path / "project_memory" / "objectives" / "long.md").write_text(
        OBJ_PAGE.format(oid="O09", status="active", attention="",
                        verdict="r16 for p = 0.035 to 0.065, r12 at p = 0.02 "
                                "and p = 0.08, at 24000 steps under cosine at "
                                "a very long tail that will be cut"),
        encoding="utf-8")
    gen.gen_node_roster()
    idx = (tmp_path / "project_memory" / "_index.md").read_text(encoding="utf-8")
    row = [l for l in idx.splitlines() if l.startswith("| O09 |")][0]
    assert "**" not in row
    assert "…" in row, "the long verdict was truncated"


def test_a_stopped_objective_is_marked(gen, tmp_path, monkeypatch):
    _roster_project(tmp_path, gen, monkeypatch)
    (tmp_path / "project_memory" / "objectives" / "stuck.md").write_text(
        OBJ_PAGE.format(oid="O03", status="active",
                        attention="attention: budget exceeded\n",
                        verdict="Waiting."), encoding="utf-8")
    gen.gen_node_roster()
    idx = (tmp_path / "project_memory" / "_index.md").read_text(encoding="utf-8")
    assert "active ⚠" in idx


def test_no_objectives_no_section(gen, tmp_path, monkeypatch):
    _roster_project(tmp_path, gen, monkeypatch)
    gen.gen_node_roster()
    idx = (tmp_path / "project_memory" / "_index.md").read_text(encoding="utf-8")
    assert "## Objectives" not in idx


# --------------------------------------------------------------------------
# The CLI split: one roster or both.
# --------------------------------------------------------------------------

def _scratch_project(tmp_path: Path) -> Path:
    (tmp_path / "project_memory" / "nodes").mkdir(parents=True)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "framework.json").write_text('{"record": "v3"}\n')
    (tmp_path / "src").mkdir()
    return tmp_path


def _run_cli(root: Path, *args: str):
    import os
    import subprocess
    env = dict(os.environ,
               RESEARCH_NOTE_PROJECT_DIR=str(root),
               CLAUDE_PROJECT_DIR=str(root))
    return subprocess.run([sys.executable, str(SCRIPTS / "gen_index.py"), *args],
                          capture_output=True, text=True, cwd=root, env=env)


def test_record_flag_writes_only_the_record_roster(tmp_path):
    """The record bus needs the split: it commits under `memory:`, a prefix
    the commit-msg hook forbids from staging src/."""
    root = _scratch_project(tmp_path)
    r = _run_cli(root, "--record")
    assert r.returncode == 0, r.stderr
    assert (root / "project_memory" / "_index.md").exists()
    assert not (root / "src" / "INDEX.md").exists()


def test_src_flag_writes_only_the_src_index(tmp_path):
    root = _scratch_project(tmp_path)
    r = _run_cli(root, "--src")
    assert r.returncode == 0, r.stderr
    assert (root / "src" / "INDEX.md").exists()
    assert not (root / "project_memory" / "_index.md").exists()


def test_src_index_uses_the_configured_library_roots(tmp_path):
    root = _scratch_project(tmp_path)
    config = json.loads(
        (SCRIPTS.parent / "templates/project.json").read_text(encoding="utf-8")
    )
    config["roles"]["libraries"] = ["code"]
    config["roles"]["tests"] = ["spec"]
    config["layers"]["source"]["paths"] = ["code", "spec"]
    path = root / ".research-note/project.json"
    path.parent.mkdir()
    path.write_text(json.dumps(config), encoding="utf-8")
    code = root / "code/pkg.py"
    code.parent.mkdir()
    code.write_text('def public():\n    """A public capability."""\n', encoding="utf-8")

    r = _run_cli(root, "--src")
    assert r.returncode == 0, r.stderr
    assert (root / "code/INDEX.md").is_file()
    assert not (root / "src/INDEX.md").exists()
    assert "code/pkg.py" in (root / "code/INDEX.md").read_text(encoding="utf-8")


def test_no_flag_still_writes_both(tmp_path):
    """Every caller that predates the split passes nothing."""
    root = _scratch_project(tmp_path)
    r = _run_cli(root)
    assert r.returncode == 0, r.stderr
    assert (root / "project_memory" / "_index.md").exists()
    assert (root / "src" / "INDEX.md").exists()


def test_an_unknown_flag_is_refused(tmp_path):
    root = _scratch_project(tmp_path)
    r = _run_cli(root, "--nope")
    assert r.returncode == 2
    assert "--nope" in r.stderr
