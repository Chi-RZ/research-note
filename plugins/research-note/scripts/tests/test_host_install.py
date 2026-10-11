"""Native failures must not leave a new project registration behind."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import host_install as hosts


@pytest.mark.parametrize("existing", [False, True])
def test_codex_failure_removes_only_a_new_claude_project_install(tmp_path, monkeypatch, existing):
    root = tmp_path / "release/plugins/research-note"
    root.mkdir(parents=True)
    project = tmp_path / "project"
    project.mkdir()
    pin = {"selector": "research-note@rn-release-test", "version": "0.1.0", "sha256": "test"}
    entry = {"id": pin["selector"], "scope": "project", "projectPath": str(project),
             "version": pin["version"], "enabled": True,
             "readFromFolder": str(root), "installPath": str(root)}
    calls = []
    installed = existing

    def claude(_project, *args):
        nonlocal installed
        calls.append(args)
        if args == ("list",):
            return [entry] if installed else []
        if args[0] == "install":
            installed = True
        return {}

    def fail(_project):
        raise ValueError("native Codex verification failed")

    monkeypatch.setattr(hosts.shutil, "which", lambda host: host)
    monkeypatch.setattr(hosts, "claude", claude)
    monkeypatch.setattr(hosts, "codex_skills", fail)
    with pytest.raises(ValueError, match="verification failed"):
        hosts.sync_hosts(project, pin, root)
    uninstall = ("uninstall", pin["selector"], "--scope", "project")
    assert (uninstall in calls) is not existing
    assert not (project / ".research-note/state/host-install.json").exists()


def test_stale_native_skills_are_refused(tmp_path, monkeypatch):
    root = tmp_path / "release/plugins/research-note"
    source = root / "skills/probe/SKILL.md"
    source.parent.mkdir(parents=True)
    source.write_text("selected release")
    cached = tmp_path / "cache/skills/probe/SKILL.md"
    cached.parent.mkdir(parents=True)
    cached.write_text("stale release")
    pin = {"selector": "research-note@rn-release-test", "version": "0.1.0", "sha256": "test"}
    monkeypatch.setattr(hosts.shutil, "which", lambda host: host if host == "codex" else None)
    monkeypatch.setattr(hosts, "codex_skills", lambda project: {"data": [{"skills": [
        {"pluginId": pin["selector"], "path": str(cached)}]}]})
    with pytest.raises(ValueError, match="skills differ"):
        hosts.sync_hosts(tmp_path, pin, root)


def test_untrusted_or_missing_hosts_remain_explicitly_pending(tmp_path, monkeypatch):
    pin = {"selector": "research-note@rn-release-test", "version": "0.1.0", "sha256": "test"}
    monkeypatch.setattr(hosts.shutil, "which", lambda host: host if host == "codex" else None)
    monkeypatch.setattr(hosts, "codex_skills", lambda project: {"data": [{"skills": []}]})
    report = hosts.sync_hosts(tmp_path, pin, tmp_path / "release/plugins/research-note")
    assert report["claude"]["status"] == "pending" and report["codex"]["status"] == "pending"
    assert "trust" in report["codex"]["reason"]
    assert json.loads((tmp_path / ".research-note/state/host-install.json").read_text()) == report
