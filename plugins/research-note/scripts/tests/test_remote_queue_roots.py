"""`remote.sh queue` finds a bare remote's live jobs under the DECLARED
experiment roots, not under a hardcoded `experiments/`.

The snapshot is what J3/J4 and the board's Running tab read. It used to begin
`[ -d "$RD/experiments" ] || exit 0`, so a project whose runs live in `trials/`
got an EMPTY snapshot — and an empty snapshot does not read as "cannot tell",
it reads as "every job left the queue", which is a J3 on every running entry.

The remote side is exercised for real: `rssh` is `ssh <opts> <host> <cmd>`, so
a stub `ssh` on PATH runs <cmd> locally against a scratch directory that plays
the cluster clone.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
PLUGIN = SCRIPTS.parent
REMOTE = SCRIPTS / "remote.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("squeue") is not None,
    reason="the bare-remote branch is only reached where the remote has no Slurm")

SSH_STUB = """#!/bin/sh
# Stand in for ssh: drop the options and the host, run the command here.
while [ $# -gt 0 ]; do
  case "$1" in
    -o|-i|-p|-F) shift 2 ;;
    -*) shift ;;
    *) break ;;
  esac
done
shift                      # the host
[ $# -gt 0 ] || exit 0
sh -c "$*"
"""

HEADER = """# Timestamp: {stamp}
# PID wrapper: {pid}
# Exit code: running
some output
"""


def declare(root: Path, experiments: list[str]) -> None:
    config = json.loads((PLUGIN / "templates/project.json").read_text())
    config["roles"]["experiments"] = experiments
    config["layers"]["experiments"]["paths"] = experiments
    (root / ".research-note").mkdir(exist_ok=True)
    (root / ".research-note/project.json").write_text(json.dumps(config))


def log_for(root: Path, rel: str, pid: int) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(HEADER.format(
        stamp=time.strftime("%Y-%m-%dT%H:%M:%S%z"), pid=pid))
    return path


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "proj"
    (root / "project_memory").mkdir(parents=True)
    (root / ".claude").mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    # the clone this "cluster" holds IS the scratch project
    (root / ".claude/hpc.env").write_text(
        f"REMOTE_HOST=fakehost\nREMOTE_DIR={root}\n")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "ssh").write_text(SSH_STUB)
    (bin_dir / "ssh").chmod(0o755)
    return root, bin_dir


def run_queue(root: Path, bin_dir: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if not k.startswith("REMOTE_")}
    env.update(PATH=f"{bin_dir}:{env.get('PATH', '/usr/bin:/bin')}",
               RESEARCH_NOTE_PROJECT_DIR=str(root),
               CLAUDE_PROJECT_DIR=str(root))
    return subprocess.run(["bash", str(REMOTE), "queue"], cwd=root, env=env,
                          capture_output=True, text=True, timeout=120)


@pytest.fixture()
def live_pid():
    proc = subprocess.Popen(["sleep", "120"])
    yield proc.pid
    proc.kill()
    proc.wait()


def test_the_snapshot_finds_a_job_under_a_declared_experiment_root(project, live_pid):
    root, bin_dir = project
    declare(root, ["trials"])
    log_for(root, "trials/newton/smooth/logs/run-a.log", live_pid)

    r = run_queue(root, bin_dir)
    assert r.returncode == 0, r.stdout + r.stderr
    snapshot = (root / ".fixer/remote_queue").read_text()
    assert f"{live_pid} RUNNING @fakehost" in snapshot, snapshot
    assert "1 job(s)" in r.stdout


def test_a_root_the_project_did_not_declare_is_not_scanned(project, live_pid):
    """The loop follows the declaration, so the same live job logged under an
    undeclared `experiments/` is not counted — and never counted twice."""
    root, bin_dir = project
    declare(root, ["trials"])
    log_for(root, "trials/newton/smooth/logs/run-a.log", live_pid)
    log_for(root, "experiments/newton/smooth/logs/run-a.log", live_pid)

    r = run_queue(root, bin_dir)
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [l for l in (root / ".fixer/remote_queue").read_text().splitlines() if l.strip()]
    assert lines == [f"{live_pid} RUNNING @fakehost"], lines


def test_several_declared_roots_are_all_scanned(project, live_pid):
    root, bin_dir = project
    declare(root, ["trials", "campaigns"])
    log_for(root, "trials/newton/smooth/logs/run-a.log", live_pid)
    log_for(root, "campaigns/other/grid/logs/run-b.log", live_pid)

    r = run_queue(root, bin_dir)
    assert r.returncode == 0, r.stdout + r.stderr
    lines = [l for l in (root / ".fixer/remote_queue").read_text().splitlines() if l.strip()]
    assert len(lines) == 2 and all(f"{live_pid} RUNNING" in l for l in lines), lines


def test_a_finished_job_is_absent_and_the_snapshot_is_still_written(project):
    """A header whose exit code is set is not in the queue; the file must still
    be replaced, or every consumer reads the previous snapshot as current."""
    root, bin_dir = project
    declare(root, ["trials"])
    path = log_for(root, "trials/newton/smooth/logs/run-a.log", 999999)
    path.write_text(path.read_text().replace("# Exit code: running", "# Exit code: 0"))

    r = run_queue(root, bin_dir)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (root / ".fixer/remote_queue").read_text().strip() == ""
    assert "0 job(s)" in r.stdout
