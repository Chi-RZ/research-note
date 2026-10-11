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

import pytest

pytestmark = pytest.mark.integration

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


def _fake_project(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "framework.json").write_text('{"record": "v1"}')
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


def _project_claude(home):
    """Native CLI stand-in: register project scope and expose its actual source."""
    bin_dir = home / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "claude"
    stub.write_text("""#!/usr/bin/env python3
import json, os, sys
from pathlib import Path
home = Path.home()
project = Path.cwd()
args = sys.argv[1:]
with (home / '.calls').open('a') as f:
    f.write(' '.join(args) + '\\n')
registry = home / '.claude/plugins/installed_plugins.json'
data = json.loads(registry.read_text())
if args[:2] == ['plugin', 'list']:
    print(json.dumps([dict(row, id=key) for key, rows in data['plugins'].items() for row in rows]))
elif args[:2] == ['plugin', 'install']:
    selector = args[2]
    market = selector.split('@')[1]
    local = json.loads((project / '.claude/settings.local.json').read_text())
    release = Path(local['extraKnownMarketplaces'][market]['source']['path'])
    root = release / 'plugins/research-note'
    version = json.loads((root / '.claude-plugin/plugin.json').read_text())['version']
    row = dict(scope='project', projectPath=str(project), enabled=True, version=version,
               installPath=str(root), readFromFolder=str(root))
    data['plugins'].setdefault(selector, []).append(row)
    registry.write_text(json.dumps(data))
    print('{}')
else:
    print('{}')
""")
    stub.chmod(0o755)
    return bin_dir


def _git_project(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".claude" / "framework.json").write_text('{"record": "v1"}')
    (proj / "project_memory").mkdir()
    for cmd in (["git", "init", "-q", "-b", "main", "."],
                ["git", "config", "user.email", "t@example.com"],
                ["git", "config", "user.name", "t"]):
        subprocess.run(cmd, cwd=proj, check=True, capture_output=True)
    return proj



def test_project_update_disables_old_selector_without_upgrading_user_install(tmp_path):
    home = _fake_home(tmp_path, [])
    proj = _git_project(tmp_path)
    registry = home / ".claude/plugins/installed_plugins.json"
    registry.write_text(json.dumps({"plugins": {"research-note@acme-labs": [
        {"projectPath": str(proj), "version": "1.0.0"}]}}))
    before = json.loads(registry.read_text())
    bin_dir = _project_claude(home)
    result = subprocess.run(["bash", str(SCRIPT), "--agents", "claude", str(proj)],
                           env={"HOME": str(home), "PATH": f"{bin_dir}:/usr/bin:/bin:/usr/local/bin"},
                           capture_output=True, text=True, timeout=300)
    assert result.returncode == 0, result.stdout + result.stderr
    calls = (home / ".calls").read_text()
    assert "plugin install research-note@rn-release-" in calls
    assert "--scope project" in calls
    assert "plugin update" not in calls and "--scope user" not in calls
    after = json.loads(registry.read_text())
    assert after["plugins"]["research-note@acme-labs"] == before["plugins"]["research-note@acme-labs"]
    assert all(row.get("scope") != "user" for rows in after["plugins"].values() for row in rows)
    settings = json.loads((proj / ".claude/settings.json").read_text())
    assert settings["enabledPlugins"]["research-note@acme-labs"] is False
    assert sum(settings["enabledPlugins"].values()) == 1


# --------------------------------------------------------------------------
# P7 — ownership-aware update: migrate once, preview, retain what is disabled,
# leave conflicts for a person. Real runs have no host CLI on PATH, so host installation is reported pending.
# --------------------------------------------------------------------------

def _project(tmp_path, name="proj", declaration=None, framework=True):
    proj = tmp_path / name
    (proj / ".claude").mkdir(parents=True)
    (proj / "project_memory").mkdir()
    if framework:
        (proj / ".claude" / "framework.json").write_text('{"framework": "research-note", "record": "v1"}')
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
    # no REMOTE_HOST: the update runs doctor, which would really ssh to it
    (proj / ".claude/hpc.env").write_text("# a cluster not declared yet\n")
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


@pytest.mark.parametrize("dry", [True, False])
def test_private_record_label_is_renamed_without_changing_records_or_policy(tmp_path, dry):
    home = tmp_path / "home"
    home.mkdir()
    proj = _project(tmp_path, declaration=_declaration())
    marker = proj / ".claude/framework.json"
    policy = {"framework": "research-note", "record": "v3", "record_language": "zh", "custom": True}
    marker.write_text(json.dumps(policy))
    record = proj / "project_memory/notes.md"
    record.write_text("An existing research record.\n")
    # Recognized pre-release contract with a project-specific appendix.
    contract = proj / ".claude/project_memory-CLAUDE.md"
    old = (PLUGIN / "templates/project_memory-CLAUDE.md").read_text().replace("Record format: v1", "Record format: v3")
    appendix = "\n## Project-specific rules\n\nKeep our custom policy.\n"
    contract.write_text(old + appendix)
    before = {p: p.read_bytes() for p in (marker, contract, record)}
    result = (run if dry else run_real)(home, proj)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "conflict: framework.json" not in result.stdout
    assert record.read_bytes() == before[record]
    if dry:
        assert all(p.read_bytes() == content for p, content in before.items())
    else:
        assert json.loads(marker.read_text()) == {**policy, "record": "v1"}
        assert "Record format: v1" in contract.read_text()
        assert contract.read_text().endswith(appendix)
