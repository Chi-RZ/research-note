"""worktree_sparse.sh — a worktree carries no record copy.

The cluster clone's exclusion applied at home: read-first inside a worktree
cannot hit a branch-point snapshot when the snapshot is not there, and the
main checkout must come through the sweep untouched."""

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "worktree_sparse.sh"


def _project(tmp_path):
    repo = tmp_path / "proj"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude" / "framework.json").write_text('{"record": "v3"}')
    (repo / "project_memory" / "nodes").mkdir(parents=True)
    (repo / "project_memory" / "nodes" / "x.md").write_text("record\n")
    (repo / "wiki").mkdir()
    (repo / "wiki" / "y.md").write_text("wiki\n")
    (repo / "src").mkdir()
    (repo / "src" / "z.py").write_text("code\n")
    for cmd in (["git", "init", "-q", "-b", "main", "."],
                ["git", "config", "user.email", "t@example.com"],
                ["git", "config", "user.name", "t"],
                ["git", "add", "-A"], ["git", "commit", "-q", "-m", "init"]):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True)
    wt = repo / ".claude" / "worktrees" / "job1"
    subprocess.run(["git", "worktree", "add", "-q", str(wt), "-b", "b1"],
                   cwd=repo, check=True, capture_output=True)
    return repo, wt


def run(repo):
    return subprocess.run(["bash", str(SCRIPT)],
                          env={"PATH": "/usr/bin:/bin:/usr/local/bin",
                               "CLAUDE_PROJECT_DIR": str(repo)},
                          capture_output=True, text=True, timeout=60)


def run_current(repo, worktree):
    return subprocess.run(
        ["bash", str(SCRIPT), "--current", str(worktree)],
        env={"PATH": "/usr/bin:/bin:/usr/local/bin",
             "RESEARCH_NOTE_PROJECT_DIR": str(repo)},
        capture_output=True, text=True, timeout=60)


def test_the_worktree_loses_the_record_and_keeps_the_code(tmp_path):
    repo, wt = _project(tmp_path)
    assert (wt / "project_memory").exists(), "precondition: full checkout"
    r = run(repo)
    assert r.returncode == 0, r.stderr
    assert not (wt / "project_memory").exists()
    assert not (wt / "wiki").exists()
    assert (wt / "src" / "z.py").exists()
    assert (wt / ".claude" / "framework.json").exists()


def test_main_is_untouched(tmp_path):
    repo, wt = _project(tmp_path)
    run(repo)
    assert (repo / "project_memory" / "nodes" / "x.md").exists()
    assert (repo / "wiki" / "y.md").exists()


def test_idempotent_and_worktree_scoped(tmp_path):
    repo, wt = _project(tmp_path)
    assert run(repo).returncode == 0
    assert run(repo).returncode == 0          # second sweep: no-op, still green
    outside = tmp_path / "handmade"
    subprocess.run(["git", "worktree", "add", "-q", str(outside), "-b", "b2"],
                   cwd=repo, check=True, capture_output=True)
    run(repo)
    assert (outside / "project_memory").exists(), \
        "a worktree OUTSIDE .claude/worktrees is not ours to reshape"


def test_current_mode_handles_a_codex_worktree_anywhere(tmp_path):
    repo, _legacy = _project(tmp_path)
    outside = tmp_path / "codex-worktree"
    subprocess.run(["git", "worktree", "add", "-q", str(outside), "-b", "codex"],
                   cwd=repo, check=True, capture_output=True)
    assert (outside / "project_memory").exists()
    result = run_current(repo, outside)
    assert result.returncode == 0, result.stderr
    assert not (outside / "project_memory").exists()
    assert not (outside / "wiki").exists()
    assert (outside / "src" / "z.py").exists()


def test_current_mode_never_sparsifies_main(tmp_path):
    repo, _worktree = _project(tmp_path)
    result = run_current(repo, repo)
    assert result.returncode == 0
    assert (repo / "project_memory" / "nodes" / "x.md").exists()
