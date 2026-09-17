"""doctor.sh's split: the core is checked for every project; an integration
only when the project enables it or the caller names it. A disabled
integration is neither started, required nor reported broken.

Run against a scratch project, output read as text — the same way a user
reads it.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
PLUGIN = SCRIPTS.parent
DOCTOR = SCRIPTS / "doctor.sh"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def doctor(proj: Path, *args: str) -> tuple[int, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("REMOTE_")}
    env["HOME"] = str(proj.parent / "home")       # no real extensions, no real agents
    # conftest points every script at a fake project through these; doctor
    # honours them first, so aim them here
    env["RESEARCH_NOTE_PROJECT_DIR"] = env["CLAUDE_PROJECT_DIR"] = str(proj)
    (proj.parent / "home").mkdir(exist_ok=True)
    r = subprocess.run(["bash", str(DOCTOR), *args], cwd=proj, env=env,
                       capture_output=True, text=True, timeout=120)
    return r.returncode, ANSI.sub("", r.stdout + r.stderr)


@pytest.fixture()
def proj(tmp_path):
    """A schema-1 project with every integration off, healthy at the core."""
    root = tmp_path / "proj"
    root.mkdir()
    git = lambda *a: subprocess.run(["git", "-C", str(root), *a], check=True,  # noqa: E731
                                    capture_output=True, text=True,
                                    env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                         "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    git("init", "-q", "-b", "main")
    for d in ("src", "tests", "experiments", "wiki", "project_memory/nodes",
              "project_memory/objectives", ".claude", ".research-note"):
        (root / d).mkdir(parents=True)
    (root / ".research-note/project.json").write_text(
        (PLUGIN / "templates/project.json").read_text())
    (root / ".research-note/.gitignore").write_text("state/\n")
    (root / ".claude/framework.json").write_text((PLUGIN / "templates/framework.json").read_text())
    venv = root / ".venv/bin"
    venv.mkdir(parents=True)
    (venv / "python").write_text("#!/bin/sh\necho Python 3.12.0\n")
    (venv / "python").chmod(0o755)
    (root / "README.md").write_text("x\n")
    git("add", "-A")
    git("commit", "-q", "-m", "chore: seed")
    git("config", "research-note.pluginRoot", str(PLUGIN))
    subprocess.run(["python3", str(SCRIPTS / "githooks_install.py"), "install", str(root),
                    "--plugin", str(PLUGIN)], check=True, capture_output=True)
    return root


def set_feature(proj: Path, name: str, value: bool) -> None:
    path = proj / ".research-note/project.json"
    config = json.loads(path.read_text())
    config["features"][name] = value
    path.write_text(json.dumps(config))


def test_a_local_only_project_is_green_and_no_integration_is_checked(proj):
    rc, out = doctor(proj)
    assert rc == 0, out
    assert "all green" in out
    for feature in ("fixer", "hpc", "editor", "cross_agent"):
        assert f"{feature}: disabled" in out and "not checked" in out
    assert "background scanner" not in out and "remote:" not in out


def test_core_alone_says_nothing_about_integrations(proj):
    rc, out = doctor(proj, "--core")
    assert rc == 0, out
    assert "disabled" not in out and "background scanner" not in out
    assert "record layer" in out and "python environment" in out


def test_a_disabled_fixer_is_not_reported_broken_but_can_be_asked_for(proj):
    rc, out = doctor(proj)
    assert rc == 0 and "fixer never ran" not in out
    rc, out = doctor(proj, "--fixer")
    assert "fixer never ran" in out, out
    assert "record layer" not in out, "a focused check does not drag the core in"
    rc, out = doctor(proj, "--fixer", "--core")
    assert "fixer never ran" in out and "record layer" in out


def test_an_enabled_integration_is_checked_by_default(proj):
    set_feature(proj, "hpc", True)
    rc, out = doctor(proj)
    assert rc == 1, out
    assert "hpc.env is missing" in out
    (proj / ".claude/hpc.env").write_text("# empty profile\n")
    rc, out = doctor(proj)
    assert rc == 0, out
    assert "local launch venue" in out


def test_the_core_finds_its_own_state_dir_and_wants_it_ignored(proj):
    rc, out = doctor(proj, "--core")
    assert "core state dir .research-note/state/ (gitignored)" in out
    (proj / ".research-note/.gitignore").unlink()
    rc, out = doctor(proj, "--core")
    assert "is not gitignored" in out


def test_a_pre_declaration_project_checks_every_integration(proj):
    (proj / ".research-note/project.json").unlink()
    rc, out = doctor(proj)
    assert "background scanner" in out
    assert "legacy project has no .research-note/project.json" in out


def test_an_unknown_flag_is_refused(proj):
    rc, out = doctor(proj, "--frobnicate")
    assert rc == 2 and "unknown argument" in out


def test_a_project_with_no_commits_yet_is_green(tmp_path):
    """bootstrap runs `git init` and the user commits afterwards, so an unborn
    branch is the state every new project passes through. rev-parse answers
    "HEAD" there, which read as the wrong branch."""
    root = tmp_path / "fresh"
    for d in ("src", "tests", "experiments", "wiki", "project_memory/nodes",
              ".claude", ".research-note"):
        (root / d).mkdir(parents=True)
    (root / ".research-note/project.json").write_text(
        (PLUGIN / "templates/project.json").read_text())
    (root / ".research-note/.gitignore").write_text("state/\n")
    (root / ".claude/framework.json").write_text((PLUGIN / "templates/framework.json").read_text())
    venv = root / ".venv/bin"
    venv.mkdir(parents=True)
    (venv / "python").write_text("#!/bin/sh\necho Python 3.12.0\n")
    (venv / "python").chmod(0o755)
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "research-note.pluginRoot", str(PLUGIN)], check=True)
    subprocess.run(["python3", str(SCRIPTS / "githooks_install.py"), "install", str(root),
                    "--plugin", str(PLUGIN)], check=True, capture_output=True)

    rc, out = doctor(root, "--core")
    assert "no commits yet" in out, out
    assert rc == 0, out


def test_doctor_names_the_top_level_directories_no_layer_owns(proj):
    """The state a project drifts into: a folder appears, nothing objects, and
    the first commit touching it is refused under every prefix months later."""
    rc, out = doctor(proj, "--core")
    assert "every top-level directory belongs to a layer" in out, out

    (proj / "packages").mkdir()
    (proj / "notebooks").mkdir()
    rc, out = doctor(proj, "--core")
    assert "no layer owns: notebooks packages" in out, out
    assert ".research-note/project.json" in out
    assert rc == 0, "a warning, not a failure — the folder may be legitimate"

    # ignored is a fine answer, and so is declared
    (proj / ".gitignore").write_text("notebooks/\n")
    config = json.loads((proj / ".research-note/project.json").read_text())
    config["layers"]["packaging"] = {"paths": ["packages"], "prefixes": ["pkg"]}
    (proj / ".research-note/project.json").write_text(json.dumps(config))
    rc, out = doctor(proj, "--core")
    assert "every top-level directory belongs to a layer" in out, out
