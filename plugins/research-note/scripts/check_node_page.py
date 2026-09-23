#!/usr/bin/env python3
"""Lint the node record: node.md pages and task pages, both lists of entries.

Codes (record v3 — DESIGN.md §10):
  N1 node.md exists, entries only, first is the gate
  N2 an implementation exists under <experiments root>/<node>/ (--cross)
  N3 the regenerated roster matches the tree              (--cross)
  FW record version matches the linter (exit 3 on mismatch)
  E1 id unique, in Date order          E2 status in the four states
  E3 date                              E4 Code names its commits
  E5 motivation in its form            E6 recipe is a knob map
  E7 Facts: sentence, table, evidence  E8 a displayed number has a Refs row
  E9 a conclusion once analyzed        E10 one spelling, no retired field
  E11 one computation script per entry   E12 every line inside a field
  E13 Facts holds no bare `Job — [log]` stanza  E14 the Conclusion carries no link
  E15 the Conclusion ends at its verdict
  E16 a cited <repo>@<sha> is retrievable (landed here, resolvable for a lib)
  P1 a title and at least one entry    P2 links and anchors resolve
  P3 figures render                    P4 a figure has a caption, embedded once
  P5 no page-level Jobs
  J1 an entry with jobs links an artifact
  J2 a live BATCH job is named by some entry — an srun alloc is not one (--cross)
  J3 J4 entry status against the queue, both directions
  J5 an entry that ran jobs left `Jobs:` empty
  J6 an id the Facts name (or a Job line) is missing from the Jobs field
  V1 a validation entry names the entry it replays
  M1 one record language, where framework.json declares it

Usage:
  python3 check_node_page.py [PATH ...] [--blocking] [--cross] [--quiet]
Exit: 0 clean · 1 findings · 3 record-version mismatch (nothing else checked).
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from projroot import nth_parent, resolve_root  # noqa: E402
from project_config import (  # noqa: E402
    ConfigError,
    initial_project_config,
    load_project_config,
)

ROOT = resolve_root(nth_parent(Path(__file__), 2))
NODES_DIR = ROOT / "project_memory" / "nodes"
#: Default kept for older importers; the N2 check reads experiment_roots().
EXPERIMENTS_DIR = ROOT / "experiments"


def experiment_roots() -> list[Path]:
    """The experiment roots this project declares (`.research-note/project.json`),
    or the standard layout when it declares nothing."""
    try:
        config = load_project_config(ROOT)
    except ConfigError:
        config = initial_project_config(legacy=True)
    return [ROOT / path for path in config["roles"]["experiments"]]

#: The record schema this linter enforces. A project declares the version it
#: was migrated to in .claude/framework.json; a mismatch means either the
#: records need migrating or the marker was never bumped — it drifted silently
#: once (the v2.3 jobs-on-entries move), so it is checked, not trusted.
RECORD_VERSION = "v3"

CJK_RE = re.compile(r"[一-鿿]")

ADVISORY_CODES: set[str] = set()


def frontmatter(text: str) -> dict[str, str]:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def sections(text: str) -> dict[str, str]:
    """`### Entry: <name>` -> body, up to the next heading of the same or higher level.

    The boundary is read off the entry's own heading level: for a `###` entry a
    `#`/`##`/`###` heading ends the body, while a deeper `####` heading is
    sub-content of the entry and stays inside it.
    """
    out: dict[str, str] = {}
    heads = list(re.finditer(r"^(#{2,4})\s+Entry:\s*(.+?)\s*$", text, re.M))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        nxt = re.search(rf"^#{{1,{len(m.group(1))}}}\s+\S", text[m.end():end], re.M)
        out[m.group(2)] = text[m.end():m.end() + nxt.start()] if nxt else text[m.end():end]
    return out


def field(body: str, key: str) -> str:
    """Read a header field. `- **Key:** value` is THE form; the bare
    `Key: value` is still PARSED (so E10 can name the offending field instead
    of every other code reporting it as missing) but it is a lint error."""
    m = re.search(rf"^(?:-\s+\*\*)?{key}:(?:\*\*)?\s*(.+?)\s*$", body, re.M)
    return m.group(1).strip() if m else ""


#: The header fields a field block may end at.
_FIELD_KEYS = ("Id", "Status", "Date", "Jobs", "Code", "Motivation", "Recipe",
               "Facts", "Conclusion", "Refs")
_FIELD_START = re.compile(r"^-\s+\*\*(?:" + "|".join(_FIELD_KEYS) + r"):\*\*", re.M)


def field_block(body: str, key: str) -> str:
    """The WHOLE of a field — its first line and every continuation line under it.

    :func:`field` deliberately reads one line, which is right for `Id:` or `Code:` and
    blind for `Facts:` and `Conclusion:`, whose content is mostly continuation. A check
    written on `field()` for those two silently passes anything below line one, which is
    exactly where the defects it looks for live.
    """
    m = re.search(rf"^-\s+\*\*{key}:\*\*", body, re.M)
    if not m:
        return ""
    nxt = _FIELD_START.search(body, m.end())
    return body[m.end():nxt.start() if nxt else len(body)]


def slugify(heading: str) -> str:
    """VS Code/GitHub-style anchor slug of a heading — lowercase, punctuation
    dropped, spaces to dashes. Used to validate `page.md#entry-...` fragments."""
    s = re.sub(r"[^\w\s-]", "", heading.lower())
    return re.sub(r"\s+", "-", s.strip())


# --------------------------------------------------------------------------
# M1 — one record language, where the project declares it.
# --------------------------------------------------------------------------

def _record_language() -> str | None:
    """The project's `record_language` from `.claude/framework.json`, or None.

    Which language a record is written in is the project's policy, not the
    framework's. It stays available because a mixed-language record is a real
    hazard (a reader who cannot read half of it), so a project that wants one
    language declares it and gets the check.
    """
    try:
        cfg = json.loads((ROOT / ".claude" / "framework.json").read_text())
        return cfg.get("record_language")
    except Exception:
        return None


def cjk_errors(text: str) -> list[str]:
    if _record_language() != "en":
        return []
    lines = [i for i, l in enumerate(text.splitlines(), 1) if CJK_RE.search(l)]
    if not lines:
        return []
    more = f" (+{len(lines) - 5} more)" if len(lines) > 5 else ""
    return [f"M1 non-English (CJK) text on line(s) {lines[:5]}{more} — "
            f"this project declares `record_language: en`"]


# --------------------------------------------------------------------------
# P3/P4 — figures render, carry a caption, embedded once.
# --------------------------------------------------------------------------

def figures_errors(path: Path, text: str) -> list[str]:
    """P4 — a figure carries a caption, and is embedded once.

    This check used to place figures too: derive which entries own a plot and
    demand a location. On a real sweep page that produced a caption naming 81
    entries — a rule whose output nobody would write by hand has stopped
    serving the reader. What the record needs is that the figure renders (P3)
    and says what it shows; where it sits is the writer's judgement.
    """
    errs: list[str] = []
    seen: dict[str, int] = {}
    for mm in re.finditer(r"^[ \t]*!\[([^\]]*)\]\(([^)]+)\)[ \t]*\n?([^\n]*)", text, re.M):
        alt, rel, nextline = mm.group(1), mm.group(2), mm.group(3)
        name = Path(rel).name
        # The caption is the italic line under the embed, or the alt text when
        # the embed carries it there — either is self-contained prose, and
        # demanding one spelling buys nothing.
        caption = nextline.strip() if nextline.strip().startswith("*") else alt
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            errs.append(f"P4 figure `{name}` is embedded {seen[name]} times on this page "
                        f"— embed it once and link it from anywhere else")
            continue
        if not caption:
            errs.append(f"P4 figure `{name}` has no caption — give the embed alt text or "
                        f"a following italic line: axes, units, what each series is, so "
                        f"the caption replaces the paragraph explaining it")
    return errs


# --------------------------------------------------------------------------
# Job-id and process plumbing. These are not format rules — they encode Slurm
# squeue parsing, bare-host PID liveness and job-id range expansion. Do not
# reinvent them.
# --------------------------------------------------------------------------

#: An artifact hyperlink in an entry narrative: a repo-relative path to the script,
#: log or cell it used. Relative (not `file://`) so editors, GitHub and Obsidian all
#: resolve it — a `file://` URL renders as nothing and cannot be clicked through.
FILELINK_RE = re.compile(r"\((\.\./[^)]+|\./[^)]+)\)")
URI_RE = re.compile(r"file:///[^\s)`\]]+")
RANGE_RE = re.compile(r"(\d{5,})\s*[–—\-]\s*(\d{2,6})")
# Absolute file:// URIs AND repo-relative links — the record contract
# mandates the latter, so a file://-only reader is blind to every entry
# the launcher recorded.
#: A host-qualified job id — `3635545@H200`. Nothing else in a record takes this
#: shape, which is what makes scanning prose for it safe.
BODY_JOBID_RE = re.compile(r"\b(\d{3,}@[A-Za-z][\w.-]*)\b")
#: `record_submit`'s own appended line. It is written ONLY by a launch, so an id here
#: that is absent from the field means the field write is the half that failed.
SUBMIT_LINE_RE = re.compile(r"^\s*Job (\S+) — \[log\]\(", re.M)
LOGURI_RE = re.compile(r"(?:file://)?((?:/|\.\./|[A-Za-z0-9_./-]*/)[^\s)`\]]*\.(?:log|out))")
PLACEHOLDER_RE = re.compile(
    r"^\s*[*_]*(TBD|TODO|pending|to[- ]?be[- ]?determined|running|in progress|n/?a|\?+|\.\.\.|—|-)[*_.\s]*$",
    re.I)


def expand_braces(s: str) -> list[str]:
    """Textually expand a single `{a..b}` numeric range in s (b zero-/prefix-padded
    to a's width). 'x641962{17..24}.out' -> ['x64196217.out', ... 'x64196224.out'].
    No brace -> [s]. Handles one range (loops for nested)."""
    m = re.search(r"\{(\d+)\.\.(\d+)\}", s)
    if not m:
        return [s]
    a, b = m.group(1), m.group(2)
    if len(b) < len(a):
        b = a[: len(a) - len(b)] + b
    lo, hi = int(a), int(b)
    if not (lo <= hi <= lo + 256):
        return [s]
    out = []
    for x in range(lo, hi + 1):
        out.extend(expand_braces(s[: m.start()] + str(x) + s[m.end():]))
    return out


def expand_jobids(cell: str) -> list[str]:
    """'64108451–54' / '64111778-81' / '64108446' -> expanded ids (prefix-expanded
    ranges ok): '64108451–54' -> 451,452,453,454.

    An id or range may carry an `@<host>` tag ('63902601@t6') naming which
    remote ran it. The tag is documentation for the reader — it is stripped
    here, so queue matching (J2/J3/J4) stays host-agnostic: the fixer's queue
    snapshot already merges every declared host's jobs into one id set."""
    out = []
    for part in re.split(r"[,\s]+", cell.strip()):
        part = re.sub(r"@[\w.-]+$", "", part)
        m = re.match(r"^(\d+)[–—\-–](\d+)$", part)
        if m:
            a, b = m.group(1), m.group(2)
            if len(b) < len(a):
                b = a[: len(a) - len(b)] + b
            lo, hi = int(a), int(b)
            if lo <= hi <= lo + 64:
                out.extend(str(x) for x in range(lo, hi + 1))
            else:
                out.append(a)
        elif part.isdigit():
            out.append(part)
    return out


_QUEUE_CACHE: tuple[bool, set[str]] | None = None   # (squeue_ok, ids)

REMOTE_SNAPSHOT_FRESH_S = 1800   # 30 min — 3 fixer cycles; older reads as unusable


def _remote_queue() -> tuple[bool, set[str]] | None:
    """(fresh, ids) when the project declares a remote HPC, else None.

    The fixer refreshes .fixer/remote_queue every cycle over ssh — one file
    covering EVERY declared host (multi-remote: rows are `jobid STATE @host`;
    the leading id is all that is read here). A STALE snapshot makes the whole
    queue read as unusable (None upstream): inventing "job left the queue"
    (J3) from old data is worse than falling back to the log-header check."""
    conf = ""
    for f in (ROOT / ".claude" / "hpc.env", ROOT / ".claude" / "hpc.local.env"):
        if f.exists():
            conf += f.read_text(encoding="utf-8")
    if not re.search(r"^\s*REMOTE_HOST=", conf, re.M):
        return None
    snap = ROOT / ".fixer" / "remote_queue"
    if snap.exists() and time.time() - snap.stat().st_mtime < REMOTE_SNAPSHOT_FRESH_S:
        return True, set(re.findall(r"^(\d+)\b", snap.read_text(encoding="utf-8"), re.M))
    return False, set()


def live_bare_job_ids() -> set[str]:
    """Job ids alive on a bare host — the no-Slurm 'queue'.

    Read back from the launcher's OWN records (:func:`bare_log_live_job`),
    which is what makes this a queue rather than a guess: hpc-submit Case B is
    the only way a job enters it, exactly as ``sbatch`` is the only way in on
    Slurm. A run that never went through the launcher has no header and never
    enters the queue: J2 means "the launcher issued this id and nobody
    recorded it", a claim about the record, not about the box."""
    return {j for log in sorted(EXPERIMENTS_DIR.rglob("logs/*.log"))
            if (j := bare_log_live_job(log))}


def _pid_elapsed_minutes(pid: str) -> float | None:
    """Minutes since PID `pid` started, from ``/proc/<pid>/stat`` field 22
    (``starttime``, clock ticks since boot) and ``/proc/uptime`` — no subprocess.

    ``None`` if elapsed time can't be determined (no such PID, or `pid` is not
    a local PID at all — a Slurm job id on a squeue-backed queue). Callers that
    can't determine age should treat it as unknown, not as fresh."""
    if not Path("/proc").is_dir():  # macOS: parse `ps -o etime=` ([[dd-]hh:]mm:ss)
        import subprocess
        r = subprocess.run(["ps", "-o", "etime=", "-p", pid],
                           capture_output=True, text=True)
        s = r.stdout.strip()
        if r.returncode != 0 or not s:
            return None
        days, _, clock = s.rpartition("-")
        try:
            secs = int(days) * 86400 if days else 0
            mult = 1
            for part in reversed(clock.split(":")):
                secs += int(part) * mult
                mult *= 60
        except ValueError:
            return None
        return secs / 60.0
    try:
        stat = (Path("/proc") / pid / "stat").read_text(encoding="ascii", errors="replace")
        uptime = float(Path("/proc/uptime").read_text().split()[0])
    except (OSError, ValueError):
        return None
    # comm (field 2) is parenthesized and may itself contain spaces/parens; skip
    # past its closing ')' before splitting the remaining whitespace-delimited
    # fields (index 0 below = field 3, so field 22 = index 19).
    fields = stat[stat.rfind(")") + 2:].split()
    if len(fields) < 20:
        return None
    try:
        starttime_ticks = int(fields[19])
    except ValueError:
        return None
    hz = os.sysconf("SC_CLK_TCK")
    return (uptime - starttime_ticks / hz) / 60.0


def queued_job_ids() -> set[str] | None:
    """All of $USER's job ids currently 'in the queue' (cached).

    Slurm: squeue. Bare host (no squeue): the launcher's live uv PIDs — see
    :func:`live_bare_job_ids`. ``None`` only when squeue exists but is unusable."""
    global _QUEUE_CACHE
    if _QUEUE_CACHE is None:
        import getpass
        import shutil
        import subprocess
        if not shutil.which("squeue"):
            _QUEUE_CACHE = (True, live_bare_job_ids())
        else:
            try:
                r = subprocess.run(
                    ["squeue", "-u", getpass.getuser(), "-h", "-o", "%i"],
                    capture_output=True, text=True, timeout=10)
                _ids = set()
                for l in r.stdout.splitlines():
                    s = l.strip()
                    if not s:
                        continue
                    _ids.add(s)
                    if "_" in s:               # array task 64414777_3 -> also base 64414777
                        _ids.add(s.split("_", 1)[0])
                _QUEUE_CACHE = (True, _ids)
            except Exception:
                _QUEUE_CACHE = (False, set())
    ok, ids = _QUEUE_CACHE
    remote = _remote_queue()
    if remote is not None:
        r_ok, r_ids = remote
        ok, ids = ok and r_ok, ids | r_ids
    return ids if ok else None


def queue_phrases() -> tuple[str, str]:
    """(gone, still-live) wording for the J3/J4 messages, named after THIS host's
    queue. A bare host has no squeue — liveness there is the launcher's uv PID —
    and saying "squeue" sends the reader hunting a Slurm failure that cannot
    exist on the box they are on."""
    import shutil
    if shutil.which("squeue"):
        return "are in squeue", "are live in squeue"
    return ("are still running (launcher uv PID gone)",
            "are still running (launcher uv PID alive)")


def _pid_alive(pid: str) -> bool:
    """True if PID `pid` is a live process (ps -p). On any error assume alive —
    conservative: never let a probe failure fake a 'finished' run into a J3."""
    import subprocess
    try:
        return subprocess.run(["ps", "-p", pid], capture_output=True,
                              timeout=5).returncode == 0
    except Exception:
        return True


def _log_head(path: Path) -> list[str]:
    """The bare-launcher header block — a log's first lines; `[]` if unreadable."""
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[:30]
    except OSError:
        return []


def log_script(path: Path) -> str | None:
    """The computation a log records, read off its `# Command:` header line."""
    cmd = next((l for l in _log_head(path) if l.startswith("# Command:")), None)
    m = re.search(r"([\w./-]+\.py)", cmd) if cmd else None
    return Path(m.group(1)).name if m else None


#: The repo-state header line: `# <project>: <sha> (clean|dirty)`. Pinned libs
#: (`# quantax: … (pinned)`) deliberately do not match.
REPO_STATE_RE = re.compile(r"^# [\w.-]+: ([0-9a-f]{7,40}) \((clean|dirty)\)")


def log_repo_state(path: Path) -> tuple[str, bool] | None:
    """(sha, dirty) of the repo a log's job ran from, or None (no header)."""
    for line in _log_head(path):
        m = REPO_STATE_RE.match(line)
        if m:
            return m.group(1), m.group(2) == "dirty"
    return None


def entry_script_errors(entries: dict[str, str], page: Path) -> list[str]:
    """E11 — one entry runs ONE computation script.

    An entry is a set of order-independent computations that call the same code,
    and "same code" is the one clause of that definition a machine can settle:
    every job the entry links wrote a log, and every log header names what ran.
    Two scripts in one entry means two probes were folded together. A second
    branch here once flagged an entry whose logs spanned two SHAs of the SAME
    script — removed: it fired twice on live pages and was wrong both times."""
    errs = []
    for name, body in entries.items():
        scripts: dict[str, list] = {}
        for rel in LOGURI_RE.findall(body):
            lp = (page.parent / rel).resolve()
            s = log_script(lp)
            if s:
                scripts.setdefault(s, [])
        if len(scripts) > 1:
            errs.append(f"E11 entry '{name}' links logs from {len(scripts)} different "
                        f"computation scripts ({', '.join(sorted(scripts))}) — one entry "
                        f"is one set of same-code computations; give each script its "
                        f"own entry")
    return errs


def log_run_state(path: Path) -> str | None:
    """Read a bare-launcher log header -> 'running' | 'done' | None (unknown).

    `launch_bare_gpu.sh` writes `# Exit code: running` (flipped to a number when
    the job ends) plus `# PID uv:` / `# PID python:`. Exit-code is authoritative
    for 'done' (immune to PID recycling); if it is still `running` we corroborate
    via PID liveness so a hard-killed job (exit code never flipped) is still
    caught. A log without a `# Exit code:` header (Slurm / hand-written) -> None."""
    head = _log_head(path)
    ec = next((l for l in head if l.startswith("# Exit code:")), None)
    if ec is None:
        return None                              # not a bare-launcher log
    if ec.split(":", 1)[1].strip() != "running":
        return "done"                            # exit code flipped -> authoritative
    pids = [m.group(1) for l in head
            if (m := re.match(r"# PID (?:uv|python):\s*(\d+)", l))]
    if pids and not any(_pid_alive(p) for p in pids):
        return "done"                            # killed before flipping exit code
    return "running"


#: How far a live PID's start time may sit from its log's `# Timestamp:` before
#: we call it a RECYCLED pid rather than this job. The launcher writes the header,
#: launches, then patches the PIDs in ~3 s later, so the true gap is seconds.
PID_REUSE_TOLERANCE_S = 300


def bare_log_live_job(path: Path) -> str | None:
    """The queue entry a bare-launcher log represents: its `# PID wrapper:` job
    id while the run is live, else ``None``.

    `# PID wrapper:` is read (falling back to `# PID uv:` for logs older than
    0.10.2) — that is the id hpc-submit Case B records in the entry's
    `- **Jobs:**` field, so queue and record speak the same language."""
    if log_run_state(path) != "running":
        return None
    head = _log_head(path)
    uv = next((m.group(1) for l in head
               if (m := re.match(r"# PID wrapper:\s*(\d+)", l))), None)
    if uv is None:   # logs older than 0.10.2 recorded the uv PID as the job id
        uv = next((m.group(1) for l in head
                   if (m := re.match(r"# PID uv:\s*(\d+)", l))), None)
    if uv is None or not _pid_alive(uv):
        return None                              # `unknown` pid, or already gone
    elapsed = _pid_elapsed_minutes(uv)
    stamp = next((l.split(":", 1)[1].strip() for l in head
                  if l.startswith("# Timestamp:")), None)
    if elapsed is None or not stamp:
        return uv                                # can't corroborate -> trust the header
    try:
        launched_s = time.time() - datetime.fromisoformat(stamp).timestamp()
    except ValueError:
        return uv
    if abs(elapsed * 60 - launched_s) > PID_REUSE_TOLERANCE_S:
        return None                              # recycled pid, not this job
    return uv


#: A launcher stamps its own id into the header — `# PID wrapper:` on a bare host,
#: `# job_id:` under Slurm. A FOREGROUND run (the <30 min exemption) writes no header
#: at all, so it has no id to record and must not be asked for one. This line is the
#: whole difference between "you forgot the id" and "there was never an id".
LAUNCHER_HEADER_RE = re.compile(r"^# (?:PID wrapper|job_id):", re.M)


def log_was_launched(path: Path) -> bool | None:
    """True if this log's header names a launcher job, False if it plainly does not,
    None if the file cannot be read — a remote log not yet pulled, where staying
    silent is the only honest answer."""
    try:
        with path.open(errors="replace") as fh:
            head = "".join(next(fh, "") for _ in range(40))
    except OSError:
        return None
    return bool(LAUNCHER_HEADER_RE.search(head))


def resolve_link(s: str, page: Path | None) -> Path:
    """A repo-relative artifact link resolved against its page."""
    q = Path(s)
    if q.is_absolute() or page is None:
        return q
    cand = (page.parent / q).resolve()
    return cand if cand.exists() else q


#: `# Exit code: <n>`. The bare launcher writes it in the header and patches it
#: when the job ends; the Slurm templates append it as the LAST line.
EXIT_CODE_RE = re.compile(r"^# Exit code:\s*(\S+)", re.M)
#: the job id a log belongs to, from its header
LOG_JOB_ID_RE = re.compile(r"^# (?:PID wrapper|job_id|PID uv):\s*(\d+)", re.M)
#: ...or from Slurm's `-%j.out` name. `.out` only: a launcher's `.log` is named by
#: its timestamp, whose trailing digits would read as a job id.
SLURM_LOG_NAME_RE = re.compile(r"-(\d+)\.out$")


def _head_text(path: Path, size: int = 4096) -> str:
    try:
        with path.open("rb") as fh:
            return fh.read(size).decode("utf-8", errors="replace")
    except OSError:
        return ""


def log_exit_code(path: Path) -> str | None:
    """How a job's log says it ended: the exit code as text, `running` while
    the launcher has not flipped it, or None when the log records none — it is
    unreadable, or the job was killed before the line was written. Head AND
    tail are read, because the launcher writes the line at the top and the
    Slurm templates at the bottom; the last occurrence wins."""
    try:
        size = path.stat().st_size
        with path.open("rb") as fh:
            chunk = fh.read(8192)
            if size > 16384:
                fh.seek(size - 8192)
            chunk += b"\n" + fh.read()
    except OSError:
        return None
    codes = EXIT_CODE_RE.findall(chunk.decode("utf-8", errors="replace"))
    return codes[-1] if codes else None


def _log_job_ids(path: Path) -> set[str]:
    ids = set(LOG_JOB_ID_RE.findall(_head_text(path)))
    m = SLURM_LOG_NAME_RE.search(path.name)
    if m:
        ids.add(m.group(1))
    return ids


_JOB_LOG_INDEX: dict[str, Path] | None = None


def job_log_index() -> dict[str, Path]:
    """Job id -> its log, across every declared experiment root (cached).

    Built only when a J3 has to say how a job ended, never on a clean lint.
    It is how a remote job's log is found once `remote.sh pull` has brought
    it back: the entry's `Jobs:` line names the id, and the log's own name or
    header names it too."""
    global _JOB_LOG_INDEX
    if _JOB_LOG_INDEX is None:
        index: dict[str, Path] = {}
        for root in experiment_roots():
            if not root.is_dir():
                continue
            for log in sorted(root.rglob("logs/*")):
                if log.suffix in (".log", ".out") and log.is_file():
                    for jid in _log_job_ids(log):
                        index.setdefault(jid, log)
        _JOB_LOG_INDEX = index
    return _JOB_LOG_INDEX


def entry_job_hosts(body: str) -> dict[str, str]:
    """id -> the `@host` its `Jobs:` cell tags it with; untagged ids are absent."""
    hosts: dict[str, str] = {}
    for part in re.split(r"[,\s]+", field(body, "Jobs").strip()):
        m = re.search(r"@([\w.-]+)$", part)
        if m:
            for jid in expand_jobids(part):
                hosts[jid] = m.group(1)
    return hosts


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path)


def j3_where(ids: list[str], hosts: dict[str, str]) -> str:
    """Where J3 looked, named after the host each job ran on — never this
    machine's queue for a job that ran on a cluster. The old wording said
    "launcher uv PID gone" for every job on a bare host, including Slurm jobs
    on a remote, which sent the reader looking for a local process that never
    existed."""
    import shutil
    n = len(ids)
    first = ids[0] + (f"@{hosts[ids[0]]}" if ids[0] in hosts else "")
    one, many = (f"its job {first}", f"none of its {n} jobs ({first}..)")
    tags = {hosts.get(j) for j in ids}
    if None not in tags and len(tags) == 1:
        host = tags.pop()
        return (f"{one} is no longer queued on {host}" if n == 1
                else f"{many} is still queued on {host}")
    if _remote_queue() is not None:
        return (f"{one} is live neither here nor in the remote queue snapshot" if n == 1
                else f"{many} is live here or in the remote queue snapshot")
    if shutil.which("squeue"):
        return f"{one} is no longer in squeue" if n == 1 else f"{many} is in squeue"
    return (f"{one} is no longer running here (launcher PID gone)" if n == 1
            else f"{many} is still running here (launcher PIDs gone)")


def j3_outcome(body: str, page: Path | None, ids: list[str]) -> str:
    """How the entry's jobs ended, read off their logs, and the move that follows.

    A J3 used to end "finished? write the conclusion" whatever the logs said,
    so a job that crashed with exit 1 was reported as ready to analyze. The
    exit code was on disk the whole time. Failure now leads: a failed job
    needs its log read and, for a code fault, research-note:correct — not a
    conclusion written over it."""
    linked: dict[str, Path] = {}
    # Only a link whose file is ON DISK says anything about how a job ended. A
    # remote job's log is linked at submission and arrives with the next pull,
    # so an absent link target is "not back yet" — reading it as "ended without
    # an exit code" would call nine un-pulled logs nine killed jobs.
    links = [lp for rel in LOGURI_RE.findall(body)
             if (lp := resolve_link(rel, page)).is_file()]
    for lp in links:
        for jid in _log_job_ids(lp):
            linked.setdefault(jid, lp)
    if len(ids) == 1 and ids[0] not in linked and len(links) == 1:
        linked[ids[0]] = links[0]                    # one job, one linked log
    jobs: list[tuple[str, Path | None]]
    if ids:
        if any(j not in linked for j in ids):
            index = job_log_index()
            linked.update({j: index[j] for j in ids if j not in linked and j in index})
        jobs = [(j, linked.get(j)) for j in ids]
    else:                                            # no ids: the linked logs are the jobs
        jobs = [(lp.name, lp) for lp in links]

    failed, killed, ok, missing = [], [], [], []
    for label, lp in jobs:
        if lp is None:
            missing.append(label)
            continue
        code = log_exit_code(lp)
        if code == "0":
            ok.append(label)
        elif code in (None, "running"):
            killed.append((label, lp))
        else:
            failed.append((label, code, lp))

    n = len(jobs)
    remote = _remote_queue() is not None
    parts = []
    if failed:
        label, code, lp = failed[0]
        more = f", +{len(failed) - 1} more" if len(failed) > 1 else ""
        parts.append(f"{'it' if n == 1 else str(len(failed))} FAILED "
                     f"({label} exit {code}: {_rel(lp)}{more})")
    if killed:
        label, lp = killed[0]
        parts.append(f"{'it' if n == 1 else str(len(killed))} ended with no exit "
                     f"code recorded — killed? ({label}: {_rel(lp)})")
    if ok:
        parts.append("it exited 0" if n == 1 else "both exited 0" if len(ok) == n == 2 else
                     f"all {n} exited 0" if len(ok) == n else f"{len(ok)} exited 0")
    if missing:
        where = "not pulled back yet" if remote else "not found"
        k = len(missing)
        parts.append(f"its log is {where}" if n == 1 else
                     f"{k} log{'s are' if k > 1 else ' is'} {where}")
    if failed or killed:
        action = ("read the log before concluding; a code fault goes through "
                  "research-note:correct, not a conclusion")
    elif missing:
        action = ("bring the missing logs back (remote.sh pull) before concluding"
                  if remote else "find how they ended before concluding")
    else:
        action = "analyze: write the conclusion and flip Status"
    return "; ".join(parts) + ". " + action[0].upper() + action[1:]


def entry_logs_state(body: str, page: Path | None = None) -> str | None:
    """Aggregate an entry's linked `.log`/`.out` artifacts into one run state:
    'running' if any linked log is still running, 'done' if all finished, None
    if none can be read. Links are repo-relative by contract, i.e. relative to
    the page."""
    def _resolve(s: str) -> Path:
        q = Path(s)
        if q.is_absolute() or page is None:
            return q
        cand = (page.parent / q).resolve()
        return cand if cand.exists() else q

    states = [s for p in LOGURI_RE.findall(body)
              if (s := log_run_state(_resolve(p))) is not None]
    if not states:
        return None
    return "running" if "running" in states else "done"


# --------------------------------------------------------------------------
# Entry format (E1-E10) — the §5 field contract.
# --------------------------------------------------------------------------

LEGAL_ENTRY_STATUS = {"open", "running", "analyzed", "closed"}
CONCLUDED = {"analyzed", "closed"}
ID_RE = re.compile(r"^\d{2}\.\d{3}$")
DATE_LINE_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
CODE_RE = re.compile(r"[\w.-]+@[0-9a-f]{7,40}")
#: `record_submit` appends this line; it is evidence, and evidence lives in the Facts
#: SENTENCE (`evidence <links>`), never as a stanza of its own. E12 catches it only when it
#: lands outside every field — indented into `Facts:` it reads as legal and is not.
JOB_STANZA_RE = re.compile(r"^[ \t]*(?:Evidence:\s*)?Job\s+\S+\s+—\s+\[log\]\(", re.M)
#: A markdown link inside `Conclusion:`. The Conclusion is the interpretation; the artifacts
#: it rests on belong to `Facts:` and the entries it borrows from to `Refs:`.
CONCL_LINK_RE = re.compile(r"\[[^\]]*\]\([^)]+\)")
VERDICT_RE = re.compile(r"\b(answers|partly answers|does not answer) the motivation")
ENTRY_RE = re.compile(r"^#{2,4}\s+Entry:\s*(.+?)\s*$", re.M)
JOBS_SEC_RE = re.compile(r"^## Jobs\n(.*?)(?=^#{1,6} |\Z)", re.S | re.M)
#: E10 — a header field written bare instead of as `- **Key:** value`.
BARE_FIELD_RE = re.compile(
    r"^(Id|Status|Date|Jobs|Code|Motivation|Recipe|Facts|Conclusion|Refs|"
    r"Findings|Result|Env):", re.M)
#: E12 — a line that OPENS a field. Retired spellings count: E10 already names
#: them, and treating them as field openers keeps E12 from reporting the same
#: line twice under a second code.
FIELD_OPEN_RE = re.compile(
    r"^-\s+\*\*(Id|Status|Date|Jobs|Code|Motivation|Recipe|Facts|Conclusion|"
    r"Refs|Findings|Result|Env):\*\*|"
    r"^(Id|Status|Date|Jobs|Code|Motivation|Recipe|Facts|Conclusion|Refs|"
    r"Findings|Result|Env):")
RETIRED_FIELDS = {
    "Findings": "split into `- **Facts:**` (what happened) and "
                "`- **Conclusion:**` (what it means) in v3",
    "Result": "folded into the verdict in v2.1",
    "Env": "retired in v2.2 — the instance belongs in the page's `task:` line",
}
RETIRED_STATUS = {
    "blocked": "retired in v3 — a run that concluded nothing writes that "
               "verdict and goes to `analyzed`",
    "done-pending-analysis": "retired in v3 — analysis happens inside "
                             "`running`; a handover's numbers wait as `running`",
}


def entry_job_ids(body: str) -> list[str]:
    """The entry's own `- **Jobs:** id, id-range` ids, ranges expanded."""
    return expand_jobids(field(body, "Jobs"))


def _refs_block(body: str) -> str:
    m = re.search(r"^-\s+\*\*Refs:\*\*\s*$(.*?)(?=^-\s+\*\*|\Z)", body, re.M | re.S)
    if m:
        return m.group(1)
    m = re.search(r"^(?:-\s+\*\*)?Refs:(?:\*\*)?(.*)", body, re.M | re.S)
    return m.group(1) if m else ""


def loose_lines(body: str) -> list[tuple[int, str]]:
    """E12 — lines of an entry that belong to no field.

    An entry is its fields and nothing else: a page that puts the table, the
    figure or a `Job N — [log]` line between the fields reads as an entry whose
    Facts are missing, because a reader (and every other check here) finds
    content only under the key that owns it. A line belongs to a field when it
    opens one (`- **Key:** …`) or continues the open one (indented); blank
    lines are neutral. Anything else is loose, and the fix is to move it under
    the field whose business it is — measurements and evidence links under
    `Facts:`, the reading under `Conclusion:`.
    """
    out: list[tuple[int, str]] = []
    open_field = False
    for n, ln in enumerate(body.splitlines(), 1):
        if not ln.strip():
            continue
        if FIELD_OPEN_RE.match(ln):
            open_field = True
            continue
        if ln[0] in " \t" and open_field:
            continue
        out.append((n, ln))
    return out


def loose_errors(name: str, body: str) -> list[str]:
    """E12 rendered as findings — one per loose line, capped so a page that
    predates the rule reports its shape rather than a wall of text."""
    loose = loose_lines(body)
    errs = [f"E12 entry '{name}' line {n} is outside every field — move it "
            f"under the field whose business it is (`Facts:` for a table, a "
            f"figure or an evidence link): {ln.strip()[:60]}"
            for n, ln in loose[:6]]
    if len(loose) > 6:
        errs.append(f"E12 entry '{name}' has {len(loose) - 6} further line(s) "
                    f"outside every field")
    return errs


def entry_errors(name: str, body: str) -> list[str]:
    """The per-entry field checks, shared by task pages and node.md.

    A `closed` entry is held to the structural checks only (Id, Status, Date,
    one spelling, and E12 — every line inside a field): the user's ✓ accepted
    it as it stood, and a schema written later does not reopen an accepted
    record — the form checks (E4-E9), which judge what a field SAYS, bind while
    an entry is still the agent's to write, which every entry is at `analyzed`,
    the state the ✓ is given from. E12 judges only WHERE a line sits, so it
    binds like E10: an accepted record is still readable only if its content is
    under the keys that own it."""
    errs: list[str] = []

    eid = field(body, "Id")
    if not eid:
        errs.append(f"E1 entry '{name}' missing `Id:` — `<nn>.<mmm>`, node number "
                    f"then per-node sequence, assigned at creation")
    elif not ID_RE.match(eid):
        errs.append(f"E1 entry '{name}' `Id: {eid}` is not `<nn>.<mmm>` "
                    f"(both zero-padded)")

    status = field(body, "Status")
    if status in RETIRED_STATUS:
        errs.append(f"E2 entry '{name}' `Status: {status}` — {RETIRED_STATUS[status]}")
    elif status not in LEGAL_ENTRY_STATUS:
        errs.append(f"E2 entry '{name}' `Status: {status or '(missing)'}` not in "
                    f"{sorted(LEGAL_ENTRY_STATUS)}")

    date = field(body, "Date")
    if not date:
        errs.append(f"E3 entry '{name}' missing `Date:` — creation time, "
                    f"`YYYY-MM-DD HH:MM`")
    elif not DATE_LINE_RE.match(date):
        errs.append(f"E3 entry '{name}' `Date: {date}` is not `YYYY-MM-DD HH:MM`")

    # E13-E15 are placement, not judgment: WHERE evidence and interpretation sit is the
    # field contract, the same business as E10/E12, so they hold for a closed entry too —
    # the `closed` return below exempts only the checks that would re-open the reading.
    facts_body = field_block(body, "Facts")
    if n := len(JOB_STANZA_RE.findall(facts_body)):
        errs.append(f"E13 entry '{name}' Facts holds {n} standalone `Job <id> — [log](...)` "
                    f"line(s) — that is `record_submit`'s append, not a field: fold each log "
                    f"into the sentence's `evidence <links>` clause, which is where the "
                    f"template puts evidence and where a reader looks for it")
    concl_body = field_block(body, "Conclusion")
    if concl_body.strip():
        if links := CONCL_LINK_RE.findall(concl_body):
            errs.append(f"E14 entry '{name}' Conclusion carries {len(links)} link(s), the "
                        f"first `{links[0][:48]}` — the Conclusion is the interpretation: an "
                        f"artifact link belongs in `Facts:` and a borrowed entry in `Refs:` "
                        f"as a `[n]`")
        if (vm := VERDICT_RE.search(concl_body)) and (tail := concl_body[vm.end():].lstrip(" .:—-").strip()):
            errs.append(f"E15 entry '{name}' Conclusion runs on past its verdict by "
                        f"{len(tail.split())} word(s) — `{tail[:48]}` — the sentence ENDS at "
                        f"the verdict; fold what follows into the `because` it belongs to, or "
                        f"move it to `Facts:` if it is a measurement and its own entry if "
                        f"answering it needs a run")

    if status == "closed":
        for m in BARE_FIELD_RE.finditer(body):
            errs.append(f"E10 entry '{name}' field `{m.group(1)}:` is bare — write "
                        f"it as `- **{m.group(1)}:** …`")
        errs += loose_errors(name, body)
        return errs

    errs += loose_errors(name, body)

    code = field(body, "Code")
    if not code:
        errs.append(f"E4 entry '{name}' missing `Code:` — `<repo>@<sha>` per repo, "
                    f"the newest commit at submission touching src/, the impl and "
                    f"the run script")
    elif not CODE_RE.search(code):
        errs.append(f"E4 entry '{name}' `Code: {code}` names no `<repo>@<sha>`")

    mot = field(body, "Motivation")
    # the field wraps over several lines; the form test reads the whole block
    mb = re.search(r"^(?:-\s+\*\*)?Motivation:(?:\*\*)?(.*?)(?=^-\s+\*\*|\Z)",
                   body, re.M | re.S)
    mot_full = " ".join(mb.group(1).split()) if mb else mot
    if not mot:
        errs.append(f"E5 entry '{name}' missing `Motivation:` — `<source> found "
                    f"<the fact, quoted>; <the question, one sentence>.`")
    elif " found " not in f" {mot_full} " and not mot_full.startswith("No entry"):
        errs.append(f"E5 entry '{name}' Motivation is not in its form — `<source> "
                    f"found <the fact, quoted>; <the question>.` (an absence reads "
                    f"`No entry … has …; <the question>.`)")
    # E5 — the Motivation ends in the QUESTION this run answers. Without it the
    # field states a rationale for running, which cannot decide what belongs in
    # the Conclusion: measured across a live record, every entry whose
    # Motivation asked nothing had grown a Conclusion of four or five parallel
    # claims, and every entry that asked something had exactly one.
    if mot and not mot_full.rstrip().endswith("?"):
        errs.append(f"E5 entry '{name}' Motivation ends in no question — the last "
                    f"clause is the one question THIS run's Recipe answers with a "
                    f"number, and it is what the Conclusion is judged against; a "
                    f"reason for running is not a question")

    recipe = field(body, "Recipe")
    if recipe and not (recipe.startswith("{") and recipe.endswith("}")
                       and ":" in recipe):
        errs.append(f"E6 entry '{name}' `Recipe:` is not a knob map — write "
                    f"`{{key: value, ...}}` (procedure prose belongs in the "
                    f"narrative)")
    if entry_job_ids(body) and not recipe:
        errs.append(f"E6 entry '{name}' has jobs but no `Recipe:` — every run's "
                    f"knob assignment is recorded on the entry that used it")

    # E10 — one schema, one spelling; no retired field.
    for m in BARE_FIELD_RE.finditer(body):
        k = m.group(1)
        errs.append(f"E10 entry '{name}' field `{k}:` is bare — write it as "
                    f"`- **{k}:** …`")
    for k, why in RETIRED_FIELDS.items():
        if field(body, k):
            errs.append(f"E10 entry '{name}' carries the retired field `{k}:` — {why}")

    if status in CONCLUDED:
        facts = field(body, "Facts")
        has_table = bool(re.search(r"^\s*\|.*\|\s*$", body, re.M))
        if not facts:
            errs.append(f"E7 entry '{name}' is `{status}` without `Facts:` — `We ran "
                        f"<…> [script]; evidence <links>.` then the table")
        else:
            if not has_table:
                errs.append(f"E7 entry '{name}' `Facts:` has no table — the table is "
                            f"required, at the aggregation the Conclusion cites")
            if not FILELINK_RE.search(body):
                errs.append(f"E7 entry '{name}' carries no evidence link — cite the "
                            f"script and the log/data behind the numbers "
                            f"(repo-relative)")

        conc = field(body, "Conclusion")
        if not conc or PLACEHOLDER_RE.match(conc):
            errs.append(f"E9 entry '{name}' is `{status}` without a `Conclusion:` — "
                        f"`The result shows <X>, because <Y> — <verdict> the "
                        f"motivation.`")
        else:
            # The whole Conclusion may wrap over several lines; the verdict may
            # sit on any of them, so search the body from the field on.
            m = re.search(r"^(?:-\s+\*\*)?Conclusion:(?:\*\*)?", body, re.M)
            tail = body[m.start():] if m else conc
            if not VERDICT_RE.search(" ".join(tail.split())):
                errs.append(f"E9 entry '{name}' Conclusion has no verdict — end the "
                            f"sentence with `answers` / `partly answers` / `does "
                            f"not answer` the motivation")

    # E8 — a displayed number this entry did not run has a Refs row: every
    # `[n]` quote marker used in the body resolves in the Refs block.
    refs = _refs_block(body)
    defined = set(re.findall(r"`\[(\d+)\]`\s*(?:→|->)", refs))
    body_wo_refs = body.replace(refs, "")
    cited = set(re.findall(r"`\[(\d+)\]`", body_wo_refs))
    for n in sorted(cited - defined):
        errs.append(f"E8 entry '{name}' quotes `[{n}]` but `Refs:` has no `[{n}]` "
                    f"row — every displayed number this entry did not run names "
                    f"the entry that ran it")

    return errs


def id_order_errors(entries: dict[str, str]) -> list[str]:
    """E1 — ids unique on the page, and the per-node sequence follows Date."""
    errs: list[str] = []
    seen: dict[str, str] = {}
    parsed: list[tuple[str, str, str]] = []
    for name, body in entries.items():
        eid, date = field(body, "Id"), field(body, "Date")
        if eid and eid in seen:
            errs.append(f"E1 id `{eid}` is on both '{seen[eid]}' and '{name}' — "
                        f"ids are assigned once and never reused")
        seen[eid or name] = name
        if ID_RE.match(eid or "") and DATE_LINE_RE.match(date or ""):
            parsed.append((eid, date, name))
    parsed.sort()
    for (a_id, a_dt, a_nm), (b_id, b_dt, b_nm) in zip(parsed, parsed[1:]):
        if a_dt > b_dt:
            errs.append(f"E1 id `{b_id}` ('{b_nm}') is dated before `{a_id}` "
                        f"('{a_nm}') — the per-node sequence follows `Date` order")
    return errs


# --------------------------------------------------------------------------
# Lifecycle vs the queue (J1, J3, J4).
# --------------------------------------------------------------------------

def jobs_errors(text: str, entries: dict[str, str],
                page: Path | None = None) -> list[str]:
    """P5  the retired page-level `## Jobs` table is present
    J1  an entry that owns jobs carries a repo-relative artifact link
    J5  an entry that plainly RAN jobs left `Jobs:` empty
    J6  an id the Facts name — or a `Job <id> —` line anywhere — is missing
        from the `Jobs:` field (Motivation/Refs quote provenance and are exempt)

    J5/J6 are J1 read the other way, and they exist because the empty field is
    silent: `Jobs:` is the canonical id contract — the J3/J4 lint, the owner
    waiter, the board's Running tab and the fixer all read liveness from it — so
    an entry at `running` with no ids is invisible to every one of them, and a
    page full of such entries still lints green. The shape is not hypothetical:
    `record_submit` writes the id into the field AND appends a `Job N — [log]`
    line, and when that append lands outside every field it trips E12 and exits
    non-zero with the id present ONLY in the appended line. Repairing the E12 by
    indenting the stray line back under `Facts:` rescues the log link and leaves
    the field empty, which is how four entries here carried nine unrecorded job
    ids that only a hand-watched ssh session ever saw."""
    errs: list[str] = []
    if JOBS_SEC_RE.search(text):
        errs.append("P5 `## Jobs` section is RETIRED — a job belongs to its entry: "
                    "move each row's id(s) into the owning entry's "
                    "`- **Jobs:**` field and delete the section")
    for name, body in entries.items():
        ids = entry_job_ids(body)
        if ids and not FILELINK_RE.search(body):
            errs.append(f"J1 entry '{name}' has jobs but no relative artifact link")
        # Only logs whose HEADER names a launcher count. A foreground run under the
        # <30 min exemption writes a log with no header and owns no id, and asking it
        # for one is how a check earns its way into being ignored.
        logs = {q for q in LOGURI_RE.findall(body)
                if log_was_launched(resolve_link(q, page)) is True}
        if not ids:
            if field(body, "Status") == "running":
                errs.append(f"J5 entry '{name}' is `running` with an empty "
                            f"`Jobs:` — a running entry has an id by definition, and "
                            f"without it no waiter, no J3 harvest and no fixer can "
                            f"see the job; recover it from the log header's "
                            f"`# PID wrapper:` (bare host) or from the submit output")
            elif logs:
                errs.append(f"J5 entry '{name}' links {len(logs)} launcher log(s) "
                            f"but its `Jobs:` field is empty — a log under `logs/` was "
                            f"written by a launcher, so the run has an id; read it from "
                            f"that log's `# PID wrapper:` header rather than copying "
                            f"from this entry's own table, which is where a "
                            f"transcription error would already be")
        else:
            # Counting logs against ids does NOT work: an entry legitimately links the
            # reference logs of the entries it compares against, so more logs than ids is
            # normal record practice, not a gap. What IS unambiguous is an id written in
            # the body and missing from the field — either a host-qualified `<id>@<host>`,
            # a form nothing but a job id takes, or `record_submit`'s own
            # `Job <id> — [log](...)` line, which is emitted only by a launch.
            # Two scopes, learned from a second real record: the `<id>@<host>`
            # scan covers FACTS ONLY, because Motivation and Refs quote OTHER
            # entries' ids as provenance ("job `35207412@t6` measured …" names
            # the source, not this entry's run); and a host of 7-40 hex chars
            # is skipped, because `<repo>@<sha>` with a NUMERIC repo name
            # ("3450@e637566") is shaped exactly like an id@host. The Job-line
            # scan stays body-wide — only a launch of THIS entry writes one.
            # `entry_job_ids` strips the `@host` tag so queue matching stays
            # host-agnostic; strip it here too or nothing ever matches.
            def _bare(tok: str) -> str:
                return re.sub(r"@[\w.-]+$", "", tok)
            named = {_bare(m.group(1))
                     for m in BODY_JOBID_RE.finditer(field_block(body, "Facts"))
                     if not re.fullmatch(r"[0-9a-f]{7,40}",
                                         m.group(1).split("@", 1)[1])}
            named |= {_bare(m.group(1)) for m in SUBMIT_LINE_RE.finditer(body)}
            if orphans := sorted(named - set(ids)):
                errs.append(f"J6 entry '{name}' names job(s) {', '.join(orphans)} in its "
                            f"body but not in `- **Jobs:**` — the field is what every "
                            f"watcher reads, so an id that lives only in the prose is "
                            f"invisible to all of them; add it there too")
    return errs


def lifecycle_errors(text: str, entries: dict[str, str],
                     page: Path | None = None) -> list[str]:
    """Entry status against the queue, both directions.

    J3  an entry is `running` but none of its jobs are in the queue -> finished,
        unreported
    J4  the page's jobs are live in the queue but no entry is marked `running`
    The log-header fallback (driven by each entry's linked `.log` instead of
    the queue) only applies when Slurm is present but `squeue` is unusable.
    On a bare host `queued_job_ids` never returns ``None`` —
    :func:`live_bare_job_ids` reads the launcher's log headers instead."""
    errs: list[str] = []
    status = {n: field(b, "Status") for n, b in entries.items()}
    running = [n for n, s in status.items() if s == "running"]
    by_entry = {n: entry_job_ids(b) for n, b in entries.items()}
    all_ids = {i for ids in by_entry.values() for i in ids}

    queue = queued_job_ids()

    if queue is not None:
        gone, live_in = queue_phrases()
        for name in running:
            ids = by_entry[name]
            if ids and not (set(ids) & queue):
                body = entries[name]
                errs.append(f"J3 entry '{name}' is running but "
                            f"{j3_where(ids, entry_job_hosts(body))} — "
                            f"{j3_outcome(body, page, ids)}")
        if not running and all_ids & queue:
            live = sorted(all_ids & queue)
            errs.append(f"J4 jobs {live[0]}.. {live_in} but no entry is marked "
                        f"running — flip the owning entry's Status to running")

    if queue is None:
        for name, body in entries.items():
            st = status[name]
            state = entry_logs_state(body, page)
            if st == "running" and state == "done":
                errs.append(f"J3 entry '{name}' is running but its linked log(s) report "
                            f"it ended — {j3_outcome(body, page, by_entry[name])}")
            elif st and st != "running" and state == "running":
                errs.append(f"J4 entry '{name}' has a live run (linked log still running, "
                            f"PID alive) but Status is '{st}' — flip it to running")
    return errs


# --------------------------------------------------------------------------
# Pages: the task page (P1, P2, P3) and node.md (N1, V1).
# --------------------------------------------------------------------------

def link_errors(path: Path, text: str) -> list[str]:
    """P3 figures render; P2 every relative link and entry anchor resolves.

    P2 is checked only for COMMITTED artifacts — `logs/` and `data/` are
    gitignored runtime output, so their absence in a fresh clone is expected."""
    errs: list[str] = []
    for url in re.findall(r"\]\((file://[^)]*\.(?:png|svg|jpg|jpeg))\)", text):
        errs.append(f"P3 figure `{url}` uses a file:// URL — figures must be "
                    f"repo-relative so they render")
    for rel in re.findall(r"!\[[^\]]*\]\((?!https?://|file://)([^)]+)\)", text):
        if not (path.parent / rel).exists():
            errs.append(f"P3 embedded figure `{rel}` does not resolve from {path.parent}")

    # both spellings of a relative target: `../x/page.md` and the bare
    # same-directory `page.md` (a deleted sibling once dangled unseen because
    # only the ./-prefixed form was matched)
    for raw in re.findall(
            r"(?<!!)\[[^\]]*\]\((\.\.?/[^)]+|[A-Za-z0-9_][\w.-]*\.md(?:#[^)]*)?)\)",
            text):
        rel, _, frag = raw.partition("#")
        if re.search(r"/(logs|data)/", rel):
            continue
        target = path.parent / rel
        if not target.exists():
            errs.append(f"P2 link `{rel}` does not resolve from {path.parent} — "
                        f"a moved page or renamed script leaves the old path dangling")
        elif frag and rel.endswith(".md"):
            slugs = {slugify("Entry: " + n) for n in ENTRY_RE.findall(
                target.read_text(encoding="utf-8"))}
            if slugs and frag not in slugs:
                errs.append(f"P2 anchor `#{frag}` not found in {target.name} — entry "
                            f"anchors are `#entry-<slug of the name>`")
    return errs


_DEFBRANCH: dict[str, str | None] = {}
#: E16 verdict per `<repo>@<sha>`, per PROCESS. A commit's reachability cannot
#: change under one run, and the same token repeats across a node's pages — so
#: a per-page cache re-shells for every page that cites it. Measured: 137
#: lookups over 47 pages, 84 distinct, 23 s of subprocess; inside the dashboard
#: that ran every fixer cycle.
_SHA_VERDICT: dict[str, str] = {}


def _git_ok(repo: Path, *args: str) -> bool:
    """`git -C repo <args>` exited 0. Any failure to even RUN git is False for
    the caller to read as "cannot tell", never as "the object is missing"."""
    import subprocess
    try:
        return subprocess.run(["git", "-C", str(repo), *args],
                              capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _git_out(repo: Path, *args: str) -> str:
    """stdout of `git -C repo <args>`, empty when it fails to run at all."""
    import subprocess
    try:
        r = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                           text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _default_branch(repo: Path) -> str | None:
    """The branch a landed commit is reachable from — origin's HEAD, else a
    local main/master. None when nothing settles it, which disarms the
    ancestry half of E16 rather than guessing a branch."""
    key = str(repo)
    if key in _DEFBRANCH:
        return _DEFBRANCH[key]
    import subprocess
    out = None
    try:
        r = subprocess.run(["git", "-C", key, "symbolic-ref", "--quiet", "--short",
                            "refs/remotes/origin/HEAD"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            out = r.stdout.strip().split("/", 1)[-1]
    except (OSError, subprocess.SubprocessError):
        out = None
    if out is None:
        for b in ("main", "master"):
            if _git_ok(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{b}"):
                out = b
                break
    _DEFBRANCH[key] = out
    return out


def _lib_checkouts(root: Path) -> dict[str, Path]:
    """<name> -> checkout, from the absolute paths `.claude/hpc.env` declares
    (`DOMAIN_LIBS`, `LIB_<name>_<host>`). That declaration is the project's
    only statement of where a pinned lib lives ON THIS MACHINE; a lib it does
    not name is one E16 cannot check, and says nothing about."""
    out: dict[str, Path] = {}
    env = root / ".claude" / "hpc.env"
    try:
        text = env.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#") or not (line.startswith("DOMAIN_LIB")
                                        or line.startswith("LIB_")):
            continue
        _, _, val = line.partition("=")
        for tok in val.strip().strip("\"'").split():
            p = Path(tok)
            if p.is_absolute() and (p / ".git").exists():
                out.setdefault(p.name, p)
    return out


def code_sha_errors(entries: dict[str, str]) -> list[str]:
    """E16 — a `<repo>@<sha>` an entry cites is still retrievable.

    E4 checks that `Code:` has the SHAPE; nothing checked that what it names
    still EXISTS. A SHA read off a worktree branch is provisional: landing is
    `merge --ff-only`, so a branch that diverged is REBASED first and every
    SHA on it is rewritten, and a branch that is abandoned takes its SHAs with
    it. Either way the page is left pointing at an object no ref reaches — and
    silently, weeks after the entry was written, which is how it was actually
    found. For THIS repo the test is therefore ancestry of the default branch,
    which is what "landed" means; for a pinned lib, whose checkout this machine
    need not even hold, it degrades to "the object resolves".

    Everything here fails OPEN — no git, no repo, no default branch, no
    declared checkout: report nothing rather than guess. A NUMERIC repo name is
    skipped, because `3450@e637566` is a `<job id>@<host>` shaped exactly like
    a `<repo>@<sha>` (the same ambiguity jobs_errors documents, mirrored)."""
    if not (ROOT / ".git").exists():
        return []
    errs: list[str] = []
    verdict = _SHA_VERDICT
    libs: dict[str, Path] | None = None
    for name, body in entries.items():
        for tok in CODE_RE.findall(body):
            repo, _, sha = tok.partition("@")
            if repo.isdigit():
                continue
            if tok not in verdict:
                if repo == ROOT.name:
                    if not _git_ok(ROOT, "cat-file", "-e", f"{sha}^{{commit}}"):
                        verdict[tok] = "gone"
                    else:
                        d = _default_branch(ROOT)
                        if d is None or _git_ok(ROOT, "merge-base",
                                                "--is-ancestor", sha, d):
                            verdict[tok] = ""
                        else:
                            # Two different situations, two different repairs:
                            # a branch still holds it (land it, then cite the
                            # landed id) or nothing does (the rewrite already
                            # happened — the entry must be pointed at whatever
                            # landed in its place).
                            held = _git_out(ROOT, "for-each-ref", "--contains", sha,
                                            "--format=%(refname:short)", "refs/heads")
                            verdict[tok] = (f"unlanded:{d}:{held.splitlines()[0]}"
                                            if held else f"orphan:{d}")
                else:
                    if libs is None:
                        libs = _lib_checkouts(ROOT)
                    lib = libs.get(repo)
                    verdict[tok] = "" if (
                        lib is None
                        or _git_ok(lib, "cat-file", "-e", f"{sha}^{{commit}}")
                    ) else "gone"
            v = verdict[tok]
            if v == "gone":
                errs.append(f"E16 entry '{name}' cites `{tok}` — no commit of that "
                            f"id is retrievable. A branch SHA does not survive the "
                            f"rebase that lands it, nor the branch being dropped; "
                            f"if a state must outlive its branch, tag it")
            elif v.startswith("unlanded:"):
                _, d, br = v.split(":", 2)
                errs.append(f"E16 entry '{name}' cites `{tok}`, which is not on "
                            f"`{d}` — it is still only on `{br}`, and the rebase "
                            f"that lands that branch will rewrite it. Land the "
                            f"code first, then record the id it landed under")
            elif v.startswith("orphan:"):
                errs.append(f"E16 entry '{name}' cites `{tok}` — no branch reaches "
                            f"that commit, so a rebase already rewrote it or its "
                            f"branch was dropped. Find what landed in its place "
                            f"(`git log {v.split(':', 1)[1]} --grep` on its subject) "
                            f"and cite that id; the object itself dies at the next gc")
    return errs


def shared_page_errors(path: Path, text: str, entries: dict[str, str]) -> list[str]:
    """Checks common to task pages and node.md — both are lists of entries."""
    errs: list[str] = []
    seen: set[str] = set()
    for n in ENTRY_RE.findall(text):
        if n in seen:
            errs.append(f"E1 duplicate `### Entry: {n}` — headings must be unique "
                        f"per page (the anchor collapses); rename one")
        seen.add(n)
    for name, body in entries.items():
        errs += entry_errors(name, body)
    errs += id_order_errors(entries)
    errs += entry_script_errors(entries, path)
    errs += code_sha_errors(entries)
    errs += jobs_errors(text, entries, path)
    errs += lifecycle_errors(text, entries, path)
    errs += link_errors(path, text)
    errs += figures_errors(path, text)
    errs += cjk_errors(text)
    return errs


def lint_page(path: Path) -> list[str]:
    """One task page: frontmatter (P1), then the shared entry checks.

    Pages live at one or two depths under nodes/: `<node>/<page>.md` or
    `<node>/<group>/<page>.md` — the optional grouping folder is the project's
    own taxonomy; the framework does not name or validate it."""
    text = path.read_text(encoding="utf-8")
    errs: list[str] = []
    fm = frontmatter(text)
    try:
        parts = path.resolve().relative_to(NODES_DIR.resolve()).parts
    except ValueError:                       # explicit CLI path outside nodes/
        parts = (path.parent.name, path.name)
    node_folder = parts[0] if len(parts) <= 2 else parts[-3]

    for key in ("node", "task"):
        if not fm.get(key):
            errs.append(f"P1 page frontmatter missing `{key}:`")
    if fm.get("node") and fm["node"] != node_folder:
        errs.append(f"P1 `node: {fm['node']}` != folder `{node_folder}` — a page "
                    f"lives in the folder of the node it probes")

    entries = sections(text)
    if not entries:
        errs.append("P1 page has no `### Entry:` section — a page records its "
                    "work as entries")
    errs += shared_page_errors(path, text, entries)
    return errs


def lint_node(path: Path) -> list[str]:
    """node.md: page frontmatter, entries only, first is the gate (N1);
    every later entry is a validation and names the entry it replays (V1)."""
    text = path.read_text(encoding="utf-8")
    errs: list[str] = []
    fm = frontmatter(text)
    for key in ("node", "task"):
        if not fm.get(key):
            errs.append(f"N1 node.md frontmatter missing `{key}:`")
    if fm.get("node") and fm["node"] != path.parent.name:
        errs.append(f"N1 `node: {fm['node']}` != folder `{path.parent.name}`")
    entries = sections(text)
    if not entries:
        errs.append("N1 node.md has no `### Entry:` — its first entry is the "
                    "gate: the node reproducing a reference its Motivation names")
    for i, (name, body) in enumerate(entries.items()):
        if i == 0 or field(body, "Status") == "closed":
            continue          # closed = accepted as it stood, same rule as E4-E9
        mot = field(body, "Motivation")
        if not re.search(r"\]\([^)]*\.md#[^)]+\)", mot):
            errs.append(f"V1 validation entry '{name}' names no entry it replays — "
                        f"link the closed entry in Motivation; the recipe and the "
                        f"number it reproduced complete the evidence")
    errs += shared_page_errors(path, text, entries)
    return errs


# --------------------------------------------------------------------------
# Cross-tree checks (--cross): FW, N2, N3, J2.
# --------------------------------------------------------------------------

def record_version_check() -> list[str]:
    """FW: the marker (.claude/framework.json `record`), the contract text
    (.claude/project_memory-CLAUDE.md `Record format:` line) and this linter
    all agree on one version — the marker drifted silently once, and a synced
    marker over a stale contract is the same failure on the other side."""
    f = ROOT / ".claude" / "framework.json"
    if not f.exists():
        return []
    try:
        declared = json.loads(f.read_text(encoding="utf-8")).get("record", "")
    except ValueError:
        return ["FW .claude/framework.json is not valid JSON"]
    if declared != RECORD_VERSION:
        return [f"FW project declares record `{declared}` but this plugin enforces "
                f"`{RECORD_VERSION}` — migrate the records, then bump the marker "
                f"(or vice versa if the marker simply lagged)"]
    contract = ROOT / ".claude" / "project_memory-CLAUDE.md"
    if contract.exists():
        m = re.search(r"^Record format:\s*(\S+)", contract.read_text(encoding="utf-8"), re.M)
        got = m.group(1) if m else "(none)"
        if got != RECORD_VERSION:
            return [f"FW the record contract declares `{got}` but the linter enforces "
                    f"`{RECORD_VERSION}` — resync the contract files (update)"]
    return []


def impl_errors() -> list[str]:
    """N2 — the record's node and the code's node are the same node: an
    implementation EXISTS under the matching name, in any language."""
    errs = []
    roots = experiment_roots()
    for p in sorted(NODES_DIR.glob("*/node.md")):
        node = p.parent.name
        impls = [root / node / "impl" for root in roots]
        if not any(impl.is_dir() and any(impl.iterdir()) for impl in impls):
            expected = " or ".join(
                f"{impl.relative_to(ROOT).as_posix()}/" for impl in impls)
            errs.append(f"N2 node `{node}` has no implementation — "
                        f"{expected} is missing or empty")
    return errs


def index_consistency() -> list[str]:
    """N3 — every node folder appears in the regenerated roster, and every
    roster row names an existing node folder."""
    idx = (ROOT / "project_memory" / "_index.md")
    if not idx.exists():
        return ["N3 project_memory/_index.md is missing — regenerate it "
                "(gen_index.py)"]
    # only the node table is the roster's node claim — the entry table below
    # has its own join (ids), not this one
    text = idx.read_text(encoding="utf-8").split("\n## Entries")[0]
    listed = set(re.findall(
        r"^\|[^|]*\|\s*(?:\[)?`?([A-Za-z0-9_][A-Za-z0-9_.-]*)`?(?:\]\([^)]*\))?\s*\|",
        text, re.M))
    on_disk = {p.parent.name for p in NODES_DIR.glob("*/node.md")}
    errs = [f"N3 node `{n}` has no roster row in _index.md — regenerate it"
            for n in sorted(on_disk - listed)]
    errs += [f"N3 _index.md row `{n}` has no project_memory/nodes/{n}/node.md"
             for n in sorted(listed - on_disk) if n not in {"node", "name"}]
    # the objectives section is the O<nn> registry (the next free number is
    # read off it), so a page missing from it hands the same number out twice
    # eventually — the drift is checked like the node rows, and the fix is the
    # same regeneration
    full = idx.read_text(encoding="utf-8")
    obj_section = full.split("\n## Objectives")
    obj_listed = (set(re.findall(r"^\|\s*(O\d{2})\s*\|", obj_section[1], re.M))
                  if len(obj_section) > 1 else set())
    obj_dir = ROOT / "project_memory" / "objectives"
    obj_on_disk = set()
    for op in obj_dir.glob("*.md"):
        m = re.search(r"^id:\s*(O\d{2})\b", op.read_text(encoding="utf-8"), re.M)
        if m:
            obj_on_disk.add(m.group(1))
    errs += [f"N3 objective `{o}` has no roster row in _index.md's Objectives "
             f"section — regenerate it (the section is the O-number registry)"
             for o in sorted(obj_on_disk - obj_listed)]
    errs += [f"N3 _index.md Objectives row `{o}` matches no page in "
             f"project_memory/objectives/ — regenerate it"
             for o in sorted(obj_listed - obj_on_disk)]
    return errs


J2_MIN_MINUTES = 5.0   # elapsed-time floor — ignores transient processes (a
                       # reviewer's own shell tool call). Deliberately NOT
                       # threaded into live_bare_job_ids/queued_job_ids: J3/J4
                       # must treat a job as queued the instant it starts.


def _is_interactive_alloc(jid: str) -> bool:
    """True when `jid` is an srun/salloc ALLOCATION rather than a batch job.

    A batch job always carries a `<id>.batch` step; an interactive allocation
    never does. squeue cannot tell J2 which it is looking at, and the
    difference decides whether silence is a fault: a debug `srun` is by
    contract NOT a recorded run ("a quick foreground smoke run does not [go
    through hpc-submit]"), so flagging one as unrecorded is noise the reader
    dismisses every time — and a check whose findings are routinely dismissed
    stops being read at all.

    Unknown is NOT interactive: no sacct, a non-zero exit, no rows — J2 keeps
    the behaviour it had rather than going quiet on a real leak."""
    import shutil
    import subprocess
    if not shutil.which("sacct"):
        return False
    try:
        r = subprocess.run(["sacct", "-j", jid, "--format=JobID", "-Pn"],
                           capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    rows = [l.strip() for l in r.stdout.splitlines() if l.strip()]
    if r.returncode != 0 or not rows:
        return False
    return not any(row.endswith(".batch") for row in rows)


def unrecorded_jobs() -> list[str]:
    """J2 — a job id that is live RIGHT NOW and has been alive at least
    `J2_MIN_MINUTES` (bare-host PIDs only) but appears in NO entry's
    `- **Jobs:**` field: submitted but never recorded, running invisibly.
    Only the submitting session knows the job's purpose, so this is
    board/session-surfaced, never headless-fixed. An interactive srun/salloc
    is excluded — it is a smoke by definition, and owes no entry."""
    queue = queued_job_ids()
    if not queue:
        return []
    recorded: set[str] = set()
    for p in list(NODES_DIR.glob("*/*.md")) + list(NODES_DIR.glob("*/*/*.md")):
        for m in re.finditer(r"^(?:-\s+\*\*)?Jobs:(?:\*\*)?\s*(.+)$",
                             p.read_text(encoding="utf-8"), re.M):
            recorded.update(expand_jobids(m.group(1)))
    leaked = []
    for jid in sorted(queue - recorded):
        age = _pid_elapsed_minutes(jid)
        if age is not None and age < J2_MIN_MINUTES:
            continue
        if _is_interactive_alloc(jid):
            continue
        leaked.append(jid)
    return [f"J2 job {jid} is live but recorded in NO entry's `- **Jobs:**` field — "
            f"record it on the entry that launched it"
            for jid in leaked]


# --------------------------------------------------------------------------
# CLI.
# --------------------------------------------------------------------------

def discover(paths: list[str]) -> list[Path]:
    if paths:
        return [Path(p).resolve() for p in paths]
    pm = ROOT / "project_memory"
    return (sorted(NODES_DIR.glob("*/*.md")) + sorted(NODES_DIR.glob("*/*/*.md"))
            + sorted(pm.glob("note/**/*.md")) + sorted(pm.glob("memory/**/*.md")))


def lint_path(path: Path) -> list[str]:
    """Dispatch: node.md -> gate/validation lint; note/ and memory/ files ->
    M1 only (no page format — they are prose channels); else -> page lint."""
    if path.name == "node.md":
        return lint_node(path)
    pm = (ROOT / "project_memory").resolve()
    rp = path.resolve()
    for chan in ("note", "memory"):
        if rp.is_relative_to(pm / chan):
            return cjk_errors(path.read_text(encoding="utf-8"))
    return lint_page(path)


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:          # a path outside the repo (explicit CLI argument)
        return str(path)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--blocking", action="store_true",
                    help="suppress ADVISORY_CODES (used by hooks)")
    ap.add_argument("--cross", action="store_true",
                    help="also run the whole-tree checks (N2, N3, J2)")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--recent", type=float, metavar="HOURS", default=None,
                    help="only lint pages modified within the last HOURS")
    a = ap.parse_args()

    # The version gate runs first, on every invocation: a project on another
    # record version gets ONE finding and exit 3, so a caller that only blocks
    # on findings (the pre-commit gate) lets it through while doctor reports it.
    fw = record_version_check()
    if fw:
        for e in fw:
            print(f"  {e}")
        return 3

    targets = discover(a.paths)
    if a.recent is not None:
        cutoff = time.time() - a.recent * 3600
        targets = [p for p in targets if p.exists() and p.stat().st_mtime >= cutoff]

    failed = 0
    for path in targets:
        if not path.exists():
            print(f"{_rel(path)}: NOT FOUND")
            failed += 1
            continue
        errs = lint_path(path)
        if a.blocking:
            errs = [e for e in errs if e.split()[0] not in ADVISORY_CODES]
        if errs:
            failed += 1
            print(f"{_rel(path)}:")
            for e in errs:
                print(f"  {e}")
        elif not a.quiet:
            print(f"{_rel(path)}: OK")

    if a.cross:
        for e in (impl_errors() + index_consistency() + unrecorded_jobs()):
            failed += 1
            print(f"  {e}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
