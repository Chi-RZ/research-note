#!/usr/bin/env python3
"""Maintain the project's four editable contract files.

The framework template is written first. Project-specific rules are written
below the ``## Project-specific rules`` heading in the same file. ``AGENTS.md``
and ``CLAUDE.md`` are two agent-specific views of that file, not two copies of
the project's rules. Older releases kept the project appendix in
``.research-note/rules/``; ``sync`` imports that appendix once for compatibility.

    contracts.py sync    PROJECT [--plugin DIR] [--dry-run] [--force]
    contracts.py render  PROJECT NAME          (print the generated text)

``sync`` updates the framework portion only when it can identify it. Text below
the project-rules heading is preserved. If the framework portion was edited in
place and the project text cannot be separated safely, the file is left alone
and a ``CONFLICT`` is reported.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

#: contract file -> (template, legacy rules filename)
CONTRACTS = {
    "CLAUDE.md": ("CLAUDE.md", "root.md"),
    "experiments-CLAUDE.md": ("experiments-CLAUDE.md", "experiments.md"),
    "project_memory-CLAUDE.md": ("project_memory-CLAUDE.md", "record.md"),
    "wiki-CLAUDE.md": ("wiki-CLAUDE.md", "wiki.md"),
}
# Read-only compatibility location for projects created by older releases.
# New projects put their additions directly in the contract file.
RULES_DIR = Path(".research-note/rules")
CONTRACT_DIR = Path(".claude")
BOUNDARY = "## Project-specific rules"

#: the 0.1.9–0.2.3 closing block, verbatim: what a project on those versions has
#: at the end of its framework half, with its own rules appended after it
LEGACY_BOUNDARY_BLOCK = """## This project's own rules

Everything above this line is framework text: `research-note:update` replaces it
with the plugin's copy whenever the two differ, so an edit made up there is lost
at the next update and a deletion up there comes back.

Add what this project decides for itself **below** this line. The updater
recognises an appendix by the framework half still matching byte for byte, and
leaves everything after it alone — it will say so, naming how many lines it kept.
If the framework text has also moved on, it refuses to copy at all and prints the
diff for you to port by hand, rather than carrying the update forward and dropping
your lines in the same stroke.

A rule here that would serve every project belongs in the plugin instead — say so
and it can be lifted into the template.
"""

SEED = """<!-- Legacy project rules for {contract}.

     The framework's text is generated from the plugin's template; whatever is
     written in this file is appended below it, in .claude/{contract}, by
     bootstrap and by every update. Edit HERE, never the generated file.
     This comment is dropped from the generated text. -->
"""

HISTORY = "history.json"     # templates/history.json: every shipped version of each template
Say = Callable[[str, str, str], None]


def template_history(templates: Path) -> dict[str, list[dict]]:
    path = templates / HISTORY
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def split_by_history(existing: str, contract: str, templates: Path) -> str | None:
    """A pre-boundary file (before 0.1.9) is some shipped template plus,
    maybe, the project's appendix. The plugin ships the length and hash of
    every version it ever released, so the framework half is recognised
    exactly and the appendix is what follows it. None when no version fits —
    the file was edited in place, or came from a template this plugin never
    shipped."""
    data = existing.encode("utf-8")
    for row in template_history(templates).get(contract, []):
        n = int(row.get("bytes", 0))
        if n and len(data) >= n and hashlib.sha256(data[:n]).hexdigest() == row.get("sha256"):
            return data[n:].decode("utf-8")
    return None


def record_history(plugin: Path) -> dict[str, list[dict]]:
    """Refresh templates/history.json from the plugin repository's git history —
    a release step, run whenever a template changes (a test holds the current
    template to the list)."""
    templates = plugin / "templates"
    repo_rel = subprocess.run(["git", "-C", str(templates), "rev-parse", "--show-prefix"],
                              capture_output=True, text=True, check=True).stdout.strip()
    history = template_history(templates)
    for contract, (template_name, _) in CONTRACTS.items():
        rel = repo_rel + template_name
        shas = subprocess.run(["git", "-C", str(templates), "log", "--format=%H", "--", template_name],
                              capture_output=True, text=True, check=True).stdout.split()
        rows = history.get(contract, [])
        seen = {row["sha256"] for row in rows}
        for sha in reversed(shas):
            blob = subprocess.run(["git", "-C", str(templates), "show", f"{sha}:{rel}"],
                                  capture_output=True, text=True)
            if blob.returncode != 0:
                continue
            digest = hashlib.sha256(blob.stdout.encode("utf-8")).hexdigest()
            if digest not in seen:
                seen.add(digest)
                rows.append({"bytes": len(blob.stdout.encode("utf-8")), "sha256": digest, "commit": sha[:7]})
        current = (templates / template_name).read_text(encoding="utf-8")
        digest = hashlib.sha256(current.encode("utf-8")).hexdigest()
        if digest not in seen:
            rows.append({"bytes": len(current.encode("utf-8")), "sha256": digest, "commit": "worktree"})
        history[contract] = rows
    (templates / HISTORY).write_text(json.dumps(history, indent=1) + "\n", encoding="utf-8")
    return history


def _print_say(state: str, what: str, detail: str = "") -> None:
    line = f"{state:<12} {what}"
    if detail:
        line += f"  {detail}"
    print(line)


def strip_leading_comment(text: str) -> str:
    """The seed's explanatory comment is for the person editing the rules file,
    not for the contract."""
    return re.sub(r"\A\s*<!--.*?-->\s*\n?", "", text, count=1, flags=re.S)


def marker(contract: str) -> str:
    """The first line of every managed contract."""
    template_name, _ = CONTRACTS[contract]
    return (f"<!-- framework section generated by research-note from "
            f"templates/{template_name}; edit project-specific rules below -->\n")


def render(template: str, rules: str = "", contract: str = "CLAUDE.md") -> str:
    """Render the template followed by the project's editable appendix."""
    body = strip_leading_comment(rules).strip("\n")
    if not template.endswith("\n"):
        template += "\n"
    return marker(contract) + template + ("\n" + body + "\n" if body else "")


def split_appendix(existing: str, template: str) -> str | None:
    """Return text below a recognised framework section, or ``None``.

    The current form is a marker, the current template, then the editable
    appendix. Older generated files have a marker followed by a historical
    template, so ``split_by_history`` is tried after the current prefix.
    """
    if existing.startswith(template):
        return existing[len(template):]
    if LEGACY_BOUNDARY_BLOCK in existing:
        return existing.split(LEGACY_BOUNDARY_BLOCK, 1)[1]
    return None


def _without_marker(text: str) -> str:
    """Remove a generated marker line while leaving ordinary files alone."""
    if text.startswith("<!--"):
        _, sep, rest = text.partition("\n")
        if sep and "research-note" in text.split("\n", 1)[0]:
            return rest
    return text


def _clean_appendix(text: str | None) -> str:
    """Normalise a user appendix or an old rules-file seed."""
    if not text:
        return ""
    body = strip_leading_comment(text).strip("\n")
    if body == "(none yet — this project has added nothing to the framework's text here)":
        return ""
    return body


def _existing_appendix(existing: str, template: str, contract: str,
                       templates: Path) -> str | None:
    """Find the editable portion of a current or older contract file."""
    body = _without_marker(existing)
    current = split_appendix(body, template)
    if current is not None:
        return _clean_appendix(current)
    historical = split_by_history(body, contract, templates)
    if historical is not None:
        return _clean_appendix(historical)
    return None


def sync(proj: Path, plugin: Path, *, dry: bool = False, force: bool = False,
         say: Say = _print_say) -> bool:
    """Update every contract while preserving its editable project appendix."""
    proj = proj.resolve()
    templates = plugin / "templates"
    changed = False
    for contract, (template_name, rules_name) in CONTRACTS.items():
        template_path = templates / template_name
        if not template_path.is_file():
            say("WARN", f".claude/{contract}", f"plugin ships no templates/{template_name}")
            continue
        template = template_path.read_text(encoding="utf-8")
        target = proj / CONTRACT_DIR / contract
        rules_path = proj / RULES_DIR / rules_name
        existing = target.read_text(encoding="utf-8") if target.is_file() else None
        rules = rules_path.read_text(encoding="utf-8") if rules_path.is_file() else None
        diff_cmd = f"python3 {Path(__file__).name} render {proj} {contract} | diff - {target}"

        legacy = _clean_appendix(rules)
        migrated = False
        if existing is None:
            state = "generated"
        else:
            appendix = _existing_appendix(existing, template, contract, templates)
            if appendix is None and not force:
                say("CONFLICT", f".claude/{contract}",
                    "the framework section was edited in place, so the project appendix "
                    f"cannot be separated safely. Review the diff, then --force if needed. {diff_cmd}")
                continue
            if appendix is None:
                appendix = legacy
                migrated = bool(legacy)
            elif not appendix and legacy:
                # One-time compatibility path for projects that used the old
                # separate rules files. The contract becomes authoritative after
                # this write; the old file is left untouched as a user-owned
                # record rather than deleted behind the user's back.
                appendix = legacy
                migrated = True
            state = "regenerated"

        if existing is None:
            appendix = legacy
            migrated = bool(legacy)
        wanted = render(template, appendix, contract)
        if existing == wanted:
            say("same", f".claude/{contract}")
            continue
        if not dry:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(wanted, encoding="utf-8")
        say("migrated" if migrated else state, f".claude/{contract}",
            "" if existing is None else f"{_differing(existing, wanted)} line(s) differed")
        changed = True
    return changed


def _differing(a: str, b: str) -> int:
    import difflib
    return sum(1 for line in difflib.unified_diff(a.splitlines(), b.splitlines(), n=0, lineterm="")
               if line[:1] in "+-" and line[:3] not in ("+++", "---"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sync")
    s.add_argument("project")
    s.add_argument("--plugin", default=str(Path(__file__).resolve().parents[1]))
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--force", action="store_true")
    h = sub.add_parser("record-history", help="refresh templates/history.json from git (release step)")
    h.add_argument("--plugin", default=str(Path(__file__).resolve().parents[1]))
    r = sub.add_parser("render")
    r.add_argument("project")
    r.add_argument("contract", choices=sorted(CONTRACTS))
    r.add_argument("--plugin", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    plugin = Path(args.plugin).expanduser()
    proj = Path(getattr(args, "project", ".")).expanduser().resolve()
    if args.command == "sync":
        sync(proj, plugin, dry=args.dry_run, force=args.force)
        return 0
    if args.command == "record-history":
        history = record_history(plugin)
        for contract, rows in history.items():
            print(f"{contract}: {len(rows)} version(s)")
        return 0
    template_name, rules_name = CONTRACTS[args.contract]
    template = (plugin / "templates" / template_name).read_text(encoding="utf-8")
    rules_path = proj / RULES_DIR / rules_name
    target = proj / CONTRACT_DIR / args.contract
    if target.is_file():
        appendix = _existing_appendix(target.read_text(encoding="utf-8"), template,
                                      args.contract, plugin / "templates")
    else:
        appendix = None
    if appendix is None:
        appendix = rules_path.read_text(encoding="utf-8") if rules_path.is_file() else ""
    sys.stdout.write(render(template, appendix, args.contract))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
