#!/usr/bin/env python3
"""Install, refresh, inspect or remove research-note's git hooks in one project.

The hook directory is `.claude/githooks/`. After install it holds:

    dispatch                  the POSIX dispatcher every hook name links to
    research-note/pre-commit  research-note's own gates (the record layer,
    research-note/commit-msg  the layer partition) — run first by the dispatcher
    pre-commit -> dispatch    one link per standard git hook name
    commit-msg -> dispatch
    pre-push   -> dispatch    ...

`core.hooksPath` points at the directory. The hooks that were active BEFORE —
`.git/hooks/` (a pre-commit framework, git-lfs, a hand-written hook), or an
earlier `core.hooksPath` — are not lost: the dispatcher forwards every event
to them after its own check, with arguments, stdin and exit code intact. An
earlier `core.hooksPath` is remembered in `research-note.previousHooksPath`;
with none, the repository's own hooks directory is the forward target.

Idempotent: a second run reports `kept` for everything and changes nothing. A
project on the pre-dispatcher layout (real `pre-commit` / `commit-msg` files
in the directory) is migrated: the files move under `research-note/` and the
names become links, so a project that had extended the old hook's RULES table
keeps those rows until it declares them in `.research-note/project.json`.

    githooks_install.py install   PROJECT [--plugin DIR] [--dry-run]
    githooks_install.py uninstall PROJECT [--dry-run]
    githooks_install.py status    PROJECT

`uninstall` removes only what install created and restores `core.hooksPath`
to its previous value (or unsets it). `status` prints one line per finding,
`OK|WARN|BAD <tab> message <tab> fix`, for doctor.
"""
from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

HOOK_DIR = ".claude/githooks"
OWN_DIR = "research-note"
DISPATCH = "dispatch"
#: the hooks research-note has a check for
OWNED = ("pre-commit", "commit-msg")
#: client-side hooks a link is always made for — the ones a developer's tooling
#: installs (pre-commit frameworks, git-lfs, commit linters)
COMMON = (
    "applypatch-msg", "pre-applypatch", "post-applypatch",
    "pre-commit", "pre-merge-commit", "prepare-commit-msg", "commit-msg",
    "post-commit", "pre-rebase", "post-checkout", "post-merge", "pre-push",
    "post-rewrite", "pre-auto-gc",
)
#: the rest of githooks(5) — linked only when the previous directory has one,
#: because several fire on every ref update and an idle link there is a
#: process spawned for nothing
RARE = (
    "pre-receive", "update", "proc-receive", "post-receive", "post-update",
    "reference-transaction", "push-to-checkout", "sendemail-validate",
    "post-index-change", "p4-changelist", "p4-prepare-changelist",
    "p4-post-changelist", "p4-pre-submit",
)
STANDARD = tuple(dict.fromkeys(COMMON + RARE))
STUB_MARK = "# research-note dispatch stub"

Say = Callable[[str, str, str], None]


def _print_say(state: str, what: str, detail: str = "") -> None:
    line = f"{state:<6} {what}"
    if detail:
        line += f"  {detail}"
    print(line)


def git(proj: Path, *args: str) -> str | None:
    run = subprocess.run(["git", "-C", str(proj), *args],
                         capture_output=True, text=True)
    if run.returncode != 0:
        return None
    return run.stdout.strip()


def _resolve_hooks_path(proj: Path, value: str) -> Path:
    """A relative core.hooksPath is relative to the work tree."""
    path = Path(value).expanduser()
    if not path.is_absolute():
        top = git(proj, "rev-parse", "--show-toplevel") or str(proj)
        path = Path(top) / path
    return path.resolve()


def previous_hooks_dir(proj: Path) -> Path | None:
    """Where the dispatcher forwards to, resolved the way it resolves it."""
    stored = git(proj, "config", "--get", "research-note.previousHooksPath")
    if stored:
        return _resolve_hooks_path(proj, stored)
    # not `--git-path hooks`: that answers core.hooksPath, i.e. our own directory
    common = git(proj, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common is None:
        common = git(proj, "rev-parse", "--git-common-dir")
        if common is None:
            return None
        if not Path(common).is_absolute():
            common = str(proj / common)
    return (Path(common) / "hooks").resolve()


def _executable_hooks(directory: Path | None) -> set[str]:
    if directory is None or not directory.is_dir():
        return set()
    return {p.name for p in directory.iterdir()
            if p.name in STANDARD and p.is_file() and os.access(p, os.X_OK)}


def _is_our_link(path: Path) -> bool:
    if path.is_symlink():
        return os.readlink(path) == DISPATCH
    if path.is_file():
        try:
            return STUB_MARK in path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
    return False


def _link(path: Path, name: str) -> str:
    try:
        path.symlink_to(DISPATCH)
        return "linked"
    except (OSError, NotImplementedError):
        path.write_text(
            "#!/bin/sh\n" f"{STUB_MARK} (symlinks unavailable here)\n"
            f'RESEARCH_NOTE_HOOK={name} exec "$(dirname "$0")/{DISPATCH}" "$@"\n',
            encoding="utf-8")
        path.chmod(0o755)
        return "linked"


def install(proj: Path, plugin: Path, *, dry: bool = False,
            say: Say = _print_say) -> bool:
    """Lay the dispatcher, research-note's checks and the links; point
    core.hooksPath at them; remember what was there before. Returns True when
    anything changed."""
    proj = proj.resolve()
    shipped = plugin / "githooks"
    hooks = proj / HOOK_DIR
    changed = False
    if not (shipped / DISPATCH).is_file():
        say("FAIL", HOOK_DIR, f"this plugin ships no githooks/{DISPATCH}")
        return False
    if git(proj, "rev-parse", "--git-dir") is None:
        say("FAIL", HOOK_DIR, "not a git repository")
        return False

    # 1. what was active before — remembered once, never overwritten by our own path
    current = git(proj, "config", "--get", "core.hooksPath")
    current_is_ours = bool(current) and _resolve_hooks_path(proj, current) == hooks.resolve()
    if current and not current_is_ours:
        stored = git(proj, "config", "--get", "research-note.previousHooksPath")
        if stored != current:
            if not dry:
                git(proj, "config", "research-note.previousHooksPath", current)
            say("ok", "previous hooks", f"core.hooksPath was {current} — every event is forwarded there")
            changed = True

    # 2. the pre-dispatcher layout: real files under the hook names
    if not dry:
        (hooks / OWN_DIR).mkdir(parents=True, exist_ok=True)
    for name in OWNED:
        legacy = hooks / name
        if not (legacy.is_file() and not legacy.is_symlink()) or _is_our_link(legacy):
            continue
        target = hooks / OWN_DIR / name
        if target.exists() and not filecmp.cmp(legacy, target, shallow=False):
            aside = hooks / OWN_DIR / f"{name}.legacy"
            if not dry:
                legacy.rename(aside)
            say("WARN", f"{HOOK_DIR}/{name}",
                f"pre-dispatcher copy differed from {OWN_DIR}/{name}; kept as {OWN_DIR}/{name}.legacy — diff and delete")
        else:
            if not dry:
                if target.exists():
                    legacy.unlink()
                else:
                    legacy.rename(target)
            say("moved", f"{HOOK_DIR}/{name}", f"-> {OWN_DIR}/{name} (pre-dispatcher layout)")
        changed = True

    # 3. framework files — synced, with one exception that is the project's own
    declared = (proj / ".research-note/project.json").is_file()
    for rel in (DISPATCH, *(f"{OWN_DIR}/{n}" for n in OWNED)):
        src, dst = shipped / rel, hooks / rel
        if not src.is_file():
            say("WARN", f"{HOOK_DIR}/{rel}", "not shipped by this plugin version")
            continue
        if not dst.exists():
            if not dry:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                dst.chmod(0o755)
            say("new", f"{HOOK_DIR}/{rel}")
            changed = True
        elif filecmp.cmp(src, dst, shallow=False):
            say("kept", f"{HOOK_DIR}/{rel}")
        elif rel.endswith("commit-msg") and not declared:
            # A pre-declaration commit-msg carries the project's layer table
            # INSIDE it; copying over that deletes the project's prefixes.
            say("WARN", f"{HOOK_DIR}/{rel}",
                "differs from the plugin's and this project declares no layers — "
                "move its RULES rows into .research-note/project.json, then re-run")
        else:
            if not dry:
                shutil.copy2(src, dst)
                dst.chmod(0o755)
            say("synced", f"{HOOK_DIR}/{rel}")
            changed = True

    # 4. one link per hook name
    previous = previous_hooks_dir(proj)
    if previous is not None and previous == hooks.resolve():
        previous = None
    forwarded = _executable_hooks(previous)
    names = sorted(set(COMMON) | set(OWNED) | (forwarded & set(RARE)))
    linked = 0
    for name in names:
        link = hooks / name
        if _is_our_link(link):
            continue
        if link.is_symlink() or link.exists():
            say("WARN", f"{HOOK_DIR}/{name}",
                "is not research-note's link — left alone; that hook name is not forwarded")
            continue
        if not dry:
            _link(link, name)
        linked += 1
    if linked:
        say("linked", f"{HOOK_DIR}/*", f"{linked} hook name(s) -> {DISPATCH}")
        changed = True
    else:
        say("kept", f"{HOOK_DIR}/*", f"{len(names)} hook name(s) -> {DISPATCH}")

    # 5. git reads the directory
    if not current_is_ours:
        if not dry:
            git(proj, "config", "core.hooksPath", HOOK_DIR)
        say("ok", "core.hooksPath", HOOK_DIR)
        changed = True
    if previous is None:
        say("ok", "forwarding", "no previous hook directory")
    elif forwarded:
        say("ok", "forwarding", f"{previous}: {', '.join(sorted(forwarded))}")
    else:
        say("ok", "forwarding", f"{previous} (no hooks there yet; any added later run too)")
    return changed


def uninstall(proj: Path, *, dry: bool = False, say: Say = _print_say) -> None:
    """Remove what install created, restore core.hooksPath, keep everything else."""
    proj = proj.resolve()
    hooks = proj / HOOK_DIR
    if hooks.is_dir():
        for path in sorted(hooks.iterdir()):
            if _is_our_link(path):
                if not dry:
                    path.unlink()
                say("removed", f"{HOOK_DIR}/{path.name}")
        for rel in (DISPATCH,):
            if (hooks / rel).exists():
                if not dry:
                    (hooks / rel).unlink()
                say("removed", f"{HOOK_DIR}/{rel}")
        own = hooks / OWN_DIR
        if own.is_dir():
            if not dry:
                shutil.rmtree(own)
            say("removed", f"{HOOK_DIR}/{OWN_DIR}/")
        if not dry and hooks.is_dir() and not any(hooks.iterdir()):
            hooks.rmdir()
    previous = git(proj, "config", "--get", "research-note.previousHooksPath")
    current = git(proj, "config", "--get", "core.hooksPath")
    if current and _resolve_hooks_path(proj, current) == hooks.resolve():
        if previous:
            if not dry:
                git(proj, "config", "core.hooksPath", previous)
            say("ok", "core.hooksPath", f"restored to {previous}")
        else:
            if not dry:
                git(proj, "config", "--unset", "core.hooksPath")
            say("ok", "core.hooksPath", "unset (git reads .git/hooks again)")
    if previous and not dry:
        git(proj, "config", "--unset", "research-note.previousHooksPath")


def status(proj: Path) -> list[tuple[str, str, str]]:
    """Findings for doctor: (level, message, fix)."""
    proj = proj.resolve()
    hooks = proj / HOOK_DIR
    out: list[tuple[str, str, str]] = []
    fix = f"python3 <plugin>/scripts/githooks_install.py install {proj}"
    current = git(proj, "config", "--get", "core.hooksPath")
    if not current:
        out.append(("BAD", "core.hooksPath unset — research-note's gates never run", fix))
        return out
    if _resolve_hooks_path(proj, current) != hooks.resolve():
        out.append(("WARN", f"core.hooksPath is {current}, not {HOOK_DIR} — "
                            "research-note's gates are not on the path git reads", fix))
        return out
    dispatch = hooks / DISPATCH
    if not (dispatch.is_file() and os.access(dispatch, os.X_OK)):
        out.append(("BAD", f"{HOOK_DIR}/{DISPATCH} missing — the hook names point at nothing", fix))
        return out
    for name in OWNED:
        own = hooks / OWN_DIR / name
        if not (own.is_file() and os.access(own, os.X_OK)):
            out.append(("BAD", f"{HOOK_DIR}/{OWN_DIR}/{name} missing", fix))
        if not _is_our_link(hooks / name):
            out.append(("BAD", f"{HOOK_DIR}/{name} is not a link to {DISPATCH}", fix))
    if not out:
        out.append(("OK", f"githooks installed (core.hooksPath={current}, dispatcher + {', '.join(OWNED)})", ""))
    previous = previous_hooks_dir(proj)
    if previous is None or previous == hooks.resolve():
        return out
    forwarded = _executable_hooks(previous)
    missing = sorted(n for n in forwarded if not _is_our_link(hooks / n))
    if missing:
        out.append(("WARN", f"{previous} has {', '.join(missing)} but no link forwards to it",
                    fix + "  (re-run picks up hooks added since)"))
    elif forwarded:
        out.append(("OK", f"forwards to {previous}: {', '.join(sorted(forwarded))}", ""))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    inst = sub.add_parser("install")
    inst.add_argument("project")
    inst.add_argument("--plugin", default=str(Path(__file__).resolve().parents[1]))
    inst.add_argument("--dry-run", action="store_true")
    un = sub.add_parser("uninstall")
    un.add_argument("project")
    un.add_argument("--dry-run", action="store_true")
    st = sub.add_parser("status")
    st.add_argument("project")
    args = parser.parse_args(argv)
    proj = Path(args.project).expanduser()
    if args.command == "install":
        install(proj, Path(args.plugin).expanduser(), dry=args.dry_run)
    elif args.command == "uninstall":
        uninstall(proj, dry=args.dry_run)
    else:
        for level, message, fix in status(proj):
            print(f"{level}\t{message}\t{fix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
