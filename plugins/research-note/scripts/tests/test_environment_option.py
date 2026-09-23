"""uv is the supported environment, not a requirement.

A project that manages Python another way declares `environment.manager =
"other"`. Everything works; what it costs — no rebuild guarantee — is stated in
doctor and in every log header, never hidden. A project that declares nothing
is on uv, exactly as before.
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
PLUGIN = SCRIPTS.parent
LAUNCHER = PLUGIN / "skills/hpc-submit/scripts/launch_bare_gpu.sh"
sys.path.insert(0, str(SCRIPTS))
import project_config as pc  # noqa: E402


# --- the declaration ---------------------------------------------------------

def test_a_project_that_declares_nothing_is_on_uv():
    config = pc.initial_project_config()
    assert pc.environment_manager(config) == "uv"
    assert pc.python_runner(config) == "uv run --no-sync python -u"
    legacy = pc.initial_project_config(legacy=True)
    assert pc.environment_manager(legacy) == "uv"


def test_other_defaults_to_plain_python_and_a_runner_can_be_declared():
    config = pc.initial_project_config()
    config["environment"] = {"manager": "other"}
    pc.validate_config(config)
    assert pc.python_runner(config) == "python -u"
    config["environment"]["runner"] = "conda run -n lab python -u"
    pc.validate_config(config)
    assert pc.python_runner(config) == "conda run -n lab python -u"


@pytest.mark.parametrize("env,match", [
    ({"manager": "conda"}, "manager must be one of"),
    ({"manager": "other", "runner": "python"}, "with `-u`"),
])
def test_a_bad_declaration_is_refused(env, match):
    config = pc.initial_project_config()
    config["environment"] = env
    with pytest.raises(pc.ConfigError, match=match):
        pc.validate_config(config)


def test_set_environment_writes_the_declaration(tmp_path):
    (tmp_path / "project_memory").mkdir()
    pc.write_project_config(tmp_path, pc.initial_project_config())
    r = subprocess.run([sys.executable, str(SCRIPTS / "project_config.py"), "--project",
                        str(tmp_path), "set-environment", "other", "--runner", "python3 -u"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    saved = json.loads((tmp_path / ".research-note/project.json").read_text())
    assert saved["environment"] == {"manager": "other", "runner": "python3 -u"}


# --- the log header says which kind of run this was --------------------------

def _launch(tmp_path, environment, **extra_env):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    if environment is not None:
        (repo / ".research-note").mkdir()
        (repo / ".research-note/project.json").write_text(
            json.dumps({"environment": environment}))
    (repo / "job.py").write_text("print('hi')\n")
    for cmd in (["add", "-A"], ["-c", "user.name=t", "-c", "user.email=t@t",
                                "commit", "-q", "-m", "init"]):
        subprocess.run(["git", "-C", str(repo), *cmd], check=True, capture_output=True)
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp_path), "ENTRY": "none",
           **extra_env}
    r = subprocess.run(["bash", str(LAUNCHER), str(repo / "job.py"), "cpu", "0.5"],
                       env=env, capture_output=True, text=True, timeout=60)
    logs = glob.glob(str(repo / "logs" / "*.log"))
    assert logs, r.stdout + r.stderr
    return Path(logs[0]).read_text()


def test_an_unlocked_run_says_so_in_its_header_and_runs_the_declared_runner(tmp_path):
    head = _launch(tmp_path, {"manager": "other", "runner": "python3 -u"})
    assert "# Environment: NOT locked" in head, head
    command = next(l for l in head.splitlines() if l.startswith("# Command:"))
    assert " python3 -u " in command and "uv run" not in command, command
    time.sleep(1)
    assert "hi" in _read_eventually(tmp_path)


def _read_eventually(tmp_path):
    log = Path(glob.glob(str(tmp_path / "repo/logs/*.log"))[0])
    for _ in range(20):
        text = log.read_text()
        if "hi" in text:
            return text
        time.sleep(0.5)
    return log.read_text()


def test_a_project_without_a_declaration_runs_locked_on_uv(tmp_path):
    head = _launch(tmp_path, None)
    assert "# Environment: locked by uv.lock" in head, head
    assert "uv run --no-sync python -u" in head


def test_an_explicit_runner_still_overrides_the_project(tmp_path):
    """RUNNER= is how a one-off run departs from the project's runner."""
    head = _launch(tmp_path, {"manager": "other"}, RUNNER="python3 -X dev -u")
    command = next(l for l in head.splitlines() if l.startswith("# Command:"))
    assert " python3 -X dev -u " in command, command


# --- the Slurm templates follow the same declaration -------------------------

@pytest.mark.parametrize("name", ["cpu_batch.slurm", "gpu_batch.slurm"])
def test_the_slurm_templates_read_the_runner_and_state_the_environment(name):
    text = (PLUGIN / "skills/hpc-submit/scripts" / name).read_text()
    assert "rn_read_env" in text and 'srun $RUNNER "$SCRIPT"' in text
    assert "# Environment: NOT locked" in text and "# Environment: locked by uv.lock" in text
    assert "srun uv run" not in text, "the runner is the project's, not hardcoded"
