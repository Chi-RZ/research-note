#!/usr/bin/env python3
"""Generate a project's four contract files from the plugin's templates plus
the project's own rules.

    .claude/CLAUDE.md                 = templates/CLAUDE.md                 + .research-note/rules/root.md
    .claude/experiments-CLAUDE.md     = templates/experiments-CLAUDE.md     + .research-note/rules/experiments.md
    .claude/project_memory-CLAUDE.md  = templates/project_memory-CLAUDE.md + .research-note/rules/record.md
    .claude/wiki-CLAUDE.md            = templates/wiki-CLAUDE.md            + .research-note/rules/wiki.md

The generated file is framework-owned and replaced freely; the rules file is
project-owned and never touched by the plugin except to create it empty or to
carry an old appendix into it once. That separation is what lets an update
move the framework text without reading the project's additions out of the
same file it is about to overwrite — the byte-prefix-plus-appendix scheme it
replaces could tell the two apart only while the framework half had not moved.

    contracts.py sync    PROJECT [--plugin DIR] [--dry-run] [--force]
    contracts.py render  PROJECT NAME          (print the generated text)

Per contract, `sync` reports one of: same · generated (file was missing) ·
regenerated (framework text moved, or the rules changed) · migrated (an old
appendix was carried into the rules file, then regenerated) · CONFLICT (a
pre-generation file whose project text cannot be told apart — left alone, the
diff command printed; --force replaces it). A generated file is recognised by
its first line and is always regenerated: it is derived state, and an edit
made inside it is lost by design — the line says so. A pre-boundary file
(before 0.1.9, no appendix section) is matched against every template version
the plugin ever shipped (`templates/history.json`, refreshed by
`record-history` at release), so its framework half is recognised exactly and
anything after it is migrated; a file matching no version is a CONFLICT.
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

#: contract file -> (template, rules file)
CONTRACTS = {
    "CLAUDE.md": ("CLAUDE.md", "root.md"),
    "experiments-CLAUDE.md": ("experiments-CLAUDE.md", "experiments.md"),
    "project_memory-CLAUDE.md": ("project_memory-CLAUDE.md", "record.md"),
    "wiki-CLAUDE.md": ("wiki-CLAUDE.md", "wiki.md"),
}
RULES_DIR = Path(".research-note/rules")
CONTRACT_DIR = Path(".claude")
BOUNDARY = "## This project's own rules"
EMPTY_RULES = "(none yet — this project has added nothing to the framework's text here)"

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

SEED = """<!-- This project's own rules for {contract}.

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
    """The first line of every generated contract. A file that carries it is
    derived state: regenerated without inspection, never edited in place."""
    template_name, rules_name = CONTRACTS[contract]
    return (f"<!-- generated by research-note from templates/{template_name} + "
            f".research-note/rules/{rules_name} — edit those, never this file -->\n")


def render(template: str, rules: str, contract: str = "CLAUDE.md") -> str:
    """The generated contract: the marker, the template, then the project's rules."""
    body = strip_leading_comment(rules).strip("\n")
    if not template.endswith("\n"):
        template += "\n"
    return marker(contract) + template + "\n" + (body if body else EMPTY_RULES) + "\n"


def split_appendix(existing: str, template: str) -> str | None:
    """The project's own text in a pre-generation contract file, or None when
    the file has no recognisable appendix structure.

    Three shapes are recognised, newest first: the current template as a
    byte-prefix (the appendix is the remainder); the 0.1.9 boundary block
    anywhere in the file (the appendix is what follows it); a file with the
    boundary heading but neither of those (edited in place — no appendix can
    be told apart, so None)."""
    if existing.startswith(template):
        return existing[len(template):]
    if LEGACY_BOUNDARY_BLOCK in existing:
        return existing.split(LEGACY_BOUNDARY_BLOCK, 1)[1]
    return None


def sync(proj: Path, plugin: Path, *, dry: bool = False, force: bool = False,
         say: Say = _print_say) -> bool:
    """Generate every contract; carry an old appendix into the rules file once.
    Returns True when anything changed."""
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

        # 1. a rules file exists for every contract; seeded once, never rewritten
        if rules is None:
            rules = SEED.format(contract=contract)
            if not dry:
                rules_path.parent.mkdir(parents=True, exist_ok=True)
                rules_path.write_text(rules, encoding="utf-8")
            say("new", str(RULES_DIR / rules_name))
            changed = True

        # 2. what kind of file is there
        if existing is None:
            state = "generated"
        elif existing.startswith(marker(contract)):
            # derived state — a template that moved, a rules edit, or an edit
            # made in the file against its first line; all regenerate
            state = "regenerated"
        elif BOUNDARY in existing:
            # 0.1.9–0.2.3: framework text with the boundary block and, maybe,
            # the project's appendix under it — carried into the rules file once
            appendix = split_appendix(existing, template)
            if appendix is None and not force:
                say("CONFLICT", f".claude/{contract}",
                    "has the boundary heading but is neither template + appendix nor the "
                    f"0.1.9 block — edited in place. Move project text into {RULES_DIR / rules_name}, "
                    f"then --force. {diff_cmd}")
                continue
            body = (appendix or "").strip()
            if body and body != EMPTY_RULES:
                if not strip_leading_comment(rules).strip():
                    rules = SEED.format(contract=contract) + appendix.lstrip("\n")
                    if not dry:
                        rules_path.write_text(rules, encoding="utf-8")
                    say("migrated", str(RULES_DIR / rules_name),
                        f"{len(body.splitlines())} line(s) carried from .claude/{contract}")
                    changed = True
                elif strip_leading_comment(rules).strip() != body and not force:
                    say("CONFLICT", f".claude/{contract}",
                        f"has an appendix AND {RULES_DIR / rules_name} already has content — "
                        f"merge by hand, then --force. {diff_cmd}")
                    continue
            state = "regenerated"
        else:
            # before 0.1.9 there was no appendix section. The framework half is
            # some template this plugin once shipped; templates/history.json
            # knows every one, so the appendix is whatever follows it
            appendix = split_by_history(existing, contract, templates)
            if appendix is None and not force:
                say("CONFLICT", f".claude/{contract}",
                    "matches no template this plugin ever shipped — edited in place, or from "
                    f"elsewhere. Move project text into {RULES_DIR / rules_name}, then --force. {diff_cmd}")
                continue
            body = (appendix or "").strip()
            if body:
                if not strip_leading_comment(rules).strip():
                    rules = SEED.format(contract=contract) + appendix.lstrip("\n")
                    if not dry:
                        rules_path.write_text(rules, encoding="utf-8")
                    say("migrated", str(RULES_DIR / rules_name),
                        f"{len(body.splitlines())} line(s) carried from .claude/{contract}")
                    changed = True
                elif strip_leading_comment(rules).strip() != body and not force:
                    say("CONFLICT", f".claude/{contract}",
                        f"has text under an old template AND {RULES_DIR / rules_name} already has content — "
                        f"merge by hand, then --force. {diff_cmd}")
                    continue
            state = "regenerated"

        # 3. generate
        wanted = render(template, rules, contract)
        if existing == wanted:
            say("same", f".claude/{contract}")
            continue
        if not dry:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(wanted, encoding="utf-8")
        say(state, f".claude/{contract}",
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
    rules = rules_path.read_text(encoding="utf-8") if rules_path.is_file() else ""
    sys.stdout.write(render(template, rules, args.contract))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
