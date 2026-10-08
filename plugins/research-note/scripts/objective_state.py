#!/usr/bin/env python3
"""Maintain derived review counts and record explicit goal/phase decisions.

approve-goal records an existing user instruction; it does not grant authority.
review-phase records a review the agent has performed; it makes no judgement.
Automatic callers hold record.lock; the CLI acquires it unless --lock-held.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import subprocess
from pathlib import Path

import check_objective_page as O
from project_config import state_dir

COUNT_RE = re.compile(r"\b\d+\s+entr(?:y|ies)\s+awaits? review\b", re.I)


def set_frontmatter(text: str, fields: dict[str, str]) -> str:
    match = re.match(r"\A---\n(.*?)\n---", text, re.S)
    if not match:
        raise ValueError("objective has no frontmatter")
    lines = [line for line in match.group(1).splitlines()
             if line.partition(":")[0] not in fields]
    lines.extend(f"{key}: {json.dumps(value, ensure_ascii=True)}" for key, value in fields.items())
    return "---\n" + "\n".join(lines) + "\n---" + text[match.end():]


def approve_goal(path: Path, instruction: str) -> None:
    if not instruction.strip():
        raise ValueError("quote the user's explicit instruction authorizing this goal change")
    previous = O.git_show(path)
    if previous is None:
        raise ValueError("new objectives use intake; goal revisions need a committed baseline")
    text = path.read_text(encoding="utf-8")
    old, new = (O.body_of(t, "Goal").strip() for t in (previous, text))
    if not new or old == new:
        raise ValueError("the Goal must contain the user-authorized revision")
    path.write_text(set_frontmatter(text, {
        "goal-approved-from": O.digest(old), "goal-approved-to": O.digest(new),
        "goal-approval": instruction.strip(),
    }), encoding="utf-8")


def review_phase(path: Path, phase: str, note: str) -> None:
    if not note.strip() or "\n" in note or "<!--" in note:
        raise ValueError("supply a one-line review note")
    text = path.read_text(encoding="utf-8")
    matches = [block for block in O.phase_blocks(text)
               if (m := O.PHASE_HEAD_RE.match(block.splitlines()[0] if block else ""))
               and f"P{m.group(1)}" == phase]
    if len(matches) != 1 or "▶" not in matches[0]:
        raise ValueError("name one phase with an existing reading to review")
    block = matches[0]
    clean = O.REVIEW_RE.sub("", block).rstrip()
    fingerprint = O.phase_fingerprint(path, clean)
    replacement = clean + f"\n  - Review: {note.strip()} <!-- rn-review:{fingerprint} -->\n\n"
    path.write_text(text.replace(block, replacement, 1), encoding="utf-8")


def counted_text(path: Path, text: str) -> str:
    refs = {((path.parent / rel).resolve(), slug)
            for rel, slug in O.ENTRY_REF_RE.findall(O.body_of(text, "Plan"))}
    count = 0
    for page, slug in refs:
        if not page.is_file():
            raise ValueError(f"cannot count missing entry source: {page}")
        statuses = O.entry_status(page)
        if slug not in statuses:
            raise ValueError(f"cannot count missing entry: {page}#entry-{slug}")
        count += statuses[slug] == "analyzed"
    match = re.search(r"(^##\s+Verdict\s*$\n)(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    if not match:
        raise ValueError("objective has no Verdict section")
    phrase = f"{count} " + ("entry awaits review" if count == 1 else "entries await review")
    verdict = match.group(2)
    if COUNT_RE.search(verdict):
        verdict = COUNT_RE.sub(phrase, verdict)
    else:
        verdict = verdict.rstrip() + f"\n\n{phrase}.\n"
    return text[:match.start(2)] + verdict + text[match.end(2):]


def sync_count(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    updated = counted_text(path, original)
    if original == updated:
        return False
    path.write_text(updated, encoding="utf-8")
    return True


def git(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(O.ROOT), *args], capture_output=True,
                          text=True, check=True, **kwargs)


def sync_dependents(changed: list[Path]) -> None:
    """Caller holds the record lock. Only clean objectives get derived commits.

    These commits change count text only. They bypass record lint because a
    changed entry may also require a human/agent phase review (O7/O13), which
    this function must not author. All other Git hooks remain active.
    """
    changed_set = {p.resolve() for p in changed}
    for obj in sorted(O.OBJ_DIR.glob("*.md")):
        if not any(page in changed_set for page, _ in O.plan_entry_refs(obj)):
            continue
        rel = str(obj.relative_to(O.ROOT))
        if git("status", "--porcelain", "--", rel).stdout.strip():
            print(f"warning: {rel} has pending edits; its count will refresh on record_sync save")
            continue
        original = obj.read_text(encoding="utf-8")
        try:
            updated = counted_text(obj, original)
            if updated == original:
                continue
            fm, _ = O.frontmatter(original)
            oid = fm.get("id", "")
            if not O.ID_RE.fullmatch(oid):
                raise ValueError("missing objective ID")
            obj.write_text(updated, encoding="utf-8")
            git("add", "--", rel)
            git("commit", "-m", f"memory: refresh {oid} review count\n\nObjective: {oid}",
                "--", rel, env={**os.environ, "SKIP_RECORD_LINT": "1"})
            print(f"review count updated: {rel}")
        except (ValueError, subprocess.CalledProcessError) as exc:
            # The objective was clean before this operation. Restore only our
            # derived edit; keep the already committed entry and other paths.
            obj.write_text(original, encoding="utf-8")
            git("restore", "--staged", "--", rel)
            print(f"warning: could not commit review count for {rel}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock-held", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)
    approve = sub.add_parser("approve-goal")
    approve.add_argument("page", type=Path)
    approve.add_argument("--instruction", required=True)
    review = sub.add_parser("review-phase")
    review.add_argument("page", type=Path)
    review.add_argument("phase")
    review.add_argument("--note", required=True)
    count = sub.add_parser("sync-count")
    count.add_argument("page", type=Path)
    deps = sub.add_parser("sync-dependents")
    deps.add_argument("pages", nargs="+", type=Path)
    args = parser.parse_args()
    lock = None
    if not args.lock_held:
        lock = (state_dir(O.ROOT) / "record.lock").open("a")
        fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        if args.command == "sync-dependents":
            sync_dependents(args.pages)
        else:
            page = args.page.resolve()
            if not page.is_relative_to(O.OBJ_DIR.resolve()) or not page.is_file():
                raise ValueError("name an existing objective in this project's objectives directory")
            if args.command == "approve-goal":
                approve_goal(page, args.instruction)
            elif args.command == "review-phase":
                review_phase(page, args.phase, args.note)
            else:
                sync_count(page)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"objective_state: {exc}")
        return 1
    finally:
        if lock:
            lock.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
