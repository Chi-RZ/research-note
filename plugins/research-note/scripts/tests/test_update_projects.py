"""update_projects.sh — the version-carrier. First test, for its worst failure.

The project loop's gate was `[ -d "$P/.claude" ]` — true for the user's HOME
(~/.claude is the global config dir: credentials, plugins, jobs), so a
projectPath row left by any session ever started in $HOME sent the full
treatment there: contract files written into HOME, the enclosing repo's
hooksPath rewritten. Found by a cluster session one command before doing it.
"""

import json
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "update_projects.sh"
PLUGIN = SCRIPT.parent.parent


def _fake_home(tmp_path, project_rows):
    home = tmp_path / "home"
    plug = home / ".claude" / "plugins"
    (plug / "cache" / "claude-setup" / "research-note" / "9.9.9" / "templates").mkdir(
        parents=True)
    (home / ".claude" / ".credentials.json").write_text("{}")   # the global dir shape
    (plug / "installed_plugins.json").write_text(json.dumps(
        {"plugins": {"research-note@claude-setup": project_rows}}))
    return home


def run(home, *args):
    return subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", *map(str, args)],
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        capture_output=True, text=True, timeout=60)


def test_home_with_global_claude_dir_is_skipped(tmp_path):
    home = _fake_home(tmp_path, [
        {"scope": "project", "projectPath": str(tmp_path / "home")}])
    r = run(home)
    assert "not a framework project" in r.stdout
    assert "needs project_memory/" in r.stdout


def test_a_real_project_passes_the_gate(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "framework.json").write_text('{"record": "v3"}')
    (proj / "project_memory").mkdir()
    home = _fake_home(tmp_path, [
        {"scope": "project", "projectPath": str(proj)}])
    r = run(home)
    assert "not a framework project" not in r.stdout
    assert str(proj) in r.stdout


def test_a_project_missing_project_memory_is_skipped(tmp_path):
    proj = tmp_path / "half"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "framework.json").write_text('{"record": "v3"}')
    home = _fake_home(tmp_path, [
        {"scope": "project", "projectPath": str(proj)}])
    r = run(home)
    assert "not a framework project" in r.stdout


def test_explicit_project_works_without_any_claude_registry(tmp_path):
    """Codex-only machines have no Claude project-scope registry."""
    home = tmp_path / "home"
    home.mkdir()
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "framework.json").write_text('{"record": "v3"}')
    (proj / "project_memory").mkdir()

    r = run(home, proj)

    assert r.returncode == 0, r.stderr
    assert f"projects: {proj}" in r.stdout
    assert "no installed_plugins.json" not in (r.stdout + r.stderr)
    version = json.loads(
        (PLUGIN / ".codex-plugin" / "plugin.json").read_text())["version"]
    assert f"target version: {version}" in r.stdout


def test_neutral_registry_drives_codex_only_no_arg_update(tmp_path):
    home = tmp_path / "home"
    registry = home / ".config" / "research-note" / "projects.json"
    registry.parent.mkdir(parents=True)
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "framework.json").write_text('{"record": "v3"}')
    (proj / "project_memory").mkdir()
    registry.write_text(json.dumps({"projects": [str(proj)]}))

    r = run(home)

    assert r.returncode == 0, r.stderr
    assert f"projects: {proj}" in r.stdout


def test_agent_selector_is_validated_before_work(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    r = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", "--agents", "neither"],
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 2
    assert "--agents wants both, claude, codex, or none" in r.stderr


def _fake_claude(home, installed_version, published_version):
    """A CLI stub plus a marketplace source publishing `published_version`.

    The source root is deliberately NOT a git clone, so marketplace_head()
    returns (None, None) and the `local != remote` staleness test cannot fire.
    What is left is the version comparison alone — the thing under test.
    """
    src = home / "src"
    (src / "plugins" / "research-note" / ".claude-plugin").mkdir(parents=True)
    (src / "plugins" / "research-note" / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "research-note", "version": published_version}))

    bin_dir = home / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "claude"
    stub.write_text(f"""#!/usr/bin/env bash
case "$*" in
  *"marketplace list --json"*)
    echo '[{{"name":"claude-setup","url":"u","ref":"uni-plugin","installLocation":"{src}"}}]' ;;
  *"plugin list --json"*)
    echo '[{{"id":"research-note@claude-setup","version":"{installed_version}"}}]' ;;
  *) echo '[]' ;;
esac
""")
    stub.chmod(0o755)
    return bin_dir


def _fake_project(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "framework.json").write_text('{"record": "v3"}')
    (proj / "project_memory").mkdir()
    return proj


def _agents_run(home, bin_dir, proj):
    return subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", "--agents", "claude", str(proj)],
        env={"HOME": str(home), "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin"},
        capture_output=True, text=True, timeout=120)


def _running_version():
    return json.loads(
        (PLUGIN / ".claude-plugin" / "plugin.json").read_text())["version"]


def test_update_is_driven_by_the_source_version_not_by_this_copy(tmp_path):
    """The updater must be able to pull a version newer than itself.

    `want` was read from the manifest of the copy EXECUTING the script, so the
    test was "is the agent on my version?" — which an installed 0.24.0 answers
    "yes" forever, and 0.25.0 shipped with Claude left behind on 0.24.0. The
    other staleness test (marketplace clone behind origin) masked it for Codex
    and not for Claude, whose marketplace root is the local source repo and so
    was already level with origin the moment the commit landed.
    """
    home = _fake_home(tmp_path, [])
    bin_dir = _fake_claude(home, installed_version=_running_version(),
                           published_version="99.0.0")
    r = _agents_run(home, bin_dir, _fake_project(tmp_path))
    assert "updating claude" in r.stdout, r.stdout
    assert "would: claude plugin update research-note@claude-setup" in r.stdout, r.stdout


def test_an_agent_already_on_the_published_version_is_left_alone(tmp_path):
    """The other direction: matching the SOURCE, not this copy, is in step."""
    home = _fake_home(tmp_path, [])
    bin_dir = _fake_claude(home, installed_version="99.0.0",
                           published_version="99.0.0")
    r = _agents_run(home, bin_dir, _fake_project(tmp_path))
    assert "updating claude" not in r.stdout, r.stdout


def test_the_agents_present_are_detected_not_declared(tmp_path):
    """One command on a Claude-only, a Codex-only or a both machine.

    Which agents to update is discovered from PATH, never passed in. The skill
    used to lead with `--agents both`, which reads as a decision the caller has
    to make; it is the default, and a machine missing one side must carry on
    rather than fail. Run with NO flag: the present agent updates, the absent
    one is reported, the run succeeds.
    """
    home = _fake_home(tmp_path, [])
    # The stub is the only CLI on this PATH — the real codex lives in ~/.local/bin.
    bin_dir = _fake_claude(home, installed_version="99.0.0",
                           published_version="99.0.0")
    r = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", str(_fake_project(tmp_path))],
        env={"HOME": str(home), "PATH": f"{bin_dir}:/usr/bin:/bin"},
        capture_output=True, text=True, timeout=120)
    assert "claude: 99.0.0" in r.stdout, r.stdout
    assert "codex : no CLI on this machine" in r.stdout, r.stdout
    assert "WARN parity" not in r.stdout, r.stdout   # one agent cannot disagree
    assert r.returncode == 0, r.stderr


def test_the_verify_step_runs_BOTH_linters():
    """Only the node linter ran here, so no objective page was ever read by a
    new linter on the way in.

    This step exists for one thing: a rule that TIGHTENED cannot be shown to
    leave the existing pages green anywhere else. O13 and O14 both shipped
    after the step was written and both went out unchecked. Asserted on the
    file because the alternative — a fixture carrying a red objective page
    through a full non-dry run — tests the linter, not the wiring.
    """
    text = SCRIPT.read_text(encoding="utf-8")
    verify = text.split("--- verify:", 1)
    assert len(verify) == 2, "the verify step's marker comment is gone"
    body = verify[1].split("# ---", 1)[0]
    assert "check_node_page.py" in body, body
    assert "check_objective_page.py" in body, body


def _stateful_claude(home, installed_version, published_version):
    """`_fake_claude`'s sibling for a NON-dry run: the stub remembers.

    The dry-run stubs report one fixed installed version forever, which is
    enough to test whether an update is ATTEMPTED. To test what happens after
    one lands, `plugin list` has to answer differently once `plugin update` has
    run — otherwise the script sees the install fail and never reaches the step
    under test.
    """
    src = home / "src"
    (src / "plugins" / "research-note" / ".claude-plugin").mkdir(parents=True)
    (src / "plugins" / "research-note" / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "research-note", "version": published_version}))

    bin_dir = home / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "claude"
    stub.write_text(f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$HOME/.calls"
S="$HOME/.installed"
[ -f "$S" ] || printf %s "{installed_version}" > "$S"
case "$*" in
  *"marketplace list --json"*)
    echo '[{{"name":"claude-setup","url":"u","ref":"uni-plugin","installLocation":"{src}"}}]' ;;
  *"plugin list --json"*)
    printf '[{{"id":"research-note@claude-setup","version":"%s"}}]\\n' "$(cat "$S")" ;;
  *"plugin update"*|*"plugin install"*)
    printf %s "{published_version}" > "$S" ;;
  *) echo '[]' ;;
esac
""")
    stub.chmod(0o755)
    return bin_dir


def _git_project(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "framework.json").write_text('{"record": "v3"}')
    (proj / "project_memory").mkdir()
    for cmd in (["git", "init", "-q", "-b", "main", "."],
                ["git", "config", "user.email", "t@example.com"],
                ["git", "config", "user.name", "t"]):
        subprocess.run(cmd, cwd=proj, check=True, capture_output=True)
    return proj


def test_pluginRoot_lands_on_the_version_installed_not_on_this_copy(tmp_path):
    """The repoint must name what was INSTALLED, not what is RUNNING.

    `research-note.pluginRoot` is an absolute path into a version directory and
    every `$PLUGIN` — both linters, the record bus, all three launchers, the
    fixer's first branch — resolves through it. The repoint lives in the
    project loop, which runs BEFORE the agents are updated, and could only ever
    name `$CACHE`: the copy executing the script. So the release run, the one
    run where the value changes, is exactly the run that gets it wrong.

    Measured: 0.29.1 installed cleanly on both agents, reported parity, and
    left all three projects executing 0.29.0's `remote.sh` — the one file that
    release existed to repair. The version pins said 0.29.1; the scripts were
    0.29.0's, silently.
    """
    home = _fake_home(tmp_path, [])
    bin_dir = _stateful_claude(home, installed_version=_running_version(),
                               published_version="99.0.0")
    # The install the stub claims to have performed has to exist on disk: the
    # repoint resolves a real directory or does nothing.
    landed = home / ".claude" / "plugins" / "cache" / "claude-setup" / "research-note" / "99.0.0"
    landed.mkdir(parents=True)
    proj = _git_project(tmp_path)

    r = subprocess.run(
        ["bash", str(SCRIPT), "--agents", "claude", str(proj)],
        env={"HOME": str(home), "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin"},
        capture_output=True, text=True, timeout=300)

    got = subprocess.run(["git", "-C", str(proj), "config", "--get",
                          "research-note.pluginRoot"],
                         capture_output=True, text=True).stdout.strip()
    assert got == str(landed), (
        f"pluginRoot is {got!r}, expected the installed 99.0.0 at {landed}\n"
        f"--- stdout ---\n{r.stdout[-2500:]}")


def test_the_project_scope_update_targets_the_INSTALLED_marketplace(tmp_path):
    """`research-note@<marketplace>` is the installer's string, not ours.

    The marketplace name is whatever `claude plugin marketplace add` registered
    on THAT machine — this repo only declares a default. The project-scope
    update spelled it out, so on any machine that registered the marketplace
    under another name the update targeted a selector matching nothing. Nothing
    failed: an unmatched selector is not an error, the pin simply never moved,
    and the version read back two lines later said `(no row)` — which looks
    like a project that was never pinned rather than one the updater cannot
    reach. The block reading that pin BACK always derived the key correctly, so
    the two halves of one operation disagreed inside a single file.

    Asserted from the CLI's own argv, not from stdout: that call is redirected
    to /dev/null, so a dry run shows nothing and only a real invocation can be
    observed.
    """
    home = _fake_home(tmp_path, [])
    proj = _git_project(tmp_path)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"plugins": {"research-note@acme-labs": [
            {"projectPath": str(proj), "version": "1.0.0"}]}}))
    bin_dir = _stateful_claude(home, installed_version="99.0.0",
                               published_version="99.0.0")
    subprocess.run(["bash", str(SCRIPT), "--agents", "claude", str(proj)],
                   env={"HOME": str(home),
                        "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin"},
                   capture_output=True, text=True, timeout=300)

    calls = (home / ".calls").read_text() if (home / ".calls").exists() else ""
    assert "plugin update research-note@acme-labs --scope project" in calls, calls
    assert "claude-setup" not in calls, calls
