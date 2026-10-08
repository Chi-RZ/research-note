#!/usr/bin/env python3
"""The harvest safety net — say, every turn, which running entries' jobs are gone.

The doctrine is "the launching session watches its own jobs", and it has a
failure mode: the session forgets, dies, or context-switches, and finished
cells sit unread until the user asks (five did, in one measured session).
Waiters and Monitors close the loop only when the agent remembered to arm
them; the layer that cannot be forgotten is a HOOK — this script is wired
into UserPromptSubmit (hooks/hooks.json), so the signal is injected into the
next turn of every session in the project, armed or not (a fresh session
sees it on its first prompt).

What it prints (stdout, empty = all quiet):
  <O<nn> ·|—> <nn>.<mmm> · <page>: J3 entry '<name>' is running but ... — one per
  running entry whose jobs have ALL gone terminal, prefixed with the active
  objective whose Plan links it (ownership hint, not an assignment: the
  doctrine still says the launching session writes the entry; anyone else
  reading the line treats it as read-first state).
  Plus one warning when a remote is declared, some running entry holds an
  @host job, and the queue snapshot is missing or stale — because the linter
  then SUPPRESSES J3 rather than invent one from stale data, and this hook's
  silence would otherwise read as "all still running".

What it deliberately reuses instead of reimplementing: `lifecycle_errors`
(J3) from check_node_page, which already merges local squeue, bare-host
wrapper PIDs from log headers, the remote snapshot with its staleness guard,
and the log exit-code fallback — every one of those a fought battle
(log-freeze-cell-is-truth; the R2-era stale-snapshot false positives).
Liveness truth is the host's wrapper PID / queue, never the log alone.

No ssh here, ever: a hook runs synchronously on the turn, so it reads the
snapshot the fixer's remote_sync refreshes every cycle (and `remote.sh
queue` refreshes on demand). Freshness is the daemon's job; this is a read.

In a LINKED WORKTREE this prints nothing, by design. A worktree belongs to a
code-editing agent: formal runs launch from main, so it owns no entries to
harvest — and its project_memory/ is a stale branch-time copy, so reading it
would report J3 for entries whose jobs ended after the branch point:
misleading noise injected into an agent doing something else.

The hook path reports only entries that have sat harvestable for MIN_AGE_MIN
minutes (first-seen times in .research-note/state/harvest_first_seen.json, shared across
sessions). A fresh J3 is the owner's Monitor's business — reporting it
project-wide from minute zero made every bystander session listen along for
the minutes the owner was already on it, and made "whose is it" a question
every turn. Past the gate the entry is presumed forgotten or orphaned, which
is exactly what a broadcast is for. A Monitor polls with --min-age 0 and
keeps its immediacy.

Usage: harvest_check.py [--min-age N] [--for O01 ...]
                                        plain text findings (a Monitor's poll;
                                        repeat --for for multiple objectives)
       harvest_check.py --hook          the COMPLETE hook payload, JSON and
                                        doctrine preamble included — hooks.json
                                        calls this with one dumb line and owns
                                        nothing but the trigger condition
Exit 0 always — a reporting surface.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_node_page as C  # noqa: E402
from project_config import state_dir  # noqa: E402

ROOT = C.ROOT
NODES = ROOT / "project_memory" / "nodes"
OBJ_DIR = ROOT / "project_memory" / "objectives"
SNAPSHOT = ROOT / ".fixer" / "remote_queue"
STALE_MIN = 30          # matches the linter's own snapshot-staleness cutoff
FIRST_SEEN = ROOT / ".research-note" / "state" / "harvest_first_seen.json"
MIN_AGE_MIN = 15        # hook default; a Monitor passes --min-age 0

RUNNING_RE = re.compile(r"^(?:-\s+\*\*)?Status:(?:\*\*)?\s*running\s*$", re.M)


def _slug(heading: str) -> str:
    s = re.sub(r"[^\w\s-]", "", heading.lower())
    return re.sub(r"\s+", "-", s.strip())


def objective_of() -> dict[tuple[Path, str], str]:
    """(page, entry slug) -> O<nn>, from every ACTIVE objective's Plan links.

    An ownership HINT for the reader: the Plan already is the task list, so
    the objective id on the line tells a session at a glance whether the
    entry is its route's. Import is lazy and failure-tolerant — a broken
    objective page must not silence the harvest signal."""
    out: dict[tuple[Path, str], str] = {}
    try:
        import check_objective_page as O
        for obj in sorted(OBJ_DIR.glob("*.md")):
            fm, _ = O.frontmatter(obj.read_text(encoding="utf-8"))
            if fm.get("status") != "active":
                continue
            oid = fm.get("id", "O??")
            for page, slug in O.plan_entry_refs(obj):
                out[(page.resolve(), slug)] = oid
    except Exception:
        pass
    return out


def objective_by_id() -> dict[tuple[Path, str], str]:
    """(page, `<nn>.<mmm>`) -> O<nn>, from every ACTIVE objective's Plan links.

    Same shape as :func:`objective_of`, with the ENTRY ID where that one has
    the heading slug. The page stays — it was never the fragile half — and the
    id replaces the half that was: E1 assigns an id at creation and never
    rewrites or reuses it, its shape carries no punctuation to slugify and no
    quote to truncate at, and O3 already cross-checks the id a Plan line cites
    against the entry's own `Id:`. A reworded heading therefore stops silently
    detaching an entry from its objective.

    The slug map stays as the fallback: O3 verifies a cited id when it is
    there, it does not require the Plan line to carry one."""
    out: dict[tuple[Path, str], str] = {}
    try:
        import check_objective_page as O
        for obj in sorted(OBJ_DIR.glob("*.md")):
            text = obj.read_text(encoding="utf-8")
            fm, _ = O.frontmatter(text)
            if fm.get("status") != "active":
                continue
            oid = fm.get("id", "O??")
            for rel, _slug, eid in O.LINK_ID_RE.findall(O.body_of(text, "Plan")):
                out[((obj.parent / rel).resolve(), eid)] = oid
    except Exception:
        pass
    return out


def _plan_nodes(oid: str) -> set[str]:
    """The node folders `oid`'s ACTIVE Plan links into — the blast radius the
    unattributed-line half of `--for` is allowed to claim."""
    out: set[str] = set()
    try:
        import check_objective_page as O
        nodes_root = (ROOT / "project_memory" / "nodes").resolve()
        for obj in sorted(OBJ_DIR.glob("*.md")):
            text = obj.read_text(encoding="utf-8")
            fm, _ = O.frontmatter(text)
            if fm.get("status") != "active" or fm.get("id") != oid:
                continue
            for page, _slug_ in O.plan_entry_refs(obj):
                try:
                    out.add(page.resolve().relative_to(nodes_root).parts[0])
                except ValueError:
                    pass
    except Exception:
        pass
    return out


def in_linked_worktree() -> bool:
    """True when ROOT is a linked git worktree (its git-dir differs from the
    common one). A non-repo answers False — the check must never block the
    report on git being absent."""
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "rev-parse",
                            "--path-format=absolute", "--git-common-dir",
                            "--git-dir"], capture_output=True, text=True,
                           timeout=10)
        if r.returncode == 0:
            common, gitdir, *_ = r.stdout.split("\n")
            return common != gitdir
    except Exception:
        pass
    return False


def age_gate(keyed: list[tuple[str, str]], min_age: int) -> list[str]:
    """Report a J3 only once it has sat harvestable for `min_age` minutes.

    First-seen stamps live in a shared state file; an entry that
    leaves the J3 set (harvested, or its job resumed) is purged, so a later
    re-finish starts a fresh clock. Written via temp + same-dir rename —
    two sessions' hooks race benignly (last writer wins on stamps both just
    read). min_age 0 skips the file entirely (the Monitor path)."""
    if min_age <= 0:
        return [line for _, line in keyed]
    now = time.time()
    try:
        seen = json.loads(FIRST_SEEN.read_text(encoding="utf-8"))
    except Exception:
        seen = {}
    current = {k for k, _ in keyed}
    out = [line for k, line in keyed
           if now - seen.get(k, now) >= min_age * 60]
    new_state = {k: seen.get(k, now) for k in current}
    if new_state != seen:
        try:
            if FIRST_SEEN.parent == ROOT / ".research-note" / "state":
                state_dir(ROOT)          # also lays the nested .gitignore
            else:
                FIRST_SEEN.parent.mkdir(parents=True, exist_ok=True)
            tmp = FIRST_SEEN.with_suffix(f".{id(seen)}.tmp")
            tmp.write_text(json.dumps(new_state), encoding="utf-8")
            tmp.replace(FIRST_SEEN)
        except Exception:
            pass                       # a stamp lost delays a report, never breaks one
    return out


def preamble() -> str:
    """The doctrine line the hook injects ABOVE the findings. It lives here —
    with the code whose behavior it describes — not in hooks.json: the trigger
    is a dumb one-liner, so a rule change (0.13.40's READ-ONLY hardening was
    an edit to a jq string inside JSON) is an edit to THIS file alone, and the
    quoted minute count can never drift from MIN_AGE_MIN because it IS it."""
    return (f"Harvest check: entries at `running` whose jobs went terminal "
            f"{MIN_AGE_MIN}+ min ago and NOBODY harvested — forgotten or "
            f"orphaned. If the entry is on YOUR objective's Plan or was YOUR "
            f"launch: harvest it THIS turn (pull artifacts if remote, analyze, "
            f"conclude). Any other session: READ-ONLY — never write another "
            f"objective's entry; picking up an orphan requires the user "
            f"saying so.")


def report(min_age: int, for_objective: str | list[str] | tuple[str, ...] | set[str] | None = None) -> str:
    """The findings text — empty string when all is quiet.

    `for_objective` is one objective id or a collection owned by one session.
    The scope is computed HERE because only this side holds the attribution: a
    line belongs when its objective is selected, or when it attributes to
    NOBODY but lives in a node a selected Plan already works in — the
    launched-before-its-Plan-line case, invisible to a printed-text grep by
    construction. Recomputing per call lets every scope follow its Plan as it
    grows. Lines attributed to another objective are dropped; they belong to
    another launching session, and repeating them every poll would rate-limit
    this watcher."""
    if not NODES.is_dir() or in_linked_worktree():
        return ""
    if isinstance(for_objective, str):
        objective_scope = {for_objective}
    else:
        objective_scope = set(for_objective or ())
    scoped_nodes = set().union(*(_plan_nodes(oid) for oid in objective_scope)) \
        if objective_scope else set()
    owners = None                      # built only if some page needs it
    by_id: dict[tuple[Path, str], str] = {}   # ditto, keyed by the entry id
    keyed: list[tuple[str, str]] = []  # (stable key, report line)
    lines: list[str] = []
    saw_remote_job = False
    for page in sorted(NODES.rglob("*.md")):
        text = page.read_text(encoding="utf-8")
        if not RUNNING_RE.search(text):
            continue                   # fast path: most pages have no running entry
        entries = C.sections(text)
        for err in C.lifecycle_errors(text, entries, page):
            if not err.startswith("J3"):
                continue
            # The name has to come back OUT of the message, and a title may
            # itself hold an apostrophe — "gate A'". A non-greedy `'(.+?)'`
            # stops at that one and yields "gate A": the wrong slug, so the
            # entry attributes to no objective, and EVERY scoped Monitor poll
            # (`grep '^O07 '`) drops the line while the unscoped hook still
            # shows it. Measured: an entry sat 7h unharvested behind a Monitor
            # that was armed and polling the whole time. The names are already
            # in hand — match them instead of re-parsing prose.
            name = max((n for n in entries
                         if err.startswith(f"J3 entry '{n}' is running")),
                        key=len, default="")
            if owners is None:
                owners = objective_of()
                by_id = objective_by_id()
            eid = C.field(entries.get(name, ""), "Id").strip("` ")
            oid = (by_id.get((page.resolve(), eid)) if eid else None) or \
                owners.get((page.resolve(), _slug(name)), "—")
            if objective_scope and oid not in objective_scope:
                if oid != "—":
                    continue           # another loop's line, drop it
                node = page.relative_to(ROOT / "project_memory" / "nodes"
                                        ).parts[0]
                if node not in scoped_nodes:
                    continue           # a node these objectives never touch
            rel = page.relative_to(ROOT).as_posix()
            keyed.append((f"{rel}#{_slug(name)}",
                          f"{oid} · {eid or '??'} · {rel}: {err}"))
        for name, body in entries.items():
            if C.field(body, "Status") == "running" and any(
                    "@" in j for j in re.split(r"[,\s]+", C.field(body, "Jobs")) if j):
                saw_remote_job = True
    lines.extend(age_gate(keyed, min_age))

    if saw_remote_job:
        age = None
        if SNAPSHOT.is_file():
            age = int((time.time() - SNAPSHOT.stat().st_mtime) / 60)
        if age is None or age > STALE_MIN:
            state = "missing" if age is None else f"{age} min old"
            lines.append(
                f"queue snapshot {state} — remote-job J3 judgments are "
                f"SUSPENDED (the linter refuses to invent one from stale "
                f"data); refresh: bash <plugin>/scripts/remote.sh queue")
    return "\n".join(lines)


def main() -> int:
    if "--hook" in sys.argv:
        # The whole hook payload, JSON included: hooks.json calls this with
        # ONE dumb line and owns nothing but the trigger condition. Built
        # here so it is tested here, and so the shell layer never again
        # holds doctrine text or jq escaping.
        text = report(MIN_AGE_MIN)
        if text:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": preamble() + "\n" + text[:1500]}}))
        return 0
    min_age = MIN_AGE_MIN
    if "--min-age" in sys.argv:
        min_age = int(sys.argv[sys.argv.index("--min-age") + 1])
    for_objectives = [sys.argv[i + 1] for i, arg in enumerate(sys.argv[:-1])
                      if arg == "--for"]
    text = report(min_age, for_objectives or None)
    if text:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
