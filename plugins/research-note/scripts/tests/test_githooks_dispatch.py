"""The hook dispatcher and its installer, run against real repositories.

The contradiction this resolves: setting `core.hooksPath` silently disables
every hook a project already had — a pre-commit framework, git-lfs, a
hand-written pre-push. After install those must run exactly as before: same
arguments, same stdin, same exit code, after research-note's own check.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
PLUGIN = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
import githooks_install as gi  # noqa: E402

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def env(**extra: str) -> dict[str, str]:
    base = {k: v for k, v in os.environ.items()
            if not k.startswith("SKIP_") and not k.startswith("RESEARCH_NOTE_HOOK")}
    return {**base, **GIT_ENV, **extra}


def sh(repo: Path, *args: str, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=repo, env=env(), capture_output=True,
                          text=True, timeout=60, **kw)


def write_hook(directory: Path, name: str, body: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return path


@pytest.fixture()
def repo(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    sh(root, "git", "init", "-q", "-b", "main")
    (root / "README.md").write_text("seed\n")
    sh(root, "git", "add", "-A")
    r = sh(root, "git", "commit", "-q", "-m", "chore: seed")
    assert r.returncode == 0, r.stderr
    return root


def commit(repo: Path, message: str, filename: str = "note.txt") -> subprocess.CompletedProcess:
    path = repo / filename
    path.write_text(path.read_text() + "x\n" if path.exists() else "x\n")
    sh(repo, "git", "add", filename)
    return sh(repo, "git", "commit", "-q", "-m", message)


def install(repo: Path, **kw) -> list[tuple[str, str, str]]:
    said: list[tuple[str, str, str]] = []
    gi.install(repo, PLUGIN, say=lambda s, w, d="": said.append((s, w, d)), **kw)
    return said


# --------------------------------------------------------------------------
# the hooks that were already there keep running
# --------------------------------------------------------------------------

def test_pre_existing_pre_commit_runs_after_research_notes_check(repo):
    marker = repo / ".git" / "old-pre-commit-ran"
    write_hook(repo / ".git/hooks", "pre-commit", f'echo "$@" > "{marker}"\nexit 0\n')
    install(repo)

    assert sh(repo, "git", "config", "core.hooksPath").stdout.strip() == ".claude/githooks"
    r = commit(repo, "chore: fine")
    assert r.returncode == 0, r.stderr
    assert marker.exists(), "the project's own pre-commit hook no longer runs"


def test_pre_push_gets_its_stdin_arguments_and_exit_code_back(repo, tmp_path):
    """git-lfs's pre-push reads the ref lines from stdin; a forward that ate
    stdin or dropped the exit code would break every LFS push silently."""
    seen = repo / ".git" / "pre-push-saw"
    write_hook(repo / ".git/hooks", "pre-push",
               f'{{ echo "args: $1 $2"; cat; }} > "{seen}"\nexit 3\n')
    install(repo)

    hook = repo / ".claude/githooks/pre-push"
    r = subprocess.run([str(hook), "origin", "ssh://x/y.git"], cwd=repo, env=env(),
                       input="refs/heads/main abc refs/heads/main def\n",
                       capture_output=True, text=True)
    assert r.returncode == 3
    assert seen.read_text() == ("args: origin ssh://x/y.git\n"
                                "refs/heads/main abc refs/heads/main def\n")

    bare = tmp_path / "remote.git"
    sh(repo, "git", "init", "-q", "--bare", str(bare))
    sh(repo, "git", "remote", "add", "origin", str(bare))
    r = sh(repo, "git", "push", "-q", "origin", "main")
    assert r.returncode != 0, "the old pre-push refused with exit 3; the push went through"


def test_research_notes_refusal_comes_first_and_stops_the_chain(repo):
    marker = repo / ".git" / "old-commit-msg-ran"
    write_hook(repo / ".git/hooks", "commit-msg", f'touch "{marker}"\n')
    install(repo)

    r = commit(repo, "nonsense: no such layer")
    assert r.returncode != 0 and "no legal layer prefix" in r.stderr
    assert not marker.exists(), "a refused commit still reached the forwarded hook"
    assert commit(repo, "chore: fine").returncode == 0
    assert marker.exists()


def test_old_hooks_exit_code_is_the_hooks_exit_code(repo):
    write_hook(repo / ".git/hooks", "pre-commit", "exit 7\n")
    install(repo)
    r = subprocess.run([str(repo / ".claude/githooks/pre-commit")], cwd=repo,
                       env=env(), capture_output=True, text=True)
    assert r.returncode == 7


def test_a_hook_added_after_install_is_forwarded_too(repo):
    install(repo)
    marker = repo / ".git" / "post-commit-ran"
    write_hook(repo / ".git/hooks", "post-commit", f'touch "{marker}"\n')
    assert commit(repo, "chore: later").returncode == 0
    assert marker.exists(), "forwarding resolves the previous directory at run time"


def test_sample_hooks_are_not_run(repo):
    """git init leaves *.sample files; they are neither executable nor hooks."""
    install(repo)
    samples = list((repo / ".git/hooks").glob("*.sample"))
    assert samples, "git init should have left samples for this test to mean anything"
    assert commit(repo, "chore: fine").returncode == 0


# --------------------------------------------------------------------------
# a previous core.hooksPath is remembered, forwarded to, and restored
# --------------------------------------------------------------------------

def test_previous_hooks_path_is_forwarded_and_restored_on_uninstall(repo):
    marker = repo / ".git" / "githooks-pre-commit-ran"
    write_hook(repo / ".githooks", "pre-commit", f'touch "{marker}"\n')
    sh(repo, "git", "config", "core.hooksPath", ".githooks")

    install(repo)
    cfg = lambda k: sh(repo, "git", "config", "--get", k).stdout.strip()  # noqa: E731
    assert cfg("core.hooksPath") == ".claude/githooks"
    assert cfg("research-note.previousHooksPath") == ".githooks"
    assert commit(repo, "chore: fine").returncode == 0
    assert marker.exists()

    gi.uninstall(repo, say=lambda *a: None)
    assert cfg("core.hooksPath") == ".githooks"
    assert cfg("research-note.previousHooksPath") == ""
    assert not (repo / ".claude/githooks/dispatch").exists()
    assert not (repo / ".claude/githooks/research-note").exists()
    assert not (repo / ".claude/githooks/pre-commit").exists()
    assert (repo / ".githooks/pre-commit").exists(), "uninstall touched a file it did not create"


def test_uninstall_unsets_hooks_path_when_none_was_configured(repo):
    install(repo)
    gi.uninstall(repo, say=lambda *a: None)
    assert sh(repo, "git", "config", "--get", "core.hooksPath").stdout.strip() == ""
    assert not (repo / ".claude/githooks").exists()


def test_a_second_install_over_itself_does_not_make_the_dispatcher_the_previous(repo):
    install(repo)
    install(repo)
    assert sh(repo, "git", "config", "--get", "research-note.previousHooksPath").stdout.strip() == ""


# --------------------------------------------------------------------------
# recursion, idempotence, the rare hooks, POSIX
# --------------------------------------------------------------------------

def test_a_forward_target_that_is_the_dispatcher_itself_does_not_loop(repo):
    install(repo)
    sh(repo, "git", "config", "research-note.previousHooksPath", ".claude/githooks")
    r = subprocess.run([str(repo / ".claude/githooks/pre-commit")], cwd=repo, env=env(),
                       capture_output=True, text=True, timeout=20)
    assert r.returncode == 0


def test_a_forwarded_hook_that_runs_git_does_not_re_enter_the_same_hook(repo):
    """A pre-commit that commits (some tools amend) would recurse forever
    without the in-flight marker."""
    count = repo / ".git" / "count"
    write_hook(repo / ".git/hooks", "pre-commit",
               f'echo x >> "{count}"\n'
               'echo y > nested.txt && git add nested.txt && git commit -q -m "chore: nested" || true\n')
    install(repo)
    # The outer commit itself fails — git refuses to lock HEAD after the nested
    # commit moved it — and that is git's verdict, not the dispatcher's. What is
    # ours: the hook ran ONCE and the chain terminated instead of recursing.
    r = commit(repo, "chore: outer")
    assert r.returncode != 0 and "cannot lock ref" in r.stderr, r.stderr
    assert count.read_text().count("x") == 1


def test_install_is_idempotent(repo):
    first = install(repo)
    assert any(s == "linked" for s, _, _ in first)
    before = sorted((p.name, p.is_symlink(), os.readlink(p) if p.is_symlink() else p.read_bytes())
                    for p in (repo / ".claude/githooks").rglob("*") if not p.is_dir())
    second = install(repo)
    assert all(s in ("kept", "ok") for s, _, _ in second), second
    after = sorted((p.name, p.is_symlink(), os.readlink(p) if p.is_symlink() else p.read_bytes())
                   for p in (repo / ".claude/githooks").rglob("*") if not p.is_dir())
    assert before == after
    assert sh(repo, "git", "status", "--porcelain", ".claude").stdout == \
        sh(repo, "git", "status", "--porcelain", ".claude").stdout


def test_rare_hooks_are_linked_only_when_the_project_has_one(repo):
    install(repo)
    assert not (repo / ".claude/githooks/reference-transaction").exists()
    write_hook(repo / ".git/hooks", "reference-transaction", "exit 0\n")
    findings = gi.status(repo)
    assert any(l == "WARN" and "reference-transaction" in m for l, m, _ in findings)
    install(repo)
    assert (repo / ".claude/githooks/reference-transaction").is_symlink()
    assert not any(l == "WARN" for l, _, _ in gi.status(repo))


def test_status_is_green_after_install_and_names_the_forwarded_hooks(repo):
    write_hook(repo / ".git/hooks", "pre-push", "exit 0\n")
    install(repo)
    findings = gi.status(repo)
    assert all(l == "OK" for l, _, _ in findings), findings
    assert any("pre-push" in m for _, m, _ in findings)


def test_status_before_install_is_red(repo):
    findings = gi.status(repo)
    assert findings and findings[0][0] == "BAD"


def test_dispatcher_is_posix_sh():
    dispatch = PLUGIN / "githooks" / "dispatch"
    assert dispatch.read_text().startswith("#!/bin/sh\n")
    for shell in ("sh", "dash", "bash"):
        if shutil.which(shell):
            r = subprocess.run([shell, "-n", str(dispatch)], capture_output=True, text=True)
            assert r.returncode == 0, (shell, r.stderr)
    if shutil.which("bash"):
        r = subprocess.run(["bash", "--posix", "-n", str(dispatch)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr


# --------------------------------------------------------------------------
# the pre-dispatcher layout is migrated, its own rows kept
# --------------------------------------------------------------------------

def test_pre_dispatcher_layout_is_migrated_and_a_customised_hook_still_runs(repo):
    """A project from before the dispatcher has real files under the hook
    names; one may carry its own RULES rows. They move under research-note/
    and keep running until the project declares its layers."""
    hooks = repo / ".claude/githooks"
    marker = repo / ".git" / "custom-commit-msg-ran"
    write_hook(hooks, "commit-msg", f'touch "{marker}"\nexit 0\n')
    shutil.copy2(PLUGIN / "githooks/research-note/pre-commit", hooks / "pre-commit")
    sh(repo, "git", "config", "core.hooksPath", ".claude/githooks")

    said = install(repo)
    states = {(s, w) for s, w, _ in said}
    assert ("moved", ".claude/githooks/commit-msg") in states
    assert ("moved", ".claude/githooks/pre-commit") in states
    assert any(s == "WARN" and w.endswith("research-note/commit-msg") for s, w, _ in said)
    assert (hooks / "commit-msg").is_symlink() and (hooks / "pre-commit").is_symlink()
    assert (hooks / "research-note/commit-msg").read_text().count("custom-commit-msg-ran") == 1
    assert sh(repo, "git", "config", "--get", "research-note.previousHooksPath").stdout.strip() == "", \
        "our own old directory must not become the forward target"
    assert commit(repo, "whatever: the custom hook decides").returncode == 0
    assert marker.exists()


def test_a_declared_project_gets_the_plugins_commit_msg_synced(repo):
    hooks = repo / ".claude/githooks"
    write_hook(hooks, "commit-msg", "exit 0\n")
    config = json.loads((PLUGIN / "templates/project.json").read_text())
    (repo / ".research-note").mkdir()
    (repo / ".research-note/project.json").write_text(json.dumps(config))
    sh(repo, "git", "config", "research-note.pluginRoot", str(PLUGIN))

    said = install(repo)
    assert ("synced", ".claude/githooks/research-note/commit-msg") in {(s, w) for s, w, _ in said}
    r = commit(repo, "nonsense: refused by the plugin's hook now")
    assert r.returncode != 0 and "no legal layer prefix" in r.stderr


def test_dry_run_changes_nothing(repo):
    said = install(repo, dry=True)
    assert any(s == "linked" for s, _, _ in said)
    assert not (repo / ".claude/githooks").exists()
    assert sh(repo, "git", "config", "--get", "core.hooksPath").stdout.strip() == ""


def test_the_cli_is_what_the_updater_and_doctor_call(repo):
    r = sh(repo, "python3", str(SCRIPTS / "githooks_install.py"), "install", str(repo),
           "--plugin", str(PLUGIN))
    assert r.returncode == 0, r.stderr
    assert any(line.startswith("linked ") for line in r.stdout.splitlines())
    r = sh(repo, "python3", str(SCRIPTS / "githooks_install.py"), "status", str(repo))
    assert r.returncode == 0 and r.stdout.startswith("OK\t"), r.stdout
