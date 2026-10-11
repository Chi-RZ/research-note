"""The public compatibility matrix for setup and update.

Each test is one row of the release gate, run against a real repository with
the real bootstrap and the real updater: an empty directory; an existing
repository with its own layout and its own git hooks; one agent or none on
PATH; local-only use; the optional fixer and HPC. Nothing here mocks a file
the user would see.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

SCRIPTS = Path(__file__).resolve().parents[1]
PLUGIN = SCRIPTS.parent
BOOTSTRAP = SCRIPTS / "bootstrap_project.py"
UPDATE = SCRIPTS / "update_projects.sh"
DOCTOR = SCRIPTS / "doctor.sh"
GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def env_for(home: Path, **extra: str) -> dict[str, str]:
    """A machine with neither claude nor codex on PATH, a private HOME, and
    none of the test suite's own project-dir overrides. `uv` is a stand-in on
    PATH: the core requires it, the matrix does not exercise it."""
    fake_bin = home / "bin"
    if not (fake_bin / "uv").exists():
        fake_bin.mkdir(exist_ok=True)
        (fake_bin / "uv").write_text("#!/bin/sh\nexit 0\n")
        (fake_bin / "uv").chmod(0o755)
    return {"HOME": str(home), "PATH": f"{fake_bin}:/usr/bin:/bin:/usr/local/bin",
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            **({"RESEARCH_NOTE_RELEASE_STORE": os.environ["RESEARCH_NOTE_RELEASE_STORE"]}
               if "RESEARCH_NOTE_RELEASE_STORE" in os.environ else {}), **GIT_ENV, **extra}


def sh(cwd: Path, home: Path, *args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=cwd, env=env_for(home, **kw.pop("env", {})),
                          capture_output=True, text=True, timeout=300, **kw)


def bootstrap(proj: Path, home: Path, *flags: str) -> subprocess.CompletedProcess:
    r = sh(proj, home, sys.executable, str(BOOTSTRAP), str(proj), "--no-self-tests", *flags)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "[FAIL" not in r.stdout, r.stdout
    return r


def update(proj: Path, home: Path) -> subprocess.CompletedProcess:
    r = sh(proj, home, "bash", str(UPDATE), "--agents", "none", str(proj))
    assert r.returncode == 0, r.stdout + r.stderr
    return r


def commit_all(proj: Path, home: Path, message: str) -> subprocess.CompletedProcess:
    sh(proj, home, "git", "add", "-A")
    return sh(proj, home, "git", "commit", "-q", "-m", message)


def write_hook(directory: Path, name: str, body: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


@pytest.fixture()
def home(tmp_path):
    h = tmp_path / "home"
    h.mkdir()
    return h


@pytest.fixture()
def empty(tmp_path):
    d = tmp_path / "fresh"
    d.mkdir()
    return d


@pytest.fixture()
def existing(tmp_path, home):
    """A repository with history, its own code layout and its own hooks."""
    d = tmp_path / "legacy"
    (d / "code").mkdir(parents=True)
    (d / "code/pkg.py").write_text("def f():\n    return 1\n")
    (d / "README.md").write_text("an existing project\n")
    sh(d, home, "git", "init", "-q", "-b", "main")
    assert commit_all(d, home, "initial").returncode == 0
    write_hook(d / ".git/hooks", "pre-commit", f'echo ran >> "{d}/.git/old-pre-commit-ran"\n')
    write_hook(d / ".git/hooks", "commit-msg", f'echo "$1" >> "{d}/.git/old-commit-msg-ran"\n')
    write_hook(d / ".git/hooks", "pre-push",
               f'{{ echo "$1 $2"; cat; }} > "{d}/.git/old-pre-push-saw"\nexit 3\n')
    return d


def declaration(**roles: list[str]) -> dict:
    config = json.loads((PLUGIN / "templates/project.json").read_text())
    config["roles"].update(roles)
    config["layers"]["source"]["paths"] = roles.get("libraries", ["src"]) + roles.get("tests", ["tests"])
    config["layers"]["experiments"]["paths"] = roles.get("experiments", ["experiments"])
    config["layers"]["knowledge"]["paths"] = roles.get("knowledge", ["wiki"])
    return config


# --------------------------------------------------------------------------
# an empty directory, local-only
# --------------------------------------------------------------------------

def test_an_empty_directory_becomes_a_local_only_project(empty, home):
    r = bootstrap(empty, home)
    assert (empty / ".git").is_dir()
    for d in ("src", "tests", "experiments", "project_memory/nodes", "wiki"):
        assert (empty / d).is_dir(), d
    config = json.loads((empty / ".research-note/project.json").read_text())
    assert not any(config["features"].values()), "a new project starts with every integration off"
    assert (empty / ".claude/CLAUDE.md").read_text().startswith("<!-- framework section generated")
    assert (empty / "CLAUDE.md").is_symlink() and (empty / "AGENTS.md").is_symlink()
    assert (empty / ".research-note/.gitignore").read_text() == (
        "state/\nruntime/\neditables/\neditables.env\n")
    assert sh(empty, home, "git", "config", "core.hooksPath").stdout.strip() == ".claude/githooks"
    # what a disabled integration leaves behind: nothing
    assert not (empty / "project_memory/dashboard.html").exists()
    assert not (empty / ".fixer").exists()
    assert not (empty / ".claude/hpc.env").exists()
    assert not (empty / ".claude/hpc-submit").exists()
    allowed = json.loads((empty / ".claude/settings.json").read_text())["permissions"]["allow"]
    assert not any("sbatch" in a or "ssh" in a for a in allowed)
    assert "· project agent bindings" in r.stdout
    assert "Claude + Codex" in r.stdout and "shared release" in r.stdout


def test_doctor_core_is_green_on_a_local_only_project(empty, home):
    bootstrap(empty, home)
    assert commit_all(empty, home, "agent: research-note setup").returncode == 0
    venv = empty / ".venv/bin"
    venv.mkdir(parents=True)
    (venv / "python").write_text("#!/bin/sh\necho Python 3.12.0\n")
    (venv / "python").chmod(0o755)
    r = sh(empty, home, "bash", str(DOCTOR), env={"RESEARCH_NOTE_PROJECT_DIR": str(empty)})
    assert r.returncode == 0, r.stdout
    assert "all green" in r.stdout
    for feature in ("fixer", "hpc", "editor"):
        assert f"{feature}: disabled" in r.stdout
    assert "Claude and Codex project runtime pinned" in r.stdout


def test_rerunning_setup_and_update_changes_nothing(empty, home):
    bootstrap(empty, home)
    assert commit_all(empty, home, "agent: research-note setup").returncode == 0
    r = bootstrap(empty, home)
    assert sh(empty, home, "git", "status", "--porcelain").stdout == "", r.stdout
    assert "[new " not in r.stdout, r.stdout
    r = update(empty, home)
    assert sh(empty, home, "git", "status", "--porcelain").stdout == "", r.stdout
    assert "nothing to sync" in r.stdout, r.stdout


# --------------------------------------------------------------------------
# an existing repository: its layout, its hooks
# --------------------------------------------------------------------------

def test_an_existing_repository_keeps_its_layout_and_passes_the_commit_checks(existing, home):
    (existing / ".research-note").mkdir()
    (existing / ".research-note/project.json").write_text(json.dumps(declaration(
        libraries=["code"], tests=["spec"], experiments=["trials"], knowledge=["docs"])))
    bootstrap(existing, home)
    for d in ("spec", "trials", "docs"):
        assert (existing / d).is_dir(), d
    assert not (existing / "src").exists() and not (existing / "wiki").exists()
    assert (existing / "trials/CLAUDE.md").is_symlink()
    assert (existing / "code/pkg.py").read_text().startswith("def f()"), "nothing was moved"

    r = commit_all(existing, home, "agent: research-note setup")
    assert r.returncode == 0, r.stderr
    # ongoing work under the declared roots, through the declared layers
    (existing / "code/more.py").write_text("x = 1\n")
    (existing / "spec/test_more.py").write_text("def test_x():\n    pass\n")
    assert commit_all(existing, home, "feat: more").returncode == 0
    (existing / "trials/n/impl").mkdir(parents=True)
    (existing / "trials/n/impl/run.py").write_text("pass\n")
    assert commit_all(existing, home, "exp(n): first node").returncode == 0


def test_an_existing_repositorys_hooks_all_still_run_after_setup_and_after_update(existing, home, tmp_path):
    bootstrap(existing, home)
    assert commit_all(existing, home, "agent: research-note setup").returncode == 0
    assert (existing / ".git/old-pre-commit-ran").read_text().count("ran") == 1
    assert (existing / ".git/old-commit-msg-ran").exists()

    bare = tmp_path / "remote.git"
    sh(tmp_path, home, "git", "init", "-q", "--bare", str(bare))
    sh(existing, home, "git", "remote", "add", "origin", str(bare))
    r = sh(existing, home, "git", "push", "-q", "origin", "main")
    assert r.returncode != 0, "the LFS-style pre-push exits 3; the push must be refused"
    saw = (existing / ".git/old-pre-push-saw").read_text()
    assert saw.startswith("origin ") and "refs/heads/main" in saw

    update(existing, home)
    (existing / "note.txt").write_text("after update\n")
    assert commit_all(existing, home, "chore: after update").returncode == 0
    assert (existing / ".git/old-pre-commit-ran").read_text().count("ran") == 2


def test_a_project_from_before_the_declaration_is_migrated_once_by_update(existing, home):
    """The migration path an installed project takes: old layout, framework.json
    only, a contract with an appendix — one update, nothing lost."""
    (existing / ".claude").mkdir()
    (existing / ".claude/framework.json").write_text((PLUGIN / "templates/framework.json").read_text())
    (existing / "project_memory").mkdir()
    old_template = (PLUGIN / "templates/CLAUDE.md").read_text()
    (existing / ".claude/CLAUDE.md").write_text(old_template + "\n## Mission\n\nkeep this\n")
    assert commit_all(existing, home, "initial framework").returncode == 0

    r = update(existing, home)
    assert "migrated  .research-note/project.json" in r.stdout
    config = json.loads((existing / ".research-note/project.json").read_text())
    assert all(config["features"].values())
    assert (existing / ".claude/CLAUDE.md").read_text().rstrip().endswith("keep this")
    assert (existing / ".claude/githooks/dispatch").exists()
    r = update(existing, home)
    assert "migrated" not in r.stdout


# --------------------------------------------------------------------------
# one agent or none; the optional integrations
# --------------------------------------------------------------------------

def test_optional_hpc_is_present_only_when_asked_for(empty, home):
    bootstrap(empty, home, "--with-hpc")
    assert (empty / ".claude/hpc.env").is_file()
    assert (empty / ".claude/hpc-submit").is_dir()
    allowed = json.loads((empty / ".claude/settings.json").read_text())["permissions"]["allow"]
    assert "Bash(sbatch:*)" in allowed
    config = json.loads((empty / ".research-note/project.json").read_text())
    assert config["features"]["hpc"] is True and config["features"]["fixer"] is False


def test_bootstrap_refuses_unknown_flags_and_help_writes_nothing(tmp_path, home):
    """`--help` once ran a real bootstrap into the caller's cwd, git init
    included — a flag the script does not know is refused, never a project path."""
    cwd = tmp_path / "somewhere"
    cwd.mkdir()
    r = sh(cwd, home, sys.executable, str(BOOTSTRAP), "--help")
    assert r.returncode == 0 and "usage:" in r.stdout
    r = sh(cwd, home, sys.executable, str(BOOTSTRAP), "--frobnicate")
    assert r.returncode == 2 and "unknown flag" in r.stderr
    assert list(cwd.iterdir()) == [], "nothing may be written by a refused or help invocation"


def test_an_existing_repos_own_claude_md_is_merged_into_one_file(existing, home):
    """The case a real adoption hits: the repo already instructs its agents.
    Afterwards there is ONE file for the root — the framework text with their
    rules below it — because two files instructing one directory means the
    framework's half can go unread (Claude documents ./CLAUDE.md and
    ./.claude/CLAUDE.md as two locations for one project file)."""
    own = "# House rules\n\nAlways run make test before committing.\n"
    (existing / "CLAUDE.md").write_text(own)
    (existing / "AGENTS.md").write_text(own)          # same rules, both agents
    assert commit_all(existing, home, "own contract").returncode == 0

    r = bootstrap(existing, home)
    assert "adopted" in r.stdout, r.stdout

    for name in ("CLAUDE.md", "AGENTS.md"):
        assert (existing / name).is_symlink(), name
    text = (existing / ".claude/CLAUDE.md").read_text()
    assert text.startswith("<!-- framework section generated by research-note")
    assert "Always run make test before committing." in text
    assert text.count("Always run make test") == 1
    # and the merged file is what an agent reads through either name
    assert (existing / "CLAUDE.md").read_text() == text
    assert (existing / "AGENTS.md").read_text() == text
    assert commit_all(existing, home, "agent: research-note setup").returncode == 0


def test_dashboard_is_opt_in_and_the_choice_survives_setup(empty, home):
    bootstrap(empty, home, "--with-dashboard")
    board = empty / "project_memory/dashboard.html"
    assert board.is_file()
    board.unlink()
    bootstrap(empty, home)
    assert board.is_file()
    board.unlink()
    bootstrap(empty, home, "--no-dashboard")
    assert not board.exists()


def test_install_check_is_read_only_and_detects_broken_views(empty, home):
    bootstrap(empty, home)
    before = {str(p.relative_to(empty)): p.read_bytes() for p in empty.rglob("*")
              if p.is_file() and ".git" not in p.parts}
    r = sh(empty, home, sys.executable, str(BOOTSTRAP), str(empty), "--check")
    assert r.returncode == 0, r.stdout + r.stderr
    after = {str(p.relative_to(empty)): p.read_bytes() for p in empty.rglob("*")
             if p.is_file() and ".git" not in p.parts}
    assert before == after
    (empty / "AGENTS.md").unlink()
    r = sh(empty, home, sys.executable, str(BOOTSTRAP), str(empty), "--check")
    assert r.returncode != 0
    assert "AGENTS.md" in r.stdout
    assert not (empty / "AGENTS.md").exists()
