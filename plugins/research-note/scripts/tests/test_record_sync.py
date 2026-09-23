"""record_sync.sh — the record bus. First direct tests.

The bus is the ONE write path onto the record's live instance; what these pin
is its transactional shape: a refused put changes nothing, a failed put leaves
main byte-identical to before (a dirty file wedges every later `put -b` on the
page), and the commit message survives the handover verbatim (-F).
"""

import hashlib
import subprocess
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
BUS = SCRIPTS / "record_sync.sh"

GREEN = """---
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
- **Facts:** We ran the d5 cell, one job at seed 0; evidence [log](../../../experiments/tanner_gnn_ln/scc/logs/slurm-ln-64196217.out).

  | d | LER |
  |---|---|
  | 5 | 2.31e-3 |

- **Conclusion:** The result shows LayerNorm lowers LER, because 2.31e-3 sits 18% below the parent's 2.8e-3 with both draws at the same shots — answers the motivation.
"""

REL = "project_memory/nodes/tanner_gnn_ln/grid.md"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(repo: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *args],
                       capture_output=True, text=True, check=True)
    return r.stdout


@pytest.fixture()
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    git(tmp_path, "config", "user.email", "t@example.com")
    git(tmp_path, "config", "user.name", "t")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "framework.json").write_text('{"record": "v3"}\n')
    page = tmp_path / REL
    page.parent.mkdir(parents=True)
    page.write_text(GREEN, encoding="utf-8")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def bus(repo: Path, *args: str, refresh: bool = False) -> subprocess.CompletedProcess:
    """The bus refreshes the dashboard in the background after each commit; the
    tests below that are not about that turn it off, so no detached process is
    writing into their repository while they assert on it."""
    import os
    env = {k: v for k, v in os.environ.items() if k != "RN_NO_DASHBOARD_REFRESH"}
    if not refresh:
        env["RN_NO_DASHBOARD_REFRESH"] = "1"
    return subprocess.run(["bash", str(BUS), *args], cwd=repo, env=env,
                          capture_output=True, text=True)


def test_a_stale_base_is_refused_and_changes_nothing(repo):
    content = repo / "c.md"
    content.write_text(GREEN.replace("2.31e-3", "2.32e-3"), encoding="utf-8")
    r = bus(repo, "put", "-m", "memory: x", "-b", "0" * 64, REL, str(content))
    assert r.returncode != 0
    assert "moved under you" in r.stderr
    assert (repo / REL).read_text(encoding="utf-8") == GREEN


def test_a_matching_base_lands_and_commits(repo):
    content = repo / "c.md"
    content.write_text(GREEN.replace("2.31e-3", "2.32e-3"), encoding="utf-8")
    r = bus(repo, "put", "-m", "memory: grid — better number",
            "-b", sha(repo / REL), REL, str(content))
    assert r.returncode == 0, r.stderr + r.stdout
    assert "2.32e-3" in (repo / REL).read_text(encoding="utf-8")
    assert "better number" in git(repo, "log", "-1", "--pretty=%s")


def test_a_failed_lint_restores_the_page_and_does_not_wedge(repo):
    """A LINT FAIL after the copy once left the file dirty on main: its sha
    then matched no committed version, so every later `put -b` was refused as
    'moved under you' until a human ran `git checkout --` by hand."""
    before = sha(repo / REL)
    content = repo / "c.md"
    content.write_text(GREEN + "\nA loose paragraph between fields.\n",
                       encoding="utf-8")
    r = bus(repo, "put", "-m", "memory: x", "-b", before, REL, str(content))
    assert r.returncode != 0
    assert "LINT FAIL" in r.stderr
    assert "restored" in r.stderr
    assert sha(repo / REL) == before, "the failed put left the record dirty"
    porcelain = git(repo, "status", "--porcelain", "--", "project_memory")
    assert porcelain.strip() == ""
    # the same base must still be accepted — the page never moved
    content.write_text(GREEN.replace("2.31e-3", "2.33e-3"), encoding="utf-8")
    r2 = bus(repo, "put", "-m", "memory: x2", "-b", before, REL, str(content))
    assert r2.returncode == 0, r2.stderr


def test_a_failed_new_page_is_removed(repo):
    content = repo / "c.md"
    content.write_text("not a page\n", encoding="utf-8")
    rel2 = "project_memory/nodes/tanner_gnn_ln/fresh.md"
    r = bus(repo, "put", "-m", "memory: x", "-b", "new", rel2, str(content))
    assert r.returncode != 0
    assert not (repo / rel2).exists(), "the failed put left a half-created page"


def test_dash_F_keeps_backticks_and_dollars_verbatim(repo):
    """Inline -m loses every backticked identifier to the CALLER's shell —
    -F reads the message from a file, no shell layer anywhere."""
    msgf = repo / "msg.txt"
    msgf.write_text("memory: grid — `impl.py` and $(hostname) stay literal\n"
                    "\nEntry: 07.001\n", encoding="utf-8")
    content = repo / "c.md"
    content.write_text(GREEN.replace("18%", "19%"), encoding="utf-8")
    r = bus(repo, "put", "-F", str(msgf), "-b", sha(repo / REL), REL, str(content))
    assert r.returncode == 0, r.stderr
    body = git(repo, "log", "-1", "--pretty=%B")
    assert "`impl.py`" in body and "$(hostname)" in body


def test_a_dotdot_path_is_refused(repo):
    content = repo / "c.md"
    content.write_text("x\n", encoding="utf-8")
    r = bus(repo, "put", "-m", "m", "-b", "new",
            "project_memory/../src/evil.py", str(content))
    assert r.returncode != 0
    assert ".." in r.stderr
    assert not (repo / "src" / "evil.py").exists()


def test_the_bus_regenerates_the_roster_into_the_same_commit(repo):
    """_index.md is derived from the pages, so a commit that moves a page and
    not the roster leaves the roster stale — and nothing joins an entry's
    status back to it (N3 checks the node table and the objectives registry
    only), so the staleness is invisible until a reader believes it."""
    content = repo / "c.md"
    content.write_text(GREEN.replace("2.31e-3", "2.34e-3"), encoding="utf-8")
    r = bus(repo, "put", "-m", "memory: grid — a new number",
            "-b", sha(repo / REL), REL, str(content))
    assert r.returncode == 0, r.stderr + r.stdout
    committed = git(repo, "show", "--name-only", "--pretty=", "HEAD").split()
    assert "project_memory/_index.md" in committed, committed
    assert (repo / "project_memory" / "_index.md").exists()
    assert git(repo, "status", "--porcelain", "--", "project_memory").strip() == ""


def test_a_roster_the_caller_passed_is_not_added_twice(repo):
    idx = repo / "project_memory" / "_index.md"
    idx.write_text("# roster\n", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "roster")
    page = repo / REL
    page.write_text(GREEN.replace("2.31e-3", "2.35e-3"), encoding="utf-8")
    idx.write_text("# roster\n\ntouched\n", encoding="utf-8")
    r = bus(repo, "-m", "memory: both at once", REL, "project_memory/_index.md")
    assert r.returncode == 0, r.stderr + r.stdout
    committed = git(repo, "show", "--name-only", "--pretty=", "HEAD").split()
    assert committed.count("project_memory/_index.md") == 1, committed


# --------------------------------------------------------------------------
# The dashboard is core: the bus keeps it current, no fixer needed.
# --------------------------------------------------------------------------

def _wait_for(path: Path, timeout: float = 30.0) -> bool:
    import time
    end = time.time() + timeout
    while time.time() < end:
        if path.exists() and path.stat().st_size > 0:
            return True
        time.sleep(0.2)
    return False


def test_a_record_write_refreshes_the_dashboard(repo):
    board = repo / "project_memory" / "dashboard.html"
    assert not board.exists()
    content = repo / "c.md"
    content.write_text(GREEN.replace("2.31e-3", "2.32e-3"), encoding="utf-8")
    r = bus(repo, "put", "-m", "memory: grid", "-b", sha(repo / REL), REL,
            str(content), refresh=True)
    assert r.returncode == 0, r.stderr + r.stdout
    assert _wait_for(board), "no dashboard after a record write"
    assert "tanner_gnn_ln" in board.read_text(encoding="utf-8")


def test_the_refresh_does_not_hold_the_record_lock(repo):
    """The bus holds the record lock on fd 9 for its whole run. A detached
    child that inherited it would keep every other writer waiting for the
    length of a regeneration — seconds, on a large record."""
    import fcntl
    content = repo / "c.md"
    content.write_text(GREEN.replace("2.31e-3", "2.34e-3"), encoding="utf-8")
    r = bus(repo, "put", "-m", "memory: grid", "-b", sha(repo / REL), REL,
            str(content), refresh=True)
    assert r.returncode == 0, r.stderr + r.stdout
    with open(repo / ".research-note" / "state" / "record.lock", "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)      # raises if still held
    assert "9>&-" in BUS.read_text(), "the child must close the lock descriptor"


def test_the_refresh_can_be_switched_off(repo):
    import time
    content = repo / "c.md"
    content.write_text(GREEN.replace("2.31e-3", "2.35e-3"), encoding="utf-8")
    r = bus(repo, "put", "-m", "memory: grid", "-b", sha(repo / REL), REL, str(content))
    assert r.returncode == 0, r.stderr
    time.sleep(2)
    assert not (repo / "project_memory" / "dashboard.html").exists()
