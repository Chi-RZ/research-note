"""Tests for githooks/ — executed against a real temp repo, not parsed.

Same doctrine as test_hooks.py: only running a hook shows what it refuses.
"""

from __future__ import annotations

import os
import json
import subprocess
from pathlib import Path

import pytest

HOOKS = Path(__file__).resolve().parents[2] / "githooks" / "research-note"
PLUGIN = HOOKS.parents[1]
GITHOOKS = HOOKS.parent


@pytest.fixture()
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main", tmp_path], check=True)
    (tmp_path / "README.md").write_text("seed\n")
    subprocess.run(["git", "-C", tmp_path, "add", "-A"], check=True)
    subprocess.run(["git", "-C", tmp_path, "commit", "-q", "-m", "chore: seed"],
                   check=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})
    return tmp_path


def commit_msg(repo: Path, staged: list[str], message: str) -> subprocess.CompletedProcess:
    for rel in staged:
        f = repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    msg = repo / ".git" / "COMMIT_EDITMSG_TEST"
    msg.write_text(message)
    env = {k: v for k, v in os.environ.items() if k != "SKIP_PREFIX_CHECK"}
    return subprocess.run(["python3", HOOKS / "commit-msg", msg],
                          cwd=repo, env=env, capture_output=True, text=True)


@pytest.mark.parametrize("staged,message,ok", [
    # prefix <-> layer (pre-existing behaviour)
    (["src/a.py", "tests/test_a.py"], "feat: add a", True),
    (["src/a.py"], "memory: wrong layer", False),
    (["experiments/n/impl/f.py"], "exp: unnamed node", False),
    (["experiments/n/impl/f.py"], "exp(n): named", True),
    # the scope is the node-history retrieval key (git log --grep=<node>):
    # a name matching no node hides the commit from that history silently
    (["experiments/n/impl/f.py"], "exp(ghost): typo scope", False),
    (["experiments/n/impl/f.py"], "exp(n*): a glob is not a node", False),
    # trailers
    (["project_memory/nodes/n/page.md"], "memory: no trailer", False),
    (["project_memory/nodes/n/page.md"], "memory: entry\n\nEntry: 07.005", True),
    (["project_memory/nodes/n/page.md"], "memory: correction\n\nCorrect: 07.005", True),
    (["project_memory/objectives/o.md"], "memory: no trailer", False),
    (["project_memory/objectives/o.md"], "memory: route\n\nObjective: O03", True),
    (["project_memory/objectives/o.md"], "memory: wrong kind\n\nEntry: 07.005", False),
    # a route change is its own commit
    (["project_memory/nodes/n/page.md", "project_memory/objectives/o.md"],
     "memory: both\n\nEntry: 07.005\nObjective: O03", False),
    # regenerated roster and the soft channels need no trailer
    (["project_memory/_index.md"], "memory: regenerate roster", True),
    (["project_memory/memory/claude/fact.md"], "memory: a fact", True),
])
def test_commit_msg(repo, staged, message, ok):
    r = commit_msg(repo, staged, message)
    assert (r.returncode == 0) is ok, r.stderr


def test_exp_scope_accepts_a_node_that_exists_but_is_not_staged(repo):
    """A run-script tweak may stage only experiments/tests/…; the node itself
    sits on disk untouched. Existence, not stagedness, is the criterion."""
    (repo / "experiments" / "real" / "impl").mkdir(parents=True)
    r = commit_msg(repo, ["experiments/tests/test_x.py"], "exp(real): tweak")
    assert r.returncode == 0, r.stderr


def test_exp_scope_rejection_names_the_retrieval_hazard(repo):
    r = commit_msg(repo, ["experiments/n/impl/f.py"], "exp(ghost): x")
    assert r.returncode != 0
    assert "retrieval key" in r.stderr and "ghost" in r.stderr


def test_commit_msg_escape_hatch(repo):
    for rel in ["project_memory/nodes/n/page.md"]:
        f = repo / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    msg = repo / ".git" / "M"
    msg.write_text("memory: no trailer")
    r = subprocess.run(["python3", HOOKS / "commit-msg", msg], cwd=repo,
                       env={**os.environ, "SKIP_PREFIX_CHECK": "1"},
                       capture_output=True, text=True)
    assert r.returncode == 0


def test_commit_msg_reads_custom_layout_from_project_config(repo):
    config = json.loads((PLUGIN / "templates/project.json").read_text())
    config["roles"]["libraries"] = ["code"]
    config["roles"]["tests"] = ["spec"]
    config["roles"]["experiments"] = ["trials"]
    config["layers"]["source"]["paths"] = ["code", "spec"]
    config["layers"]["experiments"]["paths"] = ["trials"]
    path = repo / ".research-note/project.json"
    path.parent.mkdir()
    path.write_text(json.dumps(config))
    subprocess.run(
        ["git", "-C", repo, "config", "research-note.pluginRoot", str(PLUGIN)],
        check=True,
    )
    subprocess.run(["git", "-C", repo, "add", str(path.relative_to(repo))], check=True)
    subprocess.run(
        ["git", "-C", repo, "commit", "-q", "-m", "agent: configure layout"],
        check=True,
        env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
             "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"},
    )

    assert commit_msg(repo, ["code/pkg.py", "spec/test_pkg.py"], "feat: add pkg").returncode == 0
    subprocess.run(["git", "-C", repo, "reset", "--hard", "-q", "HEAD"], check=True)
    assert commit_msg(repo, ["trials/n/impl/run.py"], "exp(n): add run").returncode == 0
    subprocess.run(["git", "-C", repo, "reset", "--hard", "-q", "HEAD"], check=True)
    wrong = commit_msg(repo, ["src/old.py"], "feat: old path")
    assert wrong.returncode == 1 and "src" in wrong.stderr


def pre_commit(repo: Path, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items()
           if k not in ("SKIP_RECORD_BRANCH_CHECK", "SKIP_RECORD_LINT")}
    env.update(env_extra or {})
    return subprocess.run(["/bin/sh", HOOKS / "pre-commit"], cwd=repo,
                          env=env, capture_output=True, text=True)


def test_pre_commit_blocks_record_off_default_branch(repo):
    subprocess.run(["git", "-C", repo, "checkout", "-q", "-b", "side"], check=True)
    f = repo / "project_memory" / "nodes" / "n" / "p.md"
    f.parent.mkdir(parents=True)
    f.write_text("x\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    r = pre_commit(repo, {"RESEARCH_NOTE_PLUGIN": str(repo / "nowhere")})
    assert r.returncode == 1 and "main" in r.stderr


def test_pre_commit_lints_staged_record_page(repo, tmp_path):
    # a fake plugin whose node linter always reports a finding (exit 1)
    plug = tmp_path / "plug"
    (plug / "scripts").mkdir(parents=True)
    (plug / "scripts" / "check_node_page.py").write_text(
        "import sys; print('E1 fake finding'); sys.exit(1)\n")
    (plug / "scripts" / "check_objective_page.py").write_text("import sys; sys.exit(0)\n")
    f = repo / "project_memory" / "nodes" / "n" / "p.md"
    f.parent.mkdir(parents=True)
    f.write_text("x\n")
    subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
    r = pre_commit(repo, {"RESEARCH_NOTE_PLUGIN": str(plug)})
    assert r.returncode == 1 and "does not lint" in r.stderr
    # a non-1 exit (version mismatch) is not this gate's to block on
    (plug / "scripts" / "check_node_page.py").write_text("import sys; sys.exit(3)\n")
    r = pre_commit(repo, {"RESEARCH_NOTE_PLUGIN": str(plug)})
    assert r.returncode == 0, r.stderr
    # escape hatch
    (plug / "scripts" / "check_node_page.py").write_text("import sys; sys.exit(1)\n")
    r = pre_commit(repo, {"RESEARCH_NOTE_PLUGIN": str(plug), "SKIP_RECORD_LINT": "1"})
    assert r.returncode == 0
