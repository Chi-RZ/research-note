"""The launchers' worktree guard — recorded evidence never launches from a
linked worktree, whose logs die with it (leaving the entry's link dangling
on a page that lives forever). Smoke (ENTRY=none) stays legal anywhere."""

import subprocess
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
LAUNCHER = SCRIPTS.parent / "skills" / "hpc-submit" / "scripts" / "launch_bare_gpu.sh"


def _repo_with_worktree(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    for cmd in (["git", "init", "-q", "-b", "main", "."],
                ["git", "config", "user.email", "t@example.com"],
                ["git", "config", "user.name", "t"]):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True)
    (repo / "script.py").write_text("print('hi')\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo,
                   check=True, capture_output=True)
    wt = tmp_path / "wt"
    subprocess.run(["git", "worktree", "add", "-q", str(wt), "-b", "b"],
                   cwd=repo, check=True, capture_output=True)
    return repo, wt


def test_a_recorded_launch_from_a_worktree_is_refused(tmp_path):
    repo, wt = _repo_with_worktree(tmp_path)
    r = subprocess.run(
        ["bash", str(LAUNCHER), str(wt / "script.py"), "cpu", "0.5"],
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp_path),
             "ENTRY": "node/page: some entry"},
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 1
    assert "WORKTREE" in r.stderr
    assert not (wt / "logs").exists(), "nothing may be created before the guard"


def test_the_same_launch_from_main_passes_the_guard(tmp_path):
    """From the main checkout the guard is silent — the run proceeds to the
    pre-flight, which fails on the missing record instead (proving we got
    PAST the worktree check)."""
    repo, wt = _repo_with_worktree(tmp_path)
    r = subprocess.run(
        ["bash", str(LAUNCHER), str(repo / "script.py"), "cpu", "0.5"],
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp_path),
             "ENTRY": "node/page: some entry"},
        capture_output=True, text=True, timeout=60)
    assert "WORKTREE" not in r.stderr


def test_smoke_from_a_worktree_stays_legal(tmp_path):
    repo, wt = _repo_with_worktree(tmp_path)
    r = subprocess.run(
        ["bash", str(LAUNCHER), str(wt / "script.py"), "cpu", "0.5"],
        env={"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(tmp_path),
             "ENTRY": "none", "RUNNER": "python3 -u"},
        capture_output=True, text=True, timeout=60)
    assert "WORKTREE" not in r.stderr


def test_all_three_launchers_carry_the_guard():
    """submit_slurm and remote.sh are hard to exercise end-to-end here; pin
    the guard's presence the way test_skill_code_names pins lint codes."""
    for f in (LAUNCHER, LAUNCHER.parent / "submit_slurm.sh",
              SCRIPTS / "remote.sh"):
        assert "linked WORKTREE" in f.read_text(encoding="utf-8"), f.name


def test_every_launcher_passes_the_phase_binding_to_record_submit():
    """The sibling of the guard test above, and it exists because the guard
    test's shape was not copied when the binding landed.

    0.28.0 made `record_submit` refuse a launch with no `--phase`/`--role`.
    Two launchers grew the BIND array; `remote.sh` did not, and nothing
    noticed — its own pre-flight then refused EVERY remote launch that named
    an ENTRY, which is the whole remote half of the venue table. The failure
    was invisible from the source: each file is internally consistent, and
    only the set of them is wrong.

    So the invariant is per CALL SITE, not per file: a file that mentions
    BIND somewhere still breaks the moment someone adds an invocation without
    it. Continuations are joined first — remote.sh's record call spans two
    lines, and a line-at-a-time check would read the tail as its own
    statement and pass.
    """
    import re
    call = re.compile(r'python3\s+"\$(?:REC|RS)"')
    for f in (LAUNCHER, LAUNCHER.parent / "submit_slurm.sh",
              SCRIPTS / "remote.sh"):
        text = f.read_text(encoding="utf-8").replace("\\\n", " ")
        sites = [ln.strip() for ln in text.splitlines() if call.search(ln)]
        assert sites, f"{f.name}: no record_submit invocation found — has it moved?"
        for site in sites:
            assert "BIND[@]" in site, (
                f"{f.name} invokes record_submit without the phase binding:\n"
                f"  {site[:160]}\n"
                f"record_submit refuses a launch with no --phase, so this call "
                f"site cannot succeed with an ENTRY named.")
