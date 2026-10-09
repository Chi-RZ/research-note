"""Editable checkouts use arbitrary real paths and one project-local uv slot."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1]
SYNC = SCRIPTS / "sync_editables.sh"
pytestmark = pytest.mark.integration
SSH_STUB = """#!/bin/sh
while [ $# -gt 0 ]; do
  case "$1" in
    -o|-i|-p|-F) shift 2 ;;
    -*) shift ;;
    *) break ;;
  esac
done
shift
[ $# -gt 0 ] || exit 0
sh -c "$*"
"""


def git(*args: str, cwd: Path | None = None) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, check=True,
                       capture_output=True, text=True)
    return r.stdout.strip()


def make_repo(path: Path) -> str:
    path.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=path)
    git("config", "user.email", "test@example.com", cwd=path)
    git("config", "user.name", "Test", cwd=path)
    (path / "lib.py").write_text("value = 1\n")
    git("add", "lib.py", cwd=path)
    git("commit", "-qm", "initial", cwd=path)
    return git("rev-parse", "HEAD", cwd=path)


@pytest.fixture()
def configured(tmp_path: Path):
    project = tmp_path / "local-project"
    remote_project = tmp_path / "remote-project"
    local_lib = tmp_path / "developer" / "mylib"
    remote_lib = tmp_path / "cluster-libs" / "mylib"
    (project / ".research-note").mkdir(parents=True)
    (remote_project / ".research-note").mkdir(parents=True)
    (project / ".research-note/project.json").write_text("{}\n")
    (project / "pyproject.toml").write_text(
        '[tool.uv.sources]\n'
        'mylib = { path = ".research-note/editables/mylib", editable = true }\n')
    sha = make_repo(local_lib)
    (project / ".research-note/editables.env").write_text(
        f"LIB_mylib_LOCAL={local_lib}\nLIB_mylib_fakehost={remote_lib}\n")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    ssh = bindir / "ssh"
    ssh.write_text(SSH_STUB)
    ssh.chmod(0o755)
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}",
           "RESEARCH_NOTE_PROJECT_DIR": str(project)}
    return project, remote_project, local_lib, remote_lib, sha, env


def run_sync(configured) -> subprocess.CompletedProcess:
    project, remote_project, _, _, _, env = configured
    return subprocess.run(
        ["bash", str(SYNC), "--host", "fakehost", "--remote-dir", str(remote_project)],
        cwd=project, env=env, capture_output=True, text=True, timeout=30)


def assert_aligned(configured, result: subprocess.CompletedProcess) -> None:
    project, remote_project, local_lib, remote_lib, sha, _ = configured
    assert result.returncode == 0, result.stdout + result.stderr
    assert (project / ".research-note/editables/mylib").resolve() == local_lib.resolve()
    assert (remote_project / ".research-note/editables/mylib").resolve() == remote_lib.resolve()
    assert git("rev-parse", "HEAD", cwd=remote_lib) == sha


def test_no_git_remote_crosses_ssh_as_a_bundle(configured):
    result = run_sync(configured)
    assert_aligned(configured, result)
    assert "via bundle" in result.stdout


def test_fetchable_origin_uses_push_and_fetch(configured, tmp_path: Path):
    _, _, local_lib, _, _, _ = configured
    origin = tmp_path / "mylib-origin.git"
    git("init", "--bare", "-q", "--initial-branch=main", str(origin))
    git("remote", "add", "origin", str(origin), cwd=local_lib)

    result = run_sync(configured)
    assert_aligned(configured, result)
    assert "via git" in result.stdout


def test_first_local_sync_initializes_a_non_git_library(tmp_path: Path):
    project = tmp_path / "project"
    library = tmp_path / "plain-library"
    (project / ".research-note").mkdir(parents=True)
    library.mkdir()
    (library / "lib.py").write_text("value = 1\n")
    (project / ".research-note/project.json").write_text("{}\n")
    (project / ".research-note/editables.env").write_text(
        f"LIB_mylib_LOCAL={library}\n")
    env = {**os.environ, "RESEARCH_NOTE_PROJECT_DIR": str(project)}

    result = subprocess.run(["bash", str(SYNC), "--local"], cwd=project,
                            env=env, capture_output=True, text=True)

    assert result.returncode == 1
    assert (library / ".git").is_dir()
    assert "make its first commit" in result.stderr
