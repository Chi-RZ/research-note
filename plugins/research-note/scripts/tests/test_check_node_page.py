"""Tests for check_node_page — record v3: node.md and task pages, lists of entries."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

import check_node_page as C


@pytest.fixture(autouse=True)
def _no_host_remote(monkeypatch):
    """_remote_queue() reads the HOST project's .claude/hpc.env and .fixer
    snapshot (module-level ROOT), so a project with a live remote HPC leaks its
    REAL queue ids into every queue assertion here. Pinned off; the
    remote-merge tests below patch it back deliberately."""
    monkeypatch.setattr(C, "_remote_queue", lambda: None)


@pytest.fixture(autouse=True)
def _reset_queue_cache():
    """`_QUEUE_CACHE` is module-level state; whichever test runs first would
    otherwise decide the cache for every test after it."""
    C._QUEUE_CACHE = None
    yield
    C._QUEUE_CACHE = None


PAGE = """---
node: tanner_gnn_ln
task: LayerNorm across the surface_code_capacity grid
---

### Entry: ln at d5 p0.06
- **Id:** 07.001
- **Status:** analyzed
- **Date:** 2026-07-21 10:00
- **Jobs:** 64196217
- **Code:** `tanner_gnn_ln@abc1234f`
- **Motivation:** The parent's grid found "LER 2.8e-3 at d5"; does LayerNorm move it at p=0.06?
- **Recipe:** {hidden_dim: 32, rounds: 4, lr: 0.001, steps: 1500, batch: 256, seed: 0}
- **Facts:** We ran the d5 cell, one job at seed 0, and got one LER; evidence [log](../../../experiments/tanner_gnn_ln/scc/logs/slurm-ln-64196217.out).

  | d | LER |
  |---|---|
  | 5 | 2.31e-3 |

- **Conclusion:** The result shows LayerNorm lowers LER, because 2.31e-3 sits 18% below the parent's 2.8e-3 with both draws at the same shots — answers the motivation.
"""

NODE = """---
node: tanner_gnn_ln
task: validate the frozen impl — the gate, then each in-place edit
---

### Entry: gate
- **Id:** 07.001
- **Status:** analyzed
- **Date:** 2026-07-20 09:00
- **Jobs:** 64196200
- **Code:** `tanner_gnn_ln@abc1234f`
- **Motivation:** The parent's grid found "LER 2.8e-3 at d5"; does the fresh impl reproduce it?
- **Recipe:** {hidden_dim: 32, rounds: 4, seed: 0}
- **Facts:** We ran the reference cell and got one draw; evidence [log](../../experiments/tanner_gnn_ln/scc/logs/gate.out).

  | draw | LER |
  |---|---|
  | 1 | 2.79e-3 |

- **Conclusion:** The result shows the impl reproduces the parent cell, because 2.79e-3 is inside the reference history's spread — answers the motivation.

### Entry: perf pass validation
- **Id:** 07.002
- **Status:** analyzed
- **Date:** 2026-07-22 09:00
- **Jobs:** 64196300
- **Code:** `tanner_gnn_ln@bcd2345a`
- **Motivation:** [gate](./node.md#entry-gate) found "2.79e-3 at the reference cell"; does the vectorised decode leave it unchanged?
- **Recipe:** {hidden_dim: 32, rounds: 4, seed: 0}
- **Facts:** We replayed the reference cell on the edited impl and got one draw; evidence [log](../../experiments/tanner_gnn_ln/scc/logs/val.out).

  | draw | LER |
  |---|---|
  | 1 | 2.80e-3 |

- **Conclusion:** The result shows the edit is behaviour-preserving, because 2.80e-3 is inside the reference history's spread — answers the motivation.
"""


def write_page(tmp_path, node, stem, text):
    d = tmp_path / node
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.md").write_text(text)
    return d / f"{stem}.md"


def write_node_md(tmp_path, node, text):
    return write_page(tmp_path, node, "node", text)


# --------------------------------------------------------------------------
# Clean fixtures lint clean.
# --------------------------------------------------------------------------

def test_lint_page_accepts_a_well_formed_page(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", PAGE)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    assert C.lint_page(p) == []


def test_lint_node_accepts_a_gate_and_a_validation(tmp_path, monkeypatch):
    p = write_node_md(tmp_path, "tanner_gnn_ln", NODE)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    assert C.lint_node(p) == []


# --------------------------------------------------------------------------
# N1 / V1 — node.md: no header, entries only, validations name their replay.
# --------------------------------------------------------------------------

def test_n1_node_md_missing_frontmatter_fires(tmp_path, monkeypatch):
    bare = NODE.split("### Entry:", 1)[1]
    p = write_node_md(tmp_path, "tanner_gnn_ln", "### Entry:" + bare)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    assert any(e.startswith("N1") and "frontmatter" in e for e in C.lint_node(p))


def test_n1_node_md_node_key_matches_the_folder(tmp_path, monkeypatch):
    p = write_node_md(tmp_path, "wrong_folder", NODE)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    assert any(e.startswith("N1") and "folder" in e for e in C.lint_node(p))


def test_n1_node_md_without_entries_fires(tmp_path, monkeypatch):
    p = write_node_md(tmp_path, "x", "prose only, no gate\n")
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("N1") and "gate" in e for e in C.lint_node(p))


def test_v1_validation_must_link_the_entry_it_replays(tmp_path, monkeypatch):
    bad = NODE.replace(
        '[gate](./node.md#entry-gate) found "2.79e-3 at the reference cell"',
        'The gate found "2.79e-3 at the reference cell"')
    p = write_node_md(tmp_path, "tanner_gnn_ln", bad)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    errs = C.lint_node(p)
    assert any(e.startswith("V1") for e in errs)


def test_v1_the_gate_itself_is_exempt(tmp_path, monkeypatch):
    p = write_node_md(tmp_path, "tanner_gnn_ln", NODE)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    assert not any(e.startswith("V1") and "'gate'" in e for e in C.lint_node(p))


# --------------------------------------------------------------------------
# P1 — page frontmatter and at-least-one-entry.
# --------------------------------------------------------------------------

def test_p1_missing_task_key(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("task: LayerNorm across the surface_code_capacity grid\n", ""))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("P1") and "task" in e for e in C.lint_page(p))


def test_p1_node_must_match_its_folder(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("node: tanner_gnn_ln", "node: bp_plain"))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("P1") and "folder" in e for e in C.lint_page(p))


def test_p1_env_scoped_page_node_is_the_grandparent(tmp_path, monkeypatch):
    d = tmp_path / "tanner_gnn_ln" / "surface_code_capacity"
    d.mkdir(parents=True)
    (d / "eval.md").write_text(PAGE)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    assert C.lint_page(d / "eval.md") == []


def test_p1_page_needs_at_least_one_entry(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", PAGE.split("### Entry:")[0])
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("P1") and "Entry" in e for e in C.lint_page(p))


# --------------------------------------------------------------------------
# E1 — id: present, formed, unique, in Date order.
# --------------------------------------------------------------------------

def test_e1_missing_id(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("- **Id:** 07.001\n", ""))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E1") and "missing" in e for e in C.lint_page(p))


def test_e1_malformed_id(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("- **Id:** 07.001", "- **Id:** 7.1"))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E1") and "7.1" in e for e in C.lint_page(p))


def _second_entry(id_, date):
    return (f"\n### Entry: a second probe\n"
            f"- **Id:** {id_}\n- **Status:** open\n- **Date:** {date}\n"
            f"- **Code:** `tanner_gnn_ln@abc1234f`\n"
            f"- **Motivation:** [first](./grid.md#entry-ln-at-d5-p006) found "
            f"\"2.31e-3\"; does d7 hold it?\n")


def test_e1_duplicate_id_fires(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE + _second_entry("07.001", "2026-07-22 10:00"))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E1") and "never reused" in e for e in C.lint_page(p))


def test_e1_ids_follow_date_order(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE + _second_entry("07.002", "2026-07-20 10:00"))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E1") and "Date` order" in e for e in C.lint_page(p))


def test_e1_duplicate_entry_heading_fires(tmp_path, monkeypatch):
    dup = PAGE + "\n### Entry: ln at d5 p0.06\n- **Id:** 07.002\n- **Status:** open\n"
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", dup)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E1") and "unique" in e for e in C.lint_page(p))


# --------------------------------------------------------------------------
# E2 — the four states; the two retired states get their own message.
# --------------------------------------------------------------------------

def test_e2_illegal_status(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("- **Status:** analyzed", "- **Status:** finished"))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E2") for e in C.lint_page(p))


@pytest.mark.parametrize("retired", ["blocked", "done-pending-analysis"])
def test_e2_retired_status_names_the_move(tmp_path, monkeypatch, retired):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("- **Status:** analyzed", f"- **Status:** {retired}"))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E2") and "retired" in e for e in C.lint_page(p))


# --------------------------------------------------------------------------
# E3 — date.
# --------------------------------------------------------------------------

def test_e3_missing_date(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("- **Date:** 2026-07-21 10:00\n", ""))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E3") and "missing" in e for e in C.lint_page(p))


def test_e3_malformed_date(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("- **Date:** 2026-07-21 10:00", "- **Date:** July 21"))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E3") and "July 21" in e for e in C.lint_page(p))


# --------------------------------------------------------------------------
# E4 — Code names its commits.
# --------------------------------------------------------------------------

def test_e4_missing_code(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("- **Code:** `tanner_gnn_ln@abc1234f`\n", ""))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E4") and "missing" in e for e in C.lint_page(p))


def test_e4_code_without_a_sha(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("- **Code:** `tanner_gnn_ln@abc1234f`",
                                "- **Code:** the current checkout"))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E4") and "<repo>@<sha>" in e for e in C.lint_page(p))


# --------------------------------------------------------------------------
# E5 — motivation in its form.
# --------------------------------------------------------------------------

def test_e5_missing_motivation(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace('- **Motivation:** The parent\'s grid found "LER 2.8e-3 '
                                'at d5"; does LayerNorm move it at p=0.06?\n', ""))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E5") and "missing" in e for e in C.lint_page(p))


def test_e5_motivation_without_the_form_fires(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace('- **Motivation:** The parent\'s grid found "LER 2.8e-3 '
                                'at d5"; does LayerNorm move it at p=0.06?',
                                "- **Motivation:** earlier results looked odd."))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E5") and "form" in e for e in C.lint_page(p))


def test_e5_an_absence_source_is_accepted(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace('- **Motivation:** The parent\'s grid found "LER 2.8e-3 '
                                'at d5"; does LayerNorm move it at p=0.06?',
                                "- **Motivation:** No entry on this node has run d5 "
                                "under LayerNorm; what does it give?"))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert not any(e.startswith("E5") for e in C.lint_page(p))


# --------------------------------------------------------------------------
# E6 — recipe is a knob map; a run's entry records one.
# --------------------------------------------------------------------------

def test_e6_recipe_must_be_a_knob_map_not_prose(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("- **Recipe:** {hidden_dim: 32, rounds: 4, lr: 0.001, "
                                "steps: 1500, batch: 256, seed: 0}",
                                "- **Recipe:** re-read the saved GS and group bond "
                                "energies by direction"))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E6") and "knob map" in e for e in C.lint_page(p))


def test_e6_an_entry_with_jobs_needs_a_recipe(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("- **Recipe:** {hidden_dim: 32, rounds: 4, lr: 0.001, "
                                "steps: 1500, batch: 256, seed: 0}\n", ""))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E6") and "no `Recipe:`" in e for e in C.lint_page(p))


def test_e6_recipe_is_optional_for_a_zero_job_entry(tmp_path, monkeypatch):
    text = PAGE.replace("- **Recipe:** {hidden_dim: 32, rounds: 4, lr: 0.001, "
                        "steps: 1500, batch: 256, seed: 0}\n", "").replace(
                        "- **Jobs:** 64196217\n", "")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert not any(e.startswith("E6") for e in C.lint_page(p))


# --------------------------------------------------------------------------
# E7 — Facts: the sentence, the table, the evidence links (once concluded).
# --------------------------------------------------------------------------

def test_e7_concluded_without_facts_fires(tmp_path, monkeypatch):
    text = PAGE.replace("- **Facts:** We ran the d5 cell, one job at seed 0, and got "
                        "one LER; evidence [log](../../../experiments/tanner_gnn_ln/"
                        "scc/logs/slurm-ln-64196217.out).\n", "")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E7") and "without" in e for e in C.lint_page(p))


def test_e7_facts_without_a_table_fires(tmp_path, monkeypatch):
    text = PAGE.replace("  | d | LER |\n  |---|---|\n  | 5 | 2.31e-3 |\n", "")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E7") and "table" in e for e in C.lint_page(p))


def test_e7_concluded_without_an_evidence_link_fires(tmp_path, monkeypatch):
    text = PAGE.replace("; evidence [log](../../../experiments/tanner_gnn_ln/scc/logs/"
                        "slurm-ln-64196217.out)", "")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    errs = C.lint_page(p)
    assert any(e.startswith("E7") and "evidence" in e for e in errs)


def test_e7_silent_while_the_entry_is_open(tmp_path, monkeypatch):
    text = PAGE.replace("- **Status:** analyzed", "- **Status:** open")
    text = text.replace("- **Facts:** We ran the d5 cell, one job at seed 0, and got "
                        "one LER; evidence [log](../../../experiments/tanner_gnn_ln/"
                        "scc/logs/slurm-ln-64196217.out).\n", "")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, {"64196217"}))
    assert not any(e.startswith("E7") for e in C.lint_page(p))


# --------------------------------------------------------------------------
# E8 — a displayed number this entry did not run has a Refs row.
# --------------------------------------------------------------------------

REFS_BLOCK = ("- **Refs:**\n"
              "  `[1]` → [the parent grid](./logs/other.md#entry-x) — the baseline row\n")


def test_e8_a_quote_marker_without_a_refs_row_fires(tmp_path, monkeypatch):
    text = PAGE.replace("| 5 | 2.31e-3 |", "| 5 | 2.31e-3 |\n  | 5 ref | 2.8e-3 `[1]` |")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E8") and "[1]" in e for e in C.lint_page(p))


def test_e8_silent_when_the_refs_row_exists(tmp_path, monkeypatch):
    text = PAGE.replace("| 5 | 2.31e-3 |", "| 5 | 2.31e-3 |\n  | 5 ref | 2.8e-3 `[1]` |")
    text += "\n" + REFS_BLOCK
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert not any(e.startswith("E8") for e in C.lint_page(p))


# --------------------------------------------------------------------------
# E9 — a conclusion once analyzed, with its verdict.
# --------------------------------------------------------------------------

def test_e9_concluded_without_a_conclusion_fires(tmp_path, monkeypatch):
    text = PAGE.replace("- **Conclusion:** The result shows LayerNorm lowers LER, "
                        "because 2.31e-3 sits 18% below the parent's 2.8e-3 with both "
                        "draws at the same shots — answers the motivation.\n", "")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E9") and "without" in e for e in C.lint_page(p))


def test_e9_placeholder_conclusion_fires(tmp_path, monkeypatch):
    text = PAGE.replace("The result shows LayerNorm lowers LER, because 2.31e-3 sits "
                        "18% below the parent's 2.8e-3 with both draws at the same "
                        "shots — answers the motivation.", "TBD")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E9") for e in C.lint_page(p))


def test_e9_conclusion_without_a_verdict_fires(tmp_path, monkeypatch):
    text = PAGE.replace(" — answers the motivation.", ".")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E9") and "verdict" in e for e in C.lint_page(p))


@pytest.mark.parametrize("verdict", ["partly answers", "does not answer"])
def test_e9_all_three_verdicts_are_legal(tmp_path, monkeypatch, verdict):
    text = PAGE.replace("answers the motivation.", f"{verdict} the motivation: reason.")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert not any(e.startswith("E9") for e in C.lint_page(p))


# --------------------------------------------------------------------------
# E10 — one spelling, no retired field.
# --------------------------------------------------------------------------

def test_e10_bare_field_is_rejected_but_still_read(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("- **Date:** 2026-07-21 10:00", "Date: 2026-07-21 10:00"))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    errs = C.lint_page(p)
    assert any(e.startswith("E10") and "Date" in e for e in errs)
    assert not any(e.startswith("E3") for e in errs)      # the value was still read


def test_e10_retired_findings_field_names_the_split(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("- **Facts:**",
                                "- **Findings:** LER 2.31e-3, fine.\n- **Facts:**"))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E10") and "Findings" in e for e in C.lint_page(p))


# --------------------------------------------------------------------------
# E11 — one entry runs one computation script.
# --------------------------------------------------------------------------

def _log(tmp_path: Path, name: str, script: str) -> Path:
    p = tmp_path / name
    p.write_text(f"# Command: uv run python -u experiments/x/{script} --flag 1\n"
                 f"# Exit code: 0\n")
    return p


def test_e11_accepts_one_script_across_many_logs(tmp_path):
    for i in range(3):
        _log(tmp_path, f"run-{i}.log", "run_scan.py")
    entries = {"a scan of three points": "\n".join(f"[log](./run-{i}.log)" for i in range(3))}
    assert C.entry_script_errors(entries, tmp_path / "page.md") == []


def test_e11_flags_two_scripts_in_one_entry(tmp_path):
    _log(tmp_path, "run.log", "run_sample.py")
    _log(tmp_path, "diag.log", "diag_basis.py")
    entries = {"measurement plus a control": "[log](./run.log) and [log](./diag.log)"}
    errs = C.entry_script_errors(entries, tmp_path / "page.md")
    assert len(errs) == 1 and errs[0].startswith("E11")


def test_e11_ignores_foreground_postprocessing(tmp_path):
    _log(tmp_path, "run.log", "run_sample.py")
    entries = {"a run and its plot": "[log](./run.log) [analyze.py](../analyze.py)"}
    assert C.entry_script_errors(entries, tmp_path / "page.md") == []


# --------------------------------------------------------------------------
# P2 — links and entry anchors resolve.
# --------------------------------------------------------------------------

def test_p2_entry_anchor_fragment_is_validated(tmp_path, monkeypatch):
    good = PAGE.replace(
        '- **Motivation:** The parent\'s grid found "LER 2.8e-3 at d5"; does LayerNorm '
        'move it at p=0.06?',
        '- **Motivation:** [ln at d5 p0.06](./other.md#entry-ln-at-d5-p006) found '
        '"2.31e-3"; does d7 hold it?')
    write_page(tmp_path, "tanner_gnn_ln", "other", PAGE)
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", good)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    assert not any(e.startswith("P2") for e in C.lint_page(p))
    bad = good.replace("#entry-ln-at-d5-p006", "#entry-no-such-thing")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", bad)
    assert any(e.startswith("P2") and "anchor" in e for e in C.lint_page(p))


def test_p2_dangling_link_fires_but_logs_are_exempt(tmp_path, monkeypatch):
    text = PAGE + "\nSee [the script](./missing.py) and [old log](../x/logs/gone.out).\n"
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    errs = C.lint_page(p)
    assert any(e.startswith("P2") and "missing.py" in e for e in errs)
    assert not any("gone.out" in e for e in errs)


# --------------------------------------------------------------------------
# P4 — a figure renders, carries a caption, embedded once.
# --------------------------------------------------------------------------

def test_p4_missing_caption_fires():
    txt = "### Entry: e\n- **Status:** analyzed\n\n![](../figures/f.png)\n"
    assert any("has no caption" in e for e in C.figures_errors(Path("p.md"), txt))


def test_p4_caption_from_alt_or_italic_line_is_accepted():
    alt = "### Entry: e\n\n![energy per site vs L](../figures/f.png)\n"
    ital = "### Entry: e\n\n![](../figures/f.png)\n*energy per site vs L*\n"
    assert C.figures_errors(Path("p.md"), alt) == []
    assert C.figures_errors(Path("p.md"), ital) == []


def test_p4_same_figure_embedded_twice_fires():
    fig = "![c](../figures/f.png)\n"
    txt = "### Entry: a\n\n" + fig + "\n### Entry: b\n\n" + fig
    assert any("embedded 2 times" in e for e in C.figures_errors(Path("p.md"), txt))


def test_p4_placement_is_the_writers_judgement():
    fig = "![levels of the measurement](../figures/f.png)\n"
    in_entry = "### Entry: the measurement\n" + fig + "\n### Entry: the control\n"
    at_foot = "### Entry: the measurement\n\n### Entry: the control\n\n## Analysis\n\n" + fig
    assert C.figures_errors(Path("p.md"), in_entry) == []
    assert C.figures_errors(Path("p.md"), at_foot) == []


# --------------------------------------------------------------------------
# P5 / J1 — the retired page-level Jobs table; jobs need an artifact link.
# --------------------------------------------------------------------------

def test_p5_retired_jobs_section_fires(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE + "\n## Jobs\n| job_id | entry |\n|--------|-------|\n")
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("P5") and "RETIRED" in e for e in C.lint_page(p))


def test_j1_entry_with_jobs_needs_a_file_link(tmp_path, monkeypatch):
    text = PAGE.replace("; evidence [log](../../../experiments/tanner_gnn_ln/scc/logs/"
                        "slurm-ln-64196217.out)", "")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("J1") for e in C.lint_page(p))


# --------------------------------------------------------------------------
# J3 / J4 — status against the queue (seeded via `_QUEUE_CACHE`).
# --------------------------------------------------------------------------

def test_j3_fires_when_a_running_entrys_job_left_the_queue(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("- **Status:** analyzed", "- **Status:** running"))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    assert any(e.startswith("J3") for e in C.lint_page(p))


def test_j3_silent_when_the_job_is_still_queued(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("- **Status:** analyzed", "- **Status:** running"))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, {"64196217"}))
    errs = C.lint_page(p)
    assert not any(e.startswith("J3") for e in errs)
    assert not any(e.startswith("J4") for e in errs)


def test_j4_fires_when_a_live_job_has_no_running_entry(tmp_path, monkeypatch):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", PAGE)  # Status: closed
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, {"64196217"}))
    assert any(e.startswith("J4") for e in C.lint_page(p))


def test_expand_jobids_accepts_host_tags():
    assert C.expand_jobids("63902601@t6") == ["63902601"]
    assert C.expand_jobids("63902601–04@t6") == [
        "63902601", "63902602", "63902603", "63902604"]
    assert C.expand_jobids("64108451–54") == [
        "64108451", "64108452", "64108453", "64108454"]


# --------------------------------------------------------------------------
# J3/J4 log-header fallback — when Slurm is present but squeue is unusable.
# --------------------------------------------------------------------------

LOG_FALLBACK_ENTRY = """---
node: tanner_gnn_ln
task: smoke
---

### Entry: ln smoke
- **Id:** 07.001
- **Status:** STATUS_PLACEHOLDER
- **Date:** 2026-07-21 10:00
- **Code:** `tanner_gnn_ln@abc1234f`
- **Motivation:** The gate found "2.8e-3"; does the smoke run land?
- **Recipe:** {hidden_dim: 32}

Ran via [run.py](file:///x/run.py), log [job](file://LOG_PLACEHOLDER).
"""


def _log_fallback_page(tmp_path, status, log_text):
    log = tmp_path / "run.log"
    log.write_text(log_text)
    text = LOG_FALLBACK_ENTRY.replace("STATUS_PLACEHOLDER", status).replace(
        "LOG_PLACEHOLDER", str(log))
    return write_page(tmp_path, "tanner_gnn_ln", "grid", text)


def test_j3_log_fallback_fires_when_running_but_log_reports_done(tmp_path, monkeypatch):
    p = _log_fallback_page(tmp_path, "running", "# Exit code: 0\n")
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (False, set()))  # squeue unusable -> None
    assert any(e.startswith("J3") for e in C.lint_page(p))


def test_j3_log_fallback_silent_when_log_still_running(tmp_path, monkeypatch):
    p = _log_fallback_page(tmp_path, "running", "# Exit code: running\n")
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (False, set()))
    errs = C.lint_page(p)
    assert not any(e.startswith("J3") for e in errs)
    assert not any(e.startswith("J4") for e in errs)


def test_j4_log_fallback_fires_when_log_running_but_status_is_not(tmp_path, monkeypatch):
    p = _log_fallback_page(tmp_path, "open", "# Exit code: running\n")
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (False, set()))
    assert any(e.startswith("J4") for e in C.lint_page(p))


# --------------------------------------------------------------------------
# queued_job_ids() and the remote snapshot.
# --------------------------------------------------------------------------

def test_queued_job_ids_returns_the_cached_ids_when_usable(monkeypatch):
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, {"64196217"}))
    assert C.queued_job_ids() == {"64196217"}


def test_queued_job_ids_returns_none_when_unusable(monkeypatch):
    monkeypatch.setattr(C, "_QUEUE_CACHE", (False, set()))
    assert C.queued_job_ids() is None


def test_remote_snapshot_ids_are_unioned_when_fresh(monkeypatch):
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, {"111"}))
    monkeypatch.setattr(C, "_remote_queue", lambda: (True, {"222"}))
    assert C.queued_job_ids() == {"111", "222"}


def test_stale_remote_snapshot_makes_the_queue_unusable(monkeypatch):
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, {"111"}))
    monkeypatch.setattr(C, "_remote_queue", lambda: (False, set()))
    assert C.queued_job_ids() is None


_REAL_REMOTE_QUEUE = C._remote_queue


def _remote_project(tmp_path, snapshot_text):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "hpc.env").write_text(
        'REMOTE_HOST=t6\nREMOTE_DIR=/x\nREMOTE_HOSTS="t6 huairou"\n')
    (tmp_path / ".fixer").mkdir()
    (tmp_path / ".fixer" / "remote_queue").write_text(snapshot_text)
    return tmp_path


def test_remote_queue_reads_host_tagged_snapshot_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "ROOT", _remote_project(
        tmp_path, "111 RUNNING @t6\n222 PENDING @huairou\n"))
    assert _REAL_REMOTE_QUEUE() == (True, {"111", "222"})


# --------------------------------------------------------------------------
# live_bare_job_ids() — the bare host's queue, from the launcher's own headers.
# --------------------------------------------------------------------------

def _bare_log(dirpath: Path, stem: str, uv_pid, py_pid, exit_code="running",
              stamp=None):
    log = dirpath / "logs" / f"{stem}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    when = stamp or datetime.now().astimezone().isoformat(timespec="seconds")
    log.write_text(
        f"# Command: uv run python -u {dirpath}/run.py\n"
        f"# Cwd: {dirpath}\n"
        f"# Timestamp: {when}\n"
        f"# PID uv: {uv_pid}\n"
        f"# PID python: {py_pid}\n"
        f"# Exit code: {exit_code}\n"
        f"# ---\n")
    return log


def test_live_bare_job_ids_reports_the_uv_pid_only(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "EXPERIMENTS_DIR", tmp_path)
    uv = subprocess.Popen(["sleep", "30"])
    py = subprocess.Popen(["sleep", "30"])
    try:
        _bare_log(tmp_path, "run-1", uv.pid, py.pid)
        assert C.live_bare_job_ids() == {str(uv.pid)}
    finally:
        for p in (uv, py):
            p.kill()
            p.wait()


def test_live_bare_job_ids_skips_a_finished_run(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "EXPERIMENTS_DIR", tmp_path)
    uv = subprocess.Popen(["sleep", "30"])
    try:
        _bare_log(tmp_path, "run-1", uv.pid, uv.pid, exit_code="0")
        assert C.live_bare_job_ids() == set()
    finally:
        uv.kill()
        uv.wait()


def test_live_bare_job_ids_rejects_a_recycled_pid(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "EXPERIMENTS_DIR", tmp_path)
    uv = subprocess.Popen(["sleep", "30"])
    try:
        _bare_log(tmp_path, "run-1", uv.pid, uv.pid,
                  stamp="2020-01-01T00:00:00+00:00")
        assert C.live_bare_job_ids() == set()
    finally:
        uv.kill()
        uv.wait()


def test_queue_phrases_do_not_say_squeue_on_a_bare_host(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda _: None)
    assert not any("squeue" in p for p in C.queue_phrases())


# --------------------------------------------------------------------------
# Cross-tree: N2, N3, J2.
# --------------------------------------------------------------------------

def test_n2_missing_impl_fires(tmp_path, monkeypatch):
    nodes = tmp_path / "project_memory" / "nodes"
    write_node_md(nodes, "tanner_gnn_ln", NODE)
    monkeypatch.setattr(C, "NODES_DIR", nodes)
    monkeypatch.setattr(C, "EXPERIMENTS_DIR", tmp_path / "experiments")
    assert any(e.startswith("N2") for e in C.impl_errors())


def test_n2_silent_when_an_impl_exists_in_any_language(tmp_path, monkeypatch):
    nodes = tmp_path / "project_memory" / "nodes"
    write_node_md(nodes, "tanner_gnn_ln", NODE)
    impl = tmp_path / "experiments" / "tanner_gnn_ln" / "impl"
    impl.mkdir(parents=True)
    (impl / "model.jl").write_text("")
    monkeypatch.setattr(C, "NODES_DIR", nodes)
    monkeypatch.setattr(C, "EXPERIMENTS_DIR", tmp_path / "experiments")
    assert C.impl_errors() == []


def test_n3_missing_index_file(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "ROOT", tmp_path)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path / "project_memory" / "nodes")
    assert any(e.startswith("N3") and "missing" in e for e in C.index_consistency())


def test_n3_flags_a_node_missing_from_the_roster(tmp_path, monkeypatch):
    nodes = tmp_path / "project_memory" / "nodes"
    write_node_md(nodes, "tanner_gnn_ln", NODE)
    idx = tmp_path / "project_memory" / "_index.md"
    idx.write_text("| 01 | other | [node.md](nodes/other/node.md) |\n")
    monkeypatch.setattr(C, "ROOT", tmp_path)
    monkeypatch.setattr(C, "NODES_DIR", nodes)
    errs = C.index_consistency()
    assert any("tanner_gnn_ln" in e and "no roster row" in e for e in errs)


def test_n3_silent_when_roster_and_tree_match(tmp_path, monkeypatch):
    nodes = tmp_path / "project_memory" / "nodes"
    write_node_md(nodes, "tanner_gnn_ln", NODE)
    idx = tmp_path / "project_memory" / "_index.md"
    idx.write_text("| 07 | [tanner_gnn_ln](nodes/tanner_gnn_ln/node.md) | LayerNorm |\n")
    monkeypatch.setattr(C, "ROOT", tmp_path)
    monkeypatch.setattr(C, "NODES_DIR", nodes)
    assert C.index_consistency() == []


def test_j2_fires_for_a_live_job_recorded_nowhere(tmp_path, monkeypatch):
    write_page(tmp_path, "tanner_gnn_ln", "grid", PAGE)  # records 64196217 only
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, {"64196217", "99999999"}))
    errs = C.unrecorded_jobs()
    assert any(e.startswith("J2") and "99999999" in e for e in errs)
    assert not any("64196217" in e for e in errs)


def test_j2_suppresses_a_leak_younger_than_the_floor(tmp_path, monkeypatch):
    write_page(tmp_path, "tanner_gnn_ln", "grid", PAGE)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, {"64196217", "88888888"}))
    monkeypatch.setattr(C, "_pid_elapsed_minutes",
                        lambda pid: 0.5 if pid == "88888888" else None)
    assert C.unrecorded_jobs() == []


# --------------------------------------------------------------------------
# M1 — one record language, where the project declares it.
# --------------------------------------------------------------------------

def _declare_language(root, lang="en"):
    (root / ".claude").mkdir(parents=True, exist_ok=True)
    (root / ".claude" / "framework.json").write_text(
        '{"framework": "research-note", "record": "v3", "record_language": "%s"}' % lang)


def test_m1_fires_only_where_the_project_declared_a_language(tmp_path, monkeypatch):
    p = write_page(tmp_path / "n", "tanner_gnn_ln", "grid", PAGE + "\n这是中文\n")
    monkeypatch.setattr(C, "NODES_DIR", tmp_path / "n")
    monkeypatch.setattr(C, "ROOT", tmp_path)
    assert not any(e.startswith("M1") for e in C.lint_page(p))
    _declare_language(tmp_path)
    assert any(e.startswith("M1") for e in C.lint_page(p))


def test_lint_path_dispatches_note_files_without_page_rules(tmp_path, monkeypatch):
    f = tmp_path / "project_memory" / "note" / "x.md"
    f.parent.mkdir(parents=True)
    f.write_text("free-form interpretation, no entries required\n")
    monkeypatch.setattr(C, "ROOT", tmp_path)
    assert C.lint_path(f) == []


# --------------------------------------------------------------------------
# sections() and the CLI.
# --------------------------------------------------------------------------

def test_sections_stops_at_a_sibling_level_heading():
    text = ("### Entry: a\nStatus: open\n#### detail\nkept\n\n"
            "### Note\nnot part of entry a\n\n### Entry: b\nStatus: open\n")
    secs = C.sections(text)
    assert set(secs) == {"a", "b"}
    assert "kept" in secs["a"]
    assert "not part of entry a" not in secs["a"]


def test_main_returns_0_and_prints_ok_for_a_clean_page(tmp_path, monkeypatch, capsys):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", PAGE)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    monkeypatch.setattr(sys, "argv", ["check_node_page.py", str(p)])
    rc = C.main()
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_main_returns_1_for_a_bad_page(tmp_path, monkeypatch, capsys):
    p = write_page(tmp_path, "tanner_gnn_ln", "grid",
                   PAGE.replace("- **Status:** analyzed", "- **Status:** bogus"))
    monkeypatch.setattr(sys, "argv", ["check_node_page.py", str(p)])
    rc = C.main()
    assert rc == 1
    assert "E2" in capsys.readouterr().out


def test_main_returns_3_on_a_record_version_mismatch(tmp_path, monkeypatch, capsys):
    """The version gate runs first and exits 3 — one finding, nothing else
    checked, so a blocking caller (pre-commit) lets old-format projects pass
    while doctor reports the migration."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "framework.json").write_text(
        '{"framework": "research-note", "record": "v2.4"}')
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", PAGE)
    monkeypatch.setattr(C, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["check_node_page.py", str(p)])
    rc = C.main()
    out = capsys.readouterr().out
    assert rc == 3
    assert "FW" in out and "OK" not in out


def test_main_recent_flag_filters_out_stale_pages(tmp_path, monkeypatch, capsys):
    old = write_page(tmp_path, "tanner_gnn_ln", "old", PAGE)
    write_page(tmp_path, "tanner_gnn_ln", "new", PAGE)
    old_time = time.time() - 10 * 3600
    os.utime(old, (old_time, old_time))
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    monkeypatch.setattr(sys, "argv", ["check_node_page.py", "--recent", "1"])
    C.main()
    out = capsys.readouterr().out
    assert "new.md" in out
    assert "old.md" not in out


def test_main_cross_runs_the_whole_tree_checks(tmp_path, monkeypatch, capsys):
    nodes = tmp_path / "project_memory" / "nodes"
    write_node_md(nodes, "tanner_gnn_ln", NODE)
    (tmp_path / "project_memory" / "_index.md").write_text("| 01 | ghost | x |\n")
    monkeypatch.setattr(C, "NODES_DIR", nodes)
    monkeypatch.setattr(C, "ROOT", tmp_path)
    monkeypatch.setattr(C, "EXPERIMENTS_DIR", tmp_path / "experiments")
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    monkeypatch.setattr(sys, "argv", ["check_node_page.py", "--cross", "--quiet",
                                      str(nodes / "tanner_gnn_ln" / "node.md")])
    rc = C.main()
    out = capsys.readouterr().out
    assert rc == 1
    assert "N2" in out and "N3" in out


# --------------------------------------------------------------------------
# closed = the user's accepted terminal record: structural checks only.
# --------------------------------------------------------------------------

def test_a_closed_entry_is_exempt_from_the_form_checks(tmp_path, monkeypatch):
    """A schema written later does not reopen an accepted record — E4-E9 bind
    while the entry is still the agent's to write (it is, at `analyzed`)."""
    text = PAGE.replace("- **Status:** analyzed", "- **Status:** closed")
    text = text.replace("- **Code:** `tanner_gnn_ln_mech_softler@abc1234f`\n", "")
    text = text.replace("- **Code:** `tanner_gnn_ln@abc1234f`\n", "")
    text = text.replace('- **Motivation:** The parent\'s grid found "LER 2.8e-3 at d5"; '
                        'does LayerNorm move it at p=0.06?',
                        "- **Motivation:** earlier results looked odd.")
    text = text.replace("- **Conclusion:** The result shows LayerNorm lowers LER, "
                        "because 2.31e-3 sits 18% below the parent's 2.8e-3 with both "
                        "draws at the same shots — answers the motivation.\n", "")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    errs = C.lint_page(p)
    assert not any(e.split()[0] in ("E4", "E5", "E7", "E8", "E9") for e in errs)


def test_a_closed_entry_still_gets_the_structural_checks(tmp_path, monkeypatch):
    text = PAGE.replace("- **Status:** analyzed", "- **Status:** closed")
    text = text.replace("- **Id:** 07.001", "- **Id:** 7.1")
    text = text.replace("- **Date:** 2026-07-21 10:00", "Date: 2026-07-21 10:00")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, set()))
    errs = C.lint_page(p)
    assert any(e.startswith("E1") for e in errs)
    assert any(e.startswith("E10") and "Date" in e for e in errs)


def test_p2_bare_same_directory_link_is_checked(tmp_path, monkeypatch):
    """`[T1](p_grid.md)` without ./ once dangled unseen after its target was
    deleted — both spellings of a relative target are held to P2."""
    # indented, so it continues the Conclusion field: E12 owns where a line
    # sits, and this test is about P2 seeing the link wherever it sits. E14
    # separately flags a Conclusion link whether or not its target exists —
    # both assertions are scoped to P2, whose business is only the dangling.
    text = PAGE + "\n  See [T1](ghost_sibling.md) for the grid.\n"
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("P2") and "ghost_sibling.md" in e for e in C.lint_page(p))
    write_page(tmp_path, "tanner_gnn_ln", "ghost_sibling", PAGE)
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    assert not any(e.startswith("P2") and "ghost_sibling" in e for e in C.lint_page(p))


def test_e5_motivation_stating_a_reason_but_asking_nothing_is_flagged(tmp_path, monkeypatch):
    """A Motivation that gives a reason to run decides nothing about what the
    Conclusion may contain — the question is what the Conclusion is judged
    against, so it has to be there."""
    text = PAGE.replace(
        '- **Motivation:** The parent\'s grid found "LER 2.8e-3 at d5"; does LayerNorm move it at p=0.06?',
        "- **Motivation:** LayerNorm is the one axis this branch has never varied, "
        "and it has to be read at d5 because the depth scan put the best depth there.")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    errs = [e for e in C.lint_page(p) if e.startswith("E5")]
    assert errs and any("no question" in e for e in errs)


def test_e5_question_may_wrap_onto_the_next_line(tmp_path, monkeypatch):
    """The field wraps; the question mark still closes it. `await review` was a
    live bug of exactly this shape, so the check reads the joined block."""
    text = PAGE.replace(
        '- **Motivation:** The parent\'s grid found "LER 2.8e-3 at d5"; does LayerNorm move it at p=0.06?',
        '- **Motivation:** The parent\'s grid found "LER 2.8e-3 at d5"; does\n'
        "  LayerNorm move it at p=0.06?")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert not [e for e in C.lint_page(p) if e.startswith("E5")]


def test_e5_question_check_stops_at_the_users_tick(tmp_path, monkeypatch):
    """E5 judges what the field SAYS, so like E4-E9 it binds while the entry is
    still the agent's to write — a closed entry is accepted as it stood."""
    text = PAGE.replace("- **Status:** analyzed", "- **Status:** closed").replace(
        '- **Motivation:** The parent\'s grid found "LER 2.8e-3 at d5"; does LayerNorm move it at p=0.06?',
        "- **Motivation:** LayerNorm is the one axis this branch has never varied.")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert not [e for e in C.lint_page(p) if e.startswith("E5")]


def test_e12_content_outside_every_field_is_flagged(tmp_path, monkeypatch):
    """A table, a figure or a `Job N — [log]` line dropped between the fields
    reads as an entry whose Facts are missing — every other check looks for
    content under the key that owns it."""
    text = PAGE + (
        "\nJob 64196218 — [log](../../../experiments/tanner_gnn_ln/scc/logs/x.out).\n"
        "\n| d | LER |\n|---|---|\n| 7 | 9.1e-4 |\n"
    )
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    errs = [e for e in C.lint_page(p) if e.startswith("E12")]
    assert errs, "loose lines after the Conclusion must be reported"
    assert any("Job 64196218" in e for e in errs)


def test_e12_indented_continuation_is_part_of_its_field(tmp_path, monkeypatch):
    """The Facts table and figure are indented under `- **Facts:**` — E12 must
    read them as that field's content, not as loose lines."""
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", PAGE)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert not [e for e in C.lint_page(p) if e.startswith("E12")]


def test_e12_binds_on_a_closed_entry(tmp_path, monkeypatch):
    """Unlike E4-E9, which judge what a field SAYS and stop at the user's ✓,
    E12 judges only WHERE a line sits — an accepted record is still readable
    only if its content is under the keys that own it."""
    text = PAGE.replace("- **Status:** analyzed", "- **Status:** closed")
    text += "\nRun on `surface_code_capacity(d=5, p=0.06)`.\n"
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    errs = C.lint_page(p)
    assert any(e.startswith("E12") for e in errs)
    assert not any(e.startswith(("E4", "E7", "E9")) for e in errs), \
        "the closed exemption on the form checks must survive E12"


def test_e12_ignores_the_page_header(tmp_path, monkeypatch):
    """Frontmatter and any page-level title sit before the first `### Entry:`
    and belong to no entry — E12 reads entry bodies only."""
    text = PAGE.replace("### Entry: ln at d5 p0.06",
                        "# The LayerNorm grid\n\nProse about the page.\n\n"
                        "### Entry: ln at d5 p0.06")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert not [e for e in C.lint_page(p) if e.startswith("E12")]


def test_fw_contract_version_line_is_checked(tmp_path, monkeypatch):
    """A synced marker over a stale contract file is the drift the marker check
    cannot see — the contract's own `Record format:` line closes it."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "framework.json").write_text(
        '{"framework": "research-note", "record": "v3"}')
    (tmp_path / ".claude" / "project_memory-CLAUDE.md").write_text(
        "# project_memory\n\nold contract, no version line\n")
    monkeypatch.setattr(C, "ROOT", tmp_path)
    errs = C.record_version_check()
    assert any("FW" in e and "contract" in e for e in errs)
    (tmp_path / ".claude" / "project_memory-CLAUDE.md").write_text(
        "# project_memory\n\nRecord format: v3\n")
    assert C.record_version_check() == []

# --------------------------------------------------------------------------
# E13-E15, J5-J6 — added as five codes in one unversioned pair of commits;
# these tests pin them (they shipped without any).
# --------------------------------------------------------------------------


def test_e13_a_job_stanza_inside_facts_is_flagged(tmp_path, monkeypatch):
    """record_submit's `Job <id> — [log]` append, indented into Facts to dodge
    E12, is still not a Facts sentence — evidence belongs in the sentence's
    `evidence <links>` clause."""
    text = PAGE.replace("- **Conclusion:**",
                        "  Job 64196217 — [log](ghost.log).\n\n- **Conclusion:**")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E13") for e in C.lint_page(p))
    assert not any(e.startswith("E13") for e in C.lint_page(
        write_page(tmp_path, "tanner_gnn_ln", "clean", PAGE)))


def test_e14_a_link_in_the_conclusion_is_flagged(tmp_path, monkeypatch):
    text = PAGE.replace("because 2.31e-3 sits",
                        "because [the log](ghost.log) shows 2.31e-3 sits")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E14") for e in C.lint_page(p))


def test_e15_a_conclusion_running_past_its_verdict_is_flagged(tmp_path, monkeypatch):
    """The retired tail (`; not covered: <Z>`) is the canonical offender: since
    0.13.28 the sentence ENDS at the verdict, and what a tail held moves into
    the because (a partly's gap: Facts + because)."""
    text = PAGE.replace(
        "— answers the motivation.",
        "— partly answers the motivation; not covered: the p=0.1 corner.")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("E15") for e in C.lint_page(p))
    assert not any(e.startswith("E15") for e in C.lint_page(
        write_page(tmp_path, "tanner_gnn_ln", "clean", PAGE)))


def test_j5_running_with_an_empty_jobs_field_is_flagged(tmp_path, monkeypatch):
    text = PAGE.replace("- **Status:** analyzed", "- **Status:** running") \
               .replace("- **Jobs:** 64196217", "- **Jobs:**")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert any(e.startswith("J5") for e in C.lint_page(p))


def test_j6_an_id_named_in_the_body_but_not_the_field_is_flagged(tmp_path, monkeypatch):
    text = PAGE.replace("evidence [log](", "evidence 64196299@H200; [log](")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    errs = C.lint_page(p)
    assert any(e.startswith("J6") and "64196299" in e for e in errs)
    assert not any(e.startswith("J6") for e in C.lint_page(
        write_page(tmp_path, "tanner_gnn_ln", "clean", PAGE)))


def test_j6_ignores_a_numeric_repo_name_in_code(tmp_path, monkeypatch):
    """`- **Code:** `3450@e637566`` is <repo>@<sha> with a numeric repo name —
    shaped exactly like an id@host. Six false J6s on a real record."""
    text = PAGE.replace("`tanner_gnn_ln@abc1234f`", "`3450@e637566`")
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert not any(e.startswith("J6") for e in C.lint_page(p))


def test_j6_ignores_a_provenance_id_quoted_in_the_motivation(tmp_path, monkeypatch):
    """Motivation and Refs quote OTHER entries' ids as provenance — 'job
    `35207412@t6` measured …' names the source, not this entry's run."""
    text = PAGE.replace(
        'The parent\'s grid found "LER 2.8e-3 at d5"',
        'The parent\'s grid job `35207412@t6` found "LER 2.8e-3 at d5"')
    p = write_page(tmp_path, "tanner_gnn_ln", "grid", text)
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    assert not any(e.startswith("J6") for e in C.lint_page(p))


def test_n3_covers_the_objectives_registry(tmp_path, monkeypatch):
    """The Objectives section is the O<nn> registry; a page missing from it
    eventually hands the same number out twice, and nothing linted the drift."""
    pm = tmp_path / "project_memory"
    (pm / "nodes" / "tanner_gnn_ln").mkdir(parents=True)
    (pm / "nodes" / "tanner_gnn_ln" / "node.md").write_text(NODE)
    (pm / "objectives").mkdir()
    (pm / "objectives" / "knee.md").write_text(
        "---\nid: O05\nstatus: active\n---\n\n## Goal\nq.\n")
    monkeypatch.setattr(C, "ROOT", tmp_path)
    monkeypatch.setattr(C, "NODES_DIR", pm / "nodes")
    roster = ("# Roster\n\n| # | node | what it is |\n|---|---|---|\n"
              "| 01 | [`tanner_gnn_ln`](nodes/tanner_gnn_ln/node.md) | x |\n"
              "\n## Entries\n\n| id | entry | status |\n|---|---|---|\n")
    (pm / "_index.md").write_text(roster)
    errs = C.index_consistency()
    assert any("N3" in e and "O05" in e and "Objectives" in e for e in errs)
    # regenerated form (section present, row there) is clean
    (pm / "_index.md").write_text(
        roster + "\n## Objectives\n\n| id | objective | status | verdict |\n"
                 "|---|---|---|---|\n| O05 | [knee](objectives/knee.md) | active | — |\n")
    assert C.index_consistency() == []
    # and a roster row whose page is gone is the other direction
    (pm / "objectives" / "knee.md").unlink()
    errs = C.index_consistency()
    assert any("N3" in e and "O05" in e for e in errs)


# --------------------------------------------------------------------------
# E16 — a cited `<repo>@<sha>` is retrievable.
# --------------------------------------------------------------------------

def _g(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, check=True).stdout.strip()


@pytest.fixture
def sha_repo(tmp_path):
    """A real checkout: one commit on the default branch, one only on a side
    branch — the two states E16 has to tell apart."""
    r = tmp_path / "myproj"
    r.mkdir()
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    _g(r, "config", "user.email", "t@example.invalid")
    _g(r, "config", "user.name", "t")
    (r / "f").write_text("1")
    _g(r, "add", "f")
    _g(r, "commit", "-qm", "landed")
    landed = _g(r, "rev-parse", "HEAD")
    _g(r, "checkout", "-q", "-b", "side")
    (r / "f").write_text("2")
    _g(r, "add", "f")
    _g(r, "commit", "-qm", "still on the branch")
    unlanded = _g(r, "rev-parse", "HEAD")
    _g(r, "checkout", "-q", "-")
    # Both caches are module-level and per PROCESS. Two fixtures built in the
    # same second from the same content produce the SAME commit sha, so a
    # verdict cached by one test is a verdict the next test would inherit.
    C._DEFBRANCH.clear()
    C._SHA_VERDICT.clear()
    yield r, landed, unlanded
    C._DEFBRANCH.clear()
    C._SHA_VERDICT.clear()


def _code(tok: str) -> dict[str, str]:
    return {"an entry": f"- **Code:** `{tok}`\n"}


def test_e16_a_landed_sha_passes(sha_repo, monkeypatch):
    r, landed, _ = sha_repo
    monkeypatch.setattr(C, "ROOT", r)
    assert C.code_sha_errors(_code(f"myproj@{landed[:8]}")) == []


def test_e16_a_sha_only_on_a_branch_fires(sha_repo, monkeypatch):
    """The 08.002 failure, caught at the moment the entry is written rather
    than weeks later, after the rebase that lands the branch rewrote it."""
    r, _, unlanded = sha_repo
    monkeypatch.setattr(C, "ROOT", r)
    errs = C.code_sha_errors(_code(f"myproj@{unlanded[:8]}"))
    assert any(e.startswith("E16") and "not on" in e for e in errs)


def test_e16_names_the_branch_that_still_holds_an_unlanded_sha(sha_repo, monkeypatch):
    r, _, unlanded = sha_repo
    monkeypatch.setattr(C, "ROOT", r)
    errs = C.code_sha_errors(_code(f"myproj@{unlanded[:8]}"))
    assert any("only on `side`" in e for e in errs)


def test_e16_tells_an_orphan_apart_from_an_unlanded_branch(sha_repo, monkeypatch):
    """The case that actually occurred: the rebase already happened and the
    branch is gone, so "land it first" is the wrong instruction — the entry has
    to be pointed at whatever landed in its place."""
    r, _, unlanded = sha_repo
    _g(r, "branch", "-D", "side")
    monkeypatch.setattr(C, "ROOT", r)
    errs = C.code_sha_errors(_code(f"myproj@{unlanded[:8]}"))
    assert any(e.startswith("E16") and "no branch reaches" in e for e in errs)


def test_e16_an_unresolvable_sha_fires(sha_repo, monkeypatch):
    r, _, _ = sha_repo
    monkeypatch.setattr(C, "ROOT", r)
    errs = C.code_sha_errors(_code("myproj@dead1234"))
    assert any(e.startswith("E16") and "retrievable" in e for e in errs)


def test_e16_skips_a_job_id_at_a_hex_host(sha_repo, monkeypatch):
    """`3450@e637566` is a `<job id>@<host>`, shaped exactly like a
    `<repo>@<sha>`; only the numeric left side tells them apart."""
    r, _, _ = sha_repo
    monkeypatch.setattr(C, "ROOT", r)
    assert C.code_sha_errors(_code("3450@e637566")) == []


def test_e16_is_silent_outside_a_git_checkout(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "ROOT", tmp_path)
    assert C.code_sha_errors(_code("myproj@dead1234")) == []


def test_e16_a_pinned_libs_sha_needs_only_to_resolve(sha_repo, tmp_path, monkeypatch):
    """A lib SHA is checked for EXISTENCE only. A state kept alive by a tag
    after the branch was rebased away is legitimate and is an ancestor of
    nothing, so demanding ancestry there would fire on correct records."""
    r, _, unlanded = sha_repo
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    (proj / ".claude" / "hpc.env").write_text(f'DOMAIN_LIBS="{r}"\n')
    monkeypatch.setattr(C, "ROOT", proj)
    assert C.code_sha_errors(_code(f"myproj@{unlanded[:8]}")) == []
    errs = C.code_sha_errors(_code("myproj@dead1234"))
    assert any(e.startswith("E16") for e in errs)


def test_e16_says_nothing_about_a_lib_the_project_never_declared(sha_repo, tmp_path,
                                                                monkeypatch):
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    monkeypatch.setattr(C, "ROOT", proj)
    assert C.code_sha_errors(_code("somelib@dead1234")) == []


# --------------------------------------------------------------------------
# J2 — an interactive srun is not an unrecorded batch job.
# --------------------------------------------------------------------------

def _fake_sacct(monkeypatch, rows, rc=0):
    import shutil as _sh
    monkeypatch.setattr(_sh, "which", lambda name: "/usr/bin/sacct")

    class _R:
        returncode = rc
        stdout = rows

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _R())


def test_j2_skips_an_interactive_srun(monkeypatch):
    """`1390595` with steps extern + .0 and NO .batch is an srun allocation —
    a smoke, which by contract owes no entry."""
    _fake_sacct(monkeypatch, "1390595\n1390595.extern\n1390595.0\n")
    assert C._is_interactive_alloc("1390595") is True


def test_j2_still_flags_a_batch_job(monkeypatch):
    _fake_sacct(monkeypatch, "1389756\n1389756.batch\n1389756.extern\n")
    assert C._is_interactive_alloc("1389756") is False


def test_j2_treats_an_unanswerable_sacct_as_not_interactive(monkeypatch):
    """Unknown must not silence a real leak."""
    _fake_sacct(monkeypatch, "", rc=1)
    assert C._is_interactive_alloc("1") is False
    import shutil as _sh
    monkeypatch.setattr(_sh, "which", lambda name: None)
    assert C._is_interactive_alloc("1") is False


def test_j2_excludes_the_interactive_id_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(C, "NODES_DIR", tmp_path)
    monkeypatch.setattr(C, "_QUEUE_CACHE", (True, {"1390595"}))
    monkeypatch.setattr(C, "_pid_elapsed_minutes", lambda jid: None)
    _fake_sacct(monkeypatch, "1390595\n1390595.extern\n1390595.0\n")
    assert C.unrecorded_jobs() == []


def test_the_e16_verdict_cache_survives_across_pages(sha_repo, monkeypatch):
    """The same `<repo>@<sha>` recurs on every page of a node, so a per-PAGE
    cache re-shells for each of them: 137 lookups where 84 were distinct, 23 s
    of subprocess inside a dashboard the fixer rebuilds every cycle."""
    r, landed, _ = sha_repo
    monkeypatch.setattr(C, "ROOT", r)
    C._SHA_VERDICT.clear()
    C._DEFBRANCH.clear()
    sha = landed[:8]
    calls = []
    real = C._git_ok
    monkeypatch.setattr(C, "_git_ok",
                        lambda repo, *a: (calls.append(a), real(repo, *a))[1])
    tok = f"myproj@{sha}"
    for _ in range(4):                      # four pages, same citation
        assert C.code_sha_errors(_code(tok)) == []
    about_sha = [a for a in calls if any(sha in str(x) for x in a)]
    assert len(about_sha) == 2, about_sha   # cat-file + is-ancestor, once each
