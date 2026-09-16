#!/usr/bin/env python3
"""One fixer cycle: detect node/task-page violations -> launch headless fixer agents -> verify -> ledger.

Cron entry is run_fixer.sh (PATH + flock); this script is the whole brain.
Violations are STATE, not events: every cycle re-runs the detectors fresh; the
worklist files under logs/run-<ts>/ are prompt payload + audit trail only and
are never read back.

On-disk state (all under <project>/.fixer/ — OUTSIDE the agent dir, because a
plugin install path carries a version number and is replaced on upgrade;
project state must survive that):
  last_run       heartbeat — mtime = last cycle start (qdash staleness check)
  ledger.jsonl   append-only events {ts, tier, key, event: fixed|failed|parked}
                 replayed each cycle for consecutive-fail counts and parked set.
                 To un-park an item by hand: append {"key": "...", "event": "fixed"}.
  (the shared record.lock lives in .research-note/state/, with the bus)
  record.lock    (legacy location, unused since 0.2.3) — the cycle's own git
                 add/commit (sweeps, attention flags) and the record-bus script
                 take it; agents launched by run_agent commit for themselves
  logs/run-<ts>/ worklist-<tier>.txt + agent-<tier>.log per run that launched agents

Tiers (config.json, read fresh each run) — check_node_page is the single source
of truth for every error type; one --blocking --cross pass is split by code:
  format   all format codes + J4 (mechanical Status flip) + N2/N3 cross lines -> sonnet
  analyze  J3/E7/E9 — a delayed ORPHAN NET, not the default analyzer: the
           submitting session watches and analyzes its own jobs, with full
           context. An item qualifies only once BOTH heartbeats have been
           silent for attention_after_min (page mtime AND newest linked log);
           stage 1 stamps the owning objective's `attention:` (no agent),
           stage 2 (only if fallback_analyze.enabled) sends items older than
           after_hours to the real agent                                          -> opus
  (J2 cross lines go to no tier: unfixable headless — only the submitting session
   had the job's context; the dashboard surfaces it for the user instead)

Every cycle also sweeps stale uncommitted project_memory node/task-page/_index
edits into a `memory: fixer — sweep` commit (plain git, no agent) — sessions are
supposed to commit their own edits, this catches what they leaked. It refuses
any diff that moves a `Status:` line: those are the user's review decisions and
must be committed by the user, not attributed to the daemon.
"""
import fcntl
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent            # .claude/fixer (or plugin fixer/)
SCRIPTS = HERE.parent / "scripts"                 # sibling of fixer/ wherever it ships
sys.path.insert(0, str(SCRIPTS))
from projroot import nth_parent, resolve_root     # noqa: E402

ROOT = resolve_root(nth_parent(HERE, 1))          # project root
STATE = ROOT / ".fixer"                           # the fixer's OWN state, gitignored


def record_lock_path() -> Path:
    """The record lock is core state, shared with the bus and the launcher's
    record step, so it lives where a project without a fixer keeps it."""
    lock_dir = ROOT / ".research-note" / "state"
    lock_dir.mkdir(parents=True, exist_ok=True)
    ignore = lock_dir.parent / ".gitignore"
    if not ignore.exists():
        ignore.write_text("state/\n", encoding="utf-8")
    return lock_dir / "record.lock"
# need /analyze judgment: J3 (run finished, unreported), E7/E9 (an entry says
# `analyzed` but carries no Facts / no Conclusion — the conclusion itself is
# missing). J4 is a mechanical open->running flip -> format tier.
LIFECYCLE = ("J3", "E7", "E9")
# impl (N2) and roster drift (N3) are printed by --cross with no page header —
# they are tree-level, so they bucket under the index pseudo-page.
CROSS_RE = re.compile(r"^N[23]\b")
# A `closed` entry is a user-reviewed, terminal record. E7/E9 fire on it too
# (the linter still reports a closed entry with no Facts/Conclusion,
# deliberately), but no unattended agent may edit it — writing one here would
# rewrite a human review decision. Dropped like J2: still linted,
# dashboard-surfaced, never auto-repaired. Matches the linter's wording.
CLOSED_ENTRY_RE = re.compile(r"^E[79] .*\bis `closed`")
INDEX_PAGE = "project_memory/_index.md"


def log(msg: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def locked_commit(files: list, msg: str) -> None:
    """The cycle's own record commits (sweeps, attention flags) go through an
    flock on .research-note/state/record.lock — shared with the record-bus script, so no two
    actors interleave add/commit. Agents commit for themselves, not here."""
    STATE.mkdir(exist_ok=True)
    with open(record_lock_path(), "a") as lk:         # "a" creates if missing
        fcntl.flock(lk, fcntl.LOCK_EX)
        paths = [str(f) for f in files]
        subprocess.run(["git", "-C", str(ROOT), "add", "--"] + paths,
                       capture_output=True, timeout=30)
        # Path-scoped: sessions stage their own work eagerly, and an unscoped
        # commit here would carry it into a `memory:` commit that the
        # layer-prefix hook then rejects — losing the fixer's write silently.
        c = subprocess.run(["git", "-C", str(ROOT), "commit", "-m", msg, "--"] + paths,
                           capture_output=True, text=True, timeout=30)
        if c.returncode != 0 and "nothing to commit" not in (c.stdout + c.stderr):
            log(f"commit FAILED ({msg}): {(c.stderr or c.stdout).strip()[:160]}")


def detect() -> tuple:
    """One check_node_page --blocking --cross pass -> (format_work, analyze_work).

    check_node_page is the single source of truth for every error type. Its
    output is `<repo-relative page>:` headers followed by indented codes, then
    the unheaded --cross lines. LIFECYCLE codes (need /analyze judgment) route
    to the analyze tier; every other per-page code — including J4, a mechanical
    open->running flip — plus the cross lines route to the format tier. J2 cross
    lines (unrecorded live jobs) are dropped: only the submitting session has the
    job's context, so the dashboard surfaces them for the user instead. E7/E9 on
    a `closed` entry are dropped for the opposite reason (see CLOSED_ENTRY_RE):
    the record is the user's, not the daemon's, to edit.
    """
    r = subprocess.run([sys.executable, str(SCRIPTS / "check_node_page.py"),
                        "--blocking", "--cross", "--quiet"],
                       capture_output=True, text=True, timeout=120, cwd=ROOT)
    # Objective pages get their own pass. Nothing there is auto-fixable — the
    # lines join the format tier so the dashboard shows them; readings and
    # entry links are the deciding turn's to supply, never the daemon's.
    o = subprocess.run([sys.executable, str(SCRIPTS / "check_objective_page.py"),
                        "--quiet"],
                       capture_output=True, text=True, timeout=120, cwd=ROOT)
    fmt, ana, page = {}, {}, None
    for line in (r.stdout + o.stdout).splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("J2") or CLOSED_ENTRY_RE.match(s):
            continue
        if CROSS_RE.match(s):
            fmt.setdefault(INDEX_PAGE, []).append(s)
        elif line.endswith(":") and not line.startswith(" "):
            page = line[:-1]
        elif page:
            code = s.split()[0]
            tier = ana if code in LIFECYCLE else fmt
            tier.setdefault(page, []).append(s)
    return fmt, ana


def report_uncommitted(fresh_min: int) -> None:
    """Name record edits nobody committed. Reporting, not repairing: the bus
    commits every write it makes, so a leftover means the bus was bypassed, and
    a daemon quietly finishing that commit would both hide the bypass and sign
    someone else's work. Only files untouched for fresh_min minutes."""
    # REPORT ONLY. Committing someone else's edit hides that the bus was
    # bypassed, signs their work with the daemon's name, and keeps an
    # unattended process in the record's write path — the thing this design
    # spent its effort removing. Whoever made the edit commits it.
    r = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain", "--",
                        "project_memory"],
                       capture_output=True, text=True, timeout=30)
    stale = []
    for line in r.stdout.splitlines():
        rel = line[3:].strip()
        if " -> " in rel or not rel.endswith(".md"):
            continue
        if not (rel.startswith("project_memory/nodes/")
                or rel.startswith("project_memory/objectives/")
                or rel == "project_memory/_index.md"):
            continue
        f = ROOT / rel
        if f.exists() and time.time() - f.stat().st_mtime > fresh_min * 60:
            stale.append(rel)
    if stale:
        # The distinction this used to draw — does the diff move a `Status:`
        # line, i.e. is it a research decision the daemon must not sign? — is
        # moot once nothing here commits. Everything is the author's to commit.
        log("UNCOMMITTED record edits (the bus commits what it writes, so these "
            "came from somewhere else) — their author should commit them: "
            + ", ".join(stale))


def stamp_attention(page: Path, note: str, msg: str) -> None:
    """Set/replace the frontmatter `attention:` line and commit that ONE file.
    Machinery frontmatter only — never Goal/Plan/Log content; the user clears
    it by resuming or deciding."""
    text = page.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    if not m:
        return
    line = f'attention: "{note}"'
    if re.search(r"^attention:", m.group(1), re.M):
        fm = re.sub(r"^attention:.*$", lambda _: line, m.group(1),
                    count=1, flags=re.M)
    else:
        fm = m.group(1) + "\n" + line
    page.write_text(text.replace(m.group(0), f"---\n{fm}\n---", 1), encoding="utf-8")
    oid = re.search(r"^id:\s*(O\d+)", fm, re.M)
    if oid:                     # objectives/ commits carry their id trailer
        msg = f"{msg}\n\nObjective: {oid.group(1)}"
    locked_commit([page], msg)


def flag_stale_objectives(days: int, fresh_min: int) -> None:
    """An active objective whose loop died mid-plan renders exactly like one
    still in flight — active, no attention badge, nothing obviously wrong. The
    loop stamps `attention:` when it STOPS deliberately; a crash stamps
    nothing. So: an active objective with no attention, no linked entry
    running, and no new Log line for `days` gets a stale marker. Machinery
    frontmatter only (never Goal/Plan/Log content), same licence as the
    lifecycle repairs; the user clears it by resuming or deciding."""
    import datetime
    today = datetime.date.today()
    for page in sorted((ROOT / "project_memory" / "objectives").glob("*.md")):
        try:
            text = page.read_text(encoding="utf-8")
        except OSError:
            continue
        m = re.match(r"^---\n(.*?)\n---", text, re.S)
        if not m:
            continue
        fm = m.group(1)
        if not re.search(r"^status:\s*active\s*$", fm, re.M):
            continue
        if re.search(r"^attention:", fm, re.M):
            continue
        # don't race a live session (same guard as the sweeper)
        if (STATE / "last_run").exists():
            import time
            if time.time() - page.stat().st_mtime < fresh_min * 60:
                continue
        # last chain activity: newest dated reading "(YYYY-MM-DD)" (old-format
        # Log lines started with the date instead), else created:
        dates = re.findall(r"^-\s*(\d{4}-\d{2}-\d{2})", text, re.M)
        dates += re.findall(r"\((\d{4}-\d{2}-\d{2})\)", text)
        cm = re.search(r"^created:\s*(\d{4}-\d{2}-\d{2})", fm, re.M)
        if cm:
            dates.append(cm.group(1))
        if not dates:
            continue
        try:
            last = max(datetime.date.fromisoformat(d) for d in dates)
        except ValueError:
            continue
        idle = (today - last).days
        if idle < days:
            continue
        # any linked task-page entry still running -> the queue owns the wait
        running = False
        for rel in re.findall(r"\]\((\.\.?/[^)]+\.md)(?:#[^)]*)?\)", text):
            q = (page.parent / rel).resolve()
            if not q.exists() or (ROOT / "project_memory" / "nodes") not in q.parents:
                continue
            if re.search(r"^(?:-\s+\*\*)?Status:(?:\*\*)?\s+running\b",
                         q.read_text(encoding="utf-8"), re.M):
                # `running` in the TEXT is not proof of a live job: a loop that
                # died mid-flight leaves exactly that, so treating it as "work
                # in progress" made this guard skip the one failure it exists
                # to catch. Ask the linter — a J3 on that page means the jobs
                # are terminal and nobody reported them.
                r = subprocess.run([sys.executable, str(SCRIPTS / "check_node_page.py"),
                                    str(q), "--quiet"],
                                   capture_output=True, text=True, timeout=60, cwd=ROOT)
                if "J3 " in r.stdout:
                    continue          # terminal jobs, unreported — not alive
                running = True
                break
        if running:
            continue
        note = (f"stale — no chain progress since {last} and nothing running; "
                f"the loop may have died. Resume with /objective run {page.stem}")
        stamp_attention(page, note,
                        f"memory: fixer — flag stale objective {page.stem} (idle {idle}d)")
        log(f"flagged stale objective {page.stem} (idle {idle}d)")


# job evidence on a page = its file://-linked logs (bare-server .log, Slurm .out)
# Both link forms: the record contract writes repo-relative links (a
# file:// URI renders as nothing and cannot be clicked through), while
# older pages and the analyze prompt still carry file://. Reading only
# one of them silently degrades evidence_age to the page mtime, which is
# the clock the orphan net runs on.
LOG_LINK_RE = re.compile(r"(?:file://)?([^)\s\"'>]+\.(?:log|out))")


def evidence_age(page: Path) -> float:
    """Seconds since the entry owner's last sign of life: the newest of the
    page mtime (a living owner writes the page continuously — its heartbeat)
    and every file://-linked log (a batch owner legitimately leaves early
    finishers unanalyzed until the grid is done, but its logs keep arriving).
    No log path parses -> page mtime alone."""
    mtimes = [page.stat().st_mtime]
    for raw in LOG_LINK_RE.findall(page.read_text(encoding="utf-8")):
        f = Path(raw) if raw.startswith("/") else ROOT / raw
        if f.is_file():
            mtimes.append(f.stat().st_mtime)
    return time.time() - max(mtimes)


def gate_analyze(raw: dict, cfg: dict) -> tuple:
    """The analyze tier is a delayed orphan net — it must never race a living
    owner (the submitting session watches and analyzes its own jobs). An item
    qualifies only when BOTH the page mtime and the newest linked log are
    older than attention_after_min. Returns (flag, run): flag = {page: (age_s,
    lines)} for the stage-1 attention stamp; run = the subset whose evidence
    age also exceeds fallback_analyze.after_hours, sent to the real agent
    (stage 2, only when fallback_analyze.enabled)."""
    fb = cfg["fallback_analyze"]
    flag, run = {}, {}
    for page, lines in raw.items():
        p = ROOT / page
        if not p.exists():
            continue
        age = evidence_age(p)
        if age < cfg["attention_after_min"] * 60:
            continue                              # owner may still be alive
        flag[page] = (age, lines)
        if fb.get("enabled") and age > fb["after_hours"] * 3600:
            run[page] = lines
    return flag, run


def flag_attention(flag: dict) -> None:
    """Stage 1: no agent — stamp the owning objective (the one whose Plan
    links this page) so the user comes looking. One stamp per objective per
    cycle; a page already flagged (same page#code), owned by a settled
    objective (O11), or owned by no objective gets no write — the dashboard
    renders stale states on its own."""
    objectives = []
    for obj in sorted((ROOT / "project_memory" / "objectives").glob("*.md")):
        try:
            objectives.append((obj, obj.read_text(encoding="utf-8")))
        except OSError:
            continue
    stamped = set()
    for page, (age, lines) in sorted(flag.items()):
        code = lines[0].split()[0]
        target = (ROOT / page).resolve()
        for obj, text in objectives:
            links = re.findall(r"\]\((\.\.?/[^)]+\.md)(?:#[^)]*)?\)", text)
            if not any((obj.parent / rel).resolve() == target for rel in links):
                continue
            m = re.match(r"^---\n(.*?)\n---", text, re.S)
            fm = m.group(1) if m else ""
            if re.search(r"^status:\s*closed\s*$", fm, re.M):
                continue
            if obj in stamped or f"{page}#{code}" in fm:
                break                             # owner found, already flagged
            stamp_attention(obj, f"{page}#{code} — jobs terminal, unanalyzed "
                                 f"for {age / 3600:.1f}h",
                            f"memory: fixer — flag orphaned entry {page}#{code}")
            stamped.add(obj)
            log(f"attention: {obj.stem} <- {page}#{code} ({age / 3600:.1f}h)")
            break


def item_keys(tier: str, page: str, lines: list) -> set:
    return {f"{tier}:{page}:{ln.split()[0]}" for ln in lines}


def ledger_state() -> dict:
    """Replay ledger -> {key: (last_state, consecutive_fails)}."""
    st = {}
    lp = STATE / "ledger.jsonl"
    if not lp.exists():
        return st
    for line in lp.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        k, ev = e.get("key"), e.get("event")
        if ev == "fixed":
            st[k] = ("fixed", 0)
        elif ev == "failed":
            st[k] = ("failed", st.get(k, ("", 0))[1] + 1)
        elif ev == "parked":
            st[k] = ("parked", st.get(k, ("", 0))[1])
    return st


def ledger_append(events: list) -> None:
    with open(STATE / "ledger.jsonl", "a", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def filter_work(tier: str, work: dict, cfg: dict, parked: set) -> dict:
    """Drop recently-edited pages, parked items, and cap pages per run (logged)."""
    fresh_min = cfg["skip_pages_modified_within_min"]
    out = {}
    for page in sorted(work):
        p = ROOT / page                        # page keys are repo-relative paths
        if p.exists() and (time.time() - p.stat().st_mtime) < fresh_min * 60:
            log(f"{tier}: skip {page} (edited < {fresh_min} min ago)")
            continue
        lines = [ln for ln in work[page]
                 if f"{tier}:{page}:{ln.split()[0]}" not in parked]
        if lines:
            out[page] = lines
    cap = cfg["tiers"][tier]["max_pages_per_run"]
    if len(out) > cap:
        dropped = sorted(out)[cap:]
        log(f"{tier}: capping at {cap} pages, deferring {len(dropped)} to next cycle: "
            + ", ".join(dropped))
        out = {p: out[p] for p in sorted(out)[:cap]}
    return out


def worklist_text(work: dict) -> str:
    return "\n".join(f"{page}:\n" + "\n".join(f"  {ln}" for ln in lines)
                     for page, lines in sorted(work.items()))


def run_agent(tier: str, tcfg: dict, prompt: str, rundir: Path) -> str:
    env = {k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"}
    logf = rundir / f"agent-{tier}.log"
    requested = os.environ.get("RESEARCH_NOTE_FIXER_AGENT", "auto").lower()
    if requested not in {"auto", "claude", "codex"}:
        raise RuntimeError("RESEARCH_NOTE_FIXER_AGENT must be auto, claude, or codex")
    if requested == "auto":
        # Prefer the agent that launched this session.  When both CLIs are
        # installed, environment provenance is less surprising than PATH order.
        if os.environ.get("CODEX_HOME") and shutil.which("codex"):
            agent = "codex"
        elif os.environ.get("CLAUDE_CODE_EXECPATH") and shutil.which("claude"):
            agent = "claude"
        # No provenance (a hand-run of run_fixer.sh, or a stub written before
        # registration baked the choice): the historical default is claude, so
        # a Claude-only project never silently changes backend.
        elif shutil.which("claude"):
            agent = "claude"
        elif shutil.which("codex"):
            agent = "codex"
        else:
            raise RuntimeError("no fixer agent found; install codex or claude")
    else:
        agent = requested
        if not shutil.which(agent):
            raise RuntimeError(f"requested fixer agent is unavailable: {agent}")

    if agent == "codex":
        # Codex has no max-turns equivalent.  The outer subprocess timeout is
        # the shared hard stop. --approve-for-me selects workspace-write itself
        # and is intentionally mutually exclusive with an explicit --sandbox.
        cmd = ["codex", "exec", "--ephemeral", "-C", str(ROOT),
               "--approve-for-me", prompt]
        label = "codex (default model)"
    else:
        cmd = ["claude", "-p", prompt, "--model", tcfg["model"],
               "--max-turns", str(tcfg["max_turns"]),
               "--permission-mode", "acceptEdits"]
        label = f"claude/{tcfg['model']}"
    log(f"{tier}: launching {label} (max {tcfg['timeout_min']} min)")
    try:
        r = subprocess.run(cmd,
                           capture_output=True, text=True, cwd=ROOT, env=env,
                           timeout=tcfg["timeout_min"] * 60)
        logf.write_text(r.stdout + "\n--- stderr ---\n" + r.stderr, encoding="utf-8")
        log(f"{tier}: agent exited {r.returncode}")
        return r.stdout
    except subprocess.TimeoutExpired as e:
        logf.write_text(f"TIMEOUT after {tcfg['timeout_min']} min\n"
                        + str(e.stdout or ""), encoding="utf-8")
        log(f"{tier}: agent TIMED OUT")
        return ""


def main() -> None:
    STATE.mkdir(exist_ok=True)
    cfg = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    override = STATE / "config.json"              # per-project tuning (shallow merge)
    if override.exists():
        cfg.update(json.loads(override.read_text(encoding="utf-8")))
    if not cfg.get("enabled", False):
        return
    # Host guard: run only on the node where the cron was registered. The
    # authorized FQDN is captured by register_cron.sh into the gitignored `host`
    # file (NOT config.json — that is git-tracked and cloned to every machine).
    # Migration = re-run register_cron.sh on the new node. Absent file = no guard.
    hf = STATE / "host"
    if hf.exists():
        want = hf.read_text(encoding="utf-8").strip()
        if want and socket.getfqdn() != want and socket.gethostname() != want:
            return
    (STATE / "last_run").touch()
    remote_sync()
    report_uncommitted(cfg["skip_pages_modified_within_min"])
    flag_stale_objectives(cfg.get("stale_objective_days", 2),
                          cfg["skip_pages_modified_within_min"])

    ledger = ledger_state()
    parked = {k for k, (s, _) in ledger.items() if s == "parked"}

    # detect() shells out to both linters over the whole record. With no agent
    # tier enabled its format half has no consumer, but the analyze half still
    # feeds the attention stamp — the cycle's remaining purpose — so it runs
    # only while something downstream can use it.
    if cfg["tiers"]["format"]["enabled"] or cfg["tiers"]["analyze"]["enabled"] \
            or cfg.get("attention_after_min"):
        raw_fmt, raw_ana = detect()
    else:
        raw_fmt, raw_ana = {}, {}
    # analyze tier, stage 1/2 split: flag qualifying orphans on their objective
    # (no agent); only fallback_analyze survivors reach the agent worklist.
    # Stamping is the SCANNER's job and runs whatever the tiers are set to: it
    # is what tells a human that a loop went quiet with work in flight. Only the
    # optional fallback ANALYSIS is gated on the tier — an agent writing
    # findings is a different act from a daemon raising a hand.
    ana_flag, ana_run = gate_analyze(raw_ana, cfg)
    flag_attention(ana_flag)
    if not cfg["tiers"]["analyze"]["enabled"]:
        ana_run = {}
    work = {}
    for tier, raw in (("format", raw_fmt), ("analyze", ana_run)):
        if not cfg["tiers"][tier]["enabled"]:
            continue
        w = filter_work(tier, raw, cfg, parked)
        if w:
            work[tier] = w
    if not work:
        return  # the common case: nothing to do, no agent, no log dir

    ts = time.strftime("%Y%m%d-%H%M%S")
    rundir = STATE / "logs" / f"run-{ts}"
    rundir.mkdir(parents=True)
    log(f"cycle {ts}: work in tiers {sorted(work)}")

    agent_parked = set()   # pages the agent itself declared PARKED
    for tier in ("format", "analyze"):        # serial: never two agents at once
        if tier not in work:
            continue
        wl = worklist_text(work[tier])
        (rundir / f"worklist-{tier}.txt").write_text(wl + "\n", encoding="utf-8")
        pf = HERE / f"prompt_{tier}.md"
        if not pf.exists():
            # prompt_analyze.md was deleted with 0.11.8: unreachable while the
            # tier is off, and its liveness/evidence recipes had drifted from
            # every implementation. Re-enabling the tier means writing a fresh
            # prompt against the current contract, not resurrecting that one.
            log(f"{tier}: no prompt_{tier}.md — tier cannot run; write one against the current contract")
            continue
        prompt = (pf.read_text(encoding="utf-8")
                  + "\n\n## Current worklist\n\n" + wl)
        out = run_agent(tier, cfg["tiers"][tier], prompt, rundir)
        for m in re.finditer(r"^PARKED: (\S+) (\S+)", out, re.M):
            agent_parked.add(f"{tier}:{m.group(1)}:{m.group(2)}")

    # Verify: re-detect; per attempted key decide fixed / failed / parked.
    events, newly_parked = [], []
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    post_fmt, post_ana = detect()
    for tier, post in (("format", post_fmt), ("analyze", post_ana)):
        if tier not in work:
            continue
        after = {k for page, lines in post.items()
                 for k in item_keys(tier, page, lines)}
        for page, lines in work[tier].items():
            for k in item_keys(tier, page, lines):
                if k not in after:
                    events.append({"ts": now, "tier": tier, "key": k, "event": "fixed"})
                elif k in agent_parked:
                    events.append({"ts": now, "tier": tier, "key": k, "event": "parked"})
                else:
                    fails = ledger.get(k, ("", 0))[1] + 1
                    events.append({"ts": now, "tier": tier, "key": k, "event": "failed"})
                    if fails >= cfg["park_after_attempts"]:
                        events.append({"ts": now, "tier": tier, "key": k, "event": "parked"})
                        newly_parked.append(k)
    ledger_append(events)
    fixed = [e["key"] for e in events if e["event"] == "fixed"]
    log(f"verify: {len(fixed)} fixed, "
        f"{len([e for e in events if e['event'] == 'failed'])} still failing, "
        f"{len(newly_parked)} newly parked")
    # parked/failing items surface on the dashboard (gen_dashboard annotates the
    # lint zone from ledger.jsonl) — no push channel: headless cron has none.


def hpc_env() -> dict:
    """KEY=VALUE pairs from .claude/hpc.env (+ .claude/hpc.local.env overlay)."""
    conf: dict = {}
    for f in (ROOT / ".claude" / "hpc.env", ROOT / ".claude" / "hpc.local.env"):
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    conf[k.strip()] = v.strip().strip('"').strip("'")
    return conf


def remote_sync() -> None:
    """When the project declares a remote HPC: refresh the queue snapshot and
    rsync logs (+ capped data) back, so this cycle's detect/analyze see fresh
    ground truth. remote.sh itself loops over EVERY declared host (REMOTE_HOSTS,
    or just REMOTE_HOST) — all clusters are monitored equally. Failures are
    tolerated — the snapshot goes stale and the linter treats the queue as
    unusable rather than inventing J3s."""
    if not hpc_env().get("REMOTE_HOST"):
        return
    env = {**os.environ, "RESEARCH_NOTE_PROJECT_DIR": str(ROOT),
           "CLAUDE_PROJECT_DIR": str(ROOT)}
    # Periodic git sync, local -> GitHub only: commits (records, code) flow up
    # every cycle so the hub never lags; the CLUSTER pulls at submit time (the
    # only moment it needs code, SHA-checked by remote.sh). Quiet no-op when
    # nothing is ahead; never pushes uncommitted work.
    subprocess.run(["git", "-C", str(ROOT), "push", "-q", "origin", "HEAD"],
                   capture_output=True, timeout=120)
    for sub in ("queue", "pull"):
        r = subprocess.run(["bash", str(SCRIPTS / "remote.sh"), sub],
                           capture_output=True, text=True, timeout=600, env=env)
        if r.returncode != 0:
            # Keep the TAIL, not the head. remote.sh writes the line that names
            # the host and the step LAST, after every ssh attempt, so a head
            # truncation reported whatever ssh happened to print first — which,
            # against an older server, is OpenSSH's three-line post-quantum
            # banner, ~200 characters of it. Every FAILED line in the log said
            # only that, cut off mid-URL, for weeks.
            tail = [ln for ln in (r.stderr or r.stdout).splitlines() if ln.strip()][-3:]
            log(f"remote {sub}: FAILED — {' | '.join(tail)[-400:]}")


def regen_dashboard() -> None:
    """Every cycle rewrites project_memory/dashboard.html — viewers (Live
    Preview, qdash, a browser tab) READ the file and never exec framework
    code, so the fixer is the single writer that keeps them fresh.

    A failure here is LOGGED, never raised. The dashboard is a VIEW; the
    cycle's real work — the scan, the attention stamps — has already happened
    by the time this runs, and letting a view abort the cycle costs both. Not
    hypothetical: the regeneration grew past its old 120 s budget as the
    record's own commit history grew, so every cycle died here — `last_run`
    stopped advancing, `last_error` stayed full, and doctor reported a dead
    daemon for six hours while the scan underneath ran correctly every time."""
    try:
        r = subprocess.run([sys.executable, str(SCRIPTS / "gen_dashboard.py")],
                           capture_output=True, text=True, timeout=600, cwd=ROOT)
        if r.returncode != 0:
            log(f"dashboard: regeneration exited {r.returncode} — "
                f"{((r.stderr or r.stdout) or '').strip()[-300:]}")
    except subprocess.TimeoutExpired:
        log("dashboard: regeneration timed out (600 s) — the board is stale, "
            "the scan above is unaffected; profile gen_dashboard.py")
    except Exception as e:                  # a view must never kill the cycle
        log(f"dashboard: regeneration failed — {type(e).__name__}: {e}")


if __name__ == "__main__":
    # last_error is the dashboard's crash indicator: non-empty = last cycle blew
    # up (detector exception, bad config, ...). Cleared on every clean cycle.
    import traceback
    STATE.mkdir(exist_ok=True)
    err = STATE / "last_error"
    try:
        main()
        regen_dashboard()
        err.write_text("", encoding="utf-8")
    except Exception:
        err.write_text(traceback.format_exc(), encoding="utf-8")
        raise
