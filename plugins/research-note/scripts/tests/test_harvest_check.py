"""harvest_check — the hook-injected safety net for finished, unharvested jobs.

The failure it closes: five cells finished and sat unread until the user
asked, because the loop closing depended on the agent remembering to arm a
waiter. The hook cannot be forgotten; these tests pin what it says and — as
important — when it stays silent.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent

PAGE = """---
node: tanner_gnn_ln
task: LayerNorm across the grid
---

### Entry: ln at d5 p0.06
- **Id:** 07.001
- **Status:** {status}
- **Date:** 2026-07-21 10:00
- **Jobs:** {jobs}
- **Code:** `tanner_gnn_ln@abc1234f`
- **Motivation:** The parent found "LER 2.8e-3"; does LayerNorm move it?
- **Recipe:** {{hidden_dim: 32, seed: 0}}
"""

OBJ = """---
id: O07
status: active
created: 2026-08-01
budget: 40 GPUh
wake-me-if: "budget exceeded"
---

## Goal

q.

## Plan

- [ ] **P1 — does LN move it?** (2 GPUh)
  - [ln at d5 p0.06](../nodes/tanner_gnn_ln/grid.md#entry-ln-at-d5-p006) `07.001` — the probe (2026-08-19)

## Verdict

**Open.** 0 entries await review.
"""


@pytest.fixture()
def hv(tmp_path, monkeypatch):
    for name in ("check_node_page", "check_objective_page", "harvest_check"):
        sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location(
        "harvest_check", SCRIPTS / "harvest_check.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["harvest_check"] = mod
    spec.loader.exec_module(mod)
    C = sys.modules["check_node_page"]
    nodes = tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln"
    nodes.mkdir(parents=True)
    (tmp_path / "project_memory" / "objectives").mkdir()
    (tmp_path / "project_memory" / "objectives" / "ln.md").write_text(
        OBJ, encoding="utf-8")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "NODES", tmp_path / "project_memory" / "nodes")
    monkeypatch.setattr(mod, "OBJ_DIR", tmp_path / "project_memory" / "objectives")
    monkeypatch.setattr(mod, "SNAPSHOT", tmp_path / ".fixer" / "remote_queue")
    monkeypatch.setattr(mod, "FIRST_SEEN", tmp_path / ".fixer" / "harvest_first_seen.json")
    monkeypatch.setattr(mod, "MIN_AGE_MIN", 0)   # immediate path; the gate has its own tests
    monkeypatch.setattr(C, "_remote_queue", lambda: None)
    C._QUEUE_CACHE = None
    yield mod, C, nodes
    C._QUEUE_CACHE = None


def run(mod, capsys, *argv):
    import sys as _sys
    old = _sys.argv
    _sys.argv = ["harvest_check.py", *argv]
    try:
        mod.main()
    finally:
        _sys.argv = old
    return capsys.readouterr().out


def test_a_running_entry_with_dead_jobs_is_reported_with_its_objective(
        hv, capsys, monkeypatch):
    mod, C, nodes = hv
    (nodes / "grid.md").write_text(
        PAGE.format(status="running", jobs="999999"), encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))   # queue empty
    out = run(mod, capsys)
    assert "J3" in out and "ln at d5 p0.06" in out
    assert out.startswith("O07 ·"), "the owning objective tags the line"


def test_an_apostrophe_in_the_title_still_attributes_to_its_objective(
        hv, capsys, monkeypatch):
    """The name was re-parsed out of `J3 entry '<name>' is running` with a
    NON-GREEDY quoted capture, so a title holding an apostrophe — "gate A'" —
    came back truncated at it. The slug then matched no Plan link, the line
    went out unattributed, and every scoped Monitor poll (`grep '^O07 '`)
    dropped it while the unscoped hook still showed it: an entry sat 7h
    unharvested behind a Monitor that was armed and polling the whole time."""
    mod, C, nodes = hv
    (mod.OBJ_DIR / "ln.md").write_text(
        OBJ.replace("[ln at d5 p0.06](../nodes/tanner_gnn_ln/grid.md#entry-ln-at-d5-p006)",
                    "[gate A' at d5 p0.06]"
                    "(../nodes/tanner_gnn_ln/grid.md#entry-gate-a-at-d5-p006)"),
        encoding="utf-8")
    (nodes / "grid.md").write_text(
        PAGE.replace("ln at d5 p0.06", "gate A' at d5 p0.06")
            .format(status="running", jobs="999999"), encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    out = run(mod, capsys)
    assert "gate A' at d5 p0.06" in out
    assert out.startswith("O07 ·"), f"attributed to nothing: {out!r}"


def test_a_renamed_title_still_attributes_through_the_entry_id(
        hv, capsys, monkeypatch):
    """The (page, slug) join dies the moment a heading is reworded and the
    Plan link is not chased — and nothing forces the two to stay in step
    except a human. The id does not move: E1 assigns it once and never
    rewrites it, and O3 already checks the id a Plan line cites against the
    entry's own. So the id is tried first."""
    mod, C, nodes = hv
    (nodes / "grid.md").write_text(
        PAGE.replace("ln at d5 p0.06", "ln at d5 p0.06 — REWORDED after the fact")
            .format(status="running", jobs="999999"), encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    out = run(mod, capsys)
    assert out.startswith("O07 ·"), f"the id did not carry it: {out!r}"


def test_the_entry_id_rides_the_line(hv, capsys, monkeypatch):
    """A Monitor can only match text, so the id has to be ON the line for a
    scope to be written against it."""
    mod, C, nodes = hv
    (nodes / "grid.md").write_text(
        PAGE.format(status="running", jobs="999999"), encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    out = run(mod, capsys)
    assert "07.001" in out, out


def test_a_live_job_stays_silent(hv, capsys, monkeypatch):
    mod, C, nodes = hv
    (nodes / "grid.md").write_text(
        PAGE.format(status="running", jobs="424242"), encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, {"424242"}))
    assert run(mod, capsys) == ""


def test_a_page_with_no_running_entry_is_never_probed(hv, capsys, monkeypatch):
    """The fast path: liveness machinery must not run at all — a page whose
    entries are all concluded costs one regex, not a queue probe."""
    mod, C, nodes = hv
    (nodes / "grid.md").write_text(
        PAGE.format(status="analyzed", jobs="999999"), encoding="utf-8")
    def boom():
        raise AssertionError("queue probed on a page with nothing running")
    monkeypatch.setattr(C, "queued_job_ids", boom)
    assert run(mod, capsys) == ""


def test_an_entry_no_active_objective_links_gets_a_dash(hv, capsys, monkeypatch):
    mod, C, nodes = hv
    (nodes / "other.md").write_text(
        PAGE.format(status="running", jobs="999999"), encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    out = run(mod, capsys)
    assert out.startswith("— ·"), "unlinked entry still reported, untagged"


def test_a_stale_snapshot_with_remote_jobs_is_said_out_loud(
        hv, capsys, monkeypatch):
    """The linter SUPPRESSES J3 on a stale snapshot rather than invent one;
    a silent hook would then read as 'all still running' — the failure mode
    of log-freeze-cell-is-truth, one layer up."""
    mod, C, nodes = hv
    (nodes / "grid.md").write_text(
        PAGE.format(status="running", jobs="1724982@H200"), encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, {"1724982"}))  # live: no J3
    # no snapshot file exists -> "missing"
    out = run(mod, capsys)
    assert "queue snapshot missing" in out and "SUSPENDED" in out


def test_exit_code_is_always_zero(hv, capsys, monkeypatch):
    mod, C, nodes = hv
    (nodes / "grid.md").write_text(
        PAGE.format(status="running", jobs="999999"), encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    assert mod.main() == 0


def test_a_linked_worktree_stays_silent(hv, capsys, monkeypatch, tmp_path):
    """A worktree owns no entries to harvest (formal runs launch from main)
    and its project_memory/ is a stale branch-time copy — reading it would
    report J3 for entries whose jobs ended after the branch point."""
    import subprocess
    mod, C, nodes = hv
    (nodes / "grid.md").write_text(
        PAGE.format(status="running", jobs="999999"), encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))   # J3 would fire
    repo = tmp_path / "mainrepo"
    repo.mkdir()
    for cmd in (["git", "init", "-q", "-b", "main", "."],
                ["git", "config", "user.email", "t@example.com"],
                ["git", "config", "user.name", "t"],
                ["git", "commit", "-q", "--allow-empty", "-m", "init"],
                ["git", "worktree", "add", "-q", str(tmp_path / "wt"), "-b", "b"]):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True)
    monkeypatch.setattr(mod, "ROOT", tmp_path / "wt")
    assert mod.main() == 0
    assert capsys.readouterr().out == ""
    # and the main checkout still reports (ROOT back on the record tree)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    assert "J3" in (mod.main(), capsys.readouterr().out)[1]


# --------------------------------------------------------------------------
# The min-age gate — the hook is deliberately slow: fresh finishes are the
# owner's Monitor's business; the broadcast is for the forgotten.
# --------------------------------------------------------------------------


def test_the_gate_holds_a_fresh_j3_and_releases_an_aged_one(
        hv, capsys, monkeypatch):
    import json, time
    mod, C, nodes = hv
    monkeypatch.setattr(mod, "MIN_AGE_MIN", 15)
    (nodes / "grid.md").write_text(
        PAGE.format(status="running", jobs="999999"), encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    assert run(mod, capsys) == "", "first sighting is stamped, not reported"
    state = json.loads(mod.FIRST_SEEN.read_text())
    assert len(state) == 1
    # backdate the stamp past the gate; a second run reports
    mod.FIRST_SEEN.write_text(json.dumps(
        {k: v - 16 * 60 for k, v in state.items()}))
    C._QUEUE_CACHE = (True, set())
    out = run(mod, capsys)
    assert "J3" in out and out.startswith("O07 ·")


def test_a_harvested_entry_is_purged_so_a_refinish_restarts_the_clock(
        hv, capsys, monkeypatch):
    import json
    mod, C, nodes = hv
    monkeypatch.setattr(mod, "MIN_AGE_MIN", 15)
    (nodes / "grid.md").write_text(
        PAGE.format(status="running", jobs="999999"), encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    run(mod, capsys)                                     # stamps it
    (nodes / "grid.md").write_text(
        PAGE.format(status="analyzed", jobs="999999"), encoding="utf-8")
    C._QUEUE_CACHE = (True, set())
    run(mod, capsys)                                     # harvested: leaves J3 set
    assert json.loads(mod.FIRST_SEEN.read_text()) == {}, "stamp purged"


def test_min_age_zero_skips_the_state_file(hv, capsys, monkeypatch):
    mod, C, nodes = hv
    monkeypatch.setattr(mod, "MIN_AGE_MIN", 0)
    (nodes / "grid.md").write_text(
        PAGE.format(status="running", jobs="999999"), encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    assert "J3" in run(mod, capsys)
    assert not mod.FIRST_SEEN.exists(), "the Monitor path writes no state"


# --------------------------------------------------------------------------
# --hook mode — the trigger is dumb; this file owns the whole payload.
# --------------------------------------------------------------------------


def test_hook_payload_is_json_with_the_preamble(hv, capsys, monkeypatch):
    import json as J
    mod, C, nodes = hv
    monkeypatch.setattr(mod, "MIN_AGE_MIN", 0)
    (nodes / "grid.md").write_text(
        PAGE.format(status="running", jobs="999999"), encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    monkeypatch.setattr(sys, "argv", ["harvest_check.py", "--hook"])
    assert mod.main() == 0
    payload = J.loads(capsys.readouterr().out)
    ctx = payload["hookSpecificOutput"]["additionalContext"]
    assert payload["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
    assert "READ-ONLY" in ctx and "J3" in ctx


def test_hook_mode_is_silent_when_quiet(hv, capsys, monkeypatch):
    mod, C, nodes = hv
    (nodes / "grid.md").write_text(
        PAGE.format(status="analyzed", jobs="999999"), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["harvest_check.py", "--hook"])
    assert mod.main() == 0
    assert capsys.readouterr().out == ""


def test_the_preamble_minute_count_is_the_constant(hv, monkeypatch):
    """The quoted '15+ min' once lived in hooks.json's jq string, free to
    drift from MIN_AGE_MIN; derived, it cannot."""
    mod, C, nodes = hv
    monkeypatch.setattr(mod, "MIN_AGE_MIN", 42)
    assert "42+ min" in mod.preamble()


def test_the_hook_wiring_is_dumb():
    """Doctrine text lives in the script, never in the trigger — the exact
    coupling 0.13.40 had to edit a jq string inside JSON to change."""
    import json as J
    hooks = J.loads((SCRIPTS.parent / "hooks" / "hooks.json").read_text())
    cmds = [h["command"]
            for grp in hooks["hooks"]["UserPromptSubmit"] for h in grp["hooks"]]
    harvest = [c for c in cmds if "hook_dispatch.py" in c and " harvest" in c]
    assert len(harvest) == 1
    for word in ("READ-ONLY", "harvested", "orphan", "additionalContext"):
        assert word not in harvest[0], f"doctrine/payload text `{word}` in the trigger"


# --------------------------------------------------------------------------
# --for — the Monitor's scope, computed by the script, never a frozen grep.
# --------------------------------------------------------------------------

def test_for_admits_the_objectives_own_line(hv, capsys, monkeypatch):
    mod, C, nodes = hv
    (nodes / "grid.md").write_text(
        PAGE.format(status="running", jobs="999999"), encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    out = run(mod, capsys, "--min-age", "0", "--for", "O07")
    assert "07.001" in out


def test_for_drops_another_objectives_line(hv, capsys, monkeypatch):
    """An unharvested line repeats every poll; on a shared node, matching
    another loop's lines is how a watcher floods itself into the rate limit."""
    mod, C, nodes = hv
    (nodes / "grid.md").write_text(
        PAGE.format(status="running", jobs="999999"), encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    out = run(mod, capsys, "--min-age", "0", "--for", "O99")
    assert out == ""


def test_for_admits_an_unattributed_line_in_a_plan_node(hv, capsys, monkeypatch):
    """The launched-before-its-Plan-line case: attributes to nobody, but lives
    in a node the objective's Plan already works in — the one gap every
    objective-keyed match shares, by construction."""
    mod, C, nodes = hv
    (nodes / "orphan.md").write_text(
        PAGE.replace("07.001", "07.019").format(status="running", jobs="999999"),
        encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    unscoped = run(mod, capsys, "--min-age", "0")
    assert unscoped.startswith("— ·"), unscoped
    out = run(mod, capsys, "--min-age", "0", "--for", "O07")
    assert "07.019" in out, out


def test_for_drops_an_unattributed_line_in_a_foreign_node(hv, capsys, monkeypatch):
    mod, C, nodes = hv
    foreign = nodes.parent / "some_other_node"
    foreign.mkdir()
    (foreign / "grid.md").write_text(
        PAGE.replace("07.001", "31.001").format(status="running", jobs="999999"),
        encoding="utf-8")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    out = run(mod, capsys, "--min-age", "0", "--for", "O07")
    assert out == ""


def test_the_name_match_takes_the_longest_candidate(hv):
    """`gate A` and `gate A' is running — twice` can both start the same J3
    message; only the longest is the actual heading the message was built
    from."""
    mod, C, nodes = hv
    entries = {"x": "", "x' is running — twice": ""}
    err = "J3 entry 'x' is running — twice' is running but none of its jobs (1..) are in squeue"
    name = max((n for n in entries
                if err.startswith(f"J3 entry '{n}' is running")), key=len, default="")
    assert name == "x' is running — twice"
