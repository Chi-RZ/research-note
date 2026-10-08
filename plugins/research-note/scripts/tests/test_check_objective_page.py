"""Tests for check_objective_page — record v3: the Goal/Plan/Verdict route."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import check_node_page as N
import check_objective_page as O


@pytest.fixture(autouse=True)
def _reset_descendants():
    O._DESCENDANTS = None
    yield
    O._DESCENDANTS = None


TASK_PAGE = """---
node: tanner_gnn_ln
task: the d grid
---

### Entry: ln at d5 p0.06
- **Id:** 07.001
- **Status:** closed
- **Date:** 2026-08-13 10:00
- **Motivation:** The parent found "2.8e-3"; does d5 hold it?
- **Conclusion:** The result shows d5 holds, because the draw sits inside the spread — answers the motivation.
"""

OBJ = """---
id: O03
status: active
created: 2026-08-13
budget: "4 GPU-hours per run"
wake-me-if: "success met | budget exceeded"
---

## Goal

Find the knee. Target:

| p | 0.02 |
|---|---|
| ref | 0.0029 |

## Plan

- [x] **P1 — does the gate hold?** (~20 min)
  - [ln at d5 p0.06](../nodes/tanner_gnn_ln/grid.md#entry-ln-at-d5-p006) `07.001` — the admissibility test (2026-08-13)
  - ▶ The gate holds, so the axis is usable.

- [ ] **P2 — where does the knee sit?** (35 GPU-h · needs: P1)

## Verdict

The route is running.
"""


def project(tmp_path, obj_text=OBJ, task_text=TASK_PAGE):
    pm = tmp_path / "project_memory"
    (pm / "objectives").mkdir(parents=True)
    node = pm / "nodes" / "tanner_gnn_ln"
    node.mkdir(parents=True)
    (node / "grid.md").write_text(task_text)
    p = pm / "objectives" / "knee.md"
    p.write_text(obj_text)
    return p


@pytest.fixture()
def obj(tmp_path, monkeypatch):
    p = project(tmp_path)
    monkeypatch.setattr(O, "ROOT", tmp_path)
    monkeypatch.setattr(O, "OBJ_DIR", tmp_path / "project_memory" / "objectives")
    return p


def relint(p, text):
    p.write_text(text)
    return O.lint(p)


def test_a_well_formed_page_lints_clean(obj):
    assert O.lint(obj) == []


# --- O1 --------------------------------------------------------------------

def test_o1_missing_key(obj):
    errs = relint(obj, OBJ.replace('wake-me-if: "success met | budget exceeded"\n', ""))
    assert any(e.startswith("O1") and "wake-me-if" in e for e in errs)


def test_o1_id_format(obj):
    errs = relint(obj, OBJ.replace("id: O03", "id: knee-3"))
    assert any(e.startswith("O1") and "O<nn>" in e for e in errs)


def test_o1_status_set_is_active_or_closed(obj):
    errs = relint(obj, OBJ.replace("status: active", "status: paused"))
    assert any(e.startswith("O1") and "paused" in e for e in errs)


# --- O10 -------------------------------------------------------------------

def test_o10_attention_on_a_closed_objective_fires(obj):
    text = OBJ.replace("status: active", "status: closed").replace(
        "created: 2026-08-13", "created: 2026-08-13\nattention: waiting on review")
    errs = relint(obj, text)
    assert any(e.startswith("O10") for e in errs)


def test_o10_attention_on_an_active_objective_is_legal(obj):
    text = OBJ.replace("created: 2026-08-13",
                       "created: 2026-08-13\nattention: src change needs approval")
    errs = relint(obj, text)
    assert not any(e.startswith("O10") for e in errs)


# --- O2 --------------------------------------------------------------------

def test_o2_missing_section(obj):
    errs = relint(obj, OBJ.replace("## Verdict\n\nThe route is running.\n", ""))
    assert any(e.startswith("O2") and "Verdict" in e for e in errs)


def test_o2_extra_section_fires(obj):
    errs = relint(obj, OBJ + "\n## Analysis\n\nprose\n")
    assert any(e.startswith("O2") and "Analysis" in e for e in errs)


def test_o2_sections_out_of_order(obj):
    text = OBJ.replace("## Goal", "## ZGoal")
    text = text.replace("## Verdict", "## Goal").replace("## ZGoal", "## Verdict")
    errs = relint(obj, text)
    assert any(e.startswith("O2") and "order" in e for e in errs)


# --- O3 --------------------------------------------------------------------

def test_o3_dangling_link(obj):
    errs = relint(obj, OBJ.replace("../nodes/tanner_gnn_ln/grid.md",
                                   "../nodes/tanner_gnn_ln/ghost.md"))
    assert any(e.startswith("O3") and "ghost.md" in e for e in errs)


def test_o3_bad_entry_anchor(obj):
    errs = relint(obj, OBJ.replace("#entry-ln-at-d5-p006", "#entry-no-such"))
    assert any(e.startswith("O3") and "anchor" in e for e in errs)


def test_o3_cited_id_must_match_the_entrys_id(obj):
    errs = relint(obj, OBJ.replace("`07.001`", "`07.009`"))
    assert any(e.startswith("O3") and "07.009" in e for e in errs)


# --- O9 --------------------------------------------------------------------

def test_o9_figure_in_the_plan_fires(obj):
    errs = relint(obj, OBJ.replace(
        "  - ▶ The gate holds, so the axis is usable.",
        "  - ▶ The gate holds.\n  - ![the gate](../figs/gate.png)"))
    assert any(e.startswith("O9") and "figure" in e for e in errs)


def test_o9_table_in_the_verdict_fires(obj):
    errs = relint(obj, OBJ.replace("The route is running.",
                                   "| p | LER |\n|---|---|\n| 0.02 | 0.003 |"))
    assert any(e.startswith("O9") and "table" in e for e in errs)


# --- O5 --------------------------------------------------------------------

def test_o5_unparseable_phase_header(obj):
    errs = relint(obj, OBJ.replace(
        "- [ ] **P2 — where does the knee sit?** (35 GPU-h · needs: P1)",
        "- [ ] P2 the knee, somewhere"))
    assert any(e.startswith("O5") and "parse" in e for e in errs)


def test_o5_needs_must_name_a_phase(obj):
    errs = relint(obj, OBJ.replace("needs: P1", "needs: P9"))
    assert any(e.startswith("O5") and "P9" in e for e in errs)


def test_o5_duplicate_phase_number(obj):
    errs = relint(obj, OBJ.replace("**P2 — where does the knee sit?**",
                                   "**P1 — where does the knee sit?**"))
    assert any(e.startswith("O5") and "more than once" in e for e in errs)


def test_o5_dependency_cycle(obj):
    text = OBJ.replace("(~20 min)", "(~20 min · needs: P2)")
    errs = relint(obj, text)
    assert any(e.startswith("O5") and "cycle" in e for e in errs)


# --- O8 --------------------------------------------------------------------

def _analyzed_task(tmp_path):
    node = tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln"
    (node / "grid.md").write_text(
        TASK_PAGE.replace("- **Status:** closed", "- **Status:** analyzed"))


def test_o8_missing_count_fires_when_an_entry_awaits(obj, tmp_path):
    _analyzed_task(tmp_path)
    errs = O.lint(obj)
    assert any(e.startswith("O8") and "no awaiting-review" in e for e in errs)


def test_o8_stale_count_fires(obj, tmp_path):
    _analyzed_task(tmp_path)
    errs = relint(obj, OBJ.replace("The route is running.",
                                   "The route is running. 3 entries await review."))
    assert any(e.startswith("O8") and "3" in e for e in errs)


def test_o8_matching_count_is_silent(obj, tmp_path):
    _analyzed_task(tmp_path)
    errs = relint(obj, OBJ.replace("The route is running.",
                                   "The route is running. 1 entries await review."))
    assert not any(e.startswith("O8") for e in errs)


def test_o8_accepts_one_entry_written_in_english(obj, tmp_path):
    """`1 entry awaits review` is the same claim as `1 entries await review`.

    The check read only `await`, so the grammatical singular matched nothing and
    fell to the missing-count branch — which then told the writer to spell it the
    one way English does not. A count check that can only be satisfied
    ungrammatically teaches every page to carry the error.
    """
    _analyzed_task(tmp_path)
    errs = relint(obj, OBJ.replace("The route is running.",
                                   "The route is running. 1 entry awaits review."))
    assert not any(e.startswith("O8") for e in errs)


def test_o8_stale_count_still_fires_when_written_in_the_singular(obj, tmp_path):
    """Accepting the spelling must not stop the count from being CHECKED."""
    _analyzed_task(tmp_path)
    errs = relint(obj, OBJ.replace("The route is running.",
                                   "The route is running. 3 entry awaits review."))
    assert any(e.startswith("O8") and "3" in e for e in errs)


# --- O6 --------------------------------------------------------------------

FOLLOW_UP = """
### Entry: follow-up probe
- **Id:** 07.002
- **Status:** open
- **Date:** 2026-08-14 10:00
- **Motivation:** [ln at d5 p0.06](./grid.md#entry-ln-at-d5-p006) found "d5 holds"; what does d7 give?
"""


def test_o6_a_spawned_probe_on_no_plan_fires(obj, tmp_path):
    node = tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln"
    (node / "grid.md").write_text(TASK_PAGE + FOLLOW_UP)
    errs = O.lint(obj)
    assert any(e.startswith("O6") and "follow-up-probe" in e for e in errs)


def test_o6_discharged_when_the_probe_joins_a_phase(obj, tmp_path):
    node = tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln"
    (node / "grid.md").write_text(TASK_PAGE + FOLLOW_UP)
    text = OBJ.replace(
        "- [ ] **P2 — where does the knee sit?** (35 GPU-h · needs: P1)",
        "- [ ] **P2 — where does the knee sit?** (35 GPU-h · needs: P1)\n"
        "  - [follow-up probe](../nodes/tanner_gnn_ln/grid.md#entry-follow-up-probe)"
        " `07.002` — the next point")
    errs = relint(obj, text)
    assert not any(e.startswith("O6") for e in errs)


def test_o6_a_closed_objective_obligates_nothing(obj, tmp_path):
    node = tmp_path / "project_memory" / "nodes" / "tanner_gnn_ln"
    (node / "grid.md").write_text(TASK_PAGE + FOLLOW_UP)
    errs = relint(obj, OBJ.replace("status: active", "status: closed"))
    assert not any(e.startswith("O6") for e in errs)


# --- O7 --------------------------------------------------------------------

def test_o7_a_reading_older_than_a_changed_conclusion_fires(obj, monkeypatch):
    then = TASK_PAGE.replace(
        "The result shows d5 holds, because the draw sits inside the spread",
        "The result shows d5 fails, because the draw sits outside the spread")
    monkeypatch.setattr(O, "blob_on", lambda pg, date: then)
    errs = O.lint(obj)
    assert any(e.startswith("O7") for e in errs)


def test_o7_silent_when_the_conclusion_is_unchanged(obj, monkeypatch):
    monkeypatch.setattr(O, "blob_on", lambda pg, date: TASK_PAGE)
    assert not any(e.startswith("O7") for e in O.lint(obj))


# --- O4 --------------------------------------------------------------------

def test_o4_goal_change_fires_against_the_committed_version(obj, monkeypatch):
    monkeypatch.setattr(O, "git_show", lambda p, rev="HEAD":
                        OBJ.replace("Find the knee.", "Find the cliff."))
    errs = O.lint(obj)
    assert any(e.startswith("O4") for e in errs)


def test_o4_silent_when_the_goal_matches_git(obj, monkeypatch):
    monkeypatch.setattr(O, "git_show", lambda p, rev="HEAD": OBJ)
    assert not any(e.startswith("O4") for e in O.lint(obj))


# --- M1 / CLI --------------------------------------------------------------

def test_m1_fires_only_where_the_project_declared_a_language(obj, tmp_path, monkeypatch):
    text = OBJ.replace("The route is running.", "路线运行中。")
    monkeypatch.setattr(N, "ROOT", tmp_path)
    errs = relint(obj, text)
    assert not any(e.startswith("M1") for e in errs)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "framework.json").write_text(
        '{"framework": "research-note", "record": "v3", "record_language": "en"}')
    errs = O.lint(obj)
    assert any(e.startswith("M1") for e in errs)


def test_main_returns_3_on_a_record_version_mismatch(obj, tmp_path, monkeypatch, capsys):
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "framework.json").write_text(
        '{"framework": "research-note", "record": "v2.4"}')
    monkeypatch.setattr(N, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_objective_page.py", str(obj)])
    rc = O.main()
    out = capsys.readouterr().out
    assert rc == 3
    assert "FW" in out


def test_main_lints_the_objective_dir_by_default(obj, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["check_objective_page.py"])
    rc = O.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "knee.md: OK" in out


def test_o11_a_narrative_verdict_fires(obj):
    long = "\n".join(f"Sentence {i} of the argument." for i in range(12))
    errs = relint(obj, OBJ.replace("The route is running.", long))
    assert any(e.startswith("O11") for e in errs)


# --- O12 ---------------------------------------------------------------------

def test_o12_a_duplicate_id_across_pages_fires(obj, tmp_path):
    """O1 sees one file at a time, so two pages both declaring the same id were
    both green — while trailers, needs: edges and the roster all key on it."""
    twin = obj.parent / "twin.md"
    twin.write_text(obj.read_text().replace("knee", "twin"), encoding="utf-8")
    errs = O.duplicate_id_errors()
    assert len(errs) == 1
    page, msg = errs[0]
    assert page.name == "twin.md" and msg.startswith("O12") and "O03" in msg


def test_o12_distinct_ids_are_clean(obj):
    twin = obj.parent / "twin.md"
    twin.write_text(obj.read_text().replace("id: O03", "id: O04"),
                    encoding="utf-8")
    assert O.duplicate_id_errors() == []


# --------------------------------------------------------------------------
# The git caches — O7 asks the same question dozens of times per run.
# --------------------------------------------------------------------------

def test_blob_on_asks_git_once_per_page_and_date(monkeypatch, tmp_path):
    """Each miss is TWO subprocesses, the first a path-filtered `rev-list`
    whose cost grows with the commit count. Uncached, a live project spent
    105 s here per dashboard build and blew the fixer's budget every cycle."""
    import check_objective_page as O
    calls = []

    class _R:
        returncode = 0
        stdout = "deadbeef"

    def fake(cmd, **kw):
        calls.append(cmd)
        return _R()

    monkeypatch.setattr(O.subprocess, "run", fake)
    monkeypatch.setattr(O, "ROOT", tmp_path)
    O._REV_CACHE.clear()
    O._BLOB_CACHE.clear()
    page = tmp_path / "project_memory" / "objectives" / "x.md"
    page.parent.mkdir(parents=True)
    page.write_text("x", encoding="utf-8")
    for _ in range(5):
        O.blob_on(page, "2026-08-22")
    assert len(calls) == 2, calls          # one rev-list + one show, then cached
    # a different date is a real rev-list miss — but it resolves to the same
    # commit here, and THAT blob is already cached: the two keys are separate
    # on purpose, and the second layer still pays off
    O.blob_on(page, "2026-08-23")
    assert len(calls) == 3, calls


# --- O13 -------------------------------------------------------------------

def _grid(obj_path):
    return obj_path.parent.parent / "nodes" / "tanner_gnn_ln" / "grid.md"


def test_o13_a_finished_phase_with_an_unticked_box_fires(obj):
    """The observed failure: the ▶ reading written, the box left alone."""
    errs = relint(obj, OBJ.replace("- [x] **P1", "- [ ] **P1"))
    assert any(e.startswith("O13") and "P1" in e and "still `[ ]`" in e for e in errs)


def test_o13_a_ticked_phase_over_an_unconcluded_entry_fires(obj):
    _grid(obj).write_text(TASK_PAGE.replace("**Status:** closed", "**Status:** running"))
    errs = O.lint(obj)                      # P1 is ticked in OBJ
    assert any(e.startswith("O13") and "P1" in e and "running" in e for e in errs)


def test_o13_leaves_a_closed_objective_alone(obj):
    """History. Reopening it to fix bookkeeping helps nobody."""
    errs = relint(obj, OBJ.replace("status: active", "status: closed")
                          .replace("- [x] **P1", "- [ ] **P1"))
    assert not [e for e in errs if e.startswith("O13")]


# --- O14 — the entry the machine knows about and the page does not ---------
#
# Reported by a session that made it repeatedly: a long job creates a gap
# between "I launched" and "I have something to say", and the entry line never
# gets written. O13 is the same failure one step later (every entry concluded,
# box still open) and it fired; nothing watched the earlier half.
#
# Validated against this project's own history before being written: at the
# commit before `memory: O02 — the Verdict catches up, and P5 carries the
# entry it launched`, O14 names exactly the running entry that phase had
# launched, and it is silent at that commit and at every later one.

LAUNCHED = TASK_PAGE + """
### Entry: ln at d7 p0.06
- **Id:** 07.002
- **Status:** running
- **Date:** 2026-08-14 09:00
- **Jobs:** 881204@t6
- **Motivation:** `07.001` found "2.8e-3"; does d7 hold it?
"""


def test_o14_a_launched_entry_in_no_phase_fires(tmp_path, monkeypatch):
    p = project(tmp_path, task_text=LAUNCHED)
    monkeypatch.setattr(O, "ROOT", tmp_path)
    monkeypatch.setattr(O, "OBJ_DIR", tmp_path / "project_memory" / "objectives")
    errs = O.lint(p)
    assert any(e.startswith("O14") and "entry-ln-at-d7-p006" in e for e in errs), errs


def test_o14_is_silent_once_a_phase_names_it(tmp_path, monkeypatch):
    named = OBJ.replace(
        "- [ ] **P2 — where does the knee sit?** (35 GPU-h · needs: P1)",
        "- [ ] **P2 — where does the knee sit?** (35 GPU-h · needs: P1)\n"
        "  - [ln at d7 p0.06](../nodes/tanner_gnn_ln/grid.md#entry-ln-at-d7-p006)"
        " `07.002` — the knee probe")
    p = project(tmp_path, obj_text=named, task_text=LAUNCHED)
    monkeypatch.setattr(O, "ROOT", tmp_path)
    monkeypatch.setattr(O, "OBJ_DIR", tmp_path / "project_memory" / "objectives")
    assert not [e for e in O.lint(p) if e.startswith("O14")], O.lint(p)


def test_o14_ignores_an_entry_that_never_launched(tmp_path, monkeypatch):
    """`Jobs:` non-empty is what makes this precise. Reading, cost accounting
    and work belonging to no route have no jobs, and must not fail a page."""
    p = project(tmp_path, task_text=LAUNCHED.replace("- **Jobs:** 881204@t6\n", ""))
    monkeypatch.setattr(O, "ROOT", tmp_path)
    monkeypatch.setattr(O, "OBJ_DIR", tmp_path / "project_memory" / "objectives")
    assert not [e for e in O.lint(p) if e.startswith("O14")], O.lint(p)


def test_o11_warning_does_not_fail_cli_but_other_errors_do(obj, monkeypatch, capsys):
    obj.write_text(OBJ.replace("The route is running.", "\n".join(["More detail."] * 12)))
    monkeypatch.setattr(sys, "argv", ["check_objective_page.py", str(obj)])
    assert O.main() == 0
    assert "O11" in capsys.readouterr().out
    obj.write_text(obj.read_text().replace("## Plan", "## Extra"))
    assert O.main() == 1


def test_o4_approval_is_bound_to_exact_goal_change(obj, monkeypatch):
    import objective_state as S
    monkeypatch.setattr(O, "git_show", lambda p, rev="HEAD": OBJ)
    obj.write_text(OBJ.replace("Find the knee.", "Find the cliff."))
    S.approve_goal(obj, "User requested switching the target from knee to cliff.")
    assert not any(e.startswith("O4") for e in O.lint(obj))
    obj.write_text(obj.read_text().replace("Find the cliff.", "Find a third target."))
    assert any(e.startswith("O4") for e in O.lint(obj))


def test_o7_review_keeps_reading_but_new_evidence_invalidates_it(obj, monkeypatch):
    import objective_state as S
    old = TASK_PAGE.replace("d5 holds", "d5 fails")
    monkeypatch.setattr(O, "blob_on", lambda pg, date: old)
    assert any(e.startswith("O7") for e in O.lint(obj))
    S.review_phase(obj, "P1", "Checked the correction; the gate reading still holds.")
    assert "▶ The gate holds, so the axis is usable." in obj.read_text()
    assert not any(e.startswith("O7") for e in O.lint(obj))
    task = obj.parent.parent / "nodes/tanner_gnn_ln/grid.md"
    task.write_text(task.read_text().replace("— answers the motivation.", "— answers the motivation.\n  A newly discovered limitation applies."))
    assert any(e.startswith("O7") for e in O.lint(obj))


def test_o8_generated_count_is_deduplicated_and_preserves_verdict(obj):
    import objective_state as S
    task = obj.parent.parent / "nodes/tanner_gnn_ln/grid.md"
    task.write_text(TASK_PAGE.replace("Status:** closed", "Status:** analyzed"))
    S.sync_count(obj)
    assert "The route is running." in obj.read_text()
    assert "1 entry awaits review" in obj.read_text()
    assert not any(e.startswith("O8") for e in O.lint(obj))
    before = obj.read_bytes()
    S.sync_count(obj)
    assert obj.read_bytes() == before
    task.write_text(TASK_PAGE)
    S.sync_count(obj)
    assert "0 entries await review" in obj.read_text()
    assert not any(e.startswith("O8") for e in O.lint(obj))
