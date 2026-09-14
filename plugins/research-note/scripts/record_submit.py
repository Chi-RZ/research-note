#!/usr/bin/env python3
"""Post-submit record for ONE launched job — invoked by the launcher, not by hand.

The hpc-submit contract says every submission must, in the same turn, land its job id
in the owning entry's `- **Jobs:**` field (a job belongs to its entry), link its log
under that field, and flip that entry to `Status: running`. Wiring
it into the launcher makes it unskippable — the launch and the record are one action.

Usage: record_submit.py <node>[/<group>]/<page> <entry name> <job_id> <log path>
                        --phase [O<nn>/]P<n> --role "<what this entry does for the phase>"
                        (or --no-objective for work that serves no phase)
       record_submit.py --check <node>[/<group>]/<page> <entry name>
Idempotent: re-recording the same job id is a no-op.
--check resolves the page and the entry WITHOUT writing — the launcher's pre-flight,
run BEFORE sbatch/nohup, so a typo'd page or entry name aborts with nothing launched
instead of costing a live job whose record failed.
Exit code: 0 recorded (--check: resolvable), 1 NOT recorded (the caller must surface
this — a launch whose record failed is a job running invisibly), 2 bad usage.
"""
from __future__ import annotations

import fcntl
import os
import subprocess
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from projroot import nth_parent, resolve_root  # noqa: E402

def _main_checkout() -> Path | None:
    """The MAIN checkout, even when invoked from a linked worktree.

    The record has one live instance and one lock, both in the main checkout.
    Resolving by walking up from cwd (projroot's rule) stops at a worktree —
    which validates, since a non-sparse worktree carries its own
    project_memory/ and .claude/ — and the job row would then be written into a
    copy nobody reads, under a lock file nobody else holds. `git rev-parse
    --git-common-dir` points at the shared .git regardless of worktree, so its
    parent is always the main checkout.

    RESEARCH_NOTE_PROJECT_DIR (then the legacy CLAUDE_PROJECT_DIR) is consulted
    first: git resolves from cwd, and a caller sitting in a DIFFERENT repo (a
    session with two projects open) would otherwise have its job row written
    into — and committed to — whichever record its cwd happens to be inside.
    """
    env = (os.environ.get("RESEARCH_NOTE_PROJECT_DIR")
           or os.environ.get("CLAUDE_PROJECT_DIR"))
    for base in ([env] if env and Path(env).is_dir() else []) + [None]:
        try:
            r = subprocess.run(["git", "rev-parse", "--path-format=absolute",
                                "--git-common-dir"], capture_output=True, text=True,
                               timeout=10, cwd=base)
            if r.returncode == 0 and r.stdout.strip():
                root = Path(r.stdout.strip()).parent
                if (root / "project_memory").is_dir():
                    return root
        except Exception:
            pass
    return None


ROOT = _main_checkout() or resolve_root(nth_parent(Path(__file__), 2))
NODES_DIR = ROOT / "project_memory" / "nodes"



def task_page(page: str) -> Path | None:
    """'peps_sma/heis_tri/dispersion' ->
    project_memory/nodes/peps_sma/heis_tri/dispersion.md (node-level
    pages like 'peps_sma/gate' resolve the same way, one level up).

    '<node>/node' resolves to node.md like any other page: since record v3 it
    is an entries-only page — the gate first, then one validation per in-place
    edit — and a validation is a real background launch whose job row must
    land automatically like everyone else's. (An earlier design kept lineage
    prose there and this function refused it; that refusal outlived the design
    by a year of versions, and every node.md validation launch was recorded by
    hand after an 'exit 3' — job running, row missing.)"""
    p = NODES_DIR / f"{page.strip()}.md"
    return p if p.exists() else None


JOBS_LINE_RE = re.compile(r"^(?:- \*\*Jobs:\*\*|Jobs:)\s*(.*?)\s*$")


def jobs_field_ids(value: str) -> set[str]:
    """The ids already on the field, exact, `@host` tags stripped:
    `1724982@H200, 63902601–04` -> {'1724982', '63902601–04'}. A substring test
    here once dropped a record silently: recording 724982 onto a field holding
    1724982 reported success and wrote nothing — realistic ids share suffixes."""
    return {tok.split("@", 1)[0]
            for tok in re.split(r"[,\s]+", value) if tok.strip()}


def find_entry(page_ref: str, entry: str) -> tuple[Path, list[str], int, str] | str:
    """Resolve (page, blocks, index, body) — or the refusal message.
    Shared by record() and the --check pre-flight, so what the pre-flight
    accepts is exactly what the post-launch record will accept."""
    page = task_page(page_ref)
    if page is None:
        return f"record_submit: no task page {page_ref}"
    text = page.read_text(encoding="utf-8")
    blocks = text.split("### Entry: ")
    hit = [i for i, b in enumerate(blocks[1:], 1) if b.startswith(entry + "\n")]
    if not hit:
        return f"record_submit: {page_ref} has no entry '{entry}' (create the entry first)"
    return page, blocks, hit[0], blocks[hit[0]]


def record(page_ref: str, entry: str, job_id: str, log: str) -> tuple[bool, str, str]:
    """-> (recorded?, message, entry id). The bool is the launcher's exit status:
    a failed record means the job runs with no page entry, which no later poll
    can repair. The entry id feeds the commit's `Entry:` trailer."""
    found = find_entry(page_ref, entry)
    if isinstance(found, str):
        return False, f"{found} — job {job_id} NOT recorded", ""
    page, blocks, i, body = found

    # Repo-relative log link — the page contract forbids file:// (renders as
    # nothing, breaks silently when a page moves; P2 checks relative links).
    try:
        log_rel = os.path.relpath(Path(log).resolve(), page.parent.resolve())
    except ValueError:          # different drive (Windows) — degrade gracefully
        log_rel = str(log)

    lines = body.split("\n")
    # Header block = the run of `- **Key:**` lines after the entry-name line.
    # The canonical form has a BLANK line between the name and the block, so
    # skip blanks first (the old scan broke at that blank and inserted the
    # Jobs field above Status).
    k = 1
    while k < len(lines) and not lines[k].startswith("- **"):
        if lines[k].strip():    # narrative already started — no header block
            break
        k += 1
    while k < len(lines) and (lines[k].startswith("- **")
                              or (lines[k][:1] == " " and lines[k].strip())):
        k += 1              # a field value may wrap; indented lines continue it
    jline = next((j for j, l in enumerate(lines)
                  if JOBS_LINE_RE.match(l)), None)
    if jline is None:
        lines.insert(k, f"- **Jobs:** {job_id}")
        jline = k
    else:
        val = JOBS_LINE_RE.match(lines[jline]).group(1)
        if job_id.split("@", 1)[0] not in jobs_field_ids(val):
            # an EMPTY field gets the id, not a `, id` after nothing —
            # and never a second `- **Jobs:**` line
            sep = ", " if val else " "
            lines[jline] = lines[jline].rstrip() + sep + job_id
    # Live log link — the log exists the moment the job starts, so link it now
    # (J3 reads it) rather than at completion. It lands as an INDENTED
    # continuation of the Jobs field: a loose line between fields is E12, and
    # a standalone `Job <id> — [log]` stanza inside Facts is E13 — under the
    # field that owns the id it is legal to both, and the id stays on the
    # field's first line where `field()` reads it.
    if f"[log]({log_rel})" not in "\n".join(lines):
        insert_at = jline + 1
        while insert_at < len(lines) and lines[insert_at][:1] in (" ", "\t") \
                and lines[insert_at].strip():
            insert_at += 1      # after any continuation already under Jobs
        lines.insert(insert_at, f"  Job {job_id} — [log]({log_rel}).")
    body = "\n".join(lines)
    body = re.sub(r"^(- \*\*Status:\*\* |Status: )open\s*$", r"\1running",
                  body, count=1, flags=re.M)
    blocks[i] = body
    page.write_text("### Entry: ".join(blocks), encoding="utf-8")
    eid_m = re.search(r"^(?:-\s+\*\*)?Id:(?:\*\*)?\s*(\S+)", body, re.M)
    return (True, f"record_submit: {page_ref} · '{entry}' -> running (job {job_id})",
            eid_m.group(1) if eid_m else "")


def parse_binding(argv: list[str]) -> tuple[list[str], str | None, str | None, bool]:
    """Strip --phase/--role/--no-objective, return (positionals, phase, role, none).

    `--phase` takes `P<n>` or `O<nn>/P<n>`; the objective half is optional
    because the page usually resolves it, and required when it does not.
    """
    pos, phase, role, no_obj = [], None, None, False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--phase" and i + 1 < len(argv):
            phase = argv[i + 1]; i += 2
        elif a == "--role" and i + 1 < len(argv):
            role = argv[i + 1]; i += 2
        elif a == "--no-objective":
            no_obj = True; i += 1
        else:
            pos.append(a); i += 1
    return pos, phase, role, no_obj


def active_objectives() -> list[tuple[Path, str]]:
    """[(path, O<nn>)] for every ACTIVE objective, or [] when none/unreadable."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import check_objective_page as O
        out = []
        for obj in sorted((ROOT / "project_memory" / "objectives").glob("*.md")):
            fm, _ = O.frontmatter(obj.read_text(encoding="utf-8"))
            if fm.get("status") == "active" and fm.get("id"):
                out.append((obj, fm["id"]))
        return out
    except Exception:
        return []


def resolve_objective(page: Path, phase: str | None) -> tuple[Path, str, str] | str:
    """(objective path, O<nn>, P<n>) for this launch, or an error STRING.

    Resolution order, cheapest first: an explicit `O<nn>/P<n>` wins; otherwise
    the objectives whose Plan already links this page; otherwise, when exactly
    one objective is active, that one. Ambiguity is REPORTED, never guessed —
    guessing the owner is what the page-scoped heuristics did, and the point of
    binding at launch is that the session knows and can simply say.
    """
    if not phase:
        return "no --phase given"
    m = re.match(r"^(?:(O\d{2})/)?(P\d+)$", phase.strip())
    if not m:
        return f"--phase {phase!r} is not `P<n>` or `O<nn>/P<n>`"
    want_oid, pnum = m.group(1), m.group(2)
    actives = active_objectives()
    if not actives:
        return "no active objective on this project"
    if want_oid:
        hit = [(o, i) for o, i in actives if i == want_oid]
        if not hit:
            return f"{want_oid} is not an active objective"
        return hit[0][0], hit[0][1], pnum
    try:
        import check_objective_page as O
        page = page.resolve()
        linked = [(o, i) for o, i in actives
                  if any(pg.resolve() == page for pg, _ in O.plan_entry_refs(o))]
    except Exception:
        linked = []
    cand = linked or actives
    if len(cand) != 1:
        names = ", ".join(i for _, i in cand)
        return (f"this page is in play for {names} — say which, as "
                f"`--phase <O<nn>>/{pnum}`")
    return cand[0][0], cand[0][1], pnum


def write_plan_line(obj: Path, pnum: str, page: Path, entry: str,
                    eid: str, role: str) -> str:
    """Insert the entry line under phase `pnum`. Returns "" or an error string.

    Everything but `role` is derived: the link text is the entry's own name,
    the target the relative path plus the slug the anchor rule computes, the id
    the one just recorded. It goes last among the phase's entry lines and
    BEFORE the reading, which stays the block's final line. No date: an entry
    line's date is the day it concluded, and this one is starting.
    """
    try:
        import check_objective_page as O
        text = obj.read_text(encoding="utf-8")
        lines = text.split("\n")
        start = None
        for i, line in enumerate(lines):
            m = O.PHASE_HEAD_RE.match(line)
            if m and f"P{int(m.group(1))}" == f"P{int(pnum[1:])}":
                start = i
                break
        if start is None:
            return f"{obj.name} has no phase {pnum}"
        end = start + 1
        while end < len(lines) and (lines[end].startswith("  ")
                                    or not lines[end].strip()):
            if lines[end].strip() and not lines[end].startswith("  "):
                break
            end += 1
        block = lines[start:end]
        slug = O._slug(entry)
        rel = os.path.relpath(page.resolve(), obj.parent.resolve())
        line = f"  - [{entry}]({rel}#entry-{slug}) `{eid}` — {role}"
        if any(f"#entry-{slug})" in b for b in block):
            return ""                      # already there: idempotent
        at = len(block)
        while at > 0 and (not block[at - 1].strip()
                          or block[at - 1].lstrip().startswith("- \u25b6")):
            at -= 1
        block.insert(at, line)
        lines[start:end] = block
        obj.write_text("\n".join(lines), encoding="utf-8")
        return ""
    except Exception as exc:                                  # pragma: no cover
        return f"could not write the Plan line ({exc})"


def _on_no_active_plan(page: Path, eid: str) -> bool:
    """True when NO active objective's Plan links this entry — the one gap
    every watcher scope shares: an entry launched before its Plan line was
    written attributes to nobody, so an objective-scoped Monitor never wakes
    for it, and it surfaces hours later through the slow project-wide hook.
    Checked HERE because launch is the only moment that owns both halves:
    the wrapper knows exactly which entry this is, and the launching session
    is still present to add the line. Fail SILENT (False) on any doubt — a
    missing objectives dir, an unparseable page — this is a courtesy note,
    never a gate."""
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import check_objective_page as O
        page = page.resolve()
        saw_active = False
        for obj in sorted((ROOT / "project_memory" / "objectives").glob("*.md")):
            text = obj.read_text(encoding="utf-8")
            fm, _ = O.frontmatter(text)
            if fm.get("status") != "active":
                continue
            saw_active = True
            body = O.body_of(text, "Plan")
            for rel, _slug, cited in O.LINK_ID_RE.findall(body):
                if cited == eid and (obj.parent / rel).resolve() == page:
                    return False
            # a Plan line may omit the id; any link into this page counts,
            # resolved the cheap way (the id check above is the precise one)
            for rel, _slug in O.ENTRY_REF_RE.findall(body):
                if (obj.parent / rel).resolve() == page:
                    return False
        # no active objective at all = a project running on standalone probes;
        # nagging every launch there is noise, not a reminder
        return saw_active
    except Exception:
        return False


def main() -> int:
    argv, phase, role, no_obj = parse_binding(sys.argv[1:])
    sys.argv = [sys.argv[0], *argv]
    if len(sys.argv) == 4 and sys.argv[1] == "--check":
        # Pre-flight, run by the launcher BEFORE sbatch/nohup: a page or entry
        # that will not resolve aborts the launch instead of costing a live job
        # whose record then fails (the exit-3 shape no retry may follow).
        found = find_entry(sys.argv[2], sys.argv[3])
        if isinstance(found, str):
            print(f"{found} — pre-flight FAILED, nothing launched", file=sys.stderr)
            return 1
        # The binding is checked HERE, before anything launches, because this
        # is the only moment that owns both halves and the only moment when
        # failing is free. Launch already writes the job row, the log link and
        # the status; the Plan line was the one half left to a later turn that
        # a long-running job reliably swallows.
        if not no_obj:
            res = resolve_objective(found[0] if isinstance(found, tuple) else
                                    task_page(sys.argv[2]) or Path("."), phase)
            if isinstance(res, str):
                if res == "no active objective on this project":
                    pass                      # standalone project: nothing to bind
                else:
                    print(f"record_submit: {res} — pre-flight FAILED, nothing "
                          f"launched. A launch comes from a phase: pass "
                          f"`--phase P<n> --role \"<what this entry does for it>\"`, "
                          f"or `--no-objective` if this run serves none.",
                          file=sys.stderr)
                    return 1
            elif not role:
                print("record_submit: --phase given without --role — pre-flight "
                      "FAILED, nothing launched. The entry line has to say what "
                      "this run does for the phase; the script can derive "
                      "everything else.", file=sys.stderr)
                return 1
        print(f"record_submit: pre-flight ok — {sys.argv[2]} · '{sys.argv[3]}'")
        return 0
    if len(sys.argv) != 5:
        print(__doc__, file=sys.stderr)
        return 2
    # The record lock (shared with the bus and the fixer) covers the whole
    # read-modify-write: a concurrent bus put on the same page can neither
    # interleave with nor overwrite this record. Released on process exit.
    lockdir = ROOT / ".fixer"
    lockdir.mkdir(exist_ok=True)
    lock = open(lockdir / "record.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_EX)
    ok, msg, eid = record(*sys.argv[1:5])
    print(msg)
    if not ok:
        return 1
    # Commit inside the same lock. An uncommitted job row is the record's most
    # fragile state: a bus `put` overwrites the whole page, the fixer's sweep
    # attributes it to the daemon, and a worktree removal takes it with it —
    # all while the job it describes is already running. Path-scoped, because
    # another actor may have staged unrelated work.
    page = task_page(sys.argv[1])
    if page is not None:
        rel = page.relative_to(ROOT)
        # Lint before committing — this is the record's SECOND door (the bus is
        # the first), and an unchecked door is not a door. The verdict differs
        # from the bus's, though, and deliberately: the bus refuses to commit
        # authored content that fails, while here the job is ALREADY RUNNING, so
        # withholding its row would leave a live job invisible (J4) to spare a
        # page a lint error. The row lands; the errors are shouted at the session
        # that launched, which is in a position to fix them this turn.
        lint = subprocess.run([sys.executable, str(Path(__file__).with_name(
            "check_node_page.py")), str(page), "--quiet"],
            capture_output=True, text=True, timeout=60)
        if lint.returncode != 0 and (lint.stdout or lint.stderr).strip():
            print(f"record_submit: the row landed, but {rel.name} does NOT lint —\n"
                  + (lint.stdout or lint.stderr).rstrip()
                  + "\n  fix it THIS turn; the job is already running.", file=sys.stderr)
        subprocess.run(["git", "-C", str(ROOT), "add", "--", str(rel)],
                       capture_output=True, timeout=30)
        # The commit-msg hook holds every nodes/ commit to an `Entry: <id>`
        # trailer — without it this auto-commit is refused and the row sits
        # uncommitted in the record's most fragile state.
        cmsg = f"memory: job {sys.argv[3]} recorded on {rel.name}"
        if eid:
            cmsg += f"\n\nEntry: {eid}"
        else:
            print("record_submit: WARNING entry has no `Id:` — the commit-msg hook "
                  "will refuse the trailer-less commit; add the Id and commit "
                  "manually", file=sys.stderr)
        c = subprocess.run(["git", "-C", str(ROOT), "commit", "-m", cmsg,
                            "--", str(rel)], capture_output=True, text=True, timeout=30)
        if c.returncode != 0 and "nothing to commit" not in (c.stdout + c.stderr):
            print(f"record_submit: WARNING commit failed — {(c.stderr or c.stdout).strip()[:160]}",
                  file=sys.stderr)
        # The Plan line, same lock, own commit. The contract keeps `nodes/` and
        # `objectives/` in separate commits with different trailers, so this
        # cannot ride the row's commit — but it CAN ride the same lock and the
        # same turn, which is the whole point: the two halves of a launch stop
        # being two turns apart.
        bound = False
        if eid and not no_obj and phase:
            res = resolve_objective(page, phase)
            if isinstance(res, str):
                print(f"record_submit: the row landed but the Plan line did NOT "
                      f"— {res}. Add it THIS turn.", file=sys.stderr)
            else:
                obj, oid, pnum = res
                err = write_plan_line(obj, pnum, page, sys.argv[2], eid,
                                      role or "")
                if err:
                    print(f"record_submit: the row landed but the Plan line did "
                          f"NOT — {err}. Add it THIS turn.", file=sys.stderr)
                else:
                    bound = True
                    orel = obj.relative_to(ROOT)
                    subprocess.run(["git", "-C", str(ROOT), "add", "--", str(orel)],
                                   capture_output=True, timeout=30)
                    subprocess.run(
                        ["git", "-C", str(ROOT), "commit", "-m",
                         f"memory: {oid} — {pnum} carries {eid}\n\nObjective: {oid}",
                         "--", str(orel)], capture_output=True, text=True, timeout=30)
                    print(f"record_submit: {eid} -> {oid} / {pnum} ({orel})")
        if eid and not bound and _on_no_active_plan(page, eid):
            print(f"record_submit: note — entry {eid} is on NO active "
                  f"objective's Plan. If this run serves one, add its Plan "
                  f"line THIS turn (objective skill, loop step 3): an "
                  f"objective-scoped watcher cannot see an entry its Plan "
                  f"never links. Standalone work can ignore this.",
                  file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
