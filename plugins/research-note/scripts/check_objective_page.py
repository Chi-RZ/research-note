#!/usr/bin/env python3
"""Lint an objective page — the Goal/Plan/Verdict route record (record v3).

A task page is checked for FORMAT; an objective page makes ASSERTIONS ABOUT
OTHER DOCUMENTS, so the rules here are cross-document consistency, and the
page's own text is only the claim, never the evidence. The page is what the
user reads INSTEAD of watching the session — a page that silently drifts is
worse than no page.

Codes (DESIGN.md §10):
  O1  frontmatter: id, status, created, budget, wake-me-if
  O2  Goal, Plan, Verdict, in order, nothing else
  O3  links resolve and land on real entries; a backticked id beside an entry
      link matches that entry's `Id:`
  O4  Goal revisions carry user authorization bound to the old/new text
  O5  the Plan is a DAG: phase headers parse, `needs:` names existing phases,
      no cycles
  O6  a probe spawned by a live Plan appears on some plan
  O7  a phase reading is not older than the conclusions it reads (keyed to the
      latest dated entry line of the phase)
  O8  the Verdict's awaiting-review count equals the `analyzed` entries the
      Plan links
  O9  no figure and no table in Plan or Verdict — both belong to the entry
      (the Goal is the user's and may carry its target table)
  O10 `attention:` present only while the loop is stopped — never on a closed
      objective
  O11 advisory: the Verdict stays the answer — the reasoning is in the
      phases
  O12 the id is unique across objectives/ — a duplicate silently merges two
      goals' trailer histories
  M1  one record language, where framework.json declares it

Review counts are derived and maintained by objective_state.py. Entry links
and phase judgements still require the deciding turn; an explicit review is
bound to its evidence, never inferred from a timestamp alone.

Usage: check_objective_page.py [PATH ...] [--quiet]
Exit: 0 clean · 1 findings · 3 record-version mismatch.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from projroot import nth_parent, resolve_root  # noqa: E402
from check_node_page import (  # noqa: E402
    CJK_RE, CONCLUDED, _record_language, record_version_check, field_block)

ROOT = resolve_root(nth_parent(Path(__file__), 2))
OBJ_DIR = ROOT / "project_memory" / "objectives"

REQUIRED_FM = ("id", "status", "created", "budget", "wake-me-if")
LEGAL_STATUS = {"active", "closed"}
ID_RE = re.compile(r"^O\d{2}$")
SECTIONS = ("Goal", "Plan", "Verdict")
#: O5 — a phase block opens with a checkbox header:
#: `- [ ] **P<n> — <question>** (<cost>[ · needs: P<i>,P<j>])`.
PHASE_HEAD_RE = re.compile(r"^-\s*\[[ xX]\]\s*\*\*P(\d+)\s*—\s*.+?\*\*\s*\(([^)]*)\)\s*$")
CHECKBOX_RE = re.compile(r"^-\s*\[[ xX]\]")
TICKED_RE = re.compile(r"^-\s*\[[xX]\]")
NEEDS_RE = re.compile(r"needs:\s*([^·)]+)")
ENTRY_HEAD_RE = re.compile(r"^#{2,4}\s+Entry:\s*(.+?)\s*$", re.M)
#: O6 — the descent join key, written the same way on both sides: a Plan link
#: and a Motivation source are both `<page>.md#entry-<slug>`.
ENTRY_REF_RE = re.compile(r"\]\(([^)]+?\.md)#entry-([\w-]+)\)")
#: A Motivation bullet runs to the next bold header field.
MOTIV_RE = re.compile(r"^- \*\*Motivation:\*\*(.*(?:\n(?!\s*- \*\*).*)*)", re.M)
FIG_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
#: An entry line's backticked id, sitting right after the link.
LINK_ID_RE = re.compile(r"\]\(([^)]+?\.md)#entry-([\w-]+)\)\s*`(\d{2}\.\d{3})`")
DATE_TAIL_RE = re.compile(r"\((\d{4}-\d{2}-\d{2})\)\s*$")


def frontmatter(text: str) -> tuple[dict[str, str], str | None]:
    """-> (fields, yaml_error). Parsed the naive way so a malformed block still
    yields fields to check, but ALSO handed to a real YAML parser: these values
    are free text and a bare `: ` inside one makes YAML read a nested mapping
    and reject the whole page for Obsidian and every other reader. Fix by
    quoting the value."""
    m = re.search(r"^---\n(.*?)\n---", text, re.S)
    out: dict[str, str] = {}
    if not m:
        return out, "no frontmatter block"
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    try:
        import yaml
        yaml.safe_load(m.group(1))
        return out, None
    except ImportError:
        return out, None
    except Exception as e:
        return out, str(e).splitlines()[0]


def body_of(text: str, name: str) -> str:
    m = re.search(rf"^##\s+{name}\s*$\n(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    return m.group(1) if m else ""


#: Both caches are per PROCESS and keyed by what git is asked, not by when:
#: a committed blob and "which commit last touched this path before <date>"
#: cannot change under a single run. They exist because O7 asks the same
#: question over and over — one reading per phase line, most of them about the
#: same page on the same date — and each miss is TWO subprocesses, the first a
#: path-filtered `rev-list` whose cost grows with the commit count. Measured on
#: a live project at 3318 commits: 129 calls, 40 distinct, 105 s; the dashboard
#: that wraps this then blew its 120 s budget every cycle and reported the
#: whole fixer as crashed.
_BLOB_CACHE: dict[tuple[str, str], str | None] = {}
_REV_CACHE: dict[tuple[str, str], str] = {}


def git_show(path: Path, rev: str = "HEAD") -> str | None:
    """The committed version of `path`, or None if git has no such blob."""
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        return None                      # outside the repo: no history
    key = (rel, rev)
    if key not in _BLOB_CACHE:
        p = subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{rel}"],
                           capture_output=True, text=True)
        _BLOB_CACHE[key] = p.stdout if p.returncode == 0 else None
    return _BLOB_CACHE[key]


def blob_on(path: Path, date: str) -> str | None:
    """The page as it stood at the END of `date` (YYYY-MM-DD), or None if git
    has no such state. O7 asks what a reading was written against."""
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        return None
    key = (rel, date)
    if key not in _REV_CACHE:
        p = subprocess.run(["git", "-C", str(ROOT), "rev-list", "-1",
                            f"--before={date} 23:59:59", "HEAD", "--", rel],
                           capture_output=True, text=True)
        _REV_CACHE[key] = p.stdout.strip()
    rev = _REV_CACHE[key]
    return git_show(path, rev) if rev else None


def _slug(heading: str) -> str:
    s = re.sub(r"[^\w\s-]", "", heading.lower())
    return re.sub(r"\s+", "-", s.strip())


def _entry_field(text: str, key: str) -> dict[str, str]:
    """slug -> the entry's `- **<key>:**` line, from a page's TEXT (so the same
    reader works on a git blob as on the file on disk)."""
    out: dict[str, str] = {}
    parts = ENTRY_HEAD_RE.split(text)
    for i in range(1, len(parts) - 1, 2):
        value = field_block(parts[i + 1], key)
        if value:
            out[_slug(parts[i])] = " ".join(value.split())
    return out


def entry_status(page: Path) -> dict[str, str]:
    return _entry_field(page.read_text(encoding="utf-8"), "Status")


def entry_names(page: Path) -> set[str]:
    return set(ENTRY_HEAD_RE.findall(page.read_text(encoding="utf-8")))


def plan_entry_refs(obj: Path) -> set[tuple[Path, str]]:
    """The (task page, entry slug) pairs an objective's Plan links."""
    text = obj.read_text(encoding="utf-8")
    return {((obj.parent / rel).resolve(), slug)
            for rel, slug in ENTRY_REF_RE.findall(body_of(text, "Plan"))}


def objective_refs() -> tuple[set[tuple[Path, str]], set[tuple[Path, str]]]:
    """(obligating, every) Plan entry refs across all objective pages — O6.

    Obligations arise only from an ACTIVE route: a closed objective's Plan is
    history, and work descending from it belongs to whatever came next."""
    obligating: set[tuple[Path, str]] = set()
    every: set[tuple[Path, str]] = set()
    for obj in sorted(OBJ_DIR.glob("*.md")):
        fm, _ = frontmatter(obj.read_text(encoding="utf-8"))
        refs = plan_entry_refs(obj)
        every |= refs
        if fm.get("status") == "active":
            obligating |= refs
    return obligating, every


_DESCENDANTS: dict[tuple[Path, str], list[tuple[Path, str]]] | None = None


def descendants() -> dict[tuple[Path, str], list[tuple[Path, str]]]:
    """parent ref -> the entries whose Motivation names it as a source, for O6.

    §5 already makes every motivation name its source, link included when one
    exists, so descent is DERIVABLE: no new field, nothing to fall out of sync.
    Cached — the walk is the same for every objective page in one run."""
    global _DESCENDANTS
    if _DESCENDANTS is not None:
        return _DESCENDANTS
    out: dict[tuple[Path, str], list[tuple[Path, str]]] = {}
    for page in sorted((ROOT / "project_memory" / "nodes").rglob("*.md")):
        parts = ENTRY_HEAD_RE.split(page.read_text(encoding="utf-8"))
        for i in range(1, len(parts) - 1, 2):
            mot = MOTIV_RE.search(parts[i + 1])
            if not mot:
                continue
            child = (page.resolve(), _slug(parts[i]))
            for rel, slug in ENTRY_REF_RE.findall(mot.group(1)):
                parent = ((page.parent / rel).resolve(), slug)
                if parent != child and child not in out.get(parent, ()):
                    out.setdefault(parent, []).append(child)
    _DESCENDANTS = out
    return out


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


ADVISORY_CODES = {"O11"}
REVIEW_RE = re.compile(r"^  - Review: .+ <!-- rn-review:([0-9a-f]{64}) -->$", re.M)


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def phase_blocks(text: str) -> list[str]:
    return re.split(r"(?=^-\s*\[[ xX]\]\s*\*\*P\d+)", body_of(text, "Plan"), flags=re.M)


def phase_fingerprint(path: Path, block: str) -> str:
    """Bind an explicit review to this reading and every full linked conclusion."""
    evidence = []
    for rel, slug in sorted(set(ENTRY_REF_RE.findall(block))):
        page = (path.parent / rel).resolve()
        if not page.is_file():
            raise ValueError(f"missing review source: {rel}")
        conclusion = _entry_field(page.read_text(encoding="utf-8"), "Conclusion").get(slug)
        if not conclusion:
            raise ValueError(f"missing conclusion: {rel}#entry-{slug}")
        evidence.append((rel, slug, conclusion))
    if not evidence:
        raise ValueError("phase has no conclusions to review")
    reading = REVIEW_RE.sub("", block).strip()
    return digest(json.dumps([reading, evidence], ensure_ascii=True, sort_keys=True))


def goal_change_approved(fm: dict, previous: str, current: str) -> bool:
    return (bool(fm.get("goal-approval", "").strip())
            and fm.get("goal-approved-from") == digest(body_of(previous, "Goal").strip())
            and fm.get("goal-approved-to") == digest(body_of(current, "Goal").strip()))


def lint(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errs: list[str] = []
    fm, yaml_err = frontmatter(text)

    # O1 — frontmatter.
    if yaml_err:
        errs.append(f"O1 frontmatter is not valid YAML ({yaml_err}) — every reader "
                    f"rejects the page. Free-text values need quoting: a bare `: ` "
                    f"reads as a nested mapping.")
    for key in REQUIRED_FM:
        if not fm.get(key):
            errs.append(f"O1 frontmatter missing `{key}:`")
    if fm.get("id") and not ID_RE.match(fm["id"]):
        errs.append(f"O1 `id: {fm['id']}` is not `O<nn>`")
    if fm.get("status") and fm["status"] not in LEGAL_STATUS:
        errs.append(f"O1 `status: {fm['status']}` not in {sorted(LEGAL_STATUS)}")

    # O10 — attention: present only while the loop is stopped.
    att = str(fm.get("attention", "") or "").strip()
    if att and fm.get("status") == "closed":
        errs.append("O10 `attention:` set on a closed objective — nothing is "
                    "waiting on the user; drop the field")

    # O2 — three sections, in order, nothing else.
    headings = re.findall(r"^##\s+(\S+)", text, re.M)
    found = [s for s in headings if s in SECTIONS]
    for s in SECTIONS:
        if s not in found:
            errs.append(f"O2 missing `## {s}` section")
    if found != [s for s in SECTIONS if s in found]:
        errs.append(f"O2 sections out of order: {found} — expected {list(SECTIONS)}")
    for s in headings:
        if s not in SECTIONS:
            errs.append(f"O2 `## {s}` is not a section of this page — Goal, Plan, "
                        f"Verdict, nothing else; facts live on the node pages")

    # O3 — every relative link resolves; an `#entry-...` anchor names a real
    # entry; a backticked id beside an entry link matches that entry's `Id:`.
    for raw in re.findall(
            r"\]\((\.\.?/[^)]+|[A-Za-z0-9_][\w.-]*\.md(?:#[^)]*)?)\)", text):
        rel, _, frag = raw.partition("#")
        target = path.parent / rel
        if not target.exists():
            errs.append(f"O3 link `{rel}` does not resolve")
        elif frag and rel.endswith(".md"):
            slugs = {_slug("Entry: " + n) for n in entry_names(target)}
            try:
                slugs |= {_slug(m.group(1)) for m in
                          re.finditer(r"^#{2,4}\s+(.+?)\s*$",
                                      target.read_text(encoding="utf-8"), re.M)}
            except OSError:
                pass
            if slugs and frag not in slugs:
                errs.append(f"O3 anchor `#{frag}` not found in {target.name}")
    for rel, slug, cited_id in LINK_ID_RE.findall(text):
        target = (path.parent / rel).resolve()
        if not target.exists():
            continue
        real = _entry_field(target.read_text(encoding="utf-8"), "Id").get(slug)
        if real and real.strip("`") != cited_id:
            errs.append(f"O3 entry link cites id `{cited_id}` but `{slug}` on "
                        f"{target.name} carries `Id: {real}`")

    # O9 — no figure and no table in Plan or Verdict; both belong to the entry.
    for sec in ("Plan", "Verdict"):
        body = body_of(text, sec)
        for m in FIG_RE.finditer(body):
            errs.append(f"O9 figure `{m.group(2)}` in {sec} — a figure belongs to "
                        f"the entry that produced it; the phase line links the entry")
        if re.search(r"^\s*\|.*\|\s*$", body, re.M):
            errs.append(f"O9 a table in {sec} — numbers live on the entry, one "
                        f"click away; the reading carries neither number nor "
                        f"mechanism")

    # O5 — the Plan is a DAG.
    plan_body = body_of(text, "Plan")
    phases: list[tuple[int, str]] = []
    for line in plan_body.splitlines():
        if not line.startswith("- "):
            continue
        m = PHASE_HEAD_RE.match(line)
        if m:
            phases.append((int(m.group(1)), m.group(2)))
        elif CHECKBOX_RE.match(line):
            errs.append(f"O5 Plan phase header `{line.strip()[:60]}` does not "
                        f"parse — the form is `- [ ] **P<n> — <the question>** "
                        f"(<cost>[ · needs: P<i>,P<j>])`")
    nums = [n for n, _ in phases]
    for n in sorted({n for n in nums if nums.count(n) > 1}):
        errs.append(f"O5 phase number P{n} appears more than once — phase numbers "
                    f"are the `needs:` join key and must be unique")
    deps: dict[int, list[int]] = {}
    for i, (num, extras) in enumerate(phases):
        m = NEEDS_RE.search(extras)
        if m:
            deps[num] = []
            for tok in (t.strip() for t in m.group(1).split(",") if t.strip()):
                if not re.fullmatch(r"P\d+", tok) or int(tok[1:]) not in set(nums):
                    errs.append(f"O5 P{num} `needs: {tok}` names no phase on "
                                f"this Plan")
                else:
                    deps[num].append(int(tok[1:]))
        else:
            deps[num] = [phases[i - 1][0]] if i else []
    color: dict[int, int] = {}

    def cyclic(n: int) -> bool:
        if color.get(n) == 1:
            return True
        if color.get(n) == 2:
            return False
        color[n] = 1
        if any(cyclic(d) for d in deps.get(n, [])):
            return True
        color[n] = 2
        return False

    if any(cyclic(n) for n in list(deps)):
        errs.append("O5 `needs:` dependencies form a cycle — the Plan is a DAG; no "
                    "phase can wait on a phase that waits on it")

    # O6 — a probe spawned by a live Plan appears on some plan. The owner
    # analyzing an entry opens the follow-up itself; if that follow-up lands in
    # no phase, this page has quietly stopped being the run's live view.
    if fm.get("status") == "active":
        _, every = objective_refs()
        desc = descendants()
        for parent in sorted(plan_entry_refs(path)):
            for child in desc.get(parent, ()):
                if child in every:
                    continue
                errs.append(f"O6 {_rel(child[0])}#entry-{child[1]} names "
                            f"`#entry-{parent[1]}` on this Plan as its source but "
                            f"sits in no phase — a follow-up of a live route joins "
                            f"the route (a new phase with `needs:`, or the phase "
                            f"whose question it serves)")

    # O14 — an entry the MACHINE knows about that this page does not. A job
    # id is written onto its entry at submission, so `Jobs:` non-empty means
    # something was actually launched; if no phase of any objective names that
    # entry while its page is on this objective's route, the Plan has stopped
    # being the live view of the run.
    #
    # This is O13's missing half. O13 fires when every entry of a phase has
    # concluded and the box is still open — it watches phases that have
    # entries. Nothing watched a phase that launched an entry and never wrote
    # the line, which is the same failure one step earlier and invisible from
    # the page alone.
    #
    # `Jobs:` non-empty is what makes it precise rather than noisy. Entries
    # with no jobs are reading, cost accounting, or work that legitimately
    # belongs to no route; requiring a launch narrows the claim to "the record
    # says less than the machine knows", which is the thing worth failing on.
    if fm.get("status") == "active":
        _, every = objective_refs()
        # Scope: the pages this objective already links, and no wider. A node
        # folder holds work belonging to no route and to other objectives, and
        # this check is a BACKSTOP now — the binding is made at launch, where
        # `record_submit` writes the Plan line and the pre-flight refuses a
        # submission that names no phase. A backstop earns narrow scope: what
        # it would additionally catch is an entry that reached the record
        # without going through the launcher at all.
        mine = {page for page, _ in plan_entry_refs(path)}
        for task_page in sorted(mine):
            if not task_page.is_file():
                continue
            # Distinct names on purpose: `text`, `status` and `jobs` are the
            # enclosing function's, holding the OBJECTIVE page under lint.
            # Reusing them here silently fed every later check the task page's
            # text instead — O4, O8, O11 and M1 all went wrong at once.
            task_text = task_page.read_text(encoding="utf-8")
            task_status = _entry_field(task_text, "Status")
            task_jobs = _entry_field(task_text, "Jobs")
            for slug, st in sorted(task_status.items()):
                if st.strip() not in ("running", "analyzed"):
                    continue
                if not task_jobs.get(slug, "").strip():
                    continue
                if (task_page, slug) in every:
                    continue
                errs.append(f"O14 {_rel(task_page)}#entry-{slug} is `{st.strip()}` with "
                            f"jobs and sits in no phase, on a page this Plan "
                            f"links — the entry line goes on its phase in the "
                            f"same turn as the submission, or this page stops "
                            f"being the run's live view")

    # O7 — a phase reading is not older than the conclusions it reads. The
    # phase's latest dated entry line is when the reading could first have been
    # written; a linked conclusion that changed after it leaves the ▶ line
    # standing on a sentence that no longer exists.
    if fm.get("status") == "active":
        for block in re.split(r"(?=^-\s*\[[ xX]\]\s*\*\*P\d+)", plan_body, flags=re.M):
            if not CHECKBOX_RE.match(block) or "▶" not in block:
                continue
            review = REVIEW_RE.search(block)
            if review:
                try:
                    current = phase_fingerprint(path, block)
                except ValueError:
                    current = None
                if current != review.group(1):
                    errs.append("O7 phase evidence or reading changed since its explicit review — re-read and review again")
                continue
            dates = [d for line in block.splitlines()
                     if (d := DATE_TAIL_RE.search(line))]
            if not dates:
                continue
            asof = max(d.group(1) for d in dates)
            hm = PHASE_HEAD_RE.search(block.splitlines()[0])
            pname = f"P{hm.group(1)}" if hm else "a phase"
            for rel, slug in ENTRY_REF_RE.findall(block):
                pg = (path.parent / rel).resolve()
                then = blob_on(pg, asof) if pg.exists() else None
                if then is None:
                    continue
                was = _entry_field(then, "Conclusion").get(slug)
                now = _entry_field(pg.read_text(encoding="utf-8"),
                                   "Conclusion").get(slug)
                # Only a CHANGED conclusion counts: absent-from-that-day's-blob
                # is almost always a reading committed after midnight.
                if was is not None and now is not None and was != now:
                    errs.append(f"O7 {pname}'s reading stands on `{slug}`, whose "
                                f"conclusion changed after {asof} — re-read it and "
                                f"rewrite the ▶ line if it no longer holds")

    # O13 — the checkbox matches the entries under it. The doctrine is one
    # sentence — the box flips when all the phase's entries concluded — and the
    # way it fails is silent and one-directional: the ▶ reading DOES get
    # written, because that is the judgement and there is something to say,
    # while the box stays `[ ]`, because ticking it says nothing and a habit
    # with no content is the one that gets skipped. Observed on a live Plan:
    # three consecutive phases carrying a finished reading over an unticked
    # box, every entry under them `analyzed`. The objective page is the
    # interface — the user reads the page, not the session — so a Plan that
    # under-reports its own progress misleads the only reader it has. It is
    # mechanically decidable, so it is not left to a habit.
    #
    # Both directions, because each means something: unticked-but-finished is
    # the forgotten tick; ticked-but-unfinished is a phase called done over an
    # entry still open. Only on an `active` objective — a closed one is
    # history, and reopening it to fix bookkeeping helps nobody.
    if fm.get("status") == "active":
        for block in re.split(r"(?=^-\s*\[[ xX]\]\s*\*\*P\d+)", plan_body, flags=re.M):
            lines = block.splitlines()
            hm = PHASE_HEAD_RE.search(lines[0]) if lines else None
            if not hm:
                continue
            states = []
            for rel, slug in ENTRY_REF_RE.findall(block):
                pg = (path.parent / rel).resolve()
                if not pg.exists():
                    continue                      # O3 owns a link that does not resolve
                if st := entry_status(pg).get(slug):
                    states.append(st)
            if not states:
                continue                          # a phase with no entry yet settles nothing
            pname, ticked = f"P{hm.group(1)}", bool(TICKED_RE.match(lines[0]))
            open_ = sorted({s for s in states if s not in CONCLUDED})
            if not open_ and not ticked:
                n = len(states)
                errs.append(f"O13 {pname} has {n} entr{'y' if n == 1 else 'ies'} and "
                            f"every one has concluded, but its box is still `[ ]` — "
                            f"the checkbox flips when all the phase's entries "
                            f"concluded")
            elif open_ and ticked:
                errs.append(f"O13 {pname} is ticked while its entries are not all "
                            f"concluded ({', '.join(open_)}) — the box says the "
                            f"question is answered")

    # O11 — the Verdict is the answer, not the argument.
    verdict_lines = [l for l in body_of(text, "Verdict").splitlines() if l.strip()]
    if len(verdict_lines) > 10:
        errs.append(f"O11 the Verdict runs {len(verdict_lines)} non-empty lines — it is "
                    f"the answer against the Goal plus the awaiting count; the "
                    f"reasoning is already in the phases")

    # O8 — the Verdict's awaiting-review count equals the `analyzed` entries
    # the Plan links. Hand-maintained it goes stale the moment an entry
    # concludes, and a stale count is a batch ✓ that silently skips an entry.
    ready = sum(1 for pg, sl in plan_entry_refs(path)
                if pg.exists() and entry_status(pg).get(sl) == "analyzed")
    verdict_body = body_of(text, "Verdict")
    # `awaits?` so one entry can be written in English. Without it the only
    # spelling the count check accepts is "1 entries await review", and the
    # natural singular falls to the branch below, whose message then asks for
    # the ungrammatical form by name.
    claim = re.search(r"(\d+)\s+entr(?:y|ies)\s+awaits? review", verdict_body, re.I)
    if claim and int(claim.group(1)) != ready:
        errs.append(f"O8 the Verdict says `{claim.group(1)} entries await review` "
                    f"but the Plan links {ready} `analyzed` entr(y/ies) — the "
                    f"count is what one ✓ closes")
    elif not claim and ready:
        errs.append(f"O8 the Verdict states no awaiting-review count while the "
                    f"Plan links {ready} `analyzed` entr(y/ies) — write "
                    f"`{ready} entr" + ("y awaits" if ready == 1 else "ies await") + " review`")

    # O4 — the Goal is the user's, byte-unchanged against the committed version.
    prev = git_show(path)
    if prev is not None:
        if (body_of(text, "Goal").strip() != body_of(prev, "Goal").strip()
                and not goal_change_approved(fm, prev, text)):
            errs.append("O4 Goal changed — the Goal is the user's; a different "
                        "goal requires explicit user authorization. Record the instruction with "
                        "objective_state.py approve-goal before committing")

    # M1 — one record language, where the project declares it.
    if _record_language() == "en":
        cjk = [i for i, l in enumerate(text.splitlines(), 1) if CJK_RE.search(l)]
        if cjk:
            more = f" (+{len(cjk) - 5} more)" if len(cjk) > 5 else ""
            errs.append(f"M1 non-English (CJK) text on line(s) {cjk[:5]}{more} — "
                        f"this project declares `record_language: en`")

    return errs


def duplicate_id_errors() -> list[tuple[Path, str]]:
    """O12 — the id is unique ACROSS the directory, not just well-formed on
    its page. O1 sees one file at a time, so two pages both declaring
    `id: O04` were both green; every `Objective:` trailer, `needs:` edge and
    roster row keys on the id, so a duplicate silently merges two goals'
    histories. The directory is a handful of files — checked on every run,
    single-page invocations included."""
    out: list[tuple[Path, str]] = []
    ids: dict[str, Path] = {}
    for p in sorted(OBJ_DIR.glob("*.md")):
        fm, _ = frontmatter(p.read_text(encoding="utf-8"))
        oid = str(fm.get("id", "") or "")
        if oid and ID_RE.match(oid):
            if oid in ids:
                out.append((p, f"O12 `id: {oid}` is already taken by "
                               f"{ids[oid].name} — ids are assigned once (next "
                               f"free O<nn>, read off the roster's Objectives "
                               f"section) and never reused; renumber this page"))
            else:
                ids[oid] = p
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    quiet = "--quiet" in sys.argv
    fw = record_version_check()
    if fw:
        for e in fw:
            print(f"  {e}")
        return 3
    if not (ROOT / "project_memory").is_dir():
        # A wrong ROOT once made OBJ_DIR.glob() come back empty and the run
        # exit 0 in silence — indistinguishable from a healthy pass.
        print(f"check_objective_page: resolved project root `{ROOT}` has no "
              f"project_memory/ — wrong root, refusing to lint nothing",
              file=sys.stderr)
        return 2
    paths = [Path(a).resolve() for a in args] or sorted(OBJ_DIR.glob("*.md"))
    bad = 0
    for p in paths:
        errs = lint(p)
        if errs:
            bad += any(e.split()[0] not in ADVISORY_CODES for e in errs)
            print(f"{_rel(p)}:")
            for e in errs:
                prefix = "warning: " if e.split()[0] in ADVISORY_CODES else ""
                print(f"  {prefix}{e}")
        elif not quiet:
            print(f"{_rel(p)}: OK")
    for p, e in duplicate_id_errors():
        bad += 1
        print(f"{_rel(p)}:")
        print(f"  {e}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
