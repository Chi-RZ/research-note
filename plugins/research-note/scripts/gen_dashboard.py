#!/usr/bin/env python3
"""Generate project_memory/dashboard.html — interactive node-tree overview.

Self-contained HTML (vanilla JS, no CDN/server): open in any browser.
Structure: node (lineage tree, by `parent:`) -> task pages -> entries (+status
chips), jobs (running/done via squeue snapshot), linter violations,
last-modified. Top red zone = needs attention (done-pending-analysis,
running-but-queue-empty, lint violations, stale pages). A collapsible
recent-activity panel shows the merged git log of the four repos.

Usage: python3 .claude/scripts/gen_dashboard.py [-o OUT.html]
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import check_node_page as cn                    # reuse parser + linter
from projroot import nth_parent, resolve_root   # noqa: E402
from project_config import (  # noqa: E402
    ConfigError, feature_enabled, initial_project_config, load_project_config)

ROOT = resolve_root(nth_parent(HERE, 1))
PM = ROOT / "project_memory"
STALE_DAYS = 7
ACTIVITY_DAYS = 14
REPOS = ("", ".claude")
# "To close" review queue = `analyzed` entries the USER still needs to review→close.
# Watermark: only entries on pages last edited ON/AFTER this FIXED local date are shown, so
# the pre-2026-06-21 backlog stays hidden while everything from 2026-06-21 onward shows
# (it does NOT roll forward each day — it is a fixed cutoff you bump by hand when you want to
# advance it). Drain the older analyzed backlog via the Overview `analyzed` status-filter chip.
TO_CLOSE_SINCE_DATE = "2026-06-21 00:00"   # fixed cutoff; show analyzed on pages edited at/after this
TO_CLOSE_SINCE = time.mktime(time.strptime(TO_CLOSE_SINCE_DATE, "%Y-%m-%d %H:%M"))


def parse_index() -> dict[str, str]:
    """_index.md node rows -> {node: 'what it is'} (the one-line description)."""
    out = {}
    idx = PM / "_index.md"
    if not idx.exists():
        return out
    for line in idx.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*\d+\s*\|\s*\[?`?([A-Za-z0-9_.-]+)`?[^|]*\|\s*(.*?)\s*\|\s*$", line)
        if m and m.group(1) not in ("node", "#"):
            out[m.group(1)] = m.group(2)
    return out


def node_info(path: Path, desc: str) -> dict:
    """One project_memory/nodes/<name>/node.md -> the tree row it anchors."""
    # record v3: node.md carries no frontmatter — the folder name is the node.
    return dict(
        name=path.parent.name,
        parent="",
        kind="",
        status="",
        date="",
        desc=desc,
        path=str(path),
        violations=cn.lint_node(path),
        pages=[],
    )


def page_info(path: Path, queue: set[str]) -> dict:
    text = path.read_text(encoding="utf-8")
    fm = cn.frontmatter(text)
    # line number of each entry heading (1-based) for the vscode :line anchor
    entry_lines: dict[str, int] = {}
    for m in cn.ENTRY_RE.finditer(text):
        entry_lines.setdefault(m.group(1).strip(), text.count("\n", 0, m.start()) + 1)
    # AUTHORITATIVE per-entry jobs come from each entry's own `- **Jobs:**`
    # field (record v2.3), NOT from scanning the narrative — an entry that
    # merely *cross-references* another arm's running job must not inherit it,
    # and 8-digit dates in prose must not be mistaken for job ids.
    table_ids = []
    entry_list = []
    for name, body in cn.sections(text).items():
        jobs = cn.entry_job_ids(body)
        table_ids.extend(jobs)
        entry_list.append(dict(name=name, status=cn.field(body, "Status") or "?",
                               jobs=jobs[:12],
                               running=sorted(set(jobs) & queue),
                               line=entry_lines.get(name),
                               findings=bool(re.search(r"^(?:-\s+\*\*)?Conclusion:", body, re.M))))
    rel_nodes = path.relative_to(PM / "nodes")
    return dict(
        node=fm.get("node", rel_nodes.parts[0]),
        name=rel_nodes.with_suffix("").as_posix().split("/", 1)[1],
        task=fm.get("task", ""),
        path=str(path),
        rel=str(path.relative_to(ROOT)),
        mtime=path.stat().st_mtime,
        entries=entry_list,
        table_ids=table_ids,
        running_jobs=sorted(set(table_ids) & queue),
        # node.md is linted by lint_node via node_info — not double-reported here
        violations=[] if path.name == "node.md" else cn.lint_page(path),
    )


def activity(days: int) -> list[dict]:
    """Merged, newest-first git log of the project + agent repos — the
    chronological view (layers inside the monorepo are told apart by prefix)."""
    out = []
    for rel in REPOS:
        d = ROOT / rel if rel else ROOT
        if not (d / ".git").exists():
            continue
        try:
            r = subprocess.run(["git", "-C", str(d), "log", f"--since={days}.days",
                                "--pretty=format:%ad %s", "--date=short"],
                               capture_output=True, text=True, timeout=30)
        except Exception:
            continue
        for line in r.stdout.splitlines():
            date, _, subject = line.partition(" ")
            if date:
                out.append(dict(date=date, repo=rel or ROOT.name, subject=subject))
    out.sort(key=lambda e: (e["date"], e["repo"]), reverse=True)
    return out


def objective_info(path: Path) -> dict:
    """One objectives/<slug>.md -> one pure "needs-you" row: status, the loop's
    `attention:` line, and how many Plan-linked entries sit at `analyzed`
    awaiting the user's ✓. Per-phase live state lives ON THE PAGE now — the
    board only says WHERE the user is needed, never restates the Plan."""
    text = path.read_text(encoding="utf-8")
    fm = cn.frontmatter(text)
    m = re.search(r"^##\s+Plan\s*$\n(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    plan = m.group(1) if m else ""

    # awaiting-review count: any markdown link under Plan whose target is a
    # `<page>.md#entry-<slug>` anchor (tolerant — matches both old flat Plans
    # and the new P<n>-phase blocks), entry Status looked up on the task page.
    awaiting = 0
    cache: dict[Path, dict[str, str]] = {}
    for rel, anchor in re.findall(r"\]\(([^)#]+\.md)#(entry-[^)]+)\)", plan):
        q = (path.parent / rel).resolve()
        if not q.exists():
            continue
        if q not in cache:
            try:
                cache[q] = {cn.slugify(f"Entry: {n}"): (cn.field(b, "Status") or "")
                            for n, b in cn.sections(q.read_text(encoding="utf-8")).items()}
            except Exception:
                cache[q] = {}
        if cache[q].get(anchor.strip()) == "analyzed":
            awaiting += 1
    try:
        import check_objective_page as co
        violations = co.lint(path)
    except Exception as e:                    # never let a linter crash kill the board
        violations = [f"objective linter failed: {e}"]
    attention = str(fm.get("attention", "") or "").strip()
    if len(attention) >= 2 and attention[0] == attention[-1] and attention[0] in "\"'":
        attention = attention[1:-1]          # shallow frontmatter reader keeps YAML quotes
    return dict(name=path.stem, path=str(path), status=fm.get("status", "?"),
                attention=attention, awaiting=awaiting, violations=violations)


def fixer_ledger_state() -> tuple[dict, int]:
    """Replay <project>/.fixer/ledger.jsonl -> ({key: (state, fails)}, park_after)."""
    state, park_after = {}, 3
    fdir = ROOT / ".fixer"
    cfg_candidates = (fdir / "config.json", ROOT / ".claude" / "fixer" / "config.json")
    try:
        for c in cfg_candidates:
            if c.exists():
                park_after = json.loads(c.read_text(encoding="utf-8"))["park_after_attempts"]
                break
    except Exception:
        pass
    if (fdir / "ledger.jsonl").exists():
        for line in (fdir / "ledger.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            k, ev = e.get("key"), e.get("event")
            if ev == "fixed":
                state[k] = ("fixed", 0)
            elif ev == "failed":
                state[k] = ("failed", state.get(k, ("", 0))[1] + 1)
            elif ev == "parked":
                state[k] = ("parked", state.get(k, ("", 0))[1])
    return state, park_after


def lint_note(ledger: dict, rel: str, code: str, park_after: int) -> str:
    """Annotate a violation with what the fixer has been doing about it.

    Frozen since the agent tiers were disabled: ledger.jsonl can no longer gain
    entries, so anything here is history, not current state. Kept so an
    old ledger still reads correctly if a tier is switched back on."""
    note = ""
    for tier in ("format", "analyze"):
        st = ledger.get(f"{tier}:{rel}:{code}")
        if st and st[0] == "parked":
            note = " — fixer GAVE UP (parked); fix by hand or clear the ledger entry"
        elif st and st[0] == "failed":
            note = f" — fixer failing ({st[1]}/{park_after} attempts)"
    return note


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", type=Path, default=PM / "dashboard.html")
    ap.add_argument("--remote-host", default=os.environ.get("DASHBOARD_REMOTE_HOST", ""),
                    help="VSCode Remote-SSH host alias; jump links become "
                         "vscode://vscode-remote/ssh-remote+<host>/... so they open "
                         "the page on the remote. Empty -> local vscode://file/... links.")
    args = ap.parse_args()

    queue = cn.queued_job_ids() or set()
    desc = parse_index()
    nodes: dict[str, dict] = {}
    pages: list[dict] = []
    for p in (sorted((PM / "nodes").glob("*/*.md"))
              + sorted((PM / "nodes").glob("*/*/*.md"))):
        if p.name == "node.md":
            n = node_info(p, desc.get(p.parent.name, ""))
            nodes[n["name"]] = n
            # v3: node.md carries real entries (the gate, the validations) —
            # they join the entry tables and the To-close queue like any page
            pages.append(page_info(p, queue))
        else:
            pages.append(page_info(p, queue))

    now = time.time()
    for pg in pages:
        pg["age_days"] = round((now - pg["mtime"]) / 86400, 1)
        pg["fresh"] = pg["mtime"] > TO_CLOSE_SINCE     # for the "To close" review queue
        pg["done"] = bool(pg["entries"]) and all(e["status"] == "closed" for e in pg["entries"])
        nodes.setdefault(pg["node"], node_info_missing(pg["node"]))["pages"].append(pg)

    ledger, park_after = fixer_ledger_state()

    objectives = [objective_info(p)
                  for p in sorted((PM / "objectives").glob("*.md"))]

    attention = []
    for ob in objectives:
        if ob["status"] == "active" and ob["awaiting"]:
            attention.append(f"objective '{ob['name']}' — {ob['awaiting']} analyzed "
                             f"entr(y/ies) awaiting your ✓ (one ✓ cascades the batch)")
        for v in ob["violations"]:
            attention.append(f"objective '{ob['name']}' · lint: {v}")
    for node in nodes.values():
        for v in node["violations"]:
            rel = str(Path(node["path"]).relative_to(ROOT))
            attention.append(f"{node['name']}/node.md · lint: {v}"
                             + lint_note(ledger, rel, v.split()[0], park_after))
        for pg in node["pages"]:
            for e in pg["entries"]:
                if False:  # done-pending-analysis retired in v3
                    attention.append(f"{node['name']} · {pg['name']} · entry '{e['name']}' "
                                     f"done-pending-analysis — ran but never reported")
                if e["status"] == "running" and pg["table_ids"] and not pg["running_jobs"]:
                    attention.append(f"{node['name']} · {pg['name']} · entry '{e['name']}' "
                                     f"running but no jobs in queue — finished? update the page")
            # ALL current violations, no age gate: the fixer drains them within
            # ~30 min, so anything lingering here is stuck (parked/failing) and
            # must never quietly age off the board.
            for v in pg["violations"]:
                attention.append(f"{node['name']} · {pg['name']} · lint: {v}"
                                 + lint_note(ledger, pg["rel"], v.split()[0], park_after))
            if pg["age_days"] > STALE_DAYS \
               and any(e["status"] in ("open", "running") for e in pg["entries"]):
                attention.append(f"{node['name']} · {pg['name']} · open work untouched for "
                                 f"{pg['age_days']:.0f} days")
            # blocked escalation: `blocked` = "user, come look / give resources". The
            # staleness rule above skips it, so a blocked entry left untouched would
            # never nudge — surface it after STALE_DAYS so it can't rot in the Blocked tab.
            if pg["age_days"] > STALE_DAYS:
                for e in pg["entries"]:
                    if False:  # blocked retired in v3
                        attention.append(f"{node['name']} · {pg['name']} · entry '{e['name']}' "
                                         f"blocked + untouched {pg['age_days']:.0f}d — needs "
                                         f"your decision/resources")

    # cross-tree health: a missing impl or roster drift makes a node invisible;
    # a J2 SUBMIT leak (live job on no entry) runs invisibly too — surface it
    # here since only the submitting session has context, so the fixer drops it.
    for c in (cn.record_version_check() + cn.impl_errors()
              + cn.index_consistency() + cn.unrecorded_jobs()):
        attention.append(c + lint_note(ledger, "project_memory/_index.md",
                                       c.split()[0], park_after))

    # remote HPC: a stale queue snapshot means the board's Running view is blind
    hpc_conf = ""
    for f in (ROOT / ".claude" / "hpc.env", ROOT / ".claude" / "hpc.local.env"):
        if f.exists():
            hpc_conf += f.read_text(encoding="utf-8")
    if re.search(r"^\s*REMOTE_HOST=", hpc_conf, re.M):
        snap = ROOT / ".fixer" / "remote_queue"
        if not snap.exists():
            attention.append("remote HPC declared but no queue snapshot yet — "
                             "run the plugin's remote.sh queue (the fixer does it per cycle)")
        elif time.time() - snap.stat().st_mtime > 1800:
            attention.append(f"remote queue snapshot "
                             f"{(time.time() - snap.stat().st_mtime) / 60:.0f} min stale — "
                             f"ssh to the cluster failing? Running/J3 views are blind")

    # Record edits nobody committed. The bus commits every write it makes, so a
    # leftover means the bus was bypassed — and since the daemon no longer
    # finishes the commit for them (that hid the bypass and signed someone
    # else's work), the board is where it has to surface or it surfaces nowhere.
    try:
        st = subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain",
                             "--", "project_memory"],
                            capture_output=True, text=True, timeout=20)
        dirty = [l[3:].strip() for l in st.stdout.splitlines() if l[3:].strip().endswith(".md")]
        if dirty:
            attention.append(f"{len(dirty)} record file(s) edited but not committed — "
                             f"the bus commits what it writes, so these came from "
                             f"somewhere else; their author should commit them: "
                             + ", ".join(dirty[:4]) + ("…" if len(dirty) > 4 else ""))
    except Exception:
        pass

    # fixer heartbeat: the daemon dying silently is the one gap nothing else
    # surfaces — for a project that RUNS one. A project with the fixer disabled
    # has no heartbeat to miss, and saying so on its board would report a
    # disabled integration as broken (the compatibility policy's one rule).
    try:
        fixer_on = feature_enabled(load_project_config(ROOT), "fixer")
    except ConfigError:
        fixer_on = feature_enabled(initial_project_config(legacy=True), "fixer")
    if fixer_on:
        hb = ROOT / ".fixer" / "last_run"
        if hb.exists():
            age_min = (time.time() - hb.stat().st_mtime) / 60
            if age_min > 30:
                attention.append(f"fixer heartbeat stale — last cycle {age_min:.0f} min ago "
                                 "(daemon dead? see fixer/start_fixer_daemon.sh)")
        else:
            attention.append("fixer heartbeat missing — the daemon never ran (.fixer/last_run)")
        # fixer crash: heartbeat alive but the cycle itself blew up (detector exception etc.)
        le = ROOT / ".fixer" / "last_error"
        if le.exists() and le.stat().st_size:
            first = le.read_text(encoding="utf-8").strip().splitlines()[-1]
            attention.append(f"fixer crashed last cycle: {first} — see .fixer/last_error")

    n_entries = sum(len(pg["entries"]) for pg in pages)
    data = dict(generated=time.strftime("%Y-%m-%d %H:%M"),
                queue_n=len(queue), nodes=list(nodes.values()), attention=attention,
                objectives=objectives,
                activity=activity(ACTIVITY_DAYS), activity_days=ACTIVITY_DAYS,
                n_pages=len(pages), n_entries=n_entries,
                vscode_remote=args.remote_host.strip())

    page = HTML_TMPL.replace("__DATA__", json.dumps(data, ensure_ascii=False)) \
                    .replace("__TITLE__", html.escape(f"{ROOT.name} — node dashboard"))
    args.out.write_text(page, encoding="utf-8")
    # The board is rewritten every fixer cycle, so tracking it turns the record
    # channel's history into churn — one diff of a minified JSON blob every ten
    # minutes, buried among the entries that actually say something. The rule
    # lives NEXT TO the artifact, in a nested .gitignore this generator owns, so
    # the project's root .gitignore stays project property (bootstrap_project.py
    # deliberately never touches an existing one). Created only when absent: a
    # project that wrote its own rule here — or decided to track the board — keeps
    # it. An already-tracked file is unaffected either way and needs
    # `git rm --cached` once.
    gi = args.out.parent / ".gitignore"
    if not gi.exists():
        gi.write_text(args.out.name + "\n", encoding="utf-8")
    print(f"wrote {args.out}  ({len(nodes)} nodes, {len(pages)} pages, {n_entries} entries, "
          f"{len(attention)} attention items, {len(queue)} jobs in queue)")
    return 0


def node_info_missing(name: str) -> dict:
    """Placeholder row for a page whose node folder has no node.md (linter N/INDEX
    will be shouting about it anyway) — never drop its pages off the board."""
    return dict(name=name, parent="", kind="?", status="?", date="", desc="(no node.md)",
                path="", violations=[], pages=[])


HTML_TMPL = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>__TITLE__</title>
<style>
 body{font:14px/1.45 -apple-system,'Segoe UI',sans-serif;margin:18px;background:#fafafa;color:#222}
 h1{font-size:20px;margin:0 0 2px} .meta{color:#777;font-size:12px;margin-bottom:10px}
 .zone{background:#fff3f3;border:1px solid #e8b4b4;border-radius:8px;padding:8px 14px;margin:10px 0}
 .zone h2{margin:0 0 4px;font-size:14px;color:#a33} .zone li{margin:2px 0;font-size:13px}
 .zone .ok{color:#383}
 /* objectives pane */
 .att{color:#b45309;background:#fef3c7;border:1px solid #f59e0b;border-radius:4px;padding:2px 8px;margin:4px 0;font-size:12px;display:inline-block}
.obj{border-left:4px solid #27ae60;padding:3px 0 4px 12px;margin:0 0 12px}
 .obj.closed{border-left-color:#7f8c8d}
 .obj h3{margin:0 0 2px;font-size:14.5px} .obj.hot{background:#fff8e6}
 .obj .rev{color:#c0392b;font-weight:600} .obj .om{color:#777;font-size:12.5px}
 .st{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;color:#fff;vertical-align:middle}
 .st.open{background:#2980b9}.st.active{background:#27ae60}.st.running{background:#e67e22}
 .st.analyzed{background:#16a085}.st.closed{background:#7f8c8d}.st.done-pending-analysis{background:#c0392b}
 .st.blocked{background:#8e44ad}.st.deprecated{background:#95a5a6}
 .st.unknown,.st\?{background:#999}
 /* activity */
 details.act{background:#fff;border:1px solid #d8dde3;border-radius:8px;padding:6px 12px;margin:10px 0}
 details.act>summary{cursor:pointer;font-size:13px;color:#555}
 .actlist{max-height:340px;overflow:auto;margin-top:6px}
 .actline{font-size:12.5px;padding:1px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .ad{color:#999;font-family:ui-monospace,monospace;font-size:11.5px}
 .ar{display:inline-block;min-width:96px;color:#4477dd;font-size:11.5px}
 /* tabs */
 .tabs{display:flex;gap:6px;margin:12px 0 0;border-bottom:2px solid #d8dde3}
 .tab{padding:7px 16px;cursor:pointer;font-size:13.5px;border:1px solid #d8dde3;border-bottom:none;
   border-radius:8px 8px 0 0;background:#eef1f4;color:#555;position:relative;top:2px;user-select:none}
 .tab.on{background:#fff;color:#222;font-weight:600;border-color:#34495e;border-bottom:2px solid #fff}
 .tab .cnt{display:inline-block;min-width:16px;text-align:center;font-size:11px;color:#fff;background:#c0392b;
   border-radius:9px;padding:0 5px;margin-left:6px}
 .tab .cnt.run{background:#e67e22} .tab .cnt.blk{background:#8e44ad} .tab .cnt.cls{background:#16a085}
 .hint{color:#777;font-size:12px;margin:8px 0}
 .pane{background:#fff;border:1px solid #d8dde3;border-top:none;padding:12px 14px;box-shadow:0 1px 3px #0002}
 /* overview tree */
 .toolbar{margin-bottom:8px} input#q{padding:5px 9px;width:300px;margin-right:10px}
 .chips{display:inline} .chip{display:inline-block;padding:2px 10px;border-radius:12px;margin:0 4px 4px 0;
   font-size:12px;background:#e8e8e8;cursor:pointer;user-select:none} .chip.on{outline:2px solid #4477dd}
 details.major{border-bottom:1px solid #eee} details.major>summary{padding:6px 4px;font-size:14px}
 details.minor{margin:2px 0} details.minor>summary{padding:3px 4px;font-size:13px}
 summary{cursor:pointer;list-style:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 summary::-webkit-details-marker{display:none}
 summary::before{content:'▸';display:inline-block;width:14px;color:#999;transition:transform .1s}
 details[open]>summary::before{transform:rotate(90deg)}
 .kids{margin-left:20px;border-left:1px solid #eee;padding-left:10px}
 .done>summary{opacity:.5} .qt{color:#333} .ty{color:#999;font-size:11px;font-style:italic}
 .badge{color:#777;font-size:11.5px} .b-run{color:#e67e22;font-weight:600} .b-pend{color:#c0392b;font-weight:600}
 .leaf{padding:2px 4px;font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
 .leaf .sn{color:#444} .jb{color:#999;font-size:11px} .fnd{color:#27ae60;font-size:11px}
 .empty{color:#aaa;font-size:12px;font-style:italic;padding:2px 4px}
 a.jump{text-decoration:none;color:#4477dd;font-weight:700;padding:0 4px;font-size:13px}
 a.jump:hover{color:#1a52c0}
 /* entry tables */
 table{border-collapse:collapse;width:100%}
 th{background:#34495e;color:#fff;padding:6px 9px;font-size:12.5px;text-align:left}
 td{padding:5px 9px;border-bottom:1px solid #eee;font-size:13px;vertical-align:top}
 tr:hover td{background:#f0f6ff} .muted{color:#888} .jobs{color:#e67e22;font-size:12px}
</style></head><body>
<h1>__TITLE__</h1>
<div class="meta" id="meta"></div>
<div class="zone"><h2>⚠ needs attention</h2><ul id="zone"></ul></div>
<details class="act"><summary id="act-sum">recent activity</summary><div class="actlist" id="act"></div></details>
<div class="tabs">
 <div class="tab on" id="tab-overview" onclick="showTab('overview')">Overview</div>
 <div class="tab" id="tab-objectives" onclick="showTab('objectives')">Objectives<span class="cnt" id="cnt-objectives"></span></div>
 <div class="tab" id="tab-close" onclick="showTab('close')">To close<span class="cnt cls" id="cnt-close"></span></div>
 <div class="tab" id="tab-running" onclick="showTab('running')">Running<span class="cnt run" id="cnt-running"></span></div>
 <div class="tab" id="tab-blocked" onclick="showTab('blocked')">Blocked<span class="cnt blk" id="cnt-blocked"></span></div>
</div>
<div class="pane" id="pane-overview">
 <div class="toolbar"><input id="q" placeholder="filter: node / task / entry…"><span class="chips" id="chips"></span></div>
 <div id="tree"></div>
</div>
<div class="pane" id="pane-objectives" style="display:none">
 <p class="hint">One row per objective — ↗ opens the page itself (the mandate, the Plan and the entry chain live there, not here). A ✓ at objective or task granularity cascades: every <b>analyzed</b> entry that step references closes with it.</p>
 <div id="objectives"></div></div>
<div class="pane" id="pane-close" style="display:none">
 <p class="hint">New <b>analyzed</b> entries awaiting your review → <b>closed</b> (machine does analyzed; you confirm close). Only analyzed work on pages edited <b>since 2026-06-21</b> shown (fixed cutoff, does not roll forward); older backlog hidden — drain it via the Overview <code>analyzed</code> filter.</p>
 <div id="close"></div></div>
<div class="pane" id="pane-running" style="display:none"><div id="running"></div></div>
<div class="pane" id="pane-blocked" style="display:none"><div id="blocked"></div></div>
<script>
const D=__DATA__, nodes=D.nodes;
document.getElementById('meta').textContent=
 `generated ${D.generated} · ${nodes.length} nodes · ${D.n_pages} task pages · `+
 `${D.n_entries} entries · ${D.queue_n} jobs in queue`;
const zone=document.getElementById('zone');
if(D.attention.length===0){zone.innerHTML='<li class="ok">✓ all clear</li>';}
else D.attention.forEach(a=>{const li=document.createElement('li');li.textContent=a;zone.appendChild(li);});

function esc(s){return (s+'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function chip(s){return `<span class="st ${s}">${esc(s)}</span>`;}



// ---- recent activity (generated from git; never hand-written) ----
document.getElementById('act-sum').textContent=
 `recent activity — ${D.activity.length} commits across 4 repos, last ${D.activity_days} days`;
document.getElementById('act').innerHTML=
 D.activity.map(a=>`<div class="actline"><span class="ad">${esc(a.date)}</span> `+
  `<span class="ar">${esc(a.repo)}</span> ${esc(a.subject)}</div>`).join('')
 ||'<div class="empty">(no commits in window)</div>';

// ---- node lineage tree: node -> task pages -> entries ----
const byName={}; nodes.forEach(n=>byName[n.name]=n);
const kids={}; nodes.forEach(n=>{const p=n.parent; if(p&&byName[p])(kids[p]=kids[p]||[]).push(n);});
const byNm=(a,b)=>a.name<b.name?-1:a.name>b.name?1:0;
const roots=nodes.filter(n=>!(n.parent&&byName[n.parent])).sort(byNm);
const allPages=[]; nodes.forEach(n=>(n.pages||[]).forEach(p=>allPages.push(p)));
function vlink(path,line){if(!path)return '';
 const base=D.vscode_remote?`vscode://vscode-remote/ssh-remote+${D.vscode_remote}${path}`
                           :`vscode://file${path}`;
 return base+(line?(':'+line):'');}
function jump(path,line,title){return path?`<a class="jump" href="${vlink(path,line)}" `+
 `data-p="${path}" data-l="${line||0}" title="open ${esc(title)} in VSCode">↗</a>`:'';}
function entryRunning(e){return e.running&&e.running.length>0;}  // job actually in queue

const F={text:'',status:new Set()};
const STATUSES=[...new Set(allPages.flatMap(p=>p.entries.map(e=>e.status)))].sort();
const chips=document.getElementById('chips');
STATUSES.forEach(s=>{const c=document.createElement('span');c.className='chip';c.textContent=s;
 c.onclick=()=>{c.classList.toggle('on');F.status.has(s)?F.status.delete(s):F.status.add(s);renderTree();};
 chips.appendChild(c);});
document.getElementById('q').oninput=e=>{F.text=e.target.value.toLowerCase();renderTree();};
function hit(s){return !F.text||(s+'').toLowerCase().includes(F.text);}
function entryKeep(e){return (!F.status.size||F.status.has(e.status));}
function pageKeep(p){
 const kept=p.entries.filter(entryKeep);
 if(!kept.length&&F.status.size)return null;
 if(F.text&&!(hit(p.name)||hit(p.task)||kept.some(e=>hit(e.name))))return null;
 return kept;}
function leafHtml(p,e){
 return `<div class="leaf">${chip(e.status)} <span class="sn">${esc(e.name)}</span>`+
  (e.running&&e.running.length?` <span class="b-run">${e.running.join(',')}▶</span>`:'')+
  (e.jobs.length&&!(e.running&&e.running.length)?` <span class="jb">${e.jobs.length} job${e.jobs.length>1?'s':''}</span>`:'')+
  (e.findings?' <span class="fnd">✓F</span>':'')+` ${jump(p.path,e.line,p.name)}</div>`;}
function pageHtml(p,kept){
 const open=(F.text||F.status.size)?' open':'';
 const inner=kept.map(e=>leafHtml(p,e)).join('')||'<div class="empty">(no entries)</div>';
 return `<details class="minor${p.done?' done':''}"${open}><summary>`+
  `<b>${esc(p.name)}</b> <span class="qt">${esc(p.task)}</span> `+
  `<span class="badge">(${kept.length} entr${kept.length===1?'y':'ies'})</span> ${jump(p.path,0,p.name)}`+
  `</summary><div class="kids">${inner}</div></details>`;}
function nodeHtml(n){
 const childHtml=(kids[n.name]||[]).slice().sort(byNm).map(nodeHtml).join('');
 const pgs=[]; (n.pages||[]).slice().sort(byNm).forEach(p=>{
  const kept=pageKeep(p); if(kept)pgs.push(pageHtml(p,kept));});
 const self=hit(n.name)||hit(n.desc);
 if(!pgs.length&&!childHtml&&!(self&&!F.status.size))return '';
 let nrun=0,npend=0;
 (n.pages||[]).forEach(p=>{if((p.running_jobs||[]).length||p.entries.some(entryRunning))nrun++;
  npend+=p.entries.filter(e=>e.status==='done-pending-analysis').length;});
 const badge=`<span class="badge">(${(n.pages||[]).length}p`+
  (nrun?` · <span class="b-run">${nrun}▶</span>`:'')+
  (npend?` · <span class="b-pend">${npend}⧖</span>`:'')+`)</span>`;
 const open=(F.text||F.status.size)?' open':'';
 const inner=pgs.join('')+childHtml||'<div class="empty">(no matching task pages)</div>';
 return `<details class="major${n.status==='deprecated'?' done':''}"${open}><summary>`+
  `${chip(n.status)} <b>${esc(n.name)}</b> <span class="qt">${esc(n.desc)}</span> `+
  `<span class="ty">${esc(n.kind)}</span> ${badge} ${jump(n.path,0,n.name)}`+
  `</summary><div class="kids">${inner}</div></details>`;}
function renderTree(){
 document.getElementById('tree').innerHTML=roots.map(nodeHtml).join('')||'<div class="empty">(nothing matches)</div>';}

// ---- entry tabs ----
function collectEntries(pred){const out=[];
 allPages.forEach(p=>p.entries.forEach(e=>{if(pred(e,p))out.push({p,e});}));return out;}
function entryTable(items,extraHead,extraCell){
 if(!items.length)return '<div class="empty">none</div>';
 let h=`<table><thead><tr><th>Node</th><th>Task</th><th>Entry</th><th>Status</th>${extraHead}<th></th></tr></thead><tbody>`;
 items.forEach(({p,e})=>{h+=`<tr><td><b>${esc(p.node)}</b></td><td>${esc(p.name)}</td>`+
  `<td>${esc(e.name)}</td><td>${chip(e.status)}</td>${extraCell(p,e)}<td>${jump(p.path,e.line,p.name)}</td></tr>`;});
 return h+'</tbody></table>';}
function renderRunning(){
 // an entry is "running" iff it has jobs in the queue AND is not already concluded
 // (an analyzed/closed/blocked entry can still MENTION a shared job that is live in
 // another arm — that must NOT drag the concluded entry into the Running tab).
 const CONCLUDED=['analyzed','closed','blocked'];
 const items=collectEntries(e=>entryRunning(e)&&!CONCLUDED.includes(e.status))
  .sort((a,b)=>(b.p.mtime||0)-(a.p.mtime||0));   // newest-edited page first
 document.getElementById('cnt-running').textContent=items.length||'';
 document.getElementById('running').innerHTML=entryTable(items,'<th>In queue</th>',
  (p,e)=>`<td class="jobs">${e.running.join(', ')}</td>`);}
function renderBlocked(){
 const items=collectEntries(e=>e.status==='blocked')
  .sort((a,b)=>(b.p.mtime||0)-(a.p.mtime||0));   // newest-edited page first
 document.getElementById('cnt-blocked').textContent=items.length||'';
 document.getElementById('blocked').innerHTML=entryTable(items,'<th>Jobs</th>',
  (p,e)=>`<td class="jobs">${e.jobs.join(', ')||'<span class="muted">—</span>'}</td>`);}
function renderClose(){
 // analyzed entries on recently-edited pages = the user's review→close queue,
 // newest page first (most-recently-edited on top) so fresh work surfaces.
 const items=collectEntries((e,p)=>e.status==='analyzed'&&p.fresh)
  .sort((a,b)=>(b.p.mtime||0)-(a.p.mtime||0));
 document.getElementById('cnt-close').textContent=items.length||'';
 document.getElementById('close').innerHTML=entryTable(items,'<th>Findings</th>',
  (p,e)=>`<td>${e.findings?'<span class="fnd">✓F</span>':'<span class="muted">—</span>'}</td>`);}

// ---- objectives tab: pure "needs-you" rows — per-phase state lives on the page ----
function renderObjectives(){
 const obs=D.objectives||[];
 const waiting=obs.reduce((n,o)=>n+(o.status==='active'?o.awaiting:0),0);
 document.getElementById('cnt-objectives').textContent=waiting||'';
 document.getElementById('objectives').innerHTML=obs.map(o=>{
  const need=o.awaiting?`<span class="rev">${o.awaiting} analyzed awaiting ✓</span>`
                       :'nothing awaiting review';
  const att=o.attention?`<div class="att">&#9888; ${esc(o.attention)}</div>`:'';
  const hot=(o.attention||o.awaiting)?' hot':'';
  return `<div class="obj ${esc(o.status)}${hot}"><h3>${chip(o.status)} ${esc(o.name)}`+
   `${jump(o.path,0,o.name)}</h3>${att}<div class="om">${need}</div></div>`;
 }).join('')||'<div class="empty">(no objectives — /objective new to open one)</div>';}

function showTab(name){['overview','objectives','close','running','blocked'].forEach(t=>{
 document.getElementById('pane-'+t).style.display=t===name?'':'none';
 document.getElementById('tab-'+t).classList.toggle('on',t===name);});}

renderTree(); renderObjectives(); renderClose(); renderRunning(); renderBlocked();

// Inside the qdash extension webview acquireVsCodeApi() exists: intercept every
// ↗ click (capture phase, so it never navigates the webview nor toggles a
// <details>) and ask the extension to open the page in an editor tab.
const QAPI=(typeof acquireVsCodeApi!=='undefined')?acquireVsCodeApi():null;
if(QAPI){document.addEventListener('click',function(e){
 const a=e.target&&e.target.closest?e.target.closest('a.jump'):null; if(!a)return;
 e.preventDefault(); e.stopPropagation();
 QAPI.postMessage({path:a.getAttribute('data-p'),line:(+a.getAttribute('data-l'))||0});
},true);}
</script></body></html>
"""

if __name__ == "__main__":
    sys.exit(main())
