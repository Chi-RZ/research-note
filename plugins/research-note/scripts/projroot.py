#!/usr/bin/env python3
"""Resolve the project root for every framework script — ONE way, loudly.

Resolution order:
  1. $RESEARCH_NOTE_PROJECT_DIR or $CLAUDE_PROJECT_DIR — used only if it validates.
  2. Walk up from cwd to the first directory that validates.
  3. The caller's legacy guess (script physically at <project>/.claude/...),
     if it validates.
  4. Hard exit 2 with a diagnosis on stderr.

A directory "validates" when it carries `project_memory/` and the public
`.research-note/project.json` marker. Legacy `.claude/framework.json` and its
pre-v0.4 `roles.json` predecessor are still accepted.
The old `parents[N]` idiom silently produced a wrong ROOT the moment a script
moved — a plugin install is exactly such a move — and one linter then passed
vacuously on an empty glob. Hence: never guess silently, never exit 0 on a
root that is not a framework project.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def is_project_root(p: Path) -> bool:
    return (p / "project_memory").is_dir() and (
        (p / ".research-note" / "project.json").is_file()
        or (p / ".claude" / "framework.json").is_file()
        or (p / ".claude" / "roles.json").is_file())   # pre-v0.4 projects


def nth_parent(p: Path, n: int) -> Path | None:
    """`p.resolve().parents[n]`, or None when the path is too shallow — the
    legacy guess must never crash before resolve_root can diagnose."""
    p = p.resolve()
    return p.parents[n] if n < len(p.parents) else None


def resolve_root(legacy: Path | None = None) -> Path:
    env = os.environ.get("RESEARCH_NOTE_PROJECT_DIR") or os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        p = Path(env).resolve()
        if is_project_root(p):
            return p
    cur = Path.cwd().resolve()
    for p in (cur, *cur.parents):
        if is_project_root(p):
            return p
    if legacy is not None:
        p = legacy.resolve()
        if is_project_root(p):
            return p
    print(
        "projroot: cannot find the project root — need a directory containing "
        "project_memory/ and .research-note/project.json (or a legacy marker).\n"
        f"  tried project-dir env={env!r}, cwd walk-up from {Path.cwd()}, "
        f"legacy layout {str(legacy) if legacy else '(none)'}.\n"
        "  Run from inside the project or export RESEARCH_NOTE_PROJECT_DIR.",
        file=sys.stderr)
    sys.exit(2)
