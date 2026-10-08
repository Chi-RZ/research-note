"""Project isolation includes both hosts' plugins, not just script lookup."""
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))


def runtime():
    spec = importlib.util.spec_from_file_location("project_runtime", SCRIPTS / "project_runtime.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project(tmp_path, name):
    p = tmp_path / name
    p.mkdir()
    subprocess.run(["git", "init", "-q", str(p)], check=True)
    return p


def source(tmp_path):
    p = tmp_path / "source"
    shutil.copytree(SCRIPTS.parent, p, ignore=shutil.ignore_patterns("__pycache__", "tests"))
    return p


def files(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*")
            if p.is_file() and not {".git", "__pycache__"}.intersection(p.relative_to(root).parts)}


def test_two_projects_keep_both_hosts_on_their_snapshot(tmp_path, monkeypatch):
    m = runtime()
    home = tmp_path / "user"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    src = source(tmp_path)
    a, b = project(tmp_path, "a"), project(tmp_path, "b")
    for p in (a, b):
        m.activate(p, m.snapshot(p, src))
    before = files(b)
    old = m.locked_root(b)
    old_skill = (old / "skills/analyze/SKILL.md").read_bytes()
    (src / "skills/analyze/SKILL.md").write_text("new skill\n")
    (src / "hooks/hooks.json").write_text('{"hooks": {}}')
    m.activate(a, m.snapshot(a, src))
    shutil.rmtree(src)  # host cache refresh/removal cannot change either pin
    assert files(b) == before
    assert (old / "skills/analyze/SKILL.md").read_bytes() == old_skill
    assert (m.locked_root(a) / "skills/analyze/SKILL.md").read_text() == "new skill\n"
    assert files(home) == {}
    for p in (a, b):
        pin = json.loads((p / m.LOCK).read_text())
        selector = pin["selector"]
        settings = json.loads((p / ".claude/settings.json").read_text())
        assert settings["enabledPlugins"][selector] is True
        assert settings["enabledPlugins"]["research-note@research-tools"] is False
        local = json.loads((p / ".claude/settings.local.json").read_text())
        market = Path(local["extraKnownMarketplaces"][pin["marketplace"]]["source"]["path"])
        entry = json.loads((market / ".claude-plugin/marketplace.json").read_text())["plugins"][0]
        assert (market / entry["source"]).resolve() == m.locked_root(p)
        import tomllib
        codex = tomllib.loads((p / ".codex/config.toml").read_text())
        assert codex["plugins"][selector]["enabled"] is True
        assert Path(codex["marketplaces"][pin["marketplace"]]["source"]) == market
        assert m.check(p) == []


def test_local_overrides_and_unrelated_settings_are_preserved(tmp_path, monkeypatch):
    m = runtime()
    p = project(tmp_path, "p")
    home = tmp_path / "user"
    (home / ".claude").mkdir(parents=True)
    (home / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {"research-note@custom": True}}))
    monkeypatch.setattr(Path, "home", lambda: home)
    (p / ".claude").mkdir()
    (p / ".claude/settings.local.json").write_text(json.dumps({"autoMemoryDirectory": "keep", "enabledPlugins": {"research-note@custom": True, "other@x": True}}))
    (p / ".codex").mkdir()
    original = '# keep comment\nmodel = "test"\n[plugins."other@x"]\nenabled = true\n'
    (p / ".codex/config.toml").write_text(original + '[plugins."research-note@custom"]\nenabled = true\n')
    before = files(home)
    pin = m.snapshot(p, source(tmp_path))
    m.activate(p, pin)
    local = json.loads((p / ".claude/settings.local.json").read_text())
    assert local["autoMemoryDirectory"] == "keep"
    assert local["enabledPlugins"]["research-note@custom"] is False
    assert local["enabledPlugins"]["other@x"] is True
    assert (p / ".codex/config.toml").read_text().startswith(original)
    once = files(p)
    m.activate(p, pin)
    assert files(p) == once
    assert files(home) == before


def test_a_mutated_snapshot_is_refused(tmp_path):
    m = runtime()
    p = project(tmp_path, "p")
    pin = m.snapshot(p, source(tmp_path))
    m.activate(p, pin)
    (m.locked_root(p) / "hooks/hooks.json").write_text("tampered")
    assert m.check(p)
    with pytest.raises(ValueError, match="digest"):
        m.locked_root(p)


def test_failed_activation_restores_previous_settings(tmp_path, monkeypatch):
    m = runtime()
    p = project(tmp_path, "p")
    src = source(tmp_path)
    m.activate(p, m.snapshot(p, src))
    before = files(p)
    (src / "skills/analyze/SKILL.md").write_text("new")
    pin = m.snapshot(p, src)
    with pytest.raises(RuntimeError):
        with m.transaction(p):
            m.activate(p, pin)
            raise RuntimeError("installation failed")
    assert {k: v for k, v in files(p).items() if "/runtime/" not in k and "/state/" not in k} == {
        k: v for k, v in before.items() if "/runtime/" not in k and "/state/" not in k}


def test_real_update_only_moves_a_and_setup_does_not_upgrade_b(tmp_path):
    from test_compat_matrix import bootstrap, sh
    m = runtime()
    home = tmp_path / "home"
    home.mkdir()
    a, b = project(tmp_path, "a"), project(tmp_path, "b")
    bootstrap(a, home)
    bootstrap(b, home)
    a_old_root = m.locked_root(a)
    a_old_digest = m.digest(a_old_root)
    before = files(b)
    b_root = sh(b, home, "git", "config", "--get", "research-note.pluginRoot").stdout
    src = source(tmp_path)
    skill = src / "skills/analyze/SKILL.md"
    skill.write_text(skill.read_text() + "\nRelease two.\n")
    hook = src / "scripts/hook_dispatch.py"
    hook.write_text(hook.read_text() + "\n# release two\n")
    result = sh(a, home, "bash", str(src / "scripts/update_projects.sh"), str(a))
    assert result.returncode == 0, result.stdout + result.stderr
    assert (m.locked_root(a) / "skills/analyze/SKILL.md").read_text().endswith("Release two.\n")
    # An already-running host may still reference this release. Updates retain
    # it so that session can finish normally while new sessions use the new pin.
    assert a_old_root.is_dir()
    assert m.digest(a_old_root) == a_old_digest
    assert m.check(a) == []
    assert files(b) == before
    assert sh(b, home, "git", "config", "--get", "research-note.pluginRoot").stdout == b_root
    # Even setup invoked from a newer plugin must follow B's existing pin.
    result = sh(b, home, sys.executable, str(src / "scripts/bootstrap_project.py"), str(b))
    assert result.returncode == 0, result.stdout + result.stderr
    assert files(b) == before
    assert m.check(b) == []


def test_real_failed_update_restores_contracts_pin_and_git_config(tmp_path):
    from test_compat_matrix import bootstrap, sh
    home = tmp_path / "home"
    home.mkdir()
    p = project(tmp_path, "p")
    bootstrap(p, home)
    before = files(p)
    git_config = (p / ".git/config").read_bytes()
    src = source(tmp_path)
    updater = src / "scripts/update_projects.sh"
    updater.write_text(updater.read_text() + "\nexit 23\n")
    result = sh(p, home, "bash", str(updater), str(p))
    assert result.returncode != 0
    assert (p / ".git/config").read_bytes() == git_config
    assert {k: v for k, v in files(p).items() if "/runtime/" not in k} == {
        k: v for k, v in before.items() if "/runtime/" not in k}


def test_worktree_update_resolves_to_main_installation(tmp_path):
    from test_compat_matrix import bootstrap, sh, commit_all
    home = tmp_path / "home"
    home.mkdir()
    p = project(tmp_path, "main")
    bootstrap(p, home)
    assert commit_all(p, home, "agent: setup").returncode == 0
    wt = tmp_path / "branch"
    result = sh(p, home, "git", "worktree", "add", "-b", "experiment", str(wt))
    assert result.returncode == 0, result.stderr
    m = runtime()
    assert m.locked_root(wt) == m.locked_root(p)
    result = sh(wt, home, "bash", str(SCRIPTS / "update_projects.sh"), "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"projects: {p}" in result.stdout


def test_restore_after_move_rebinds_both_hosts_without_changing_release(tmp_path):
    m = runtime()
    p = project(tmp_path, "p")
    src = source(tmp_path)
    m.activate(p, m.snapshot(p, src))
    pin = json.loads((p / m.LOCK).read_text())
    moved = tmp_path / "moved"
    p.rename(moved)
    m.restore(moved, src)
    new = json.loads((moved / m.LOCK).read_text())
    assert new["sha256"] == pin["sha256"]
    assert new["selector"] != pin["selector"]
    assert m.check(moved) == []


def test_restore_clone_requires_matching_content(tmp_path):
    m = runtime()
    p = project(tmp_path, "p")
    src = source(tmp_path)
    m.activate(p, m.snapshot(p, src))
    pin = json.loads((p / m.LOCK).read_text())
    shutil.rmtree(p / m.RUNTIME)
    m.restore(p, src)
    assert json.loads((p / m.LOCK).read_text())["sha256"] == pin["sha256"]
    shutil.rmtree(p / m.RUNTIME)
    (src / "skills/analyze/SKILL.md").write_text("different")
    with pytest.raises(ValueError, match="locked content"):
        m.restore(p, src)


def test_contract_conflict_prevents_runtime_switch(tmp_path):
    from test_compat_matrix import bootstrap, sh
    home = tmp_path / "home"
    home.mkdir()
    p = project(tmp_path, "p")
    bootstrap(p, home)
    contract = p / ".claude/CLAUDE.md"
    contract.write_text("project edited the framework\n" + contract.read_text())
    before = files(p)
    result = sh(p, home, "bash", str(SCRIPTS / "update_projects.sh"), str(p))
    assert result.returncode != 0
    assert "contract preflight failed" in result.stderr
    assert files(p) == before
