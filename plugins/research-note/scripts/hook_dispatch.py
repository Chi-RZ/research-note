#!/usr/bin/env python3
"""Translate Claude/Codex command-hook payloads into shared framework actions."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from project_config import ConfigError, feature_enabled, load_project_config

PLUGIN = Path(__file__).resolve().parent.parent
READ_ONLY = re.compile(
    r"^\s*(?:cd [^;&|]*&&\s*)?(?:grep|rg|cat|less|head|tail|sed|awk|ls|find|diff|wc|git)(?:\s|$)"
)
SUBMISSION = re.compile(
    r"(?:^|[;&|(]|\$\()\s*(?:sbatch|srun)(?:\s|$)|launch_bare_gpu\.sh|"
    r"(?:bash|sh|\./|source)\s+\S*submit[A-Za-z0-9_/]*\.sh"
)


def payload() -> dict:
    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def is_project(path: Path) -> bool:
    return (path / "project_memory").is_dir() and (
        (path / ".research-note/project.json").is_file()
        or
        (path / ".claude" / "framework.json").is_file()
        or (path / ".claude" / "roles.json").is_file()
    )


def project_root(data: dict) -> Path | None:
    candidates = [
        os.environ.get("RESEARCH_NOTE_PROJECT_DIR"),
        os.environ.get("CLAUDE_PROJECT_DIR"),
        data.get("cwd"),
        str(Path.cwd()),
    ]
    for value in candidates:
        if not value:
            continue
        start = Path(value).expanduser().resolve()
        for candidate in (start, *start.parents):
            if is_project(candidate):
                return candidate
    cwd = Path(str(data.get("cwd") or Path.cwd())).expanduser().resolve()
    common = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
    )
    if common.returncode == 0:
        main = Path(common.stdout.strip()).resolve().parent
        if is_project(main):
            return main
    return None


def hook_event(data: dict, fallback: str) -> str:
    return str(data.get("hook_event_name") or fallback)


def emit_context(event: str, context: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": event,
            "additionalContext": context,
        }
    }))


def child_env(root: Path) -> dict[str, str]:
    return {
        **os.environ,
        "RESEARCH_NOTE_PROJECT_DIR": str(root),
        "CLAUDE_PROJECT_DIR": str(root),
    }


def submission(data: dict) -> int:
    tool = data.get("tool_input") or {}
    command = str(tool.get("command") or tool.get("cmd") or "")
    if not command or READ_ONLY.search(command) or not SUBMISSION.search(command):
        return 0
    emit_context(
        hook_event(data, "PostToolUse"),
        # Name what is still a PERSON's to do. The job id, the log link, the
        # status and the phase's entry line are all written by record_submit
        # now; reminding about those trains the reader to skim the reminder.
        "Recording rule (root agent contract): if this was a job submission, "
        "record_submit has already written the job id, the log link, the status "
        "and the phase's entry line. What is still yours THIS turn: the phase's "
        "\u25b6 reading if the launch changes it, and any figure or table the "
        "entry owes. Ignore this if no job was launched; never invent a Jobs row.",
    )
    return 0


def edited_paths(data: dict) -> list[Path]:
    tool = data.get("tool_input") or {}
    values: list[str] = []
    for key in ("file_path", "path"):
        if tool.get(key):
            values.append(str(tool[key]))
    patch = str(tool.get("command") or tool.get("patch") or "")
    values.extend(re.findall(r"^\*\*\* (?:Add|Update) File: (.+)$", patch, re.M))
    cwd = Path(str(data.get("cwd") or Path.cwd())).resolve()
    result: list[Path] = []
    for value in values:
        path = Path(value)
        result.append(path.resolve() if path.is_absolute() else (cwd / path).resolve())
    return list(dict.fromkeys(result))


def lint(data: dict) -> int:
    root = project_root(data)
    if root is None:
        return 0
    findings: list[str] = []
    for path in edited_paths(data):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        if rel.startswith("project_memory/nodes/") and rel.endswith(".md"):
            linter = "check_node_page.py"
        elif rel.startswith("project_memory/objectives/") and rel.endswith(".md"):
            linter = "check_objective_page.py"
        else:
            continue
        if not path.exists():
            continue
        run = subprocess.run(
            [sys.executable, str(PLUGIN / "scripts" / linter), str(path), "--quiet"],
            cwd=root,
            env=child_env(root),
            capture_output=True,
            text=True,
        )
        if run.returncode == 1 and (run.stdout or run.stderr).strip():
            findings.append((run.stdout + run.stderr).strip()[:1500])
    if findings:
        emit_context(
            hook_event(data, "PostToolUse"),
            "Record lint on the page just edited (fix this turn):\n" + "\n".join(findings),
        )
    return 0


def worktree(data: dict) -> int:
    root = project_root(data)
    cwd = Path(str(data.get("cwd") or root or Path.cwd())).resolve()
    if root is None:
        return 0
    subprocess.run(
        ["bash", str(PLUGIN / "scripts" / "worktree_sparse.sh"), "--current", str(cwd)],
        cwd=cwd,
        env=child_env(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=12,
        check=False,
    )
    return 0


def routing(data: dict) -> int:
    emit_context(
        hook_event(data, "UserPromptSubmit"),
        "Routing check: if the user asks for new work that runs a computation or "
        "produces a result, place it in the research record yourself and state in "
        "one line where it landed. Work for an active objective is a phase on its "
        "Plan. Questions, discussion, code reading and search are answered directly.",
    )
    return 0


def harvest(data: dict) -> int:
    root = project_root(data)
    if root is None:
        return 0
    cwd = Path(str(data.get("cwd") or Path.cwd())).resolve()
    where = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--path-format=absolute",
         "--git-common-dir", "--git-dir"],
        capture_output=True,
        text=True,
    )
    if where.returncode == 0:
        common, gitdir, *_ = where.stdout.splitlines()
        if Path(common).resolve() != Path(gitdir).resolve():
            return 0
    run = subprocess.run(
        [sys.executable, str(PLUGIN / "scripts" / "harvest_check.py"), "--hook"],
        cwd=root,
        env=child_env(root),
        capture_output=True,
        text=True,
        timeout=15,
    )
    if run.stdout:
        print(run.stdout, end="")
    return 0


def session_start(data: dict) -> int:
    root = project_root(data)
    if root is None:
        return 0
    worktree({**data, "cwd": str(Path(str(data.get("cwd") or root)).resolve())})
    try:
        config = load_project_config(root)
    except ConfigError:
        return 0
    if not feature_enabled(config, "fixer"):
        return 0
    subprocess.Popen(
        ["bash", str(PLUGIN / "fixer" / "start_fixer_daemon.sh"), str(root)],
        cwd=root,
        env=child_env(root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    return 0


ACTIONS = {
    "submission": submission,
    "lint": lint,
    "worktree": worktree,
    "routing": routing,
    "harvest": harvest,
    "session-start": session_start,
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ACTIONS:
        print("usage: hook_dispatch.py <submission|lint|worktree|routing|harvest|session-start>", file=sys.stderr)
        return 2
    return ACTIONS[sys.argv[1]](payload())


if __name__ == "__main__":
    raise SystemExit(main())
