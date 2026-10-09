"""lib_paths: the LIB_<name>_<side> declaration scheme.

One declaration buys both halves of DESIGN.md §8.2 — the header line and the
push gate — so the resolution functions are load-bearing in four places: the
canonical scripts/lib_paths.sh (sourced by remote.sh, doctor.sh) and verbatim
copies inside the launchers, which travel to the cluster alone and cannot
source a neighbour. The first test holds the copies byte-identical; the rest
pin the resolution semantics.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
CANON = ROOT / "scripts" / "lib_paths.sh"
COPIES = [
    ROOT / "skills" / "hpc-submit" / "scripts" / "launch_bare_gpu.sh",
    ROOT / "skills" / "hpc-submit" / "scripts" / "gpu_batch.slurm",
    ROOT / "skills" / "hpc-submit" / "scripts" / "cpu_batch.slurm",
]
START, END = "# >>> lib_paths", "# <<< lib_paths <<<"


def marked_block(path: Path) -> str:
    t = path.read_text(encoding="utf-8")
    return t[t.index(START): t.index(END) + len(END)]


def test_every_copy_matches_the_canonical_block():
    canon = marked_block(CANON)
    for f in COPIES:
        assert marked_block(f) == canon, f"{f.name} drifted from lib_paths.sh"


def run(script: str, env_lines: str = "") -> str:
    """Run a snippet with the canonical functions and the given declarations."""
    return subprocess.run(
        ["bash", "-c", f'{env_lines}\nsource "{CANON}"\n{script}'],
        capture_output=True, text=True, check=False,
    ).stdout


def test_names_are_enumerated_once_across_sides():
    out = run("lib_names",
              'LIB_mylib_LOCAL=/a\nLIB_mylib_hpc=/b\nLIB_other_LOCAL=/c')
    assert sorted(out.split()) == ["mylib", "other"]


def test_underscored_name_keeps_its_identity():
    out = run("lib_names", 'LIB_qec_bench_LOCAL=/a\nLIB_qec_bench_H200=/b')
    assert out.split() == ["qec_bench"]


def test_path_here_picks_the_side_that_exists(tmp_path):
    here = tmp_path / "here"; here.mkdir()
    out = run('lib_path_here mylib',
              f'LIB_mylib_LOCAL=/nonexistent-side\nLIB_mylib_hpc={here}')
    assert out.strip() == str(here)


def test_path_here_is_not_fooled_by_a_longer_name(tmp_path):
    """LIB_foo_bar_LOCAL declares lib foo_bar, never a side of lib foo."""
    trap = tmp_path / "trap"; trap.mkdir()
    out = run('lib_path_here foo || echo NONE',
              f'LIB_foo_bar_LOCAL={trap}')
    assert out.strip() == "NONE"


def test_path_for_reads_the_named_side_only():
    out = run('lib_path_for mylib H200',
              'LIB_mylib_LOCAL=/a\nLIB_mylib_H200=/b')
    assert out.strip() == "/b"
    assert run('lib_path_for mylib other || true',
               'LIB_mylib_LOCAL=/a').strip() == ""


def test_project_local_slots_are_discovered_without_the_path_config(tmp_path):
    lib = tmp_path / "actual"; lib.mkdir()
    slots = tmp_path / ".research-note/editables"; slots.mkdir(parents=True)
    (slots / "mylib").symlink_to(lib, target_is_directory=True)
    out = run('lib_names; lib_path_here mylib', f'REPO_ROOT={tmp_path}')
    assert out.splitlines() == ["mylib", str(slots / "mylib")]


@pytest.mark.parametrize("host,key", [
    ("H200", "H200"),
    ("my-cluster", "mycluster"),
    ("east.example.org", "eastexampleorg"),
])
def test_hostkey_drops_every_nonalnum(host, key):
    assert run(f'lib_hostkey "{host}"').strip() == key


def test_no_declarations_yield_nothing_under_set_u():
    out = run("set -u; lib_names; echo OK")
    assert out.strip() == "OK"


def test_legacy_lib_checkouts_is_not_a_phantom_lib():
    """LIB_CHECKOUTS (bump_lib's legacy name->path map) starts with LIB_ and
    would enumerate as a lib named CHECKOUTS — the push gate then demands
    LIB_CHECKOUTS_LOCAL and refuses every push."""
    out = subprocess.run(
        ["bash", "-c",
         f'export LIB_CHECKOUTS="qec=/x" LIB_real_LOCAL=/tmp; '
         f'source "{CANON}"; lib_names'],
        capture_output=True, text=True)
    names = out.stdout.split()
    assert "CHECKOUTS" not in names
    assert "real" in names
