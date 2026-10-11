#!/usr/bin/env python3
"""Set the research-note version in both host manifests and the marketplace.

Run once at the start of a development cycle, then once for its release.
This only edits version declarations; it does not commit, tag or publish.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


NUMBER = r"(?:0|[1-9][0-9]*)"
PRE = rf"(?:{NUMBER}|[0-9]*[A-Za-z-][0-9A-Za-z-]*)"
SEMVER = re.compile(rf"{NUMBER}\.{NUMBER}\.{NUMBER}(?:-{PRE}(?:\.{PRE})*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?")
MANIFESTS = (
    "plugins/research-note/.claude-plugin/plugin.json",
    "plugins/research-note/.codex-plugin/plugin.json",
    ".claude-plugin/marketplace.json",
)


def set_version(repo: Path, version: str) -> list[Path]:
    if not SEMVER.fullmatch(version):
        raise ValueError("expected a SemVer version, e.g. 0.1.1-dev.1 or 0.1.1")
    edits = []
    # Validate all three before changing any, including marketplace identity.
    for rel in MANIFESTS:
        path = repo / rel
        data = json.loads(path.read_text(encoding="utf-8"))
        candidates = data.get("plugins", []) if rel == MANIFESTS[-1] else [data]
        matches = [item for item in candidates if item.get("name") == "research-note"]
        if len(matches) != 1:
            raise ValueError(f"expected one research-note entry in {path}")
        entry = matches[0]
        if entry.get("version") != version:
            entry["version"] = version
            edits.append((path, json.dumps(data, indent=2, ensure_ascii=False) + "\n"))
    for path, content in edits:
        path.write_text(content, encoding="utf-8")
    return [path for path, _ in edits]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        changed = set_version(args.repo.resolve(), args.version)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, f"set_version: {exc}\n")
    print(f"research-note {args.version}: {len(changed)} manifest(s) updated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
