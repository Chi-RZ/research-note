"""Execute the shared Claude/Codex command hooks against both payload shapes."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PLUGIN = Path(__file__).resolve().parents[2]
HOOKS = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())
sys.path.insert(0, str(PLUGIN / "scripts"))


def _commands():
    for event, entries in HOOKS["hooks"].items():
        for entry in entries:
            for hook in entry.get("hooks", []):
                yield event, hook["command"]


@pytest.mark.parametrize(
    "event,cmd", list(_commands()),
    ids=lambda value: value if isinstance(value, str) and len(value) < 30 else "",
)
def test_hook_command_is_valid_shell(event, cmd):
    run = subprocess.run(["/bin/sh", "-n"], input=cmd, capture_output=True, text=True)
    assert run.returncode == 0, f"{event}: {run.stderr.strip()}"


def _one(event: str) -> str:
    return next(command for name, command in _commands() if name == event)


def _run(event: str, data: dict):
    return subprocess.run(
        ["/bin/sh", "-c", _one(event)],
        input=json.dumps(data),
        capture_output=True,
        text=True,
        env={**os.environ, "PLUGIN_ROOT": str(PLUGIN)},
    )


def test_user_prompt_submit_emits_valid_json():
    run = _run("UserPromptSubmit", {"hook_event_name": "UserPromptSubmit"})
    assert run.returncode == 0 and not run.stderr.strip()
    output = json.loads(run.stdout)
    assert output["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert output["hookSpecificOutput"]["additionalContext"].strip()


@pytest.mark.parametrize("command,expect_context", [
    ("sbatch gpu_batch.slurm", True),
    ("bash launch_bare_gpu.sh run.py", True),
    ("srun --pty python x.py", True),
    ("bash submit_gs.sh", True),
    ("grep -c 'launch_bare_gpu.sh' f", False),
    ("cat scripts/launch_bare_gpu.sh", False),
    ("git log --oneline", False),
    ("ls -la experiments/", False),
    ("python3 run.py", False),
])
def test_post_tool_use_fires_only_on_a_submission(command, expect_context):
    run = _run("PostToolUse", {
        "hook_event_name": "PostToolUse",
        "tool_input": {"command": command},
    })
    assert run.returncode == 0
    assert bool(run.stdout.strip()) is expect_context
    if expect_context:
        assert json.loads(run.stdout)["hookSpecificOutput"]["hookEventName"] == "PostToolUse"


def test_hooks_use_the_cross_agent_plugin_root_contract():
    for _event, command in _commands():
        assert "PLUGIN_ROOT" in command and "CLAUDE_PLUGIN_ROOT" in command
        assert "CLAUDE_PROJECT_DIR" not in command
        assert "jq " not in command


def test_codex_apply_patch_payload_exposes_edited_paths(tmp_path):
    from hook_dispatch import edited_paths

    data = {
        "cwd": str(tmp_path),
        "tool_input": {
            "command": "*** Begin Patch\n*** Update File: project_memory/nodes/x.md\n"
        },
    }
    assert edited_paths(data) == [(tmp_path / "project_memory/nodes/x.md").resolve()]


def test_session_start_does_not_launch_a_disabled_fixer(tmp_path, monkeypatch):
    import hook_dispatch

    (tmp_path / "project_memory").mkdir()
    config = tmp_path / ".research-note/project.json"
    config.parent.mkdir()
    config.write_text("{}")
    monkeypatch.setattr(hook_dispatch, "project_root", lambda _data: tmp_path)
    monkeypatch.setattr(hook_dispatch, "worktree", lambda _data: 0)
    launched = []
    monkeypatch.setattr(
        hook_dispatch.subprocess, "Popen", lambda *args, **kwargs: launched.append(args)
    )

    assert hook_dispatch.session_start({}) == 0
    assert launched == []


def test_session_start_keeps_legacy_fixer_behaviour(tmp_path, monkeypatch):
    import hook_dispatch

    (tmp_path / "project_memory").mkdir()
    marker = tmp_path / ".claude/framework.json"
    marker.parent.mkdir()
    marker.write_text("{}")
    monkeypatch.setattr(hook_dispatch, "project_root", lambda _data: tmp_path)
    monkeypatch.setattr(hook_dispatch, "worktree", lambda _data: 0)
    launched = []
    monkeypatch.setattr(
        hook_dispatch.subprocess, "Popen", lambda *args, **kwargs: launched.append(args)
    )

    assert hook_dispatch.session_start({}) == 0
    assert len(launched) == 1
