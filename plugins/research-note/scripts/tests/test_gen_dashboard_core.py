"""The board on a project that runs no fixer.

The compatibility policy's one rule for a disabled integration: it is not
started, not required, not reported as broken. The board reported a missing
fixer heartbeat on every project, fixer or not — and blamed cron, which the
fixer has not used for many releases.
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


def project(tmp_path: Path, *, declare: bool, fixer: bool = False) -> Path:
    root = tmp_path / "proj"
    for d in ("src", "tests", "experiments", "wiki", "project_memory/nodes",
              "project_memory/objectives", ".claude"):
        (root / d).mkdir(parents=True)
    (root / ".claude/framework.json").write_text((PLUGIN / "templates/framework.json").read_text())
    if declare:
        config = json.loads((PLUGIN / "templates/project.json").read_text())
        config["features"]["fixer"] = fixer
        (root / ".research-note").mkdir()
        (root / ".research-note/project.json").write_text(json.dumps(config))
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


def attention(root: Path) -> list[str]:
    env = {**os.environ, "RESEARCH_NOTE_PROJECT_DIR": str(root), "CLAUDE_PROJECT_DIR": str(root)}
    for script in ("gen_index.py", "gen_dashboard.py"):
        r = subprocess.run(["python3", str(SCRIPTS / script)], cwd=root, env=env,
                           capture_output=True, text=True, timeout=120)
        assert r.returncode == 0, script + "\n" + r.stdout + r.stderr
    html = (root / "project_memory/dashboard.html").read_text()
    m = re.search(r'"attention":\s*(\[.*?\])', html, re.S)
    assert m, "no attention list in the board"
    return json.loads(m.group(1))


def test_a_project_without_a_fixer_has_no_fixer_items_on_its_board(tmp_path):
    items = attention(project(tmp_path, declare=True, fixer=False))
    assert not any("fixer" in item for item in items), items


def test_a_project_that_runs_a_fixer_is_still_told_when_it_never_ran(tmp_path):
    items = attention(project(tmp_path, declare=True, fixer=True))
    assert any("fixer heartbeat missing" in item for item in items), items
    assert not any("cron" in item for item in items), "the fixer is a daemon"


def test_a_pre_declaration_project_keeps_the_heartbeat_check(tmp_path):
    """Before the declaration every project ran a fixer; the check must not
    vanish from those boards on update."""
    items = attention(project(tmp_path, declare=False))
    assert any("fixer heartbeat missing" in item for item in items), items
