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





def test_no_argument_means_the_current_project_only(tmp_path):
    """An update touches the project it was asked from — never every project
    on the machine, which changed hooks under projects with work running."""
    home = _fake_home(tmp_path, [{"scope": "project", "projectPath": str(tmp_path / "other")}])
    proj = _git_project(tmp_path)
    r = subprocess.run(["bash", str(SCRIPT), "--dry-run"], cwd=proj,
                       env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"},
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert f"projects: {proj}" in r.stdout
    assert "other" not in r.stdout.split("projects:", 1)[1].splitlines()[0]


def test_a_directory_that_is_not_a_project_is_skipped(tmp_path):
    """HOME carries ~/.claude, and a bare `.claude` probe once sent the full
    treatment there: contract files in HOME, the enclosing repo's hooksPath."""
    home = _fake_home(tmp_path, [])
    r = run(home, home)
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



def test_agent_selector_is_validated_before_work(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    r = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run", "--agents", "neither"],
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        capture_output=True, text=True, timeout=60)
    assert r.returncode == 2
    assert "--agents wants both, claude, codex, or none" in r.stderr



def _fake_project(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "framework.json").write_text('{"record": "v3"}')
    (proj / "project_memory").mkdir()
    return proj




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



def test_agents_are_left_to_their_own_update_commands(tmp_path):
    """The updater syncs projects and moves each project's Claude pin; it never
    refreshes a marketplace or installs a version. That was 250 lines of
    registry handling that broke when an agent changed its registry — Codex
    refusing a renamed marketplace was the last case. pluginRoot therefore
    names the copy running the script, which is the one just installed."""
    home = _fake_home(tmp_path, [])
    proj = _git_project(tmp_path)
    bin_dir = _stateful_claude(home, installed_version="1.0.0",
                               published_version="99.0.0")
    r = subprocess.run(["bash", str(SCRIPT), str(proj)],
                       env={"HOME": str(home),
                            "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin"},
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr
    calls = (home / ".calls").read_text() if (home / ".calls").exists() else ""
    assert "marketplace update" not in calls and "--scope user" not in calls, calls
    root = subprocess.run(["git", "-C", str(proj), "config", "--get",
                           "research-note.pluginRoot"],
                          capture_output=True, text=True).stdout.strip()
    assert root == str(PLUGIN.resolve()), root


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


# --------------------------------------------------------------------------
# P7 — ownership-aware update: migrate once, preview, retain what is disabled,
# leave conflicts for a person. Real runs use --agents none so no CLI is touched.
# --------------------------------------------------------------------------

def _project(tmp_path, name="proj", declaration=None, framework=True):
    proj = tmp_path / name
    (proj / ".claude").mkdir(parents=True)
    (proj / "project_memory").mkdir()
    if framework:
        (proj / ".claude" / "framework.json").write_text('{"framework": "research-note", "record": "v3"}')
    if declaration is not None:
        (proj / ".research-note").mkdir()
        (proj / ".research-note" / "project.json").write_text(json.dumps(declaration))
    subprocess.run(["git", "init", "-q", str(proj)], check=True)
    return proj


def run_real(home, *args):
    return subprocess.run(
        ["bash", str(SCRIPT), "--agents", "none", *map(str, args)],
        env={"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/local/bin"},
        capture_output=True, text=True, timeout=180)


def _declaration(**features):
    config = json.loads((PLUGIN / "templates" / "project.json").read_text())
    config["features"].update(features)
    return config


def test_a_pre_declaration_project_is_migrated_once_with_every_integration_on(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    proj = _project(tmp_path)
    r = run_real(home, proj)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "migrated  .research-note/project.json" in r.stdout
    config = json.loads((proj / ".research-note/project.json").read_text())
    assert all(config["features"].values()), "an update must not disable what the project had"
    assert (proj / ".research-note/.gitignore").read_text() == "state/\n"
    r = run_real(home, proj)
    assert "migrated" not in r.stdout, "once"


def test_a_project_declared_but_without_framework_json_is_a_framework_project(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    proj = _project(tmp_path, declaration=_declaration(), framework=False)
    r = run(home, proj)
    assert "not a framework project" not in r.stdout
    assert f"=== {proj}" in r.stdout


def test_dry_run_prints_the_ownership_table_before_touching_anything(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    proj = _project(tmp_path, declaration=_declaration())
    r = run(home, proj)
    assert "ownership — what this update may touch, and how:" in r.stdout
    for path in (".claude/settings.json", ".claude/hpc.env", "git config core.hooksPath"):
        assert path in r.stdout
    assert "hpc is disabled in project.json — left exactly as it is" in r.stdout
    assert not (proj / ".claude/CLAUDE.md").exists()


def test_a_disabled_hpc_is_retained_not_repaired(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    proj = _project(tmp_path, declaration=_declaration(hpc=False))
    (proj / ".claude/settings.json").write_text(json.dumps({"permissions": {"allow": []}}))
    r = run_real(home, proj)
    assert "hpc: disabled in .research-note/project.json" in r.stdout
    allowed = json.loads((proj / ".claude/settings.json").read_text())["permissions"]["allow"]
    assert "Bash(git:*)" in allowed, "core permissions still merge"
    assert not any("sbatch" in rule or "ssh" in rule for rule in allowed), \
        "a project without a cluster gets no cluster permissions"


def test_an_enabled_hpc_gets_the_cluster_permissions_and_its_files_checked(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    proj = _project(tmp_path, declaration=_declaration(hpc=True))
    (proj / ".claude/settings.json").write_text(json.dumps({"permissions": {"allow": []}}))
    (proj / ".claude/hpc.env").write_text("REMOTE_HOST=hpc\n")
    r = run_real(home, proj)
    allowed = json.loads((proj / ".claude/settings.json").read_text())["permissions"]["allow"]
    assert "Bash(sbatch:*)" in allowed and "Bash(ssh:*)" in allowed
    assert "hpc.env: template documents keys this project lacks" in r.stdout
    assert "hpc: disabled" not in r.stdout


def test_conflicts_are_counted_and_nothing_there_is_overwritten(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    proj = _project(tmp_path, declaration=_declaration(hpc=True))
    slurm = proj / ".claude/hpc-submit/cpu_batch.slurm"
    slurm.parent.mkdir(parents=True)
    slurm.write_text("#!/bin/bash\n#SBATCH --partition=mine\nthe project's own\n")
    (proj / ".claude/framework.json").write_text('{"framework": "research-note", "record": "v2"}')
    r = run_real(home, proj)
    assert "conflict: submit template cpu_batch.slurm differs" in r.stdout
    assert "conflict: framework.json record 'v2'" in r.stdout
    assert "2 item(s) above need a person — nothing was overwritten there" in r.stdout
    assert slurm.read_text().endswith("the project's own\n")
    assert json.loads((proj / ".claude/framework.json").read_text())["record"] == "v2"


def test_a_clean_project_reports_no_conflicts(tmp_path):
    home = tmp_path / "home"; home.mkdir()
    proj = _project(tmp_path, declaration=_declaration())
    r = run_real(home, proj)
    assert "need a person" not in r.stdout
