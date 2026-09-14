"""record_submit: the launcher's post-submit record write.

A failed record means a job running with no page row — the record's most
fragile state, and the one an exit-3 launcher retry turns into a duplicate GPU
job. These are the first tests this script has had; the case that motivated
them is node.md, which a year-old design decision excluded from resolution
long after v3 made it an entries-only page whose validation entries launch
real background jobs.
"""

import importlib.util
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
- **Status:** open
- **Date:** 2026-07-21 10:00
- **Motivation:** The parent's grid found "LER 2.8e-3 at d5"; does LayerNorm move it?
- **Recipe:** {hidden_dim: 32, seed: 0}
"""

NODE_MD = """---
node: tanner_gnn_ln
task: validate the frozen impl — the two-code gate, then each in-place edit
---

### Entry: ln gate on repetition d3 p0.05
- **Id:** 07.006
- **Status:** closed
- **Date:** 2026-07-20 10:00
- **Motivation:** The gate found "0.00725"; does the impl reproduce it?
- **Recipe:** {seed: 0}
- **Facts:** We ran the gate cell; evidence inline.

  | LER | 0.00715 |
  |---|---|

- **Conclusion:** The result shows it reproduces — answers the motivation.

### Entry: chunked evaluation validation
- **Id:** 07.007
- **Status:** open
- **Date:** 2026-07-21 11:00
- **Motivation:** [the gate](#x) `07.006` found "0.00715"; does chunking keep it?
- **Recipe:** {seed: 0}
"""


@pytest.fixture()
def rs(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "record_submit_under_test", SCRIPTS / "record_submit.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    nodes = tmp_path / "project_memory" / "nodes"
    (nodes / "tanner_gnn_ln").mkdir(parents=True)
    (nodes / "tanner_gnn_ln" / "grid.md").write_text(PAGE, encoding="utf-8")
    (nodes / "tanner_gnn_ln" / "node.md").write_text(NODE_MD, encoding="utf-8")
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "NODES_DIR", nodes)
    return mod


def test_a_task_page_resolves(rs):
    assert rs.task_page("tanner_gnn_ln/grid").name == "grid.md"


def test_node_md_resolves_like_any_other_page(rs):
    """The v3 contract says node.md is entries only; its validations launch
    real jobs, so '<node>/node' must resolve — the old refusal left every such
    launch recorded by hand after an exit 3."""
    assert rs.task_page("tanner_gnn_ln/node").name == "node.md"


def test_a_missing_page_still_refuses(rs):
    assert rs.task_page("tanner_gnn_ln/ghost") is None
    ok, msg, _ = rs.record("tanner_gnn_ln/ghost", "x", "1", "/tmp/x.log")
    assert not ok and "NOT recorded" in msg


def test_recording_onto_a_node_md_validation(rs, tmp_path):
    log = tmp_path / "experiments" / "run.log"
    log.parent.mkdir(); log.write_text("")
    ok, msg, eid = rs.record("tanner_gnn_ln/node", "chunked evaluation validation",
                             "990001@H200", str(log))
    assert ok, msg
    assert eid == "07.007", "the entry id feeds the commit's `Entry:` trailer"
    text = (tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln"
            / "node.md").read_text(encoding="utf-8")
    gate, validation = text.split("### Entry: chunked evaluation validation")
    assert "- **Jobs:** 990001@H200" in validation
    assert "[log](" in validation
    assert "- **Status:** running" in validation
    assert "- **Jobs:**" not in gate, "the gate entry must be untouched"
    assert "- **Status:** closed" in gate


def test_a_second_job_appends_to_the_jobs_field(rs, tmp_path):
    log = tmp_path / "run.log"; log.write_text("")
    rs.record("tanner_gnn_ln/node", "chunked evaluation validation", "1@h", str(log))
    ok, *_ = rs.record("tanner_gnn_ln/node", "chunked evaluation validation", "2@h", str(log))
    assert ok
    text = (tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln"
            / "node.md").read_text(encoding="utf-8")
    assert "- **Jobs:** 1@h, 2@h" in text


def test_an_unknown_entry_refuses(rs, tmp_path):
    ok, msg, _ = rs.record("tanner_gnn_ln/node", "no such entry", "1", "/tmp/x.log")
    assert not ok and "no entry" in msg


def test_a_suffix_id_is_not_a_duplicate(rs, tmp_path):
    """`724982 in '- **Jobs:** 1724982'` is True as a substring — the old test,
    which reported 'recorded' and wrote nothing. Ids are compared exactly."""
    log = tmp_path / "run.log"; log.write_text("")
    rs.record("tanner_gnn_ln/grid", "ln at d5 p0.06", "1724982@H200", str(log))
    ok, msg, _ = rs.record("tanner_gnn_ln/grid", "ln at d5 p0.06", "724982@H200", str(log))
    assert ok, msg
    text = (tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln"
            / "grid.md").read_text(encoding="utf-8")
    assert "- **Jobs:** 1724982@H200, 724982@H200" in text


def test_the_same_id_is_still_a_noop(rs, tmp_path):
    log = tmp_path / "run.log"; log.write_text("")
    rs.record("tanner_gnn_ln/grid", "ln at d5 p0.06", "1724982@H200", str(log))
    rs.record("tanner_gnn_ln/grid", "ln at d5 p0.06", "1724982@H200", str(log))
    text = (tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln"
            / "grid.md").read_text(encoding="utf-8")
    assert text.count("1724982") == 2, "field + log line, once each"


def test_an_empty_jobs_field_is_filled_not_duplicated(rs, tmp_path):
    """A bare `- **Jobs:**` (no trailing space) once failed the field regex, so
    a SECOND Jobs field was inserted — two fields, and every later reader free
    to pick the wrong one (J5/J6 exist because of the shape this produced)."""
    page = tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln" / "grid.md"
    page.write_text(page.read_text(encoding="utf-8").replace(
        "- **Status:** open", "- **Status:** open\n- **Jobs:**"), encoding="utf-8")
    log = tmp_path / "run.log"; log.write_text("")
    ok, msg, _ = rs.record("tanner_gnn_ln/grid", "ln at d5 p0.06", "31@h", str(log))
    assert ok, msg
    text = page.read_text(encoding="utf-8")
    assert text.count("**Jobs:**") == 1
    assert "- **Jobs:** 31@h" in text


def test_the_log_line_sits_under_the_jobs_field(rs, tmp_path):
    """E12 bans a loose line between fields; E13 bans a standalone
    `Job <id> — [log]` stanza inside Facts. The log link must land as an
    indented continuation of `- **Jobs:**` — legal to both, and the id stays
    on the field's first line where `field()` reads it."""
    import importlib.util as ilu
    spec = ilu.spec_from_file_location("cnp_under_test", SCRIPTS / "check_node_page.py")
    cnp = ilu.module_from_spec(spec)
    sys.modules[spec.name] = cnp
    spec.loader.exec_module(cnp)

    log = tmp_path / "run.log"; log.write_text("")
    rs.record("tanner_gnn_ln/node", "chunked evaluation validation", "77@h", str(log))
    text = (tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln"
            / "node.md").read_text(encoding="utf-8")
    body = text.split("### Entry: chunked evaluation validation")[1]
    assert cnp.loose_lines(body) == [], "the log line is loose (E12)"
    assert not cnp.JOB_STANZA_RE.findall(cnp.field_block(body, "Facts")), \
        "the log line landed in Facts (E13)"
    assert "77@h" in cnp.field(body, "Jobs"), "the id left the field's first line"
    assert "[log](" in body


def test_check_preflight_resolves_without_writing(rs, tmp_path):
    found = rs.find_entry("tanner_gnn_ln/grid", "ln at d5 p0.06")
    assert not isinstance(found, str)
    assert isinstance(rs.find_entry("tanner_gnn_ln/grid", "typo'd entry"), str)
    assert isinstance(rs.find_entry("tanner_gnn_ln/ghost", "x"), str)
    text = (tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln"
            / "grid.md").read_text(encoding="utf-8")
    assert "Jobs" not in text, "--check must not write"


# --------------------------------------------------------------------------
# The no-Plan-line launch note — _on_no_active_plan.
# --------------------------------------------------------------------------

OBJ_LINKING = """---
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
  - [ln at d5 p0.06](../nodes/tanner_gnn_ln/grid.md#entry-ln-at-d5-p006) `07.001` — the probe

## Verdict

**Open.** 0 entries await review.
"""


def _objdir(rs, tmp_path, text=None):
    d = tmp_path / "project_memory" / "objectives"
    d.mkdir(exist_ok=True)
    if text is not None:
        (d / "ln.md").write_text(text, encoding="utf-8")
    return d


def test_a_plan_linked_entry_raises_no_note(rs, tmp_path):
    _objdir(rs, tmp_path, OBJ_LINKING)
    page = tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln" / "grid.md"
    assert rs._on_no_active_plan(page, "07.001") is False


def test_an_unlinked_entry_raises_the_note(rs, tmp_path):
    """gate B / gate C: launched, recorded, and on no Plan — every
    objective-scoped watcher blind to them, silently."""
    _objdir(rs, tmp_path, OBJ_LINKING.replace(
        "../nodes/tanner_gnn_ln/grid.md", "../nodes/other_node/grid.md"))
    page = tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln" / "grid.md"
    assert rs._on_no_active_plan(page, "07.001") is True


def test_a_closed_objectives_link_does_not_count(rs, tmp_path):
    """The closed page still links the entry, but a closed Plan is history —
    only an ACTIVE watcher can miss anything. A second active objective
    exists so the note has an audience at all."""
    d = _objdir(rs, tmp_path, OBJ_LINKING.replace("status: active", "status: closed"))
    (d / "other.md").write_text(
        OBJ_LINKING.replace("id: O07", "id: O08").replace(
            "../nodes/tanner_gnn_ln/grid.md", "../nodes/elsewhere/x.md"),
        encoding="utf-8")
    page = tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln" / "grid.md"
    assert rs._on_no_active_plan(page, "07.001") is True


def test_no_active_objective_anywhere_stays_silent(rs, tmp_path):
    """No active objective = no objective-scoped watcher to miss the entry;
    the note would be noise on a project running standalone probes."""
    _objdir(rs, tmp_path, OBJ_LINKING.replace("status: active", "status: closed"))
    page = tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln" / "grid.md"
    assert rs._on_no_active_plan(page, "07.001") is False


def test_no_objectives_dir_stays_silent(rs, tmp_path):
    """The note is a courtesy, never a gate — any doubt reads as linked."""
    page = tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln" / "grid.md"
    assert rs._on_no_active_plan(page, "07.001") is False


# --- the launch binds its phase, or it does not launch ---------------------
#
# Reported three ways by one session: a phase showing nothing under it, a
# harvest scope claiming another objective's entry, and an entry the machine
# knew about that the page did not. One cause — the Plan line was left to a
# turn after the launch, and a long-running job swallows that turn. The script
# already wrote the job id, the log link and the status; the binding is the one
# half that was still a reminder ("this is a courtesy note, never a gate").
#
# The session supplies the two things only it knows — which phase, and what the
# entry does for it. Everything else on the line is derived.

OBJ = """---
id: O07
status: active
created: 2026-07-20
budget: "4 GPU-hours per run"
wake-me-if: "success met"
---

## Goal

Does LayerNorm move the grid?

## Plan

- [ ] **P1 — does LayerNorm move the LER at d5?** (~20 min)

- [ ] **P2 — and at d7?** (~20 min · needs: P1)
  - [an earlier probe](../nodes/tanner_gnn_ln/grid.md#entry-ln-at-d5-p006) `07.001` — context
  - ▶ Nothing yet.

## Verdict

Running.
"""


@pytest.fixture()
def rs_obj(rs, tmp_path):
    objs = tmp_path / "project_memory" / "objectives"
    objs.mkdir(parents=True)
    (objs / "ln.md").write_text(OBJ, encoding="utf-8")
    return rs


def _plan(tmp_path):
    return (tmp_path / "project_memory" / "objectives" / "ln.md").read_text()


def test_the_plan_line_lands_under_the_named_phase(rs_obj, tmp_path):
    obj, oid, pnum = rs_obj.resolve_objective(
        tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln" / "grid.md", "P1")
    assert (oid, pnum) == ("O07", "P1")
    err = rs_obj.write_plan_line(
        obj, pnum,
        tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln" / "grid.md",
        "ln at d5 p0.06", "07.001", "the admissibility test")
    assert err == "", err
    text = _plan(tmp_path)
    p1 = text.split("- [ ] **P1")[1].split("- [ ] **P2")[0]
    assert "`07.001` — the admissibility test" in p1
    assert "grid.md#entry-ln-at-d5-p006" in p1


def test_the_line_goes_before_the_reading(rs_obj, tmp_path):
    """▶ stays the block's last line — it is the phase's conclusion, and an
    entry line after it reads as evidence that arrived too late to count."""
    obj, _, _ = rs_obj.resolve_objective(
        tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln" / "grid.md", "P2")
    rs_obj.write_plan_line(
        obj, "P2",
        tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln" / "node.md",
        "chunked evaluation validation", "07.007", "the chunking check")
    p2 = _plan(tmp_path).split("- [ ] **P2")[1]
    assert p2.index("`07.007`") < p2.index("▶"), p2


def test_writing_the_same_line_twice_is_a_no_op(rs_obj, tmp_path):
    obj, _, _ = rs_obj.resolve_objective(
        tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln" / "grid.md", "P2")
    page = tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln" / "grid.md"
    before = _plan(tmp_path)
    rs_obj.write_plan_line(obj, "P2", page, "ln at d5 p0.06", "07.001", "again")
    assert _plan(tmp_path) == before, "already linked — must not duplicate"


def test_an_unknown_phase_is_reported_not_guessed(rs_obj, tmp_path):
    obj, _, _ = rs_obj.resolve_objective(
        tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln" / "grid.md", "P1")
    err = rs_obj.write_plan_line(
        obj, "P9",
        tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln" / "grid.md",
        "ln at d5 p0.06", "07.001", "x")
    assert "no phase P9" in err


def test_a_missing_phase_argument_refuses(rs_obj):
    assert rs_obj.resolve_objective(Path("x"), None) == "no --phase given"


def test_two_objectives_in_play_are_not_guessed_between(rs_obj, tmp_path):
    """Guessing the owner is what the page-scoped heuristics did. The session
    knows; it is asked to say."""
    objs = tmp_path / "project_memory" / "objectives"
    (objs / "other.md").write_text(OBJ.replace("id: O07", "id: O08"),
                                   encoding="utf-8")
    res = rs_obj.resolve_objective(tmp_path / "project_memory" / "nodes"
                                   / "tanner_gnn_ln" / "ghost.md", "P1")
    assert isinstance(res, str) and "O07" in res and "O08" in res


def test_parse_binding_strips_the_flags():
    pos, phase, role, none = rs_parse(["a", "b", "c", "d", "--phase", "O07/P1",
                                       "--role", "the test"])
    assert pos == ["a", "b", "c", "d"]
    assert (phase, role, none) == ("O07/P1", "the test", False)


def rs_parse(argv):
    spec = importlib.util.spec_from_file_location(
        "rs_parse_mod", SCRIPTS / "record_submit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.parse_binding(argv)
