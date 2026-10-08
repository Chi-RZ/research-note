"""Runs the shell suite for land_and_launch.sh, so it rides the normal test run.

The suite is shell because every property it checks is about git worktrees,
file descriptors and flock(2); a mock would have to fake exactly the things
that can be wrong.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

SUITE = Path(__file__).with_suffix(".sh")


@pytest.mark.skipif(not shutil.which("git"), reason="needs git")
def test_land_and_launch_shell_suite():
    r = subprocess.run(["bash", str(SUITE)], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout + r.stderr
