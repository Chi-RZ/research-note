"""src/INDEX.md is current whenever src/ moves.

The index is a generated view, and the discovery rule reads it before any new
code is written. Regenerating it is a step AFTER a branch lands, in the MAIN
checkout (a worktree here is sparse and generates a short index) — a different
place from the work, and skipping it fails nothing. The reporting session
skipped it twice in one day; ten capabilities sat in src/ for hours with no
row, and the user found the dirty tree, not the agent.

What makes this checkable at all: the generator IS the verifier. There is no
second implementation of "what the index should say" to drift out of step.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
HOOK = SCRIPTS.parent / "githooks" / "pre-commit"

SRC = '''"""a module."""


def alpha():
    """First capability."""


def beta():
    """Second capability."""
'''


@pytest.fixture()
def proj(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("gen_index_under_test",
                                                  SCRIPTS / "gen_index.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    src = tmp_path / "src"
    src.mkdir()
    (src / "thing.py").write_text(SRC)
    (tmp_path / "project_memory" / "nodes").mkdir(parents=True)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "SRC", src)
    monkeypatch.setattr(mod, "SRC_INDEX", src / "INDEX.md")
    return mod, tmp_path


def test_check_passes_on_a_freshly_generated_index(proj):
    mod, _ = proj
    mod.gen_src_index()
    assert mod.gen_src_index(check=True) is True


def test_check_fails_when_src_gained_a_capability(proj, capsys):
    mod, tmp_path = proj
    mod.gen_src_index()
    (tmp_path / "src" / "thing.py").write_text(
        SRC + '\n\ndef gamma():\n    """Third capability."""\n')
    assert mod.gen_src_index(check=True) is False
    err = capsys.readouterr().err
    assert "STALE" in err and "MAIN CHECKOUT" in err, err


def test_check_fails_when_the_index_is_absent(proj):
    mod, _ = proj
    assert mod.gen_src_index(check=True) is False


def test_check_writes_nothing(proj):
    """A gate that repairs the thing it guards hides the miss it exists to
    surface — and pre-commit runs before the index could be staged anyway."""
    mod, tmp_path = proj
    mod.gen_src_index()
    idx = tmp_path / "src" / "INDEX.md"
    (tmp_path / "src" / "thing.py").write_text(SRC + '\n\ndef gamma():\n    """x."""\n')
    before = idx.read_text()
    mod.gen_src_index(check=True)
    assert idx.read_text() == before


def test_the_parse_warnings_of_the_source_do_not_reach_the_gate(proj, capsys):
    """A gate that prints a screen of unrelated SyntaxWarnings is a gate people
    learn to scroll past."""
    mod, tmp_path = proj
    (tmp_path / "src" / "noisy.py").write_text('def d():\n    """a \\d regex."""\n')
    mod.gen_src_index()
    mod.gen_src_index(check=True)
    assert "SyntaxWarning" not in capsys.readouterr().err


def test_the_hook_only_runs_the_check_when_src_is_staged(tmp_path):
    """Every other commit must be untouched — a record commit, a wiki commit
    and an agent commit pay nothing for this gate."""
    text = HOOK.read_text()
    assert "SKIP_SRC_INDEX" in text
    gate = text.split("--- 3.")[1]
    assert "grep -q '^src/'" in gate, gate
    r = subprocess.run(["sh", "-n", str(HOOK)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
